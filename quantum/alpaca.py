"""A real broker for the live engine: Alpaca (https://alpaca.markets).

This is the code that replaces paper trading.  It implements the same four
methods as :class:`quantum.live.PaperBroker`, so the engine does not change;
only where orders go does.

Safety, in the order the checks run
-----------------------------------
1. **Keys come from the environment, never from files or chat.**
   ``ALPACA_API_KEY_ID`` and ``ALPACA_API_SECRET_KEY``; in GitHub Actions
   they are repository secrets.
2. **Paper by default.**  With no ``ALPACA_BASE_URL`` the broker talks to
   Alpaca's paper endpoint: real market, real order handling, fake money.
3. **Real money needs two deliberate settings**: ``ALPACA_BASE_URL`` set to
   the live endpoint *and* ``QT_ALLOW_REAL_MONEY=yes``.  Either alone is
   refused.
4. **The account must be tradable**: blocked or restricted accounts are
   refused before any order.
5. **Only today's bar can trade.**  The engine catches up on missed days;
   a real broker must never place an order for a past date, so an order for
   a bar older than ``max_bar_age_days`` calendar days (default 1) is
   refused.  "Today" is the date in New York (America/New_York), the
   exchange's calendar, not UTC: the workflow runs at 21:30 UTC, which is
   17:30 EDT / 16:30 EST, the same New York date as the close, but a run
   after 20:00 EDT (19:00 EST) is already tomorrow in UTC and would see its
   own bar as a day old.  The one-day allowance covers a run after New York
   midnight but before the next open (the order still fills at that open,
   exactly as one sent right after the close would); a Friday bar is three
   days old by Monday and is refused, so a missed day is never traded late.
6. **Budget cap, with realized P&L kept.**  The engine's cash is its own
   ledger: ``budget`` (by default the config's ``initial_cash``) less what
   its own fills spent (buys, with fees) plus what they returned (sells,
   and cash in lieu on a split), taken from the fills in its state file and
   updated with every order sent.  A loss taken on a sale therefore stays
   lost: the budget does not refill, and the drawdown kill switch sees it.
   The cash reported is that ledger, capped by the account's actual cash and
   never below zero.  Bookkeeping fills (a note and price 0) move no cash.
   Without a fill history (a fresh state), or when the history's share
   counts do not match what the account holds (a paper state reused, an
   order cancelled after it was recorded; logged), the ledger falls back to
   ``budget`` less the cost basis of what the engine's tickers hold, which
   cannot see realized P&L.  It
   manages only its own tickers; anything else in the account is invisible
   to it and never sold.
7. **No doubling up.**  If an order for one of its tickers is still open
   (orders sent after the close wait for the next open), it sends nothing
   new for that ticker this run.

Orders are market orders, ``time_in_force: day``, fractional quantities
rounded to six decimals, each with a ``client_order_id`` of
``qt-<bar date>-<symbol>-<side>``.  A run replayed the same evening (after a
failed state push) sends the same ids; Alpaca rejects the duplicates, and
the broker treats that as "already sent": it logs the order and records no
new fill.  Sent after the close, they fill at the next open,
so the fills the engine records carry the *close* as an estimate; the next
run reads the real positions and cash back from Alpaca, so the book always
reconciles to the broker.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import date, datetime
from typing import Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

from .live import Bar, Broker, Fill, Order

__all__ = ["AlpacaBroker", "BrokerRefused", "PAPER_URL", "LIVE_URL", "from_environment"]

PAPER_URL = "https://paper-api.alpaca.markets"
LIVE_URL = "https://api.alpaca.markets"

Transport = Callable[[str, str, dict | None], object]
"""``(method, path, body) -> parsed JSON``.  Injected in tests."""


class BrokerRefused(RuntimeError):
    """A safety check stopped the broker.  Nothing was sent."""


EXCHANGE_TZ = ZoneInfo("America/New_York")


def _new_york_today() -> date:
    """Today's date on the exchange's calendar."""
    return datetime.now(EXCHANGE_TZ).date()


def _is_duplicate_order_id(exc: Exception) -> bool:
    """Alpaca's rejection of a ``client_order_id`` it has already seen
    (HTTP 422, "client_order_id must be unique")."""
    text = str(exc).lower()
    return "client_order_id" in text and "422" in text


def net_cash_flow(fills: Sequence[Mapping]) -> float:
    """Cash the fills moved: sells and cash in lieu add, buys and fees subtract.

    A bookkeeping fill (a truthy ``note`` and price 0: a split or dividend
    re-base) moves no cash; one with a price (cash in lieu) does.
    """
    total = 0.0
    for f in fills:
        price = float(f.get("price", 0) or 0)
        if f.get("note") and price == 0:
            continue
        total -= float(f.get("quantity", 0) or 0) * price + float(f.get("fee", 0) or 0)
    return total


def _http_transport(base_url: str, key_id: str, secret: str, timeout: float = 30.0) -> Transport:
    def call(method: str, path: str, body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            base_url.rstrip("/") + path, data=data, method=method,
            headers={"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret,
                     "Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"Alpaca {method} {path} failed: HTTP {exc.code} {detail}") from None
        return json.loads(raw) if raw else None
    return call


class AlpacaBroker(Broker):
    """Places the engine's orders with Alpaca.  See the module docstring."""

    def __init__(self, tickers: Sequence[str], budget: float, transport: Transport,
                 base_url: str = PAPER_URL, max_bar_age_days: int = 1,
                 today: Callable[[], date] | None = None,
                 log: Callable[[str], None] | None = None,
                 fills: Sequence[Mapping] | None = None) -> None:
        """``fills`` is the engine's own fill history (``EngineState.fills``,
        dicts with ticker, quantity, price, fee, date and an optional note).
        ``None`` means no history is known; see :meth:`cash`."""
        self.tickers = [t.upper() for t in tickers]
        self.budget = float(budget)
        self.base_url = base_url
        self.max_bar_age_days = int(max_bar_age_days)
        self._call = transport
        self._today = today or _new_york_today
        self._log = log or (lambda line: None)
        self.submitted: list[dict] = []
        account = self._call("GET", "/v2/account", None) or {}
        for flag in ("account_blocked", "trading_blocked", "trade_suspended_by_user"):
            if account.get(flag):
                raise BrokerRefused(f"Alpaca account is not tradable ({flag})")
        if str(account.get("status", "ACTIVE")).upper() != "ACTIVE":
            raise BrokerRefused(f"Alpaca account status is {account.get('status')!r}, not ACTIVE")
        self._account = account
        self._positions_raw: list[dict] | None = None
        # The engine's ledger: budget plus the cash its own fills moved.
        self._flows: float | None = None
        if fills is not None:
            self._flows = net_cash_flow(fills)
            mismatch = self._history_mismatch(fills)
            if mismatch:
                # The history is not this account's (a paper state reused,
                # an order cancelled after it was recorded): its flows would
                # misstate the cash, so use the account's cost basis instead.
                self._log(f"fill history does not match the Alpaca account ({mismatch}); "
                          "cash falls back to the budget less the cost of what is held")
                self._flows = None
        # Sent this run, not yet filled: counted in positions() so equity
        # stays whole between an order leaving and its fill at the next open.
        self._pending: dict[str, float] = {}

    def _history_mismatch(self, fills: Sequence[Mapping]) -> str:
        """Empty when the shares the fills add up to are what the account holds."""
        booked: dict[str, float] = {}
        for f in fills:
            sym = str(f.get("ticker", "")).upper()
            booked[sym] = booked.get(sym, 0.0) + float(f.get("quantity", 0) or 0)
        held = self._held()
        for sym in sorted(set(self.tickers) & (set(booked) | set(held))):
            b, h = booked.get(sym, 0.0), held.get(sym, 0.0)
            if abs(b - h) > max(1e-4, 0.005 * max(abs(b), abs(h))):
                return f"{sym}: fills say {b:g} shares, account holds {h:g}"
        return ""

    @property
    def is_paper(self) -> bool:
        return self.base_url.rstrip("/") == PAPER_URL

    @property
    def mode(self) -> str:
        """What the dashboard shows: ``alpaca-paper`` or ``alpaca-live``."""
        return "alpaca-paper" if self.is_paper else "alpaca-live"

    # -- reading the account ------------------------------------------------
    def _positions_list(self) -> list[dict]:
        if self._positions_raw is None:
            self._positions_raw = list(self._call("GET", "/v2/positions", None) or [])
        return self._positions_raw

    def _held(self) -> dict[str, float]:
        """What the account holds of the engine's tickers (filled orders only)."""
        out = {}
        for p in self._positions_list():
            sym = str(p.get("symbol", "")).upper()
            if sym in self.tickers:
                qty = float(p.get("qty", 0) or 0)
                if abs(qty) > 1e-12:
                    out[sym] = qty
        return out

    def positions(self) -> dict[str, float]:
        """The account's positions in the engine's tickers, plus the orders
        this run sent (they fill at the next open, and their cost has
        already left :meth:`cash`)."""
        out = self._held()
        for sym, qty in self._pending.items():
            out[sym] = out.get(sym, 0.0) + qty
        return {s: q for s, q in out.items() if abs(q) > 1e-12}

    @property
    def engine_cash(self) -> float:
        """The engine's own ledger, before the account cap."""
        if self._flows is None:
            held_cost = sum(float(p.get("cost_basis", 0) or 0) for p in self._positions_list()
                            if str(p.get("symbol", "")).upper() in self.tickers)
            return self.budget - held_cost
        return self.budget + self._flows

    def cash(self) -> float:
        """Cash the engine may use: its ledger (budget plus the realized
        flows of its own fills), capped by the account's cash, never negative."""
        account_cash = float(self._account.get("cash", 0) or 0)
        return max(0.0, min(account_cash, self.engine_cash))

    def _open_order_symbols(self) -> set[str]:
        orders = self._call("GET", "/v2/orders?status=open&limit=500", None) or []
        return {str(o.get("symbol", "")).upper() for o in orders}

    # -- placing orders -----------------------------------------------------
    def accepts(self, bar: Bar) -> bool:
        return (self._today() - date.fromisoformat(bar.date)).days <= self.max_bar_age_days

    def submit(self, orders: Sequence[Order], bar: Bar) -> list[Fill]:
        if not self.accepts(bar):
            age = (self._today() - date.fromisoformat(bar.date)).days
            self._log(f"{bar.date} not sent: the bar is {age} days old; a real broker only trades today's bar")
            return []
        pending = self._open_order_symbols()
        fills: list[Fill] = []
        for order in sorted(orders, key=lambda o: o.quantity):  # sells first
            sym = order.ticker.upper()
            if sym not in self.tickers:
                raise BrokerRefused(f"order for {sym}, which the bot does not manage")
            qty = round(abs(order.quantity), 6)
            if qty <= 0:
                continue
            if sym in pending:
                self._log(f"{bar.date} {sym} skipped: an earlier order is still open")
                continue
            side = "buy" if order.quantity > 0 else "sell"
            if side == "sell":
                qty = min(qty, round(abs(self._held().get(sym, 0.0)), 6))
                if qty <= 0:
                    continue
            body = {"symbol": sym, "qty": f"{qty:.6f}".rstrip("0").rstrip("."), "side": side,
                    "type": "market", "time_in_force": "day",
                    "client_order_id": f"qt-{bar.date}-{sym}-{side}"}
            try:
                placed = self._call("POST", "/v2/orders", body) or {}
            except RuntimeError as exc:
                if not _is_duplicate_order_id(exc):
                    raise
                # Sent by an earlier run of this same bar (whose state was
                # not saved): already at the broker, so no new fill here;
                # the next run reads the real position back.
                self._log(f"{bar.date} {sym} {side} skipped: already sent ({body['client_order_id']})")
                continue
            self.submitted.append({"date": bar.date, **body, "id": placed.get("id"), "status": placed.get("status")})
            signed = qty if side == "buy" else -qty
            # The close is an estimate; the next run reads the real fill back.
            fill = Fill(sym, signed, bar.prices[sym], 0.0, bar.date)
            fills.append(fill)
            if self._flows is None:
                # No history: start the ledger from what the account shows now.
                self._flows = self.engine_cash - self.budget
            self._flows -= fill.quantity * fill.price + fill.fee
            self._pending[sym] = self._pending.get(sym, 0.0) + signed
        return fills


def from_environment(tickers: Sequence[str], budget: float, env: dict | None = None,
                     log: Callable[[str], None] | None = None,
                     transport: Transport | None = None,
                     fills: Sequence[Mapping] | None = None) -> AlpacaBroker:
    """Build the broker from environment variables, enforcing the real-money lock.

    ``fills`` is the engine's fill history from its state file (see
    :class:`AlpacaBroker`); ``None`` when there is no state to resume."""
    env = os.environ if env is None else env
    key, secret = env.get("ALPACA_API_KEY_ID", ""), env.get("ALPACA_API_SECRET_KEY", "")
    if not key or not secret:
        raise BrokerRefused("ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY must be set "
                            "(in GitHub: repository Settings > Secrets and variables > Actions)")
    base = (env.get("ALPACA_BASE_URL") or PAPER_URL).rstrip("/")
    if base not in (PAPER_URL, LIVE_URL):
        raise BrokerRefused(f"ALPACA_BASE_URL must be {PAPER_URL} or {LIVE_URL}, not {base!r}")
    if base == LIVE_URL and env.get("QT_ALLOW_REAL_MONEY", "").strip().lower() != "yes":
        raise BrokerRefused("ALPACA_BASE_URL points at the real-money endpoint but "
                            "QT_ALLOW_REAL_MONEY is not 'yes'; refusing to trade real money")
    call = transport or _http_transport(base, key, secret)
    return AlpacaBroker(tickers, budget, call, base_url=base, log=log, fills=fills)
