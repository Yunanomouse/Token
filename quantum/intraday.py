"""A paper backtester for minute-bar day trading with Kaufman's adaptive average.

This is built for one specific, very common style and nothing else: pick the
most volatile stocks of the day, go long when the Kaufman Adaptive Moving
Average (KAMA) turns up by more than its noise filter, get out when it turns
down by the same amount, hold for minutes, be flat by the close, and do all of
it in a small cash account that buys whole shares only.  The point is to test
that style *honestly* -- with the frictions a $50 account actually faces --
and to compare it with random entries under exactly the same conditions.

What it is, precisely
---------------------
* **The indicator** is Perry Kaufman's, as published in *Smarter Trading*
  (1995) and *Trading Systems and Methods*:

  - efficiency ratio ``ER_t = |C_t - C_{t-n}| / sum_{i=t-n+1..t} |C_i - C_{i-1}|``
  - smoothing constant ``sc_t = (ER_t * (2/(fast+1) - 2/(slow+1)) + 2/(slow+1))**2``
  - ``KAMA_t = KAMA_{t-1} + sc_t * (C_t - KAMA_{t-1})``, seeded with
    ``KAMA_n = C_n``.

  Defaults ``n=10, fast=2, slow=30`` are Kaufman's.  KAMA runs continuously
  per ticker across days, as it does on a chart, so each morning starts with
  a warmed-up average built from prior sessions only.

* **The signal** is Kaufman's filter rule.  ``filter_t = k * std(dKAMA)`` over
  the last ``filter_n`` one-bar KAMA changes.  Go long when
  ``KAMA_t - min(KAMA over the last lookback bars) > filter_t``; exit when
  ``max(KAMA since entry) - KAMA_t > filter_t``.  Long only: a cash account
  cannot short.

* **The screen** ranks, each morning, the tickers by the *previous* sessions'
  (high - low) / close range and keeps the top ``top_n`` whose last prior
  close lets at least one whole share fit the position budget.  Nothing
  from the current session is used.

* **Execution** is deliberately unflattering.  A signal on bar ``t``'s close
  fills at bar ``t+1``'s *open*, moved against you by ``slippage_bps``.  Stops
  are checked on the bar's low and fill at ``min(stop, open)`` so a gap is
  taken in full.  Everything is closed at the first bar at or after
  ``flat_by``; nothing is held overnight.  Shares are floored to whole
  numbers, cash never goes negative, and -- by default -- the proceeds of a
  sale are unsettled until the next session (T+1), so a small account cannot
  recycle the same dollars into trade after trade in one day.

* **The baseline** (:func:`random_baseline`) takes the strategy's trades and
  replays the same number of entries per day, with holding times drawn from
  the strategy's own, at random times on random screened tickers, through the
  same engine, costs and rules.  If the KAMA signal cannot beat that, it has
  no edge.

What it is not
--------------
It is not a live trading tool, and it does not predict anything.  At $50 with
whole shares the minimum trade is one share of whatever you can afford, and
10 bps per side of slippage is often optimistic on the most volatile names.
Read the baseline comparison before reading the return.

Running it
----------
::

    from quantum.intraday import IntradayConfig, load_bars, backtest, random_baseline
    bars = load_bars("data/intraday/bars.csv")
    cfg = IntradayConfig()
    res = backtest(bars, cfg)
    base = random_baseline(bars, cfg, res["trades"], seed=0)
    print(res["summary"], base["summary"], sep="\\n")
"""

from __future__ import annotations

import csv
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

__all__ = [
    "IntradayConfig",
    "load_bars",
    "efficiency_ratio",
    "kama",
    "kaufman_filter",
    "kama_signals",
    "daily_ranges",
    "volatility_screen",
    "backtest",
    "random_baseline",
    "summarize",
]

_FIELDS = ("open", "high", "low", "close", "volume")


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------


def load_bars(path: str | Path) -> dict[str, dict[str, np.ndarray]]:
    """Read a long CSV of minute bars into per-ticker arrays.

    The file has columns ``datetime,ticker,open,high,low,close,volume`` with
    ``datetime`` like ``2026-09-23 09:31:00`` (New York time, regular session
    only).  Returns ``{ticker: {"datetime": str array, "open": float array,
    ..., "volume": float array}}``, each ticker sorted by time.
    """
    rows: dict[str, list[tuple]] = {}
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        missing = {"datetime", "ticker", *_FIELDS} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path}: missing columns {sorted(missing)}")
        for r in reader:
            try:
                vals = tuple(float(r[f]) for f in _FIELDS)
            except (TypeError, ValueError):
                continue
            rows.setdefault(r["ticker"].strip(), []).append((r["datetime"].strip(), *vals))
    return {t: _to_arrays(sorted(rs, key=lambda x: x[0])) for t, rs in rows.items()}


def _to_arrays(rows: Sequence[tuple]) -> dict[str, np.ndarray]:
    out = {"datetime": np.array([r[0] for r in rows], dtype=str)}
    for j, f in enumerate(_FIELDS, start=1):
        out[f] = np.array([r[j] for r in rows], dtype=float)
    return out


# --------------------------------------------------------------------------
# Kaufman's adaptive moving average
# --------------------------------------------------------------------------


def efficiency_ratio(close: np.ndarray, n: int = 10) -> np.ndarray:
    """Kaufman's efficiency ratio: net move over n bars divided by path length.

    ``ER_t = |C_t - C_{t-n}| / sum |C_i - C_{i-1}|`` over the ``n`` one-bar
    changes ending at ``t``.  1 on a straight line, near 0 in pure noise, and
    defined as 0 when the window has no movement at all.  ``NaN`` for
    ``t < n``.  Causal: ``ER_t`` uses only ``C_{t-n} .. C_t``.
    """
    c = np.asarray(close, dtype=float)
    if n < 1:
        raise ValueError("n must be at least 1")
    er = np.full(c.shape, np.nan)
    if c.size <= n:
        return er
    change = np.abs(c[n:] - c[:-n])
    vol = np.lib.stride_tricks.sliding_window_view(np.abs(np.diff(c)), n).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        er[n:] = np.where(vol > 0, change / np.where(vol > 0, vol, 1.0), 0.0)
    return er


def kama(close: np.ndarray, n: int = 10, fast: int = 2, slow: int = 30) -> np.ndarray:
    """Kaufman Adaptive Moving Average.

    ``sc_t = (ER_t * (2/(fast+1) - 2/(slow+1)) + 2/(slow+1))**2`` and
    ``KAMA_t = KAMA_{t-1} + sc_t * (C_t - KAMA_{t-1})``, seeded with
    ``KAMA_n = C_n``; earlier values are ``NaN``.  Causal.
    """
    if not 1 <= fast < slow:
        raise ValueError("need 1 <= fast < slow")
    c = np.asarray(close, dtype=float)
    out = np.full(c.shape, np.nan)
    if c.size <= n:
        return out
    fast_sc, slow_sc = 2.0 / (fast + 1), 2.0 / (slow + 1)
    sc = (efficiency_ratio(c, n) * (fast_sc - slow_sc) + slow_sc) ** 2
    k = c[n]
    out[n] = k
    for t in range(n + 1, c.size):
        k = k + sc[t] * (c[t] - k)
        out[t] = k
    return out


def kaufman_filter(ama: np.ndarray, filter_n: int = 20, k: float = 0.5) -> np.ndarray:
    """Kaufman's noise filter: ``k`` times the rolling (population) standard
    deviation of the last ``filter_n`` one-bar changes in the average.

    ``NaN`` until ``filter_n`` valid changes exist.  Causal.
    """
    a = np.asarray(ama, dtype=float)
    out = np.full(a.shape, np.nan)
    if a.size <= filter_n:
        return out
    d = np.diff(a)  # d[j] = a[j+1] - a[j]
    win = np.lib.stride_tricks.sliding_window_view(d, filter_n)
    out[filter_n:] = k * win.std(axis=1)  # NaN windows stay NaN
    return out


def _rolling_min(a: np.ndarray, w: int) -> np.ndarray:
    out = np.full(a.shape, np.nan)
    if a.size >= w:
        out[w - 1:] = np.lib.stride_tricks.sliding_window_view(a, w).min(axis=1)
    return out


def kama_signals(close: np.ndarray, config: "IntradayConfig") -> dict[str, np.ndarray]:
    """Per-bar arrays for one ticker: ``kama``, ``filter``, and ``entry``
    (bool: ``KAMA - min(KAMA, lookback) > filter``).  The exit rule depends
    on the entry bar and is evaluated inside the backtest."""
    a = kama(close, config.kama_n, config.kama_fast, config.kama_slow)
    f = kaufman_filter(a, config.filter_n, config.filter_k)
    lo = _rolling_min(a, config.entry_lookback)
    with np.errstate(invalid="ignore"):
        entry = (a - lo) > f
    return {"kama": a, "filter": f, "entry": entry & ~np.isnan(f) & ~np.isnan(lo)}


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


@dataclass
class IntradayConfig:
    cash: float = 50.0
    deploy_fraction: float = 0.7
    """Share of current equity put into a position (the owner uses 60-80%)."""
    max_positions: int = 1
    whole_shares: bool = True
    slippage_bps: float = 10.0
    """Per side, always against you: buys fill higher, sells lower."""
    commission: float = 0.0
    """Flat fee per order (each side)."""
    max_trades_per_day: int = 6
    """Round trips (entries) per session."""
    stop_loss_pct: float | None = None
    """Optional hard stop, as a fraction below the entry fill, checked on
    each bar's low and filled at ``min(stop, open)``."""
    flat_by: str = "15:55"
    """Close everything at the first bar at or after this time."""
    no_entry_after: str = "15:30"
    """No entry signal is acted on from a bar at or after this time."""
    settled_cash_only: bool = True
    """Cash account, T+1: sale proceeds cannot be reused until the next
    session."""
    kama_n: int = 10
    kama_fast: int = 2
    kama_slow: int = 30
    filter_n: int = 20
    filter_k: float = 0.5
    entry_lookback: int = 3
    """Bars over which the KAMA low (entry) is taken."""
    top_n: int = 5
    screen_days: int = 1
    """Prior sessions averaged for the volatility ranking."""
    strategy: str = "kama"
    """``kama``: Kaufman's filter rule.  ``orb``: opening-range breakout
    (Zarattini, Barbon & Aziz 2024): buy when a bar closes above the first
    bar's high, if the first bar closed up; exit on the stop or at the end
    of the day."""
    screen: str = "range"
    """``range``: prior-day (high - low) / close.  ``rvol``: relative volume
    of today's first bar against its average over ``rvol_days`` prior
    sessions ("stocks in play"); needs the first bar to have closed."""
    rvol_days: int = 14
    min_rvol: float = 1.0
    min_price: float = 0.0
    """Prior close at least this (the ORB paper uses $5)."""
    min_atr: float = 0.0
    """Daily ATR over ``rvol_days`` sessions at least this, in dollars."""
    min_avg_volume: float = 0.0
    """Average daily shares over ``rvol_days`` sessions at least this."""
    stop_atr_mult: float | None = None
    """Stop this many daily ATRs below the entry fill (the ORB paper: 0.10)."""
    er_min: float | None = None
    """KAMA entries only when the efficiency ratio is above this."""
    vwap_filter: bool = False
    """KAMA entries only above the session VWAP; exit on a close below it."""
    trade_from: str | None = None
    """First session (``YYYY-MM-DD``) the account trades.  Earlier sessions
    only warm up the KAMA and feed the volatility screen."""

    def __post_init__(self) -> None:
        if self.cash <= 0:
            raise ValueError("cash must be positive")
        if not 0.0 < self.deploy_fraction <= 1.0:
            raise ValueError("deploy_fraction must lie in (0, 1]")
        if self.max_positions < 1 or self.max_trades_per_day < 0 or self.top_n < 1:
            raise ValueError("max_positions and top_n must be >= 1, max_trades_per_day >= 0")
        if self.slippage_bps < 0 or self.commission < 0:
            raise ValueError("slippage_bps and commission must be non-negative")
        if self.stop_loss_pct is not None and not 0.0 < self.stop_loss_pct < 1.0:
            raise ValueError("stop_loss_pct must lie in (0, 1)")
        if self.entry_lookback < 1 or self.filter_n < 2 or self.screen_days < 1:
            raise ValueError("entry_lookback >= 1, filter_n >= 2, screen_days >= 1")
        if not 1 <= self.kama_fast < self.kama_slow or self.kama_n < 1:
            raise ValueError("need kama_n >= 1 and 1 <= kama_fast < kama_slow")
        if self.strategy not in ("kama", "orb") or self.screen not in ("range", "rvol"):
            raise ValueError("strategy must be kama or orb; screen must be range or rvol")
        if self.stop_atr_mult is not None and self.stop_atr_mult <= 0:
            raise ValueError("stop_atr_mult must be positive")

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------
# Volatility screen
# --------------------------------------------------------------------------


def daily_ranges(bars: dict[str, dict[str, np.ndarray]]) -> dict[str, dict[str, tuple[float, float]]]:
    """``{ticker: {date: ((high - low) / close, close)}}`` per session, using
    that session's high, low and last close."""
    out: dict[str, dict[str, tuple[float, float]]] = {}
    for t, b in bars.items():
        dates = np.array([d[:10] for d in b["datetime"]])
        per: dict[str, tuple[float, float]] = {}
        if dates.size:
            starts = np.flatnonzero(np.r_[True, dates[1:] != dates[:-1]])
            ends = np.r_[starts[1:], dates.size]
            for s, e in zip(starts, ends):
                c = b["close"][e - 1]
                rng = (b["high"][s:e].max() - b["low"][s:e].min()) / c if c > 0 else 0.0
                per[str(dates[s])] = (float(rng), float(c))
        out[t] = per
    return out


def volatility_screen(ranges: dict[str, dict[str, tuple[float, float]]], date: str, budget: float,
                      top_n: int = 5, screen_days: int = 1, slippage_bps: float = 0.0,
                      commission: float = 0.0, tradable: set[str] | None = None) -> list[str]:
    """Tickers for ``date``, most volatile first, using prior sessions only.

    Each ticker is scored by its mean (high - low) / close range over its last
    ``screen_days`` sessions strictly before ``date``.  A ticker qualifies if
    its last prior close (plus slippage and commission) fits one whole share
    in ``budget``; the top ``top_n`` qualifiers are returned.  ``tradable``
    optionally restricts to tickers that have bars on ``date``.
    """
    scored = []
    for t, per in ranges.items():
        if tradable is not None and t not in tradable:
            continue
        prior = sorted(d for d in per if d < date)[-screen_days:]
        if not prior:
            continue
        last_close = per[prior[-1]][1]
        if last_close * (1 + slippage_bps / 1e4) + commission > budget:
            continue
        scored.append((-float(np.mean([per[d][0] for d in prior])), t))
    scored.sort()
    return [t for _, t in scored[:top_n]]


def daily_stats(bars: dict[str, dict[str, np.ndarray]], days: int = 14) -> dict[str, dict[str, dict]]:
    """Per ticker and session: the first bar (``first_open``, ``first_high``,
    ``first_close``, ``first_volume``), and from the ``days`` sessions strictly
    before it, ``atr`` (mean true range), ``avg_volume`` (daily shares),
    ``avg_first_volume``, ``prev_close`` and ``rvol`` (today's first-bar
    volume over ``avg_first_volume``)."""
    out: dict[str, dict[str, dict]] = {}
    for t, b in bars.items():
        dates = np.array([d[:10] for d in b["datetime"]])
        per: dict[str, dict] = {}
        if not dates.size:
            out[t] = per
            continue
        starts = np.flatnonzero(np.r_[True, dates[1:] != dates[:-1]])
        ends = np.r_[starts[1:], dates.size]
        rows = []
        for s, e in zip(starts, ends):
            rows.append((str(dates[s]), float(b["open"][s]), float(b["high"][s]), float(b["close"][s]),
                         float(b["volume"][s]), float(b["high"][s:e].max()), float(b["low"][s:e].min()),
                         float(b["close"][e - 1]), float(b["volume"][s:e].sum())))
        for k, (d, fo, fh, fc, fv, hi, lo, cl, vol) in enumerate(rows):
            prior = rows[max(0, k - days):k]
            info = {"first_open": fo, "first_high": fh, "first_close": fc, "first_volume": fv}
            if prior:
                trs = []
                for j, r in enumerate(prior):
                    pc = rows[k - len(prior) + j - 1][7] if k - len(prior) + j - 1 >= 0 else r[7]
                    trs.append(max(r[5] - r[6], abs(r[5] - pc), abs(r[6] - pc)))
                afv = float(np.mean([r[4] for r in prior]))
                info.update(atr=float(np.mean(trs)), avg_volume=float(np.mean([r[8] for r in prior])),
                            avg_first_volume=afv, prev_close=prior[-1][7],
                            rvol=fv / afv if afv > 0 else 0.0, n_prior=len(prior))
            per[d] = info
        out[t] = per
    return out


def rvol_screen(stats: dict[str, dict[str, dict]], date: str, budget: float, config: "IntradayConfig",
                tradable: set[str] | None = None) -> list[str]:
    """"Stocks in play" for ``date``: highest relative volume of the first bar,
    among names with a full ``rvol_days`` history, ``rvol >= min_rvol``, a
    prior close >= ``min_price``, ATR >= ``min_atr``, average volume >=
    ``min_avg_volume``, and one whole share affordable in ``budget``."""
    c = config
    scored = []
    for t, per in stats.items():
        if tradable is not None and t not in tradable:
            continue
        s = per.get(date)
        if not s or s.get("n_prior", 0) < c.rvol_days:
            continue
        if (s["rvol"] < c.min_rvol or s["prev_close"] < c.min_price or s["atr"] < c.min_atr
                or s["avg_volume"] < c.min_avg_volume):
            continue
        if s["prev_close"] * (1 + c.slippage_bps / 1e4) + c.commission > budget:
            continue
        scored.append((-s["rvol"], t))
    scored.sort()
    return [t for _, t in scored[:c.top_n]]


def session_vwap(b: dict[str, np.ndarray]) -> np.ndarray:
    """Volume-weighted average of the typical price, reset each session."""
    tp = (b["high"] + b["low"] + b["close"]) / 3.0
    v = b["volume"].astype(float)
    out = np.empty(tp.size)
    dates = np.array([d[:10] for d in b["datetime"]])
    if not dates.size:
        return out
    starts = np.flatnonzero(np.r_[True, dates[1:] != dates[:-1]])
    for s, e in zip(starts, np.r_[starts[1:], dates.size]):
        cv = np.cumsum(v[s:e])
        ctp = np.cumsum(tp[s:e] * v[s:e])
        out[s:e] = np.where(cv > 0, ctp / np.where(cv > 0, cv, 1), tp[s:e])
    return out


def resample(bars: dict[str, dict[str, np.ndarray]], minutes: int) -> dict[str, dict[str, np.ndarray]]:
    """Aggregate bars into ``minutes``-long bars, labelled by their start time."""
    out = {}
    for t, b in bars.items():
        keys = []
        for d in b["datetime"]:
            m = (int(d[11:13]) * 60 + int(d[14:16]) - 570) // minutes * minutes + 570
            keys.append(f"{d[:10]} {m // 60:02d}:{m % 60:02d}:00")
        keys = np.array(keys)
        if not keys.size:
            out[t] = {k: v[:0] for k, v in b.items()}
            continue
        starts = np.flatnonzero(np.r_[True, keys[1:] != keys[:-1]])
        ends = np.r_[starts[1:], keys.size]
        out[t] = {
            "datetime": keys[starts],
            "open": b["open"][starts],
            "high": np.maximum.reduceat(b["high"], starts),
            "low": np.minimum.reduceat(b["low"], starts),
            "close": b["close"][ends - 1],
            "volume": np.add.reduceat(b["volume"], starts),
        }
    return out


# --------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------


class _KamaPolicy:
    """Kaufman's filter rule on precomputed per-ticker arrays."""

    def __init__(self, bars, config):
        self.sig = {t: kama_signals(b["close"], config) for t, b in bars.items()}
        self.close = {t: b["close"] for t, b in bars.items()}
        self.er = ({t: efficiency_ratio(b["close"], config.kama_n) for t, b in bars.items()}
                   if config.er_min is not None else None)
        self.vwap = {t: session_vwap(b) for t, b in bars.items()} if config.vwap_filter else None
        self.er_min = config.er_min

    def start_day(self, date, screen, times, trades_today_cap):
        pass

    def want_entry(self, ticker, i, time):
        ok = bool(self.sig[ticker]["entry"][i])
        if ok and self.er is not None:
            ok = bool(self.er[ticker][i] > self.er_min)
        if ok and self.vwap is not None:
            ok = bool(self.close[ticker][i] > self.vwap[ticker][i])
        return ok, {}

    def want_exit(self, ticker, i, pos):
        if self.vwap is not None and self.close[ticker][i] < self.vwap[ticker][i]:
            return True
        s = self.sig[ticker]
        a, f = s["kama"][i], s["filter"][i]
        if np.isnan(a):
            return False
        pos["peak"] = a if pos.get("peak") is None else max(pos["peak"], a)
        return not np.isnan(f) and pos["peak"] - a > f


class _OrbPolicy:
    """Opening-range breakout, long only: the first bar of the session is the
    range; if it closed up, buy after a later bar closes above its high.
    Once per ticker per day.  Exits come from the stop and the end of day."""

    def __init__(self, bars, config):
        self.bars = bars
        self.day: dict[str, tuple[int, float, bool]] = {}
        self.done: set[str] = set()

    def start_day(self, date, screen, times, trades_today_cap):
        self.day, self.done = {}, set()
        for t, b in self.bars.items():
            idx = np.flatnonzero(np.char.startswith(b["datetime"].astype(str), date))
            if idx.size:
                s = int(idx[0])
                self.day[t] = (s, float(b["high"][s]), bool(b["close"][s] > b["open"][s]))

    def want_entry(self, ticker, i, time):
        if ticker in self.done or ticker not in self.day:
            return False, {}
        s, hi, up = self.day[ticker]
        if i > s and up and self.bars[ticker]["close"][i] > hi:
            self.done.add(ticker)
            return True, {}
        return False, {}

    def want_exit(self, ticker, i, pos):
        return False


class _RandomPolicy:
    """Same count of entries per day and same holding-time distribution as a
    given set of trades, at random times on random screened tickers."""

    def __init__(self, trades, config, seed):
        self.rng = np.random.default_rng(seed)
        self.per_day: dict[str, int] = {}
        for tr in trades:
            d = tr["entry_time"][:10]
            self.per_day[d] = self.per_day.get(d, 0) + 1
        self.holds = np.array([max(1, int(tr.get("bars_held", 1))) for tr in trades] or [1])
        self.no_entry_after = config.no_entry_after
        self.queue: list[tuple[str, str, int]] = []

    def start_day(self, date, screen, times, trades_today_cap):
        k = self.per_day.get(date, 0)
        ok = [t for t in times if t[11:16] < self.no_entry_after]
        self.queue = []
        if k and screen and ok:
            when = sorted(self.rng.choice(len(ok), size=k, replace=len(ok) < k))
            who = self.rng.integers(0, len(screen), size=k)
            hold = self.rng.choice(self.holds, size=k)
            self.queue = [(ok[w], screen[j], int(h)) for w, j, h in zip(when, who, hold)]

    def want_entry(self, ticker, i, time):
        if self.queue and self.queue[0][0] <= time and self.queue[0][1] == ticker:
            _, _, h = self.queue.pop(0)
            return True, {"hold": h}
        return False, {}

    def want_exit(self, ticker, i, pos):
        return i - pos["entry_idx"] >= pos["meta"]["hold"] - 1


def _simulate(bars, config: IntradayConfig, policy, open_session: bool = False) -> dict:
    cfg = config
    slip = cfg.slippage_bps / 1e4
    ranges = daily_ranges(bars)
    stats = daily_stats(bars, cfg.rvol_days) if (cfg.screen == "rvol" or cfg.stop_atr_mult) else {}
    index = {t: {d: i for i, d in enumerate(b["datetime"])} for t, b in bars.items()}
    by_date: dict[str, set[str]] = {}
    for t, b in bars.items():
        for d in b["datetime"]:
            by_date.setdefault(d[:10], set()).add(str(d))
    last_of_day: dict[str, dict[str, int]] = {}
    for t, b in bars.items():
        ld: dict[str, int] = {}
        for i, d in enumerate(b["datetime"]):
            ld[d[:10]] = i
        last_of_day[t] = ld

    settled, unsettled = float(cfg.cash), 0.0
    positions: dict[str, dict] = {}
    trades: list[dict] = []
    equity_curve: list[dict] = []
    total_steps = invested_steps = 0
    in_use_frac: list[float] = []
    in_use_dollars: list[float] = []

    def equity_now():
        return settled + unsettled + sum(p["shares"] * p["last"] for p in positions.values())

    def close_pos(t, i, price, reason):
        nonlocal settled, unsettled
        p = positions.pop(t)
        fill = price * (1 - slip)
        proceeds = p["shares"] * fill - cfg.commission
        if cfg.settled_cash_only:
            unsettled += proceeds
        else:
            settled += proceeds
        pnl = proceeds - p["cost"]
        trades.append({
            "ticker": t, "entry_time": p["entry_time"], "entry_price": p["entry_price"],
            "exit_time": str(bars[t]["datetime"][i]), "exit_price": float(fill), "shares": p["shares"],
            "pnl": float(pnl), "pnl_pct": float(pnl / p["cost"]) if p["cost"] else 0.0, "reason": reason,
            "bars_held": int(i - p["entry_idx"]),
        })

    dates = [d for d in sorted(by_date) if not cfg.trade_from or d >= cfg.trade_from]
    for date in dates:
        still_open = open_session and date == dates[-1]
        settled += unsettled
        unsettled = 0.0
        times = sorted(by_date[date])
        eq0 = equity_now()
        tradable = {t for t in bars if date in last_of_day[t]}
        if cfg.screen == "rvol":
            screen = rvol_screen(stats, date, cfg.deploy_fraction * eq0, cfg, tradable)
        else:
            screen = volatility_screen(ranges, date, cfg.deploy_fraction * eq0, cfg.top_n, cfg.screen_days,
                                       cfg.slippage_bps, cfg.commission, tradable=tradable)
        policy.start_day(date, screen, times, cfg.max_trades_per_day)
        pending: dict[str, tuple[str, dict]] = {}
        entries = 0

        for now in times:
            hm = now[11:16]
            live = [(t, index[t][now]) for t in screen if now in index[t]]
            # 1. exits at the open: end of day, then signalled exits.
            for t, i in live:
                if t not in positions:
                    continue
                if hm >= cfg.flat_by:
                    pending.pop(t, None)
                    close_pos(t, i, bars[t]["open"][i], "eod")
                elif pending.get(t, ("",))[0] == "sell":
                    pending.pop(t)
                    close_pos(t, i, bars[t]["open"][i], "signal")
            # 2. entries at the open.
            for t, i in live:
                if pending.get(t, ("",))[0] != "buy":
                    continue
                _, meta = pending.pop(t)
                if hm >= cfg.flat_by or t in positions:
                    continue
                fill = bars[t]["open"][i] * (1 + slip)
                spend = min(cfg.deploy_fraction * equity_now(), settled) - cfg.commission
                shares = spend / fill if spend > 0 else 0.0
                if cfg.whole_shares:
                    shares = float(math.floor(shares + 1e-12))
                if shares <= 0 or (cfg.whole_shares and shares < 1):
                    continue
                fill = float(fill)
                cost = shares * fill + cfg.commission
                settled = max(0.0, settled - cost)
                entries += 1
                positions[t] = {
                    "shares": shares, "entry_price": fill, "cost": cost, "entry_idx": i,
                    "entry_time": now, "last": float(bars[t]["close"][i]), "peak": None, "meta": meta,
                    "stop": _stop_price(cfg, stats, t, date, fill),
                }
            # 3. intrabar stop, forced close on the last bar, signals on the close.
            for t, i in live:
                b = bars[t]
                if t in positions:
                    p = positions[t]
                    if p["stop"] is not None and b["low"][i] <= p["stop"]:
                        pending.pop(t, None)
                        close_pos(t, i, min(p["stop"], b["open"][i]), "stop")
                        continue
                    p["last"] = float(b["close"][i])
                    if i == last_of_day[t][date] and not still_open:
                        pending.pop(t, None)
                        close_pos(t, i, b["close"][i], "eod")
                        continue
                    if t not in pending and hm < cfg.flat_by and policy.want_exit(t, i, p):
                        pending[t] = ("sell", {})
                elif (t not in pending and hm < cfg.no_entry_after and (still_open or i != last_of_day[t][date])
                      and entries + sum(1 for v in pending.values() if v[0] == "buy") < cfg.max_trades_per_day
                      and len(positions) + sum(1 for v in pending.values() if v[0] == "buy") < cfg.max_positions):
                    want, meta = policy.want_entry(t, i, now)
                    if want:
                        pending[t] = ("buy", meta)
            total_steps += 1
            if positions:
                invested_steps += 1
                val = sum(p["shares"] * p["last"] for p in positions.values())
                in_use_dollars.append(val)
                in_use_frac.append(val / equity_now())

        if still_open:
            break
        for t in list(positions):  # safety net: never hold overnight
            close_pos(t, last_of_day[t][date], bars[t]["close"][last_of_day[t][date]], "eod")
        equity_curve.append({"date": date, "equity": float(equity_now())})

    open_positions = []
    if open_session and dates:
        for t, p in positions.items():
            open_positions.append({
                "ticker": t, "shares": p["shares"], "entry_time": p["entry_time"],
                "entry_price": p["entry_price"], "last": p["last"],
                "unrealized": float(p["shares"] * p["last"] * (1 - slip) - p["cost"]),
                "exit_pending": pending.get(t, ("",))[0] == "sell",
            })
        equity_curve.append({"date": dates[-1], "equity": float(equity_now())})

    summary = summarize(trades, equity_curve, cfg.cash)
    summary.update({
        "avg_capital_in_use": float(np.mean(in_use_frac)) if in_use_frac else 0.0,
        "avg_capital_in_use_dollars": float(np.mean(in_use_dollars)) if in_use_dollars else 0.0,
        "time_invested_fraction": invested_steps / total_steps if total_steps else 0.0,
    })
    result = {"trades": trades, "equity": equity_curve, "summary": summary, "config": cfg.to_dict()}
    if open_session:
        result["open"] = {
            "positions": open_positions,
            "pending_buys": [t for t, v in pending.items() if v[0] == "buy"],
            "cash_settled": float(settled), "cash_unsettled": float(unsettled),
            "entries_today": entries if dates else 0,
            "screen": list(screen) if dates else [],
        }
    return result


def _stop_price(cfg: IntradayConfig, stats: dict, ticker: str, date: str, fill: float) -> float | None:
    stops = []
    if cfg.stop_loss_pct:
        stops.append(fill * (1 - cfg.stop_loss_pct))
    atr = stats.get(ticker, {}).get(date, {}).get("atr") if cfg.stop_atr_mult else None
    if atr:
        stops.append(fill - cfg.stop_atr_mult * atr)
    return max(stops) if stops else None


def _max_drawdown(values: Sequence[float]) -> float:
    v = np.asarray(values, dtype=float)
    if v.size == 0:
        return 0.0
    peak = np.maximum.accumulate(v)
    return float(np.max((peak - v) / peak))


def summarize(trades: Sequence[dict], equity_curve: Sequence[dict], cash: float) -> dict:
    """Headline statistics for a list of trades and a daily equity curve."""
    pnl = np.array([t["pnl"] for t in trades], dtype=float)
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    final = equity_curve[-1]["equity"] if equity_curve else cash
    days = len(equity_curve)
    gross_loss = -losses.sum()
    return {
        "initial_equity": cash,
        "final_equity": final,
        "total_return": float(final / cash - 1.0),
        "n_trades": int(pnl.size),
        "n_days": days,
        "trades_per_day": float(pnl.size / days) if days else 0.0,
        "win_rate": float(wins.size / pnl.size) if pnl.size else None,
        "avg_win": float(wins.mean()) if wins.size else None,
        "avg_loss": float(losses.mean()) if losses.size else None,
        "avg_pnl_pct": float(np.mean([t["pnl_pct"] for t in trades])) if trades else None,
        "profit_factor": (float(wins.sum() / gross_loss) if gross_loss > 0
                          else (math.inf if wins.size else None)),
        "max_drawdown_daily": _max_drawdown([cash] + [e["equity"] for e in equity_curve]),
        "max_drawdown_trades": _max_drawdown(cash + np.r_[0.0, np.cumsum(pnl)]),
        "exits": {r: sum(1 for t in trades if t["reason"] == r) for r in ("signal", "stop", "eod")},
    }


def backtest(bars: dict[str, dict[str, np.ndarray]], config: IntradayConfig | None = None,
             open_session: bool = False) -> dict:
    """Run Kaufman's KAMA filter strategy over minute bars.

    Returns ``{"trades": [...], "equity": [{"date", "equity"}], "summary": {...},
    "config": {...}}``.  Each trade has ``ticker, entry_time, entry_price,
    exit_time, exit_price, shares, pnl, pnl_pct, reason`` (``signal``,
    ``stop`` or ``eod``) and ``bars_held``.  See the module docstring for the
    execution rules.

    ``open_session=True`` treats the newest session as still trading: its
    last bar is not the close, so a position stays open and is reported,
    with the day's pending orders and cash, under ``result["open"]``.  This
    is how a live paper run re-evaluates the day so far.
    """
    config = config or IntradayConfig()
    policy = _OrbPolicy(bars, config) if config.strategy == "orb" else _KamaPolicy(bars, config)
    return _simulate(bars, config, policy, open_session=open_session)


def random_baseline(bars: dict[str, dict[str, np.ndarray]], config: IntradayConfig,
                    trades: Sequence[dict], seed: int = 0) -> dict:
    """Random entries under the same screen, timing, costs and rules.

    For every day, the same number of entries as ``trades`` has on that day
    are placed at uniformly random bar times (before ``no_entry_after``) on
    uniformly random screened tickers, each held for a number of bars drawn
    from ``trades``' own holding times (stops and the end-of-day close still
    apply).  Entries that would overlap an open position wait for it to
    close.  Returns the same structure as :func:`backtest`.
    """
    return _simulate(bars, config, _RandomPolicy(trades, config, seed))
