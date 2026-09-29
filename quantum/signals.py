"""Score a trading indicator on the intraday bot's own engine, the same way for everyone.

This is the referee for the indicator duel (``docs/indicator_duel.md``).  An
indicator is a small Python file; this module loads it, checks that it
cannot see the future, runs it through :mod:`quantum.intraday` with the
live bot's account and costs, and scores it against rules written down
before any result was seen.  Nothing here trades: every run is on paper.

The contract
------------
An indicator file defines, with numpy as its only dependency:

* ``NAME``: a short label.
* ``TIMEFRAME``: bar length in minutes, one of 5, 15, 30 or 60.  The 5-minute
  source bars are aggregated to it (bars labelled by their start time).
* ``PARAMS``: a dict of keyword arguments for ``signals`` (optional).
* ``signals(bars, **params)``: given one ticker's bars -- a dict of equal
  length numpy arrays ``datetime`` (``"YYYY-MM-DD HH:MM:SS"``, New York
  time, regular session only, several sessions in a row), ``open``,
  ``high``, ``low``, ``close``, ``volume`` -- return a dict with two bool
  arrays of the same length: ``entry`` (go long) and ``exit`` (get out).

A signal on bar ``t`` may use bars ``0..t`` only.  It is acted on at bar
``t+1``'s open, moved 0.1% against you; everything is closed by 15:55 (or
at the last bar of the session); an exit signal while flat and an entry
signal while long are ignored.  Which stocks it may trade each day, how
much it buys and the cash rules are the live bot's, fixed for every
contestant: the five most volatile affordable names by prior-day range,
70% of equity per position, one position at a time, whole shares, sale
proceeds unusable until the next session (T+1), at most 6 entries a day,
no entries from 15:30.

The rules (pre-registered 2026-09-29)
-------------------------------------
The data is the frozen 5-minute download, complete sessions through
``FROZEN_END``.  The first ``WARMUP_SESSIONS`` only warm up the indicator
and the screen.  The last ``TEST_SESSIONS`` are the test window; the ones
between are the training window.  Tune on training only.  An indicator
passes if, on the test window:

1. it makes money, and makes money on the training window too;
2. it makes money in each half of the test window;
3. it still makes money at 0.25% per side;
4. it beats at least 90% of ``RANDOM_RUNS`` random-entry runs (same number
   of entries per day, holding times drawn from its own, same costs);
5. it trades at least ``MIN_TEST_TRADES`` times.

The duel is decided on the forward window, ``FORWARD``: sessions that had
not happened when the rules were written, scored once they have.  Yahoo
keeps 5-minute bars for about 60 days, so it must be scored before
``FORWARD_SCORE_BY``.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

import numpy as np

from .intraday import IntradayConfig, _simulate, random_baseline, resample

__all__ = [
    "BOT_CONFIG",
    "FORWARD",
    "FROZEN_END",
    "Indicator",
    "causality_violations",
    "evaluate",
    "load_indicator",
    "run_window",
    "sessions",
]

FROZEN_END = "2026-09-28"
WARMUP_SESSIONS = 10
TEST_SESSIONS = 20
RANDOM_RUNS = 40
RANDOM_PASS = 0.90
MIN_TEST_TRADES = 30
STRESS_SLIPPAGE_BPS = 25.0
FORWARD = ("2026-09-30", "2026-10-27")
FORWARD_SCORE_BY = "2026-12-15"
TIMEFRAMES = (5, 15, 30, 60)

BOT_CONFIG = IntradayConfig(
    cash=50.0, deploy_fraction=0.7, max_positions=1, whole_shares=True, slippage_bps=10.0,
    max_trades_per_day=6, settled_cash_only=True, flat_by="15:55", no_entry_after="15:30",
    top_n=5, screen_days=1,
)
"""The live intraday bot's account and costs (live/intraday/config.json)."""


@dataclass
class Indicator:
    name: str
    timeframe: int
    fn: Callable[..., dict]
    params: dict = field(default_factory=dict)
    path: str = ""

    def __call__(self, bars: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        return _checked(self.fn(bars, **self.params), len(bars["close"]), self.name)


def load_indicator(path: str | Path) -> Indicator:
    """Import an indicator file and check it follows the contract."""
    path = Path(path)
    spec = importlib.util.spec_from_file_location(f"indicator_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"{path}: not a Python file")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for name in ("NAME", "TIMEFRAME", "signals"):
        if not hasattr(mod, name):
            raise ValueError(f"{path}: missing {name}")
    if int(mod.TIMEFRAME) not in TIMEFRAMES:
        raise ValueError(f"{path}: TIMEFRAME must be one of {TIMEFRAMES}, not {mod.TIMEFRAME!r}")
    return Indicator(str(mod.NAME), int(mod.TIMEFRAME), mod.signals, dict(getattr(mod, "PARAMS", {}) or {}), str(path))


def _checked(out, n: int, name: str) -> dict[str, np.ndarray]:
    if not isinstance(out, dict) or "entry" not in out or "exit" not in out:
        raise ValueError(f"{name}: signals() must return a dict with 'entry' and 'exit'")
    res = {}
    for key in ("entry", "exit"):
        a = np.asarray(out[key])
        if a.shape != (n,):
            raise ValueError(f"{name}: '{key}' has shape {a.shape}, expected ({n},)")
        if a.dtype != bool:
            if a.dtype.kind == "f" and np.isnan(a).any():
                raise ValueError(f"{name}: '{key}' contains NaN; return booleans")
            a = a.astype(bool)
        res[key] = a
    return res


# --------------------------------------------------------------------------
# Data windows
# --------------------------------------------------------------------------


def sessions(bars: dict[str, dict[str, np.ndarray]]) -> list[str]:
    return sorted({str(d)[:10] for b in bars.values() for d in b["datetime"]})


def _until(bars, end: str):
    """Bars on or before session ``end``."""
    cut = f"{end}~"
    return {t: {k: v[b["datetime"] < cut] for k, v in b.items()} for t, b in bars.items()}


def prepare(bars, timeframe: int, end: str = FROZEN_END):
    """Complete sessions through ``end``, aggregated to ``timeframe`` minutes."""
    out = _until(bars, end)
    if timeframe != 5:
        out = resample(out, timeframe)
    return {t: b for t, b in out.items() if b["datetime"].size}


# --------------------------------------------------------------------------
# Causality: an indicator must not see the future
# --------------------------------------------------------------------------


def causality_violations(ind: Indicator, bars, n_tickers: int = 8, n_cuts: int = 6) -> list[str]:
    """Recompute on truncated histories; any change to an earlier bar's
    signal means the indicator used a later bar."""
    found = []
    for t in sorted(bars)[:n_tickers]:
        b = bars[t]
        n = len(b["close"])
        if n < 20:
            continue
        full = ind(b)
        for cut in np.linspace(n // 3, n - 1, n_cuts).astype(int):
            part = ind({k: v[:cut] for k, v in b.items()})
            for key in ("entry", "exit"):
                diff = np.flatnonzero(part[key] != full[key][:cut])
                if diff.size:
                    found.append(f"{t}: '{key}' at {b['datetime'][diff[0]]} changes when later bars are removed")
                    break
    return found


# --------------------------------------------------------------------------
# Running an indicator
# --------------------------------------------------------------------------


class SignalPolicy:
    """Adapter from an indicator's entry/exit arrays to quantum.intraday's engine."""

    def __init__(self, bars, ind: Indicator):
        self.sig = {t: ind(b) for t, b in bars.items()}

    def start_day(self, date, screen, times, trades_today_cap):
        pass

    def want_entry(self, ticker, i, time):
        return bool(self.sig[ticker]["entry"][i]), {}

    def want_exit(self, ticker, i, pos):
        return bool(self.sig[ticker]["exit"][i])


def run_window(prepared, ind: Indicator, start: str, end: str, config: IntradayConfig = BOT_CONFIG,
               policy: SignalPolicy | None = None) -> dict:
    """A fresh $50 account trading sessions ``start..end``; earlier sessions warm up."""
    bars = _until(prepared, end)
    cfg = replace(config, trade_from=start)
    return _simulate(bars, cfg, policy or SignalPolicy(bars, ind))


def _summary(res: dict) -> dict:
    s = res["summary"]
    return {"return": s["total_return"], "final": s["final_equity"], "trades": s["n_trades"],
            "win_rate": s["win_rate"], "max_dd": s["max_drawdown_daily"], "days": s["n_days"],
            "in_use": s["avg_capital_in_use"]}


def evaluate(bars, ind: Indicator, config: IntradayConfig = BOT_CONFIG, end: str = FROZEN_END,
             random_runs: int = RANDOM_RUNS, forward: bool = False) -> dict:
    """Score one indicator under the pre-registered rules (see the module docstring)."""
    prepared = prepare(bars, ind.timeframe, FORWARD[1] if forward else end)
    days = sessions(prepared)
    report: dict = {"name": ind.name, "timeframe": ind.timeframe, "params": ind.params, "path": ind.path}
    report["causality"] = causality_violations(ind, prepared)
    if forward:
        fwd = [d for d in days if FORWARD[0] <= d <= FORWARD[1]]
        if not fwd:
            report["forward"] = None
            return report
        res = run_window(prepared, ind, fwd[0], fwd[-1], config)
        report["forward"] = {"sessions": [fwd[0], fwd[-1], len(fwd)], **_summary(res)}
        return report
    if len(days) < WARMUP_SESSIONS + TEST_SESSIONS + 5:
        raise ValueError(f"need at least {WARMUP_SESSIONS + TEST_SESSIONS + 5} sessions, have {len(days)}")
    train, test = days[WARMUP_SESSIONS:-TEST_SESSIONS], days[-TEST_SESSIONS:]
    half = TEST_SESSIONS // 2
    policy = SignalPolicy(_until(prepared, test[-1]), ind)  # signals are causal: one pass serves every window

    def window(a, b, cfg=config):
        return run_window(prepared, ind, a, b, cfg, policy)

    tr, te = window(train[0], train[-1]), window(test[0], test[-1])
    h1, h2 = window(test[0], test[half - 1]), window(test[half], test[-1])
    stress = window(test[0], test[-1], replace(config, slippage_bps=STRESS_SLIPPAGE_BPS))
    rand = []
    if te["trades"] and random_runs:
        test_bars = _until(prepared, test[-1])
        cfg = replace(config, trade_from=test[0])
        rand = [random_baseline(test_bars, cfg, te["trades"], seed=s)["summary"]["total_return"]
                for s in range(random_runs)]
    beat = float(np.mean([te["summary"]["total_return"] > r for r in rand])) if rand else 0.0
    report.update(
        windows={"train": [train[0], train[-1], len(train)], "test": [test[0], test[-1], len(test)]},
        train=_summary(tr), test=_summary(te), test_half1=_summary(h1), test_half2=_summary(h2),
        test_stress=_summary(stress), random_beaten=beat,
        random_median=float(np.median(rand)) if rand else None,
    )
    gates = {
        "profitable_test_and_train": te["summary"]["total_return"] > 0 and tr["summary"]["total_return"] > 0,
        "profitable_both_test_halves": h1["summary"]["total_return"] > 0 and h2["summary"]["total_return"] > 0,
        "profitable_at_0.25pct": stress["summary"]["total_return"] > 0,
        "beats_90pct_of_random": beat >= RANDOM_PASS,
        f"at_least_{MIN_TEST_TRADES}_test_trades": te["summary"]["n_trades"] >= MIN_TEST_TRADES,
        "no_lookahead": not report["causality"],
    }
    report["gates"] = gates
    report["passed"] = all(gates.values())
    return report
