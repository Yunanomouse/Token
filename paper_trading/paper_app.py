"""Paper Trading: buy and sell by hand with pretend money, on this computer.

A separate program from the bots and Quantum Station.  You start an account
with a balance you choose, look up a stock, and place market, limit or stop
orders.  Orders fill against real (delayed) Yahoo quotes, or against made-up
demo prices, with the commission and slippage you set.  Nothing here talks to
a broker: there is no broker code in this module, no keys are read, and the
only network request is a quote lookup.

Plain Python 3.10+, nothing to install (Windows also needs ``tzdata``, which
``start.py`` offers to install).  Run it with ``Paper Trading.bat`` (Windows)
or ``python3 start.py``.  The account lives in ``paper_data/`` next to this
file (or ``QT_PAPER_HOME``, or ``--home``).  See README.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import subprocess
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import date, datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

from datetime import time as dtime
from http.server import BaseHTTPRequestHandler
from zoneinfo import ZoneInfo

__all__ = ["Book", "PaperServer", "market_open", "next_session", "yahoo_quote", "DemoQuotes", "serve", "main"]

HERE = Path(__file__).resolve().parent
NY = ZoneInfo("America/New_York")
DEFAULT_PORT = 8778
MAX_BODY = 1_048_576  # bytes; a POST body larger than this is refused unread
PAGE_FILE = Path(__file__).with_name("paper_page.html")
SCHEMA = 1

TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,9}$")
DEFAULT_CASH = 100_000.0
MAX_CASH = 100_000_000.0
MAX_QTY = 10_000_000.0
MAX_PRICE = 1_000_000.0
QTY_DECIMALS = 6
QUOTE_TTL = 20.0            # seconds a live quote is reused
REFRESH_EVERY = 30.0        # seconds between background checks of open orders
EQUITY_EVERY = timedelta(minutes=5)
EQUITY_POINTS = 5000
KEEP_ORDERS = 2000
DEFAULT_WATCH = ["AAPL", "MSFT", "SPY"]
DEFAULT_SETTINGS = {"commission": 0.0, "slippage_bps": 2.0, "fractional": False, "practice_fills": False}
ORDER_TYPES = ("market", "limit", "stop")
SIDES = ("buy", "sell")
TIFS = ("day", "gtc")


# --------------------------------------------------------------------------
# Market hours
# --------------------------------------------------------------------------

# Full-day NYSE closures, from the exchange's published schedule.  Outside
# these years every weekday counts as a trading day.
HOLIDAYS = {
    # 2026
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19",
    "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    # 2027 (Juneteenth falls on a Saturday: observed Friday 18th; Independence
    # Day on a Sunday: observed Monday 5th; Christmas on a Saturday: Friday 24th)
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18",
    "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
}
EARLY_CLOSE = {"2026-11-27", "2026-12-24", "2027-11-26"}  # 13:00 closes
OPEN = dtime(9, 30)


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d.isoformat() not in HOLIDAYS


def session_close(d: date) -> dtime:
    return dtime(13, 0) if d.isoformat() in EARLY_CLOSE else dtime(16, 0)



def market_open(now: datetime) -> bool:
    """True during the regular New York session (9:30 to 16:00, 13:00 on half days)."""
    ny = now.astimezone(NY)
    d = ny.date()
    return is_trading_day(d) and OPEN <= ny.time() < session_close(d)


def next_session(now: datetime) -> date:
    """The session an order placed now belongs to: today's if it hasn't
    closed yet, else the next trading day."""
    ny = now.astimezone(NY)
    d = ny.date()
    if is_trading_day(d) and ny.time() < session_close(d):
        return d
    d += timedelta(days=1)
    while not is_trading_day(d):
        d += timedelta(days=1)
    return d


def session_end(d: date) -> datetime:
    return datetime.combine(d, session_close(d), tzinfo=NY)


# --------------------------------------------------------------------------
# Quotes
# --------------------------------------------------------------------------

UA = "Mozilla/5.0 (paper trading practice app)"


def yahoo_quote(ticker: str, timeout: float = 15.0) -> dict:
    """Yahoo's latest (delayed) regular-session price for ``ticker``.

    Raises ValueError for an unknown symbol, OSError when Yahoo can't be
    reached.  Nothing about the user is sent: only the symbol."""
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(ticker, safe='')}?interval=1d&range=5d")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise ValueError(f"{ticker}: no such symbol") from None
        raise OSError(f"Yahoo answered HTTP {exc.code}") from None
    except ValueError:
        raise OSError("Yahoo sent an unreadable answer") from None
    try:
        chart = data.get("chart") or {}
        if chart.get("error"):
            raise ValueError(f"{ticker}: no such symbol")
        res = (chart.get("result") or [None])[0] or {}
        meta = res.get("meta") or {}
        price = meta.get("regularMarketPrice")
    except (AttributeError, KeyError, IndexError, TypeError):  # JSON, but not the chart's shape
        raise OSError("Yahoo sent an unreadable answer") from None
    if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
        raise ValueError(f"{ticker}: Yahoo has no price")
    prev = meta.get("chartPreviousClose", meta.get("previousClose"))
    ts = meta.get("regularMarketTime")
    return {
        "ticker": ticker,
        "price": float(price),
        "prev_close": float(prev) if isinstance(prev, (int, float)) and math.isfinite(prev) and prev > 0 else None,
        "time": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds") if isinstance(ts, (int, float)) else None,
        "name": str(meta.get("longName") or meta.get("shortName") or "")[:80],
        "currency": str(meta.get("currency") or "")[:8],
        "source": "yahoo",
    }


class DemoQuotes:
    """Made-up prices that wander like a stock (about 2% a day), for trying
    the program with no internet or with the market closed.  Every symbol is
    accepted.  ``state`` is a dict the caller persists so prices carry over."""

    def __init__(self, state: dict, clock: Callable[[], datetime]) -> None:
        self.state = state
        self.clock = clock

    @staticmethod
    def base(ticker: str) -> float:
        h = int(hashlib.sha256(ticker.encode()).hexdigest()[:8], 16)
        return round(20 + (h % 38000) / 100, 2)  # 20.00 .. 399.99

    def __call__(self, ticker: str) -> dict:
        now = self.clock()
        last = self.state.get(ticker)
        if not isinstance(last, dict) or not all(isinstance(last.get(k), (int, float)) for k in ("price", "t", "open")):
            price = self.base(ticker)
            last = {"price": price, "open": price, "t": now.timestamp()}
        dt_days = max(0.0, now.timestamp() - last["t"]) / 86400.0
        price = last["price"]
        if dt_days > 0:
            rng = random.Random(f"{ticker}:{int(now.timestamp())}")
            price = max(0.5, price * math.exp(0.02 * math.sqrt(dt_days) * rng.gauss(0, 1)))
            price = round(price, 2)
        self.state[ticker] = {"price": price, "open": last["open"], "t": now.timestamp()}
        return {"ticker": ticker, "price": price, "prev_close": last["open"],
                "time": now.isoformat(timespec="seconds"), "name": f"{ticker} (demo)", "currency": "USD",
                "source": "demo"}


# --------------------------------------------------------------------------
# The account
# --------------------------------------------------------------------------


def _now_iso(now: datetime) -> str:
    return now.astimezone(timezone.utc).isoformat(timespec="seconds")


def _num(value, name: str, lo: float, hi: float, allow_zero: bool = False) -> float:
    """``value`` as a finite float in range, else ValueError with a plain message."""
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number")
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number") from None
    if not math.isfinite(v):
        raise ValueError(f"{name} must be a number")
    if v < lo or v > hi or (v == 0 and not allow_zero):
        raise ValueError(f"{name} must be between {lo:g} and {hi:g}")
    return v


def new_account(now: datetime, starting_cash: float = DEFAULT_CASH, prices: str = "live") -> dict:
    return {
        "schema": SCHEMA, "created": _now_iso(now), "starting_cash": starting_cash, "cash": starting_cash,
        "prices": prices, "settings": dict(DEFAULT_SETTINGS), "positions": {}, "orders": [], "fills": [],
        "realized": 0.0, "fees": 0.0, "watchlist": list(DEFAULT_WATCH), "equity": [], "next_id": 1,
        "demo_state": {},
    }


def _valid_account(acct) -> bool:
    try:
        return (acct.get("schema") == SCHEMA and math.isfinite(float(acct["cash"]))
                and float(acct["starting_cash"]) > 0 and acct.get("prices") in ("live", "demo")
                and isinstance(acct["positions"], dict) and isinstance(acct["orders"], list)
                and isinstance(acct["fills"], list) and isinstance(acct["settings"], dict))
    except (AttributeError, KeyError, TypeError, ValueError):
        return False


class Book:
    """The paper account: orders, fills, positions and cash, saved in
    ``<home>/account.json`` after every change.

    ``quotes`` (a function ticker -> quote dict) and ``clock`` (-> aware
    datetime) can be replaced, which the tests do."""

    def __init__(self, home: str | Path | None = None, quotes: Callable[[str], dict] | None = None,
                 clock: Callable[[], datetime] | None = None) -> None:
        self.home = Path(home or os.environ.get("QT_PAPER_HOME") or HERE / "paper_data").resolve()
        self.home.mkdir(parents=True, exist_ok=True)
        self.path = self.home / "account.json"
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._live_quotes = quotes or yahoo_quote
        self.lock = threading.RLock()
        self.quotes: dict[str, dict] = {}       # ticker -> last quote (with "fetched")
        self.quote_errors: dict[str, str] = {}
        self.notes: list[str] = []
        self.acct = self._load()

    # ---- storage ---------------------------------------------------------

    def _load(self) -> dict:
        if not self.path.exists():
            acct = new_account(self.clock())
            self._write(acct)
            return acct
        try:
            acct = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            acct = None
        if not _valid_account(acct):
            kept = self._backup("corrupt")
            self.notes.append(f"account.json could not be read; it was kept as {kept.name} and a new "
                              f"${DEFAULT_CASH:,.0f} account was started.")
            acct = new_account(self.clock())
            self._write(acct)
            return acct
        settings = dict(DEFAULT_SETTINGS)
        settings.update({k: v for k, v in acct["settings"].items() if k in DEFAULT_SETTINGS})
        acct["settings"] = settings
        for key, default in (("realized", 0.0), ("fees", 0.0), ("watchlist", []), ("equity", []),
                             ("next_id", 1), ("demo_state", {})):
            acct.setdefault(key, default)
        return acct

    def _write(self, acct: dict | None = None) -> None:
        acct = acct if acct is not None else self.acct
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(acct, indent=1, allow_nan=False), encoding="utf-8")
        os.replace(tmp, self.path)

    def _backup(self, label: str) -> Path:
        stamp = self.clock().astimezone(NY).strftime("%Y%m%d-%H%M%S")
        dest = self.home / f"account.{label}-{stamp}.json"
        n = 1
        while dest.exists():
            n += 1
            dest = self.home / f"account.{label}-{stamp}-{n}.json"
        os.replace(self.path, dest)
        return dest

    # ---- quotes ----------------------------------------------------------

    def _source(self) -> Callable[[str], dict]:
        if self.acct["prices"] == "demo":
            return DemoQuotes(self.acct["demo_state"], self.clock)
        return self._live_quotes

    def quote(self, ticker: str, fresh: bool = False) -> dict:
        """A quote for ``ticker`` (cached for ``QUOTE_TTL`` seconds).
        Raises ValueError (bad or unknown symbol) or OSError (no connection)."""
        ticker = clean_ticker(ticker)
        now = time.monotonic()
        with self.lock:
            q = self.quotes.get(ticker)
            if q and not fresh and now - q["fetched"] < QUOTE_TTL and q.get("source") == self._kind():
                return q
            source = self._source()
            if self.acct["prices"] == "demo":  # no network; its state is the account's
                q = dict(source(ticker))
                q["fetched"] = now
                self.quotes[ticker] = q
                return q
        try:
            q = dict(source(ticker))  # network, outside the lock
        except (ValueError, OSError) as exc:
            with self.lock:
                self.quote_errors[ticker] = str(exc)
            raise
        except Exception as exc:  # a malformed answer must not stop the program
            with self.lock:
                self.quote_errors[ticker] = f"quote failed: {type(exc).__name__}"
            raise OSError(f"quote failed: {type(exc).__name__}") from None
        q["fetched"] = now
        with self.lock:
            self.quotes[ticker] = q
            self.quote_errors.pop(ticker, None)
        return q

    def _kind(self) -> str:
        return "demo" if self.acct["prices"] == "demo" else "yahoo"

    def _price(self, ticker: str) -> float | None:
        q = self.quotes.get(ticker)
        return q["price"] if q and q.get("source") == self._kind() else None

    # ---- money -----------------------------------------------------------

    def _slip(self) -> float:
        return float(self.acct["settings"]["slippage_bps"]) / 10_000.0

    def _fee(self) -> float:
        return float(self.acct["settings"]["commission"])

    def _reserved(self, exclude: int | None = None) -> float:
        """Cash set aside for open buy orders, at their limit, stop or last price."""
        total = 0.0
        for o in self.acct["orders"]:
            if o["status"] != "open" or o["side"] != "buy" or o["id"] == exclude:
                continue
            px = (o.get("limit_price") or o.get("stop_price") or self._price(o["ticker"])
                  or o.get("quote_at_entry") or 0.0)  # after a restart no quote is known yet
            total += o["qty"] * px * (1 + self._slip()) + self._fee()
        return total

    def _shares_promised(self, ticker: str) -> float:
        return sum(o["qty"] for o in self.acct["orders"]
                   if o["status"] == "open" and o["side"] == "sell" and o["ticker"] == ticker)

    def _can_fill_now(self, now: datetime) -> bool:
        return self.acct["prices"] == "demo" or market_open(now) or bool(self.acct["settings"]["practice_fills"])

    # ---- orders ----------------------------------------------------------

    def place(self, form: dict) -> dict:
        """Validate and place an order; fill it at once if it can."""
        try:
            ticker = clean_ticker(form.get("ticker"))
            side = _choice(form.get("side"), SIDES, "side")
            otype = _choice(form.get("type", "market"), ORDER_TYPES, "order type")
            tif = _choice(form.get("tif", "day"), TIFS, "time in force")
            qty = _num(form.get("qty"), "Quantity", 0, MAX_QTY)
            limit = _num(form.get("limit_price"), "Limit price", 0, MAX_PRICE) if otype == "limit" else None
            stop = _num(form.get("stop_price"), "Stop price", 0, MAX_PRICE) if otype == "stop" else None
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        with self.lock:
            fractional = bool(self.acct["settings"]["fractional"])
        if fractional:
            qty = round(qty, QTY_DECIMALS)
            if qty <= 0:
                return {"ok": False, "error": "Quantity is too small"}
        elif qty != int(qty):
            return {"ok": False, "error": "Whole shares only (turn on fractional shares in Settings)"}
        try:
            q = self.quote(ticker)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        except OSError as exc:
            return {"ok": False, "error": f"No price for {ticker}: {exc}. Try again, or use demo prices."}
        with self.lock:
            now = self.clock()
            price = q["price"]
            if side == "sell":
                held = self.acct["positions"].get(ticker, {}).get("shares", 0.0)
                free = held - self._shares_promised(ticker)
                if qty > free + 1e-9:
                    return {"ok": False, "error": f"You can sell at most {_fmt_qty(max(free, 0))} {ticker} "
                                                  "(no short selling; shares in open sell orders are counted)"}
            else:
                est_px = limit if otype == "limit" else stop if otype == "stop" else price
                need = qty * est_px * (1 + self._slip()) + self._fee()
                power = self.acct["cash"] - self._reserved()
                if need > power + 1e-9:
                    return {"ok": False, "error": f"Not enough buying power: this needs about ${need:,.2f}, "
                                                  f"you have ${max(power, 0):,.2f}"}
            order = {"id": self.acct["next_id"], "ticker": ticker, "side": side, "type": otype, "tif": tif,
                     "qty": qty, "limit_price": limit, "stop_price": stop, "status": "open",
                     "created": _now_iso(now), "session": next_session(now).isoformat(),
                     "quote_at_entry": price, "filled_at": None, "fill_price": None, "fee": None, "note": ""}
            self.acct["next_id"] += 1
            self.acct["orders"].append(order)
            self._try_fill(order, q, now)
            if order["status"] == "open" and not self._can_fill_now(now):
                order["note"] = (f"Market closed: waits for the {order['session']} session"
                                 if otype == "market" else "Market closed: checked again once it opens")
            self._trim()
            self._record_equity(now, force=True)
            self._write()
            return {"ok": True, "order": dict(order)}

    def cancel(self, order_id) -> dict:
        with self.lock:
            for o in self.acct["orders"]:
                if o["id"] == order_id and not isinstance(order_id, bool):
                    if o["status"] != "open":
                        return {"ok": False, "error": f"Order {order_id} is already {o['status']}"}
                    o["status"], o["note"] = "cancelled", "Cancelled by you"
                    o["closed_at"] = _now_iso(self.clock())
                    self._write()
                    return {"ok": True, "order": dict(o)}
        return {"ok": False, "error": "No such order"}

    def _try_fill(self, o: dict, q: dict, now: datetime) -> None:
        """Fill, expire or leave ``o`` (an open order) against quote ``q``."""
        if o["tif"] == "day" and now >= session_end(date.fromisoformat(o["session"])) \
                and self.acct["prices"] != "demo" and not self.acct["settings"]["practice_fills"]:
            o["status"], o["note"], o["closed_at"] = "expired", "Day order: the session ended", _now_iso(now)
            return
        if not self._can_fill_now(now):
            return
        if self.acct["prices"] != "demo" and market_open(now) and not _from_this_session(q, now):
            return  # e.g. 9:31 and Yahoo still shows last night's close: wait for today's price
        p, s = q["price"], self._slip()
        buy = o["side"] == "buy"
        if o["type"] == "market":
            fill = p * (1 + s) if buy else p * (1 - s)
        elif o["type"] == "limit":
            lim = o["limit_price"]
            if (buy and p > lim) or (not buy and p < lim):
                return
            fill = min(p * (1 + s), lim) if buy else max(p * (1 - s), lim)
        else:
            stop = o["stop_price"]
            if (buy and p < stop) or (not buy and p > stop):
                return
            fill = p * (1 + s) if buy else p * (1 - s)
        fill = round(fill, 4)
        fee = self._fee()
        pos = self.acct["positions"].get(o["ticker"], {"shares": 0.0, "cost": 0.0})
        if buy:
            cost = o["qty"] * fill + fee
            if cost > self.acct["cash"] + 1e-9:
                o["status"], o["closed_at"] = "rejected", _now_iso(now)
                o["note"] = f"Not enough cash when it filled (needed ${cost:,.2f})"
                return
            self.acct["cash"] -= cost
            pos = {"shares": pos["shares"] + o["qty"], "cost": pos["cost"] + cost}
            realized = 0.0
        else:
            if o["qty"] > pos["shares"] + 1e-9:
                o["status"], o["closed_at"] = "rejected", _now_iso(now)
                o["note"] = "You no longer hold enough shares"
                return
            part = o["qty"] / pos["shares"]
            basis = pos["cost"] * part
            proceeds = o["qty"] * fill - fee
            realized = proceeds - basis
            self.acct["cash"] += proceeds
            self.acct["realized"] += realized
            pos = {"shares": pos["shares"] - o["qty"], "cost": pos["cost"] - basis}
        if pos["shares"] <= 1e-9:
            self.acct["positions"].pop(o["ticker"], None)
        else:
            pos["shares"] = round(pos["shares"], QTY_DECIMALS)
            self.acct["positions"][o["ticker"]] = pos
        self.acct["cash"] = round(self.acct["cash"], 6)
        self.acct["fees"] += fee
        o.update(status="filled", filled_at=_now_iso(now), fill_price=fill, fee=fee, closed_at=_now_iso(now),
                 note="" if market_open(now) or self.acct["prices"] == "demo"
                 else "Practice fill: market closed, filled at the last price")
        self.acct["fills"].append({"order_id": o["id"], "ticker": o["ticker"], "side": o["side"], "qty": o["qty"],
                                   "price": fill, "fee": fee, "time": o["filled_at"],
                                   "realized": round(realized, 6) if not buy else None,
                                   "source": q.get("source", "")})

    def refresh(self, fresh: bool = False) -> dict:
        """Fetch quotes for everything open, held or watched; fill what can fill.

        ``fresh`` skips the quote cache (the page's Refresh prices button).
        Errors for symbols no longer open, held or watched are dropped, so a
        mistyped lookup doesn't stay on the page."""
        with self.lock:
            tickers = sorted({o["ticker"] for o in self.acct["orders"] if o["status"] == "open"}
                             | set(self.acct["positions"]) | set(self.acct["watchlist"]))
            for t in [t for t in self.quote_errors if t not in tickers]:
                del self.quote_errors[t]
        got = {}
        for t in tickers:
            try:
                got[t] = self.quote(t, fresh=fresh)
            except (ValueError, OSError) as exc:
                with self.lock:  # quote() records most errors; a bad symbol fails before it can
                    self.quote_errors.setdefault(t, str(exc))
        with self.lock:
            now = self.clock()
            changed = 0
            for o in self.acct["orders"]:
                if o["status"] == "open" and o["ticker"] in got:
                    before = o["status"]
                    self._try_fill(o, got[o["ticker"]], now)
                    changed += o["status"] != before
                elif o["status"] == "open" and o["tif"] == "day" and self.acct["prices"] != "demo" \
                        and not self.acct["settings"]["practice_fills"] \
                        and now >= session_end(date.fromisoformat(o["session"])):
                    o["status"], o["note"], o["closed_at"] = "expired", "Day order: the session ended", _now_iso(now)
                    changed += 1
            recorded = self._record_equity(now)
            if changed or recorded or self.acct["prices"] == "demo":
                self._trim()
                self._write()
            return {"ok": True, "quotes": len(got), "changed": changed}

    def _trim(self) -> None:
        orders = self.acct["orders"]
        if len(orders) > KEEP_ORDERS:
            keep_open = [o for o in orders if o["status"] == "open"]
            closed = [o for o in orders if o["status"] != "open"]
            closed = closed[len(closed) - max(KEEP_ORDERS - len(keep_open), 0):]  # [-0:] would keep all
            self.acct["orders"] = sorted(keep_open + closed, key=lambda o: o["id"])
        self.acct["fills"] = self.acct["fills"][-KEEP_ORDERS:]

    # ---- valuation -------------------------------------------------------

    def _valuation(self) -> tuple[float, list[dict], bool]:
        rows, value, unknown = [], 0.0, False
        for t, pos in sorted(self.acct["positions"].items()):
            px = self._price(t)
            q = self.quotes.get(t) or {}
            if px is None:
                unknown = True
            mv = pos["shares"] * (px if px is not None else pos["cost"] / pos["shares"])
            value += mv
            avg = pos["cost"] / pos["shares"]
            prev = q.get("prev_close") if px is not None else None
            rows.append({"ticker": t, "shares": pos["shares"], "avg_cost": avg, "cost": pos["cost"],
                         "price": px, "market_value": mv if px is not None else None,
                         "unrealized": mv - pos["cost"] if px is not None else None,
                         "unrealized_pct": (mv / pos["cost"] - 1) if px is not None and pos["cost"] > 0 else None,
                         "day_change": pos["shares"] * (px - prev) if prev else None})
        return self.acct["cash"] + value, rows, unknown

    def _record_equity(self, now: datetime, force: bool = False) -> bool:
        equity, _, unknown = self._valuation()
        if unknown:
            return False
        pts = self.acct["equity"]
        if pts and not force:
            try:
                if now - datetime.fromisoformat(pts[-1]["t"]) < EQUITY_EVERY:
                    return False
            except (KeyError, TypeError, ValueError):
                pass
        pts.append({"t": _now_iso(now), "equity": round(equity, 4)})
        del pts[:-EQUITY_POINTS]
        return True

    def snapshot(self) -> dict:
        with self.lock:
            now = self.clock()
            equity, rows, unknown = self._valuation()
            a = self.acct
            start = a["starting_cash"]
            watch = []
            for t in a["watchlist"]:
                q = self.quotes.get(t)
                q = q if q and q.get("source") == self._kind() else None
                watch.append({"ticker": t, "price": q["price"] if q else None,
                              "prev_close": q.get("prev_close") if q else None,
                              "name": q.get("name", "") if q else "", "time": q.get("time") if q else None,
                              "error": self.quote_errors.get(t)})
            orders = sorted(a["orders"], key=lambda o: -o["id"])
            return {
                "ok": True, "now": _now_iso(now), "home": str(self.home),
                "prices": a["prices"], "created": a["created"], "settings": dict(a["settings"]),
                "market": {"open": market_open(now), "next_session": next_session(now).isoformat(),
                           "can_fill": self._can_fill_now(now)},
                "starting_cash": start, "cash": a["cash"], "buying_power": a["cash"] - self._reserved(),
                "equity": equity, "equity_unknown": unknown, "total_pl": equity - start,
                "total_pl_pct": equity / start - 1, "realized": a["realized"], "fees": a["fees"],
                "positions": rows, "open_orders": [o for o in orders if o["status"] == "open"],
                "orders": orders[:300], "fills": list(reversed(a["fills"]))[:300], "equity_curve": a["equity"],
                "watchlist": watch, "quote_errors": dict(self.quote_errors), "notes": list(self.notes),
            }

    # ---- account settings ------------------------------------------------

    def reset(self, form: dict) -> dict:
        try:
            cash = _num(form.get("starting_cash", DEFAULT_CASH), "Starting balance", 1, MAX_CASH)
            prices = _choice(form.get("prices", "live"), ("live", "demo"), "prices")
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        with self.lock:
            kept = self._backup("bak")
            watch = list(self.acct.get("watchlist") or DEFAULT_WATCH)
            settings = dict(self.acct["settings"])
            self.acct = new_account(self.clock(), round(cash, 2), prices)
            self.acct["watchlist"], self.acct["settings"] = watch, settings
            self.quotes.clear()
            self.quote_errors.clear()
            self.notes.clear()
            self._write()
            return {"ok": True, "kept": kept.name}

    def update_settings(self, form: dict) -> dict:
        new = {}
        try:
            if "commission" in form:
                new["commission"] = _num(form["commission"], "Commission", 0, 100, allow_zero=True)
            if "slippage_bps" in form:
                new["slippage_bps"] = _num(form["slippage_bps"], "Slippage", 0, 500, allow_zero=True)
            for key in ("fractional", "practice_fills"):
                if key in form:
                    v = _strict_bool(form[key])
                    if v is None:
                        raise ValueError(f"{key} must be true or false")
                    new[key] = v
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        with self.lock:
            if new.get("fractional") is False and any(
                    p["shares"] != int(p["shares"]) for p in self.acct["positions"].values()):
                return {"ok": False, "error": "You hold fractional shares; sell them before turning this off"}
            self.acct["settings"].update(new)
            self._write()
            return {"ok": True, "settings": dict(self.acct["settings"])}

    def watch(self, ticker, add) -> dict:
        try:
            ticker = clean_ticker(ticker)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        add = _strict_bool(add)
        if add is None:
            return {"ok": False, "error": "add must be true or false"}
        with self.lock:
            wl = self.acct["watchlist"]
            if add and ticker not in wl:
                if len(wl) >= 50:
                    return {"ok": False, "error": "The watchlist holds 50 symbols"}
                wl.append(ticker)
            elif not add and ticker in wl:
                wl.remove(ticker)
            self._write()
            return {"ok": True, "watchlist": list(wl)}


def _from_this_session(q: dict, now: datetime) -> bool:
    """False when the quote's time is from before today's 9:30 open (a
    delayed quote still showing the previous close).  A quote without a
    time is taken as current."""
    try:
        t = datetime.fromisoformat(q["time"])
    except (KeyError, TypeError, ValueError):
        return True
    if t.tzinfo is None:
        return True
    return t >= datetime.combine(now.astimezone(NY).date(), OPEN, tzinfo=NY)


def clean_ticker(value) -> str:
    t = (value if isinstance(value, str) else "").strip().upper()
    if not TICKER_RE.match(t):
        raise ValueError("Enter a stock symbol such as AAPL (letters, digits, '.' or '-', up to 10)")
    return t


def _choice(value, options, name: str) -> str:
    v = value.strip().lower() if isinstance(value, str) else None
    if v not in options:
        raise ValueError(f"{name} must be one of: {', '.join(options)}")
    return v


def _fmt_qty(q: float) -> str:
    return f"{q:,.6f}".rstrip("0").rstrip(".") if q != int(q) else f"{int(q):,}"


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------


def _strict_bool(value) -> bool | None:
    """true/false, "true"/"false", 1/0; None for anything else, so "no" or
    "maybe" is not read as true."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in ("true", "false", "1", "0"):
        return value.strip().lower() in ("true", "1")
    return None


def open_folder(path: Path) -> dict:
    """Show the account folder in the file manager (this computer only)."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return {"ok": True}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}


def _finite(obj):
    """``obj`` with NaN and infinities as None: browsers reject them in JSON."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _finite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_finite(v) for v in obj]
    return obj


class _Handler(BaseHTTPRequestHandler):
    """Refuses what another web page could forge: a Host other than this
    computer's address (DNS rebinding), a POST from another origin, a POST
    that isn't JSON (a plain HTML form can't send JSON), or an oversized body."""

    def log_message(self, fmt: str, *args) -> None:  # quiet the console
        pass

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status: int = 200) -> None:
        self._send(status, json.dumps(_finite(obj), allow_nan=False).encode("utf-8"), "application/json")

    def _allowed(self, post: bool) -> bool:
        port = self.server.server_address[1]
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if (self.headers.get("Host") or "").strip().lower() not in hosts:
            self._json({"ok": False, "error": "forbidden host"}, 403)
            return False
        if post:
            origin = self.headers.get("Origin")
            if origin is not None and origin.strip().lower() not in {f"http://{h}" for h in hosts}:
                self._json({"ok": False, "error": "forbidden origin"}, 403)
                return False
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ctype != "application/json":
                self._json({"ok": False, "error": "Content-Type must be application/json"}, 415)
                return False
        return True

    def _read_json_body(self) -> dict | None:
        length = (self.headers.get("Content-Length") or "").strip()
        if not (length.isascii() and length.isdigit()):
            self._json({"ok": False, "error": "a valid Content-Length is required"}, 400)
            return None
        if int(length) > MAX_BODY:
            self._json({"ok": False, "error": f"request body over {MAX_BODY} bytes"}, 413)
            return None
        try:
            body = json.loads(self.rfile.read(int(length)) or b"{}")
        except (ValueError, RecursionError):
            self._json({"ok": False, "error": "bad JSON"}, 400)
            return None
        if not isinstance(body, dict):
            self._json({"ok": False, "error": "expected a JSON object"}, 400)
            return None
        return body


class PaperServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = os.name != "nt"  # POSIX: restart at once; Windows: a second copy must fail

    def __init__(self, address: tuple[str, int], book: Book) -> None:
        super().__init__(address, _PaperHandler)
        self.book = book


class _PaperHandler(_Handler):
    """Only 127.0.0.1/localhost Host headers, JSON POSTs from this page only
    (see ``_Handler``)."""
    server: PaperServer

    def do_GET(self) -> None:  # noqa: N802
        if not self._allowed(post=False):
            return
        url = urlparse(self.path)
        book = self.server.book
        if url.path in ("/", "/index.html"):
            try:
                page = PAGE_FILE.read_bytes()
            except OSError:
                page = b"<!doctype html><title>Paper Trading</title><p>paper_page.html is missing.</p>"
            self._send(200, page, "text/html; charset=utf-8")
        elif url.path == "/api/account":
            self._json(book.snapshot())
        elif url.path == "/api/quote":
            t = (parse_qs(url.query).get("t") or [""])[0]
            try:
                q = book.quote(t)
                self._json({"ok": True, "quote": {k: v for k, v in q.items() if k != "fetched"}})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)})
            except OSError as exc:
                self._json({"ok": False, "error": f"No price: {exc}"})
        elif url.path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        if not self._allowed(post=True):
            return
        path = urlparse(self.path).path
        book = self.server.book
        body = self._read_json_body()
        if body is None:
            return
        if path == "/api/order":
            self._json(book.place(body))
        elif path == "/api/cancel":
            oid = body.get("id")
            self._json(book.cancel(oid) if isinstance(oid, int) and not isinstance(oid, bool)
                       else {"ok": False, "error": "id must be an order number"})
        elif path == "/api/refresh":
            self._json(book.refresh(fresh=True))
        elif path == "/api/reset":
            self._json(book.reset(body))
        elif path == "/api/settings":
            self._json(book.update_settings(body))
        elif path == "/api/watch":
            self._json(book.watch(body.get("ticker"), body.get("add", True)))
        elif path == "/api/open-folder":
            self._json(open_folder(book.home))
        else:
            self._json({"error": "not found"}, 404)


def _refresher(book: Book, stop: threading.Event) -> None:
    while not stop.wait(REFRESH_EVERY):
        try:
            book.refresh()
        except Exception as exc:  # keep checking orders whatever one round does
            print(f"refresh failed: {type(exc).__name__}: {exc}")


def serve(port: int = DEFAULT_PORT, open_browser: bool = True, home: str | Path | None = None,
          block: bool = True, background: bool = True) -> PaperServer:
    book = Book(home)
    try:
        server = PaperServer(("127.0.0.1", port), book)
    except OSError:
        url = f"http://127.0.0.1:{port}/"
        print(f"Port {port} is in use: Paper Trading is probably already open. Opening {url}")
        if open_browser:
            webbrowser.open(url)
        raise
    threading.Thread(target=server.serve_forever, name="paper-http", daemon=True).start()
    stop = threading.Event()
    server.stop_refresh = stop  # type: ignore[attr-defined]
    if background:
        threading.Thread(target=_refresher, args=(book, stop), name="paper-refresh", daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Paper Trading: {url}")
    print(f"Account folder: {book.home}")
    print("PRETEND MONEY ONLY: no broker is connected. Keep this window open; close it to stop.")
    for note in book.notes:
        print(note)
    if open_browser:
        webbrowser.open(url)
    if block:
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            print("stopping")
            stop.set()
            server.shutdown()
    return server


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python paper_app.py", description=__doc__.split("\n")[0])
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--home", default=None, help="the account folder (default: paper_data/ or QT_PAPER_HOME)")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        serve(args.port, not args.no_browser, args.home)
    except OSError as exc:
        print(f"could not start: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
