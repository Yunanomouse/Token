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
   a bar older than ``max_bar_age_days`` calendar days is refused.
6. **Budget cap.**  The engine sees at most ``budget`` dollars of cash
   (by default the config's ``initial_cash``), less the cost of what it
   already holds, however much the account has.  It manages only its own
   tickers; anything else in the account is invisible to it and never sold.
7. **No doubling up.**  If an order for one of its tickers is still open
   (orders sent after the close wait for the next open), it sends nothing
   new for that ticker this run.

Orders are market orders, ``time_in_force: day``, fractional quantities
rounded to six decimals.  Sent after the close, they fill at the next open,
so the fills the engine records carry the *close* as an estimate; the next
run reads the real positions and cash back from Alpaca, so the book always
reconciles to the broker.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from typing import Callable, Sequence

from .live import Bar, Broker, Fill, Order

__all__ = ["AlpacaBroker", "BrokerRefused", "PAPER_URL", "LIVE_URL", "from_environment"]

PAPER_URL = "https://paper-api.alpaca.markets"
LIVE_URL = "https://api.alpaca.markets"

Transport = Callable[[str, str, dict | None], object]
"""``(method, path, body) -> parsed JSON``.  Injected in tests."""


class BrokerRefused(RuntimeError):
    """A safety check stopped the broker.  Nothing was sent."""


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
                 base_url: str = PAPER_URL, max_bar_age_days: int = 4,
                 today: Callable[[], date] | None = None,
                 log: Callable[[str], None] | None = None) -> None:
        self.tickers = [t.upper() for t in tickers]
        self.budget = float(budget)
        self.base_url = base_url
        self.max_bar_age_days = int(max_bar_age_days)
        self._call = transport
        self._today = today or (lambda: datetime.now(timezone.utc).date())
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

    def positions(self) -> dict[str, float]:
        out = {}
        for p in self._positions_list():
            sym = str(p.get("symbol", "")).upper()
            if sym in self.tickers:
                qty = float(p.get("qty", 0) or 0)
                if abs(qty) > 1e-12:
                    out[sym] = qty
        return out

    def cash(self) -> float:
        """Cash the engine may use: the account's cash, capped by the budget
        less the cost of what the engine already holds."""
        account_cash = float(self._account.get("cash", 0) or 0)
        held_cost = sum(float(p.get("cost_basis", 0) or 0) for p in self._positions_list()
                        if str(p.get("symbol", "")).upper() in self.tickers)
        return max(0.0, min(account_cash, self.budget - held_cost))

    def _open_order_symbols(self) -> set[str]:
        orders = self._call("GET", "/v2/orders?status=open&limit=500", None) or []
        return {str(o.get("symbol", "")).upper() for o in orders}

    # -- placing orders -----------------------------------------------------
    def submit(self, orders: Sequence[Order], bar: Bar) -> list[Fill]:
        age = (self._today() - date.fromisoformat(bar.date)).days
        if age > self.max_bar_age_days:
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
                qty = min(qty, round(abs(self.positions().get(sym, 0.0)), 6))
                if qty <= 0:
                    continue
            body = {"symbol": sym, "qty": f"{qty:.6f}".rstrip("0").rstrip("."), "side": side,
                    "type": "market", "time_in_force": "day",
                    "client_order_id": f"qt-{bar.date}-{sym}-{side}"}
            placed = self._call("POST", "/v2/orders", body) or {}
            self.submitted.append({"date": bar.date, **body, "id": placed.get("id"), "status": placed.get("status")})
            signed = qty if side == "buy" else -qty
            # The close is an estimate; the next run reads the real fill back.
            fills.append(Fill(sym, signed, bar.prices[sym], 0.0, bar.date))
        self._positions_raw = None  # positions change once orders fill
        return fills


def from_environment(tickers: Sequence[str], budget: float, env: dict | None = None,
                     log: Callable[[str], None] | None = None,
                     transport: Transport | None = None) -> AlpacaBroker:
    """Build the broker from environment variables, enforcing the real-money lock."""
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
    return AlpacaBroker(tickers, budget, call, base_url=base, log=log)
