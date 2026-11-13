"""How to tell a trading bot's skill from luck, and whether it beats 1/N.

The tests in the literature (Bailey & López de Prado) that a small live
track record can honestly be put through:

* :func:`probabilistic_sharpe` -- the probability that the true Sharpe ratio
  exceeds a benchmark, given the observed one, the sample length, and the
  skew and kurtosis of the returns (Bailey & López de Prado 2012).
* :func:`min_track_record` -- how many observations are needed before that
  probability can reach a confidence level (same paper).
* :func:`expected_max_sharpe` and :func:`deflated_sharpe` -- the Sharpe a
  best-of-N search would find by luck alone, and the probabilistic Sharpe
  measured against it (Bailey & López de Prado 2014).

:func:`evaluate_bot` applies them to the engine's own state: the bot's daily
returns against an equal-weight portfolio of the same stocks over the same
days, which is the benchmark it has to beat (DeMiguel, Garlappi & Uppal
2009).  The verdict follows a stop rule fixed in advance
(:data:`STOP_RULE`), so a run of luck cannot be read as skill after the
fact.  Everything here is per period (daily for the bot); annualise with
sqrt(252).
"""

from __future__ import annotations

import math
from statistics import NormalDist
from typing import Sequence

import numpy as np

__all__ = [
    "STOP_RULE",
    "probabilistic_sharpe",
    "min_track_record",
    "expected_max_sharpe",
    "deflated_sharpe",
    "evaluate_bot",
]

_N = NormalDist()
_EULER_GAMMA = 0.5772156649015329

STOP_RULE = {
    "review_after_days": 756,  # three years of trading days
    "stop_if_probability_below": 0.5,
    "text": ("Fixed 2026-09-30, before any live result: after 756 trading days (about "
             "three years), stop the bot if the probability that it beats equal weight "
             "of the same stocks is below 50%."),
}


def _moments(returns: np.ndarray) -> tuple[float, float, float]:
    """Per-period Sharpe (no risk-free rate), skewness, and raw kurtosis (normal = 3)."""
    r = np.asarray(returns, dtype=np.float64)
    sd = r.std(ddof=1)
    if len(r) < 3 or sd <= 0:
        return 0.0, 0.0, 3.0
    z = (r - r.mean()) / r.std(ddof=0)
    return float(r.mean() / sd), float((z**3).mean()), float((z**4).mean())


def probabilistic_sharpe(returns: Sequence[float], benchmark_sr: float = 0.0) -> float:
    """P(true per-period Sharpe > ``benchmark_sr``) given the observed returns."""
    r = np.asarray(returns, dtype=np.float64)
    if len(r) < 3:
        return float("nan")
    sr, skew, kurt = _moments(r)
    denom = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr**2
    if denom <= 0:
        return float("nan")
    return float(_N.cdf((sr - benchmark_sr) * math.sqrt(len(r) - 1) / math.sqrt(denom)))


def min_track_record(sr: float, skew: float = 0.0, kurt: float = 3.0,
                     benchmark_sr: float = 0.0, alpha: float = 0.05) -> float:
    """Observations needed for the probabilistic Sharpe to reach ``1 - alpha``.

    ``sr`` is per period.  At an annual Sharpe of 0.5 on normal monthly
    returns this is about 132 months; at 1.0, about 35.
    """
    if sr <= benchmark_sr:
        return float("inf")
    z = _N.inv_cdf(1.0 - alpha)
    return 1.0 + (1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr**2) * (z / (sr - benchmark_sr)) ** 2


def expected_max_sharpe(n_trials: int, sr_std: float) -> float:
    """The best Sharpe that ``n_trials`` independent tries of a worthless idea would show."""
    if n_trials < 2:
        return 0.0
    return sr_std * ((1.0 - _EULER_GAMMA) * _N.inv_cdf(1.0 - 1.0 / n_trials)
                     + _EULER_GAMMA * _N.inv_cdf(1.0 - 1.0 / (n_trials * math.e)))


def deflated_sharpe(returns: Sequence[float], n_trials: int, sr_std: float) -> float:
    """Probabilistic Sharpe against the best a search of ``n_trials`` would find by luck."""
    return probabilistic_sharpe(returns, expected_max_sharpe(n_trials, sr_std))


def evaluate_bot(state, trade_from: str | None = None, periods_per_year: int = 252,
                 first_bar: int = 0) -> dict:
    """The bot against equal weight of its own stocks, from its first tradable day.

    ``state`` is an :class:`quantum.live.EngineState`.  The first tradable
    day is the first date on or after ``trade_from``; without it, bar
    ``first_bar`` (the first the engine can trade after its warm-up, see
    :func:`quantum.live.first_tradable_bar`), so equal weight is not
    credited with a run the bot could not take part in.  Equal weight is
    rebalanced daily, costless -- a generous benchmark, and the one the
    backtests used.  Returns plain numbers and a verdict under
    :data:`STOP_RULE`.
    """
    dates = list(state.dates)
    start = min(max(int(first_bar), 0), len(dates))
    if trade_from:
        start = next((i for i, d in enumerate(dates) if d >= trade_from), len(dates))
    equity = np.asarray(state.equity_curve[start:], dtype=np.float64)
    prices = np.asarray(state.prices[start:], dtype=np.float64)
    n = len(equity) - 1
    out = {"days": max(n, 0), "from": dates[start] if start < len(dates) else None,
           "stop_rule": STOP_RULE["text"]}
    if n < 2:
        out["verdict"] = "too early: fewer than 3 trading days since the first tradable day"
        return out
    bot = equity[1:] / equity[:-1] - 1.0
    ew = (prices[1:] / prices[:-1] - 1.0).mean(axis=1)
    active = bot - ew
    a = math.sqrt(periods_per_year)
    te = float(active.std(ddof=1))
    out.update({
        "bot_return": float(np.prod(1.0 + bot) - 1.0),
        "equal_weight_return": float(np.prod(1.0 + ew) - 1.0),
        "bot_sharpe_annual": float(bot.mean() / bot.std(ddof=1) * a) if bot.std(ddof=1) > 0 else 0.0,
        "equal_weight_sharpe_annual": float(ew.mean() / ew.std(ddof=1) * a) if ew.std(ddof=1) > 0 else 0.0,
        "tracking_error_annual": te * a,
        "information_ratio_annual": float(active.mean() / te * a) if te > 0 else 0.0,
        "probability_beats_equal_weight": probabilistic_sharpe(active) if te > 0 else float("nan"),
    })
    p = out["probability_beats_equal_weight"]
    need = STOP_RULE["review_after_days"]
    if n < need:
        out["verdict"] = (f"too early to judge: {n} of {need} trading days; "
                          "no result before then says anything about skill")
    elif not (p >= STOP_RULE["stop_if_probability_below"]):
        out["verdict"] = f"STOP: after {n} days the chance it beats equal weight is {p:.0%}"
    else:
        out["verdict"] = f"keep running: after {n} days the chance it beats equal weight is {p:.0%}"
    return out
