"""A standalone trading engine the portfolio optimiser can run inside, live.

This is the piece that turns the package from a research library into a
program: a loop that takes prices as they arrive, refits the optimiser on a
trailing window, turns target weights into orders, checks them against risk
limits, sends them to a broker, and persists everything it knows so it can be
stopped and restarted without losing its book.

What it is, precisely
---------------------
* **A price feed** (:class:`PriceFeed`) delivers one bar per tick: a date and
  a close per ticker.  Two are provided.  :class:`ReplayFeed` replays a CSV
  bar by bar, so the whole engine can be run end to end on bundled history
  with no network at all.  :class:`FileFeed` tails a CSV that some other
  process appends to -- a broker export, a cron job hitting a data vendor --
  and delivers each new row as it appears.  Anything that can write a CSV
  row is therefore a live feed.

* **A broker** (:class:`Broker`) accepts orders and reports fills and
  positions.  :class:`PaperBroker` fills at the bar's close with a
  proportional fee and keeps a ledger; it is the default and, today, the
  only implementation.  A real broker is a subclass with the same four
  methods.  ``--live`` refuses to start unless one is supplied, on purpose.

* **A strategy** is any function ``MarketData -> weights`` -- the same
  signature the walk-forward backtest uses, so what was validated there is
  what runs here.  The default is the cardinality-constrained mean-variance
  problem solved by simulated annealing, which the backtest showed matched
  exhaustive search at every rebalance on a decade of real prices.

* **Risk limits** (:class:`RiskLimits`) are checked *before* every order:
  maximum weight per name, maximum one-way turnover per rebalance, minimum
  history before the first trade, and a drawdown kill switch that liquidates
  and halts.  The kill switch is not advisory: once tripped the engine will
  not trade again until the state file is edited by a person.

* **State** (:class:`EngineState`) is written to JSON after every tick.  On
  start the engine reads it back and resumes from the last bar it saw, so a
  crash or a reboot costs nothing but the ticks in between.

What it is not
--------------
It does not predict prices.  The optimiser inside it beat equal weight on one
real decade with a t-statistic of 2.1 and a hindsight-selected universe, and
lost to it on synthetic data; see ``docs/quantum_trading.md``.  Nothing in
this file changes that arithmetic.  It also does not connect to any exchange:
supplying a real :class:`Broker` is the operator's decision and code.

Running it
----------
::

    python3 -m quantum live --config live.json            # loop until stopped
    python3 -m quantum live --config live.json --once     # one tick, for cron
    python3 -m quantum live --replay data/prices/us_equities_1989_2018.csv \\
        --tickers AAPL,XOM,JPM,WMT,PFE --start 2010-01-01  # paper run on history

``live.json`` holds an :class:`EngineConfig`; ``--replay`` builds one for
you.  Every tick logs one line; the state file is the source of truth.
"""

from __future__ import annotations

import csv
import json
import math
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, Sequence

import numpy as np

from .backtest import cardinality_strategy, equal_weight, markowitz_long_only
from .market import MarketData

__all__ = [
    "Bar",
    "Broker",
    "Engine",
    "EngineConfig",
    "EngineState",
    "FileFeed",
    "Fill",
    "Order",
    "PaperBroker",
    "PriceFeed",
    "ReplayFeed",
    "RiskLimits",
    "build_strategy",
    "load_config",
    "run",
    "snapshot",
    "trade_ledger",
]


# --------------------------------------------------------------------------
# Feeds
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Bar:
    """One observation: a date string (ISO) and a close per ticker."""

    date: str
    prices: dict[str, float]

    def vector(self, tickers: Sequence[str]) -> np.ndarray:
        return np.array([self.prices[t] for t in tickers], dtype=np.float64)


class PriceFeed:
    """Yields :class:`Bar` objects in time order.  Subclasses implement ``bars``."""

    tickers: list[str]

    def bars(self) -> Iterator[Bar]:  # pragma: no cover - abstract
        raise NotImplementedError


def _read_csv_bars(path: Path, tickers: Sequence[str] | None, date_column: str | None) -> tuple[list[str], list[Bar]]:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return list(tickers or []), []
    header = list(rows[0].keys())
    if date_column is None:
        date_column = next((c for c in header if c.lower() in ("date", "timestamp", "time", "day")), header[0])
    cols = list(tickers) if tickers else [c for c in header if c != date_column]
    bars: list[Bar] = []
    for row in rows:
        try:
            prices = {c: float(row[c]) for c in cols}
        except (TypeError, ValueError, KeyError):
            continue  # a missing cell: skip the bar rather than invent a price
        if any(not math.isfinite(v) or v <= 0 for v in prices.values()):
            continue
        bars.append(Bar(str(row[date_column])[:10], prices))
    return cols, bars


class ReplayFeed(PriceFeed):
    """Replay a wide CSV bar by bar -- the offline, deterministic feed."""

    def __init__(self, path: str | Path, tickers: Sequence[str] | None = None,
                 start: str | None = None, end: str | None = None,
                 date_column: str | None = None) -> None:
        self.path = Path(path)
        self.tickers, bars = _read_csv_bars(self.path, tickers, date_column)
        self._bars = [b for b in bars if (not start or b.date >= start) and (not end or b.date <= end)]

    def __len__(self) -> int:
        return len(self._bars)

    def bars(self) -> Iterator[Bar]:
        yield from self._bars


class FileFeed(PriceFeed):
    """Tail a CSV that another process appends to; one bar per new row.

    This is how the engine goes live without depending on any vendor API:
    whatever fetches prices -- a cron job, a broker export, a hand-maintained
    sheet -- writes a row, and the engine picks it up on its next poll.  Rows
    already seen (by date) are ignored, so the writer may rewrite the file.
    """

    def __init__(self, path: str | Path, tickers: Sequence[str] | None = None,
                 poll_seconds: float = 60.0, date_column: str | None = None,
                 after: str | None = None, max_polls: int | None = None) -> None:
        self.path = Path(path)
        self.poll_seconds = float(poll_seconds)
        self.date_column = date_column
        self.after = after
        self.max_polls = max_polls
        self.tickers, _ = _read_csv_bars(self.path, tickers, date_column) if self.path.exists() else (list(tickers or []), [])
        if tickers:
            self.tickers = list(tickers)

    def bars(self) -> Iterator[Bar]:
        seen = self.after
        polls = 0
        while self.max_polls is None or polls < self.max_polls:
            polls += 1
            if self.path.exists():
                _, bars = _read_csv_bars(self.path, self.tickers, self.date_column)
                for bar in bars:
                    if seen is None or bar.date > seen:
                        seen = bar.date
                        yield bar
            if self.max_polls is not None and polls >= self.max_polls:
                return
            time.sleep(self.poll_seconds)


# --------------------------------------------------------------------------
# Brokers
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Order:
    ticker: str
    quantity: float          # shares; negative sells
    reason: str = "rebalance"


@dataclass(frozen=True)
class Fill:
    ticker: str
    quantity: float
    price: float
    fee: float
    date: str


class Broker:
    """The four things an execution venue must do.  Subclass to go live."""

    def positions(self) -> dict[str, float]:  # pragma: no cover - abstract
        raise NotImplementedError

    def cash(self) -> float:  # pragma: no cover - abstract
        raise NotImplementedError

    def submit(self, orders: Sequence[Order], bar: Bar) -> list[Fill]:  # pragma: no cover - abstract
        raise NotImplementedError

    def snapshot(self) -> dict:
        return {"positions": self.positions(), "cash": self.cash()}


class PaperBroker(Broker):
    """Fills every order at the bar's close, less a proportional fee.

    No slippage model, no partial fills, no rejected orders: the friendliest
    possible venue, which makes its results an upper bound on a real one.
    """

    def __init__(self, cash: float = 100_000.0, fee_rate: float = 0.0005,
                 positions: dict[str, float] | None = None) -> None:
        self._cash = float(cash)
        self.fee_rate = float(fee_rate)
        self._positions: dict[str, float] = dict(positions or {})
        self.fills: list[Fill] = []

    def positions(self) -> dict[str, float]:
        return {k: v for k, v in self._positions.items() if abs(v) > 1e-12}

    def cash(self) -> float:
        return self._cash

    def submit(self, orders: Sequence[Order], bar: Bar) -> list[Fill]:
        fills: list[Fill] = []
        # Sells first so their proceeds fund the buys.
        for order in sorted(orders, key=lambda o: o.quantity):
            if abs(order.quantity) < 1e-12:
                continue
            price = bar.prices[order.ticker]
            notional = order.quantity * price
            fee = abs(notional) * self.fee_rate
            if notional + fee > self._cash + 1e-9:
                # Scale the buy down to what cash allows rather than reject it.
                affordable = max(self._cash / (price * (1.0 + self.fee_rate)), 0.0)
                if affordable < 1e-9:
                    continue
                order = Order(order.ticker, affordable, order.reason + "/scaled")
                notional = affordable * price
                fee = notional * self.fee_rate
            self._cash -= notional + fee
            self._positions[order.ticker] = self._positions.get(order.ticker, 0.0) + order.quantity
            fill = Fill(order.ticker, order.quantity, price, fee, bar.date)
            fills.append(fill)
            self.fills.append(fill)
        return fills


# --------------------------------------------------------------------------
# Gains and losses
# --------------------------------------------------------------------------


def trade_ledger(fills: Sequence[dict], last_prices: dict[str, float] | None = None) -> dict:
    """Gains and losses per trade and per name, by average cost, from the fills.

    Rebuilt from the fill history every time rather than stored, so it works
    on any saved state and cannot drift from the trades.  A buy's fee is part
    of its cost; a sell's fee comes off its proceeds.  With that convention
    ``realized + unrealized`` is exactly the change in equity since the start
    (cash plus positions at ``last_prices``).  A round trip runs from a flat
    position to flat again; it is a win if it closed with a gain.
    """
    last_prices = last_prices or {}
    shares: dict[str, float] = {}
    basis: dict[str, float] = {}
    realized: dict[str, float] = {}
    trip: dict[str, dict] = {}
    trips: list[dict] = []
    annotated: list[dict] = []
    for f in fills:
        t, q, px, fee = f["ticker"], float(f["quantity"]), float(f["price"]), float(f["fee"])
        held = shares.get(t, 0.0)
        pnl = 0.0
        if q > 0:
            if held <= 1e-12:
                trip[t] = {"ticker": t, "entry_date": f["date"], "cost": 0.0, "pnl": 0.0}
            shares[t] = held + q
            basis[t] = basis.get(t, 0.0) + q * px + fee
            trip[t]["cost"] += q * px + fee
        elif held > 1e-12:
            sold = min(-q, held)
            avg = basis[t] / held
            pnl = sold * px - fee - avg * sold
            shares[t] = held - sold
            basis[t] -= avg * sold
            realized[t] = realized.get(t, 0.0) + pnl
            trip[t]["pnl"] += pnl
            if shares[t] <= 1e-9 * max(held, 1.0):
                shares[t], basis[t] = 0.0, 0.0
                done = trip.pop(t)
                done.update(exit_date=f["date"], exit_price=px,
                            return_pct=done["pnl"] / done["cost"] if done["cost"] > 0 else 0.0)
                trips.append(done)
        annotated.append({**f, "realized_pnl": pnl})

    names = sorted(set(shares) | set(realized))
    by_name, positions = {}, {}
    for t in names:
        unreal = 0.0
        if shares.get(t, 0.0) > 1e-12:
            px = last_prices.get(t)
            value = shares[t] * px if px is not None else basis[t]
            unreal = value - basis[t]
            positions[t] = {"shares": shares[t], "avg_cost": basis[t] / shares[t], "cost_basis": basis[t],
                            "price": px, "market_value": value, "unrealized_pnl": unreal,
                            "unrealized_pct": unreal / basis[t] if basis[t] > 0 else 0.0,
                            "since": trip[t]["entry_date"]}
        r = realized.get(t, 0.0)
        by_name[t] = {"realized_pnl": r, "unrealized_pnl": unreal, "total_pnl": r + unreal}
    wins = [x for x in trips if x["pnl"] > 0]
    total_real = sum(realized.values())
    total_unreal = sum(p["unrealized_pnl"] for p in positions.values())
    return {
        "fills": annotated,
        "positions": positions,
        "by_ticker": by_name,
        "round_trips": trips,
        "realized_pnl": total_real,
        "unrealized_pnl": total_unreal,
        "total_pnl": total_real + total_unreal,
        "n_round_trips": len(trips),
        "n_wins": len(wins),
        "win_rate": len(wins) / len(trips) if trips else None,
        "avg_win": sum(x["pnl"] for x in wins) / len(wins) if wins else None,
        "avg_loss": (sum(x["pnl"] for x in trips if x["pnl"] <= 0) / (len(trips) - len(wins))
                     if len(trips) > len(wins) else None),
    }


# --------------------------------------------------------------------------
# Configuration, limits, state
# --------------------------------------------------------------------------


@dataclass
class RiskLimits:
    max_weight: float = 0.40
    """No single name above this fraction of equity after a rebalance."""
    max_turnover: float = 0.50
    """Maximum one-way turnover per rebalance, as a fraction of equity:
    max(buys, sells), so cash counts and a first trade from all cash deploys
    at most this much."""
    max_drawdown: float = 0.25
    """Peak-to-trough equity loss that trips the kill switch."""
    min_history: int = 252
    """Bars required before the first fit; no trading until then."""
    min_cash_fraction: float = 0.0
    """Cash kept aside, as a fraction of equity."""


@dataclass
class EngineConfig:
    tickers: list[str]
    strategy: str = "cardinality"
    cardinality: int = 4
    risk_aversion: float = 2.0
    solver: str = "simulated_annealing"
    window: int = 252
    rebalance_every: int = 21
    """Bars between refits; 21 is roughly monthly on daily bars."""
    initial_cash: float = 100_000.0
    fee_rate: float = 0.0005
    limits: RiskLimits = field(default_factory=RiskLimits)
    state_path: str = "live_state.json"
    seed: int = 0
    trade_from: str | None = None
    """First date the engine may trade.  Earlier bars are warm-up: their
    prices feed the estimates, but no order is placed and the book stays
    in cash.  This is what keeps a bot started today from back-filling a
    year of trades it never made."""

    def __post_init__(self) -> None:
        self.tickers = [str(t) for t in self.tickers]
        if not self.tickers:
            raise ValueError("at least one ticker is required")
        if len(set(self.tickers)) != len(self.tickers):
            raise ValueError("duplicate tickers")
        if self.window < 3:
            raise ValueError("window must be at least 3 bars (a covariance needs three observations)")
        if self.rebalance_every < 1:
            raise ValueError("rebalance_every must be at least 1")
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if not 0.0 <= self.fee_rate < 1.0:
            raise ValueError("fee_rate must lie in [0, 1)")
        if self.strategy == "cardinality" and not 1 <= self.cardinality <= len(self.tickers):
            raise ValueError("cardinality must be between 1 and the number of tickers")

    @classmethod
    def from_dict(cls, data: dict) -> "EngineConfig":
        data = dict(data)
        limits = data.pop("limits", {}) or {}
        return cls(limits=RiskLimits(**limits), **data)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EngineState:
    """Everything needed to resume: the book, the history, the flags."""

    tickers: list[str]
    dates: list[str] = field(default_factory=list)
    prices: list[list[float]] = field(default_factory=list)
    cash: float = 0.0
    positions: dict[str, float] = field(default_factory=dict)
    equity_curve: list[float] = field(default_factory=list)
    peak_equity: float = 0.0
    last_rebalance_index: int = -1
    target_weights: dict[str, float] = field(default_factory=dict)
    halted: bool = False
    halt_reason: str = ""
    fills: list[dict] = field(default_factory=list)
    log: list[str] = field(default_factory=list)

    @property
    def n_bars(self) -> int:
        return len(self.dates)

    def save(self, path: str | Path) -> None:
        p = Path(path)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=1), encoding="utf-8")
        tmp.replace(p)  # atomic on POSIX: a crash mid-write leaves the old file

    @classmethod
    def load(cls, path: str | Path) -> "EngineState":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(**data)


# --------------------------------------------------------------------------
# Strategy factory
# --------------------------------------------------------------------------


def build_strategy(config: EngineConfig) -> Callable[[MarketData], np.ndarray]:
    if config.strategy == "equal_weight":
        return lambda market: equal_weight(market)
    if config.strategy == "markowitz":
        fn = markowitz_long_only(config.risk_aversion)
        return lambda market: fn(market)
    if config.strategy == "cardinality":
        fn = cardinality_strategy(config.cardinality, config.risk_aversion, config.solver, seed=config.seed) \
            if config.solver != "exhaustive" else cardinality_strategy(config.cardinality, config.risk_aversion, "exhaustive")
        return lambda market: fn(market)
    raise ValueError(f"unknown strategy {config.strategy!r}")


# --------------------------------------------------------------------------
# The engine
# --------------------------------------------------------------------------


class Engine:
    def __init__(self, config: EngineConfig, broker: Broker | None = None,
                 state: EngineState | None = None, strategy=None,
                 log: Callable[[str], None] | None = None) -> None:
        self.config = config
        self.limits = config.limits
        self.state = state or EngineState(tickers=list(config.tickers), cash=config.initial_cash)
        if self.state.tickers != list(config.tickers):
            raise ValueError("state file was written for a different ticker list")
        self.broker = broker or PaperBroker(self.state.cash, config.fee_rate, self.state.positions)
        self.strategy = strategy or build_strategy(config)
        self._log = log or (lambda line: None)

    # -- accounting --------------------------------------------------------
    def equity(self, bar: Bar) -> float:
        value = self.broker.cash()
        for ticker, qty in self.broker.positions().items():
            value += qty * bar.prices[ticker]
        return float(value)

    def weights(self, bar: Bar) -> dict[str, float]:
        eq = self.equity(bar)
        if eq <= 0:
            return {}
        return {t: q * bar.prices[t] / eq for t, q in self.broker.positions().items()}

    # -- one tick ----------------------------------------------------------
    def on_bar(self, bar: Bar) -> dict:
        st = self.state
        if st.dates and bar.date <= st.dates[-1]:
            return {"date": bar.date, "action": "duplicate", "equity": st.equity_curve[-1] if st.equity_curve else None}
        st.dates.append(bar.date)
        st.prices.append([bar.prices[t] for t in st.tickers])
        eq = self.equity(bar)
        st.equity_curve.append(eq)
        st.peak_equity = max(st.peak_equity, eq)
        drawdown = 1.0 - eq / st.peak_equity if st.peak_equity > 0 else 0.0
        event = {"date": bar.date, "equity": eq, "drawdown": drawdown, "action": "hold", "fills": []}

        if st.halted:
            event["action"] = "halted"
        elif drawdown >= self.limits.max_drawdown and self.broker.positions():
            fills = self._liquidate(bar, "kill_switch")
            st.halted = True
            st.target_weights = {}
            st.halt_reason = f"drawdown {drawdown:.1%} >= limit {self.limits.max_drawdown:.1%} on {bar.date}"
            event.update(action="kill_switch", fills=fills)
        elif self.config.trade_from and bar.date < self.config.trade_from:
            event["action"] = "warmup"
        elif st.n_bars >= max(self.limits.min_history, self.config.window) and (
            st.last_rebalance_index < 0 or st.n_bars - st.last_rebalance_index >= self.config.rebalance_every
        ):
            fills, targets, note = self._rebalance(bar)
            st.last_rebalance_index = st.n_bars
            st.target_weights = targets
            event.update(action="rebalance", fills=fills, targets=targets, note=note)

        st.cash = self.broker.cash()
        st.positions = self.broker.positions()
        st.fills.extend(asdict(f) for f in event["fills"])
        line = (f"{bar.date} equity={eq:,.2f} dd={drawdown:.1%} {event['action']}"
                + (f" fills={len(event['fills'])}" if event["fills"] else "")
                + (f" note={event['note']}" if event.get("note") else ""))
        st.log.append(line)
        st.log = st.log[-500:]
        self._log(line)
        event["fills"] = [asdict(f) for f in event["fills"]]
        return event

    def _market(self) -> MarketData:
        window = np.array(self.state.prices[-self.config.window:], dtype=np.float64)
        return MarketData(list(self.state.tickers), window)

    def _rebalance(self, bar: Bar) -> tuple[list[Fill], dict[str, float], str]:
        market = self._market()
        raw = np.clip(np.asarray(self.strategy(market), dtype=np.float64).reshape(-1), 0.0, None)
        if raw.sum() <= 0:
            return [], {}, "strategy returned no positions"
        target = raw / raw.sum()

        # Risk limit 1: per-name cap, renormalised.  Applied iteratively so
        # the cap holds after mass is redistributed.
        cap = self.limits.max_weight
        for _ in range(len(target)):
            over = target > cap
            if not over.any():
                break
            excess = float((target[over] - cap).sum())
            target[over] = cap
            under = ~over
            if under.any() and target[under].sum() > 0:
                target[under] += excess * target[under] / target[under].sum()
        investable = 1.0 - self.limits.min_cash_fraction
        target = target * investable

        # Risk limit 2: turnover cap, by shrinking the move toward the target.
        current = np.array([self.weights(bar).get(t, 0.0) for t in self.state.tickers])
        move = target - current
        # Cash is a holding too: it moves by -sum(move).  Counting it makes
        # this max(buys, sells) / equity, so going from all cash to fully
        # invested is 100% turnover, not 50%.
        turnover = float((np.abs(move).sum() + abs(move.sum())) / 2.0)
        note = ""
        if turnover > self.limits.max_turnover and turnover > 0:
            scale = self.limits.max_turnover / turnover
            target = current + move * scale
            note = f"turnover {turnover:.1%} capped to {self.limits.max_turnover:.1%}"

        eq = self.equity(bar)
        orders = []
        for i, ticker in enumerate(self.state.tickers):
            desired = target[i] * eq / bar.prices[ticker]
            held = self.broker.positions().get(ticker, 0.0)
            delta = desired - held
            if abs(delta * bar.prices[ticker]) >= 1.0:  # ignore sub-dollar dust
                orders.append(Order(ticker, float(delta)))
        fills = self.broker.submit(orders, bar)
        targets = {t: float(w) for t, w in zip(self.state.tickers, target) if w > 1e-9}
        return fills, targets, note

    def _liquidate(self, bar: Bar, reason: str) -> list[Fill]:
        orders = [Order(t, -q, reason) for t, q in self.broker.positions().items()]
        return self.broker.submit(orders, bar)

    # -- loop --------------------------------------------------------------
    def run(self, feed: PriceFeed, once: bool = False, state_path: str | Path | None = None) -> list[dict]:
        path = Path(state_path or self.config.state_path)
        events: list[dict] = []
        for bar in feed.bars():
            missing = [t for t in self.state.tickers if t not in bar.prices]
            if missing:
                self._log(f"{bar.date} skipped: missing {missing}")
                continue
            event = self.on_bar(bar)
            if event["action"] == "duplicate":
                continue  # already in the state; not a tick
            events.append(event)
            self.state.save(path)
            if once:
                break
        return events

    def summary(self) -> str:
        st = self.state
        if not st.equity_curve:
            return "no bars processed"
        eq = np.array(st.equity_curve)
        total = eq[-1] / eq[0] - 1.0
        years = max(len(eq) / 252.0, 1e-9)
        peak = np.maximum.accumulate(eq)
        dd = float(np.max(1.0 - eq / peak))
        lines = [
            f"bars            : {st.n_bars} ({st.dates[0]} to {st.dates[-1]})",
            f"equity          : {eq[0]:,.2f} -> {eq[-1]:,.2f} ({total:+.2%}, {((1+total)**(1/years)-1):+.2%}/yr)",
            f"max drawdown    : {dd:.1%}",
            f"fills           : {len(st.fills)}, fees paid {sum(f['fee'] for f in st.fills):,.2f}",
            f"halted          : {st.halted}" + (f" ({st.halt_reason})" if st.halted else ""),
            "positions       : " + (", ".join(f"{t} {w:.1%}" for t, w in sorted(st.target_weights.items(), key=lambda kv: -kv[1])) or "none"),
        ]
        if st.fills:
            led = trade_ledger(st.fills, dict(zip(st.tickers, st.prices[-1])))
            lines.append(f"gains/losses    : realized {led['realized_pnl']:+,.2f}, unrealized {led['unrealized_pnl']:+,.2f}"
                         f", total {led['total_pnl']:+,.2f}")
            if led["n_round_trips"]:
                lines.append(f"round trips     : {led['n_round_trips']} closed, {led['n_wins']} won ({led['win_rate']:.0%})")
        return "\n".join(lines)


# --------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------


def snapshot(engine: "Engine", max_points: int = 1500, price_days: int = 600) -> tuple[dict, dict]:
    """The bot's state as two JSON documents for the dashboard.

    ``status`` is what a person looks at: the book, the equity curve from
    the first tradable bar, recent fills and log.  ``prices`` is the price
    history the engine has seen, so the dashboard can re-run the same
    engine in the browser and check that it lands on the same number.
    """
    st, cfg = engine.state, engine.config
    start = 0
    if cfg.trade_from:
        start = next((i for i, d in enumerate(st.dates) if d >= cfg.trade_from), len(st.dates))
    dates, curve = st.dates[start:], st.equity_curve[start:]
    step = max(1, len(curve) // max_points)
    idx = list(range(0, len(curve), step))
    if curve and idx[-1] != len(curve) - 1:
        idx.append(len(curve) - 1)
    last_prices = dict(zip(st.tickers, st.prices[-1])) if st.prices else {}
    equity = st.equity_curve[-1] if st.equity_curve else cfg.initial_cash
    ledger = trade_ledger(st.fills, last_prices)
    status = {
        "schema": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "paper",
        "config": cfg.to_dict(),
        "last_date": st.dates[-1] if st.dates else None,
        "bars_seen": st.n_bars,
        "live_bars": len(dates),
        "equity": equity,
        "cash": st.cash,
        "peak_equity": st.peak_equity,
        "positions": st.positions,
        "last_prices": last_prices,
        "target_weights": st.target_weights,
        "halted": st.halted,
        "halt_reason": st.halt_reason,
        "curve_dates": [dates[i] for i in idx],
        "curve": [curve[i] for i in idx],
        "fills": ledger["fills"][-60:],
        "pnl": {k: v for k, v in ledger.items() if k not in ("fills", "round_trips")}
               | {"round_trips": ledger["round_trips"][-60:]},
        "n_fills": len(st.fills),
        "fees": sum(f.get("fee", 0.0) for f in st.fills),
        "log": st.log[-60:],
    }
    keep = max(0, st.n_bars - price_days)
    prices = {
        "schema": 1,
        "tickers": st.tickers,
        "dates": st.dates[keep:],
        "prices": st.prices[keep:],
        "offset": keep,
        "full_history": keep == 0,
    }
    return status, prices


def load_config(path: str | Path) -> EngineConfig:
    return EngineConfig.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def run(config: EngineConfig, feed: PriceFeed, broker: Broker | None = None,
        once: bool = False, resume: bool = True, log: Callable[[str], None] | None = None) -> Engine:
    """Build (or resume) an engine, run it over the feed, return it."""
    path = Path(config.state_path)
    state = EngineState.load(path) if resume and path.exists() else None
    engine = Engine(config, broker=broker, state=state, log=log)
    engine.run(feed, once=once, state_path=path)
    return engine
