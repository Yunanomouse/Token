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
``t+1``'s open, moved 0.1% against you.  Everything is closed at the open
of the last bar starting at or before 15:55 for the timeframe (``flat_by``:
15:55 on 5-minute bars, 15:45 on 15-minute, 15:30 on 30- and 60-minute),
or at the last bar of the session if that comes first.  An exit signal
while flat and an entry signal while long are ignored.  Which stocks it may trade each day, how
much it buys and the cash rules are the live bot's, fixed for every
contestant: the five most volatile affordable names by prior-day range,
70% of equity per position, one position at a time, whole shares, sale
proceeds unusable until the next session (T+1), at most 6 entries a day.
Entry signals on bars starting at 15:30 or later are ignored, so on
5-minute bars the last usable signal is the 15:25 bar's, filled at the
15:30 open.

The rules (pre-registered 2026-09-29)
-------------------------------------
The data is the frozen 5-minute download, complete sessions through
``FROZEN_END``.  The windows are fixed dates: ``TRAIN`` and ``TEST``
(``WARMUP_SESSIONS`` sessions before ``TRAIN`` only warm up the indicator
and the screen).  :func:`evaluate` refuses data that does not yield
exactly these windows -- the first ``WARMUP_SESSIONS`` sessions warm-up,
then ``TRAIN``, then the last ``TEST_SESSIONS`` sessions ``TEST`` -- so a
different download cannot silently shift them.  Tune on training only.
An indicator passes if, on the test window:

1. it makes money, and makes money on the training window too;
2. it makes money in each half of the test window;
3. it still makes money at 0.25% per side;
4. it beats at least 90% of ``RANDOM_RUNS`` random-entry runs (same number
   of entries per day, holding times drawn from its own, same costs);
5. it trades at least ``MIN_TEST_TRADES`` times;
6. it shows no look-ahead (:func:`causality_violations`).

The duel is decided on the forward window, ``FORWARD``: sessions that had
not happened when the rules were written, scored once they have -- only
when the data holds all ``FORWARD_SESSIONS`` of them and the last one runs
through the close; until then the forward result is "incomplete".  An
entry showing look-ahead is never ranked ahead of anyone.  Yahoo keeps
5-minute bars for about 60 days, so it must be scored before
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
    "FORWARD_SESSIONS",
    "FROZEN_END",
    "Indicator",
    "TEST",
    "TRAIN",
    "causality_violations",
    "config_for",
    "evaluate",
    "flat_by_for",
    "forward_status",
    "load_indicator",
    "rank",
    "run_window",
    "sessions",
    "split_windows",
]

FROZEN_END = "2026-09-28"
WARMUP_SESSIONS = 10
TRAIN = ("2026-07-21", "2026-08-28")  # 29 sessions, pre-registered
TEST = ("2026-08-31", "2026-09-28")   # 20 sessions, pre-registered
TEST_SESSIONS = 20
RANDOM_RUNS = 40
RANDOM_PASS = 0.90
MIN_TEST_TRADES = 30
STRESS_SLIPPAGE_BPS = 25.0
FORWARD = ("2026-09-30", "2026-10-27")
FORWARD_SESSIONS = 20
SESSION_OPEN, LAST_FLAT = "09:30", "15:55"
FORWARD_SCORE_BY = "2026-12-15"
TIMEFRAMES = (5, 15, 30, 60)
assert TEST[1] == FROZEN_END and TRAIN[1] < TEST[0] and FORWARD[0] > FROZEN_END

BOT_CONFIG = IntradayConfig(
    cash=50.0, deploy_fraction=0.7, max_positions=1, whole_shares=True, slippage_bps=10.0,
    max_trades_per_day=6, settled_cash_only=True, flat_by="15:55", no_entry_after="15:30",
    top_n=5, screen_days=1,
)
"""The live intraday bot's account and costs (live/intraday/config.json) as
pre-registered for the duel: a flat 10 bps per side.  The live config has
since added a half-tick cost, a higher cost near the open and a $2 minimum
price; the duel keeps the rules it was registered with.

Its ``flat_by`` is the 5-minute value; the referee always runs an indicator
with :func:`config_for` its timeframe."""


def _minutes(hm: str) -> int:
    return int(hm[:2]) * 60 + int(hm[3:5])


def flat_by_for(timeframe: int) -> str:
    """Open of the last ``timeframe``-minute bar starting at or before 15:55.

    9:30 + floor((15:55 - 9:30) / tf) * tf: 15:55 for 1 and 5 minutes, 15:45
    for 15, 15:30 for 30 and 60.  The engine flattens at the open of the first
    bar at or after ``flat_by``; with 15:55 on 15-minute bars that bar never
    comes, and positions would ride to the session's close instead.
    """
    tf = int(timeframe)
    if tf <= 0:
        raise ValueError(f"timeframe must be positive, not {timeframe!r}")
    start = _minutes(SESSION_OPEN)
    m = start + (_minutes(LAST_FLAT) - start) // tf * tf
    return f"{m // 60:02d}:{m % 60:02d}"


def config_for(timeframe: int, config: IntradayConfig = BOT_CONFIG) -> IntradayConfig:
    """``config`` with the flatten time of ``timeframe`` (:func:`flat_by_for`)."""
    return replace(config, flat_by=flat_by_for(timeframe))


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


def split_windows(days: list[str], train: tuple[str, str] | None = None,
                  test: tuple[str, str] | None = None) -> tuple[list[str], list[str]]:
    """The training and test sessions, which must be exactly the pre-registered ones.

    The windows are the fixed dates ``TRAIN`` and ``TEST``.  The session-count
    rule they were derived from (``WARMUP_SESSIONS`` of warm-up, then
    training, then the last ``TEST_SESSIONS`` as test) is kept only as a check:
    data that does not yield both, identically, is refused with a ValueError
    rather than scored on shifted windows.
    """
    train, test = tuple(train or TRAIN), tuple(test or TEST)
    days = sorted(d for d in days if d <= test[1])
    tr = [d for d in days if train[0] <= d <= train[1]]
    te = [d for d in days if test[0] <= d <= test[1]]
    problems = []
    if not tr or (tr[0], tr[-1]) != train:
        problems.append(f"training window {train[0]}..{train[1]} has sessions "
                        f"{(tr[0] + '..' + tr[-1]) if tr else 'none'} ({len(tr)})")
    if len(te) != TEST_SESSIONS or (te[0], te[-1]) != test:
        problems.append(f"test window {test[0]}..{test[1]} must hold {TEST_SESSIONS} sessions, has "
                        f"{(te[0] + '..' + te[-1]) if te else 'none'} ({len(te)})")
    n_warm = len([d for d in days if d < train[0]])
    if n_warm != WARMUP_SESSIONS:
        problems.append(f"{n_warm} warm-up sessions before {train[0]}, expected {WARMUP_SESSIONS}")
    between = [d for d in days if train[1] < d < test[0]]
    if between:
        problems.append(f"sessions between training and test: {between}")
    if not problems and (days[WARMUP_SESSIONS:-TEST_SESSIONS] != tr or days[-TEST_SESSIONS:] != te):
        problems.append("the session-count split does not match the pre-registered dates")
    if problems:
        raise ValueError("the data does not yield the pre-registered windows: " + "; ".join(problems))
    return tr, te


def forward_status(bars, window: tuple[str, str] | None = None, n_sessions: int = FORWARD_SESSIONS) -> dict:
    """Whether the (5-minute) data holds the whole forward window.

    Complete only with all ``n_sessions`` sessions from ``window[0]`` to
    ``window[1]`` and the last of them running through the close (a bar
    starting at ``LAST_FLAT``, 15:55).  Otherwise the status is "incomplete",
    with the counts, and nothing is scored.
    """
    window = tuple(window or FORWARD)
    days = [d for d in sessions(bars) if window[0] <= d <= window[1]]
    last = days[-1] if days else None
    last_bar = None
    if last:
        times = [str(d)[11:16] for b in bars.values() for d in np.asarray(b["datetime"]).astype(str)
                 if d.startswith(last)]
        last_bar = max(times) if times else None
    last_complete = last_bar is not None and last_bar >= LAST_FLAT
    complete = (len(days) == n_sessions and days[0] == window[0] and days[-1] == window[1] and last_complete)
    return {"status": "complete" if complete else "incomplete", "window": list(window),
            "sessions_have": len(days), "sessions_needed": n_sessions,
            "first_session": days[0] if days else None, "last_session": last,
            "last_bar": last_bar, "last_session_complete": last_complete}


# --------------------------------------------------------------------------
# Causality: an indicator must not see the future
# --------------------------------------------------------------------------

CAUSALITY_FIRST_CUT = 20


def _cut_points(datetimes, n_cuts: int, first: int = CAUSALITY_FIRST_CUT) -> list[int]:
    """Truncation lengths: evenly from bar ``first`` to the end, plus the
    middle of evenly chosen sessions, so a cut falls inside a session and not
    only wherever the even spacing happens to land."""
    n = len(datetimes)
    if n <= first:
        return []
    cuts = set(np.linspace(first, n - 1, n_cuts).astype(int).tolist())
    day = np.array([str(d)[:10] for d in datetimes])
    starts = np.flatnonzero(np.r_[True, day[1:] != day[:-1]])
    ends = np.r_[starts[1:], n]
    mids = [int(a + b) // 2 for a, b in zip(starts, ends) if b - a >= 2]
    if mids:
        cuts.update(mids[j] for j in np.linspace(0, len(mids) - 1, min(n_cuts, len(mids))).astype(int))
    return sorted(c for c in cuts if first <= c < n)


def causality_violations(ind: Indicator, bars, n_tickers: int | None = None, n_cuts: int = 8) -> list[str]:
    """Recompute on truncated histories; any change to an earlier bar's
    signal means the indicator used a later bar.

    Every ticker is checked (``n_tickers`` limits it, for speed in research
    only).  All the truncated runs are computed before any full run, each on
    its own copy of the arrays, so an indicator that caches results or
    mutates its input cannot hand the truncated runs the full run's answer.
    """
    tickers = sorted(bars)[:n_tickers] if n_tickers else sorted(bars)
    parts: dict[str, list[tuple[int, dict]]] = {}
    for t in tickers:
        b = bars[t]
        parts[t] = [(cut, ind({k: np.array(v[:cut], copy=True) for k, v in b.items()}))
                    for cut in _cut_points(b["datetime"], n_cuts)]
    found = []
    for t in tickers:
        if not parts[t]:
            continue
        b = bars[t]
        full = ind({k: np.array(v, copy=True) for k, v in b.items()})
        for cut, part in parts[t]:
            bad = False
            for key in ("entry", "exit"):
                diff = np.flatnonzero(part[key] != full[key][:cut])
                if diff.size:
                    found.append(f"{t}: '{key}' at {b['datetime'][diff[0]]} changes when bars from "
                                 f"{b['datetime'][cut]} on are removed")
                    bad = True
                    break
            if bad:
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
    """A fresh $50 account trading sessions ``start..end``; earlier sessions warm up.

    The flatten time is always the indicator's timeframe's (:func:`config_for`)."""
    bars = _until(prepared, end)
    cfg = replace(config_for(ind.timeframe, config), trade_from=start)
    return _simulate(bars, cfg, policy or SignalPolicy(bars, ind))


def _summary(res: dict) -> dict:
    s = res["summary"]
    return {"return": s["total_return"], "final": s["final_equity"], "trades": s["n_trades"],
            "win_rate": s["win_rate"], "max_dd": s["max_drawdown_daily"], "days": s["n_days"],
            "in_use": s["avg_capital_in_use"]}


def evaluate(bars, ind: Indicator, config: IntradayConfig = BOT_CONFIG, random_runs: int = RANDOM_RUNS,
             forward: bool = False, windows: tuple[tuple[str, str], tuple[str, str]] | None = None,
             forward_window: tuple[str, str] | None = None) -> dict:
    """Score one indicator under the pre-registered rules (see the module docstring).

    ``bars`` are the 5-minute bars.  ``windows`` (training, test) and
    ``forward_window`` default to the pre-registered ``TRAIN``, ``TEST`` and
    ``FORWARD``; other values are for tests on synthetic data only.
    """
    config = config_for(ind.timeframe, config)
    train_w, test_w = windows or (TRAIN, TEST)
    fwd_w = tuple(forward_window or FORWARD)
    prepared = prepare(bars, ind.timeframe, fwd_w[1] if forward else test_w[1])
    days = sessions(prepared)
    report: dict = {"name": ind.name, "timeframe": ind.timeframe, "params": ind.params, "path": ind.path,
                    "flat_by": config.flat_by}
    report["causality"] = causality_violations(ind, prepared)
    if forward:
        status = forward_status(_until(bars, fwd_w[1]), fwd_w)
        report["forward"] = status
        if status["status"] == "complete":
            res = run_window(prepared, ind, fwd_w[0], fwd_w[1], config)
            status.update(sessions=[fwd_w[0], fwd_w[1], status["sessions_have"]], **_summary(res))
        return report
    train, test = split_windows(days, train_w, test_w)
    half = len(test) // 2
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


def rank(reports: list[dict], forward: bool = False) -> tuple[dict | None, str]:
    """The entry ahead, and why; ``(None, reason)`` when nobody can be.

    An entry showing look-ahead is never ahead.  On the forward window
    nobody is ahead until every entry's forward result is complete.
    """
    clean = [r for r in reports if not r.get("causality")]
    if not clean:
        return None, "every entry shows look-ahead"
    if forward:
        pending = [r["name"] for r in reports if (r.get("forward") or {}).get("status") != "complete"]
        if pending:
            return None, "the forward window is incomplete"
        return max(clean, key=lambda r: r["forward"]["return"]), "forward return"
    return (max(clean, key=lambda r: (sum(r["gates"].values()), r["test"]["return"])),
            f"gates passed, then test return (frozen through {FROZEN_END}; the forward window decides the duel)")
