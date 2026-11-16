"""Walk-forward validation: does the optimiser's portfolio hold up out of sample?

Every portfolio number elsewhere in this package is *in-sample*: the expected
return and covariance the optimiser sees are estimated from the same prices
the portfolio is then scored on.  That flatters any optimiser, and it flatters
mean-variance optimisation most of all, because it is a machine for finding
the noise in a return estimate and betting on it.

This module scores portfolios the only way that counts: fit on a trailing
window, hold for the next period, roll forward, repeat, and report what the
held portfolio actually earned.  Everything is compared against the equal
weight portfolio, which needs no estimate at all and is famously hard to beat
(DeMiguel, Garlappi and Uppal, 2009).

What it can and cannot tell you
-------------------------------
It can tell you whether the *cardinality-constrained* optimiser -- the one
thing here a QUBO solver adds over a linear solve -- earns its keep against
naive diversification on a given price history.  It cannot tell you whether
the quantum solver adds anything, because on every problem small enough to
simulate, simulated annealing and exhaustive search find the same optimum;
see :mod:`quantum.portfolio`.  The solver is a means of reaching the optimum,
and the backtest tests the optimum.

The synthetic price generator is a constant-drift geometric Brownian motion.
That is the *most* favourable world for mean-variance optimisation -- the
drift is real and stationary, so a long enough window recovers it.  Real
equity drift is neither, so treat synthetic results as an upper bound on what
the optimiser will do on live data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Sequence

import numpy as np

from .market import MarketData
from .portfolio import (
    PortfolioConstraints,
    PortfolioProblem,
    exhaustive_cardinality,
    solve_portfolio,
    unconstrained_mean_variance,
)

Strategy = Callable[[MarketData, np.ndarray | None], np.ndarray]

__all__ = [
    "BacktestResult",
    "StrategyPerformance",
    "cardinality_strategy",
    "equal_weight",
    "markowitz_long_only",
    "max_drawdown",
    "performance",
    "walk_forward",
]


# --------------------------------------------------------------------------
# Strategies: MarketData (and last weights) -> long-only weights summing to one
# --------------------------------------------------------------------------


def _normalise(weights: np.ndarray) -> np.ndarray:
    w = np.clip(np.asarray(weights, dtype=np.float64).reshape(-1), 0.0, None)
    total = w.sum()
    return w / total if total > 0 else np.full(w.size, 1.0 / w.size)


def equal_weight(market: MarketData, previous: np.ndarray | None = None) -> np.ndarray:
    """``1/N``.  The benchmark that needs no forecast."""
    return np.full(market.n_assets, 1.0 / market.n_assets)


def markowitz_long_only(risk_aversion: float = 1.0) -> Strategy:
    """Closed-form mean-variance weights, clipped long-only and renormalised."""

    def strategy(market: MarketData, previous: np.ndarray | None = None) -> np.ndarray:
        return _normalise(
            unconstrained_mean_variance(
                market.expected_returns, market.covariance, risk_aversion, long_only=True
            )
        )

    return strategy


def cardinality_strategy(
    cardinality: int,
    risk_aversion: float = 1.0,
    solver: str = "simulated_annealing",
    **solver_kwargs,
) -> Strategy:
    """Pick exactly ``K`` names by solving the QUBO with the given solver.

    ``solver="exhaustive"`` enumerates every subset instead, which on small
    universes proves the heuristic solvers are hitting the true optimum.
    """

    def strategy(market: MarketData, previous: np.ndarray | None = None) -> np.ndarray:
        if solver == "exhaustive":
            mask, _ = exhaustive_cardinality(
                market.expected_returns, market.covariance, cardinality, risk_aversion
            )
            return _normalise(mask.astype(np.float64))
        problem = PortfolioProblem(
            market.expected_returns,
            market.covariance,
            market.tickers,
            risk_aversion=risk_aversion,
            constraints=PortfolioConstraints(cardinality=cardinality),
        )
        result = solve_portfolio(problem, solver=solver, **solver_kwargs)
        return _normalise(result.weights)

    return strategy


# --------------------------------------------------------------------------
# Performance statistics
# --------------------------------------------------------------------------


def max_drawdown(period_returns: np.ndarray) -> float:
    """Largest peak-to-trough loss of the compounded equity curve."""
    r = np.asarray(period_returns, dtype=np.float64)
    if r.size == 0:
        return 0.0
    equity = np.cumprod(1.0 + r)
    peak = np.maximum.accumulate(equity)
    return float(np.max(1.0 - equity / peak))


@dataclass
class StrategyPerformance:
    """Out-of-sample statistics of one strategy over the walk."""

    name: str
    period_returns: np.ndarray
    weights: np.ndarray                     # (n_periods, n_assets)
    periods_per_year: float
    in_sample_sharpe: float

    @property
    def n_periods(self) -> int:
        return int(self.period_returns.size)

    @property
    def total_return(self) -> float:
        return float(np.prod(1.0 + self.period_returns) - 1.0)

    @property
    def annual_return(self) -> float:
        years = self.n_periods / self.periods_per_year
        return float((1.0 + self.total_return) ** (1.0 / years) - 1.0) if years > 0 else 0.0

    @property
    def annual_volatility(self) -> float:
        if self.n_periods < 2:
            return float("nan")
        return float(self.period_returns.std(ddof=1) * math.sqrt(self.periods_per_year))

    @property
    def sharpe(self) -> float:
        vol = self.annual_volatility
        return self.annual_return / vol if vol > 0 else float("nan")

    @property
    def max_drawdown(self) -> float:
        return max_drawdown(self.period_returns)

    @property
    def turnover(self) -> float:
        """Mean one-way turnover per rebalance, as a fraction of the book."""
        if self.weights.shape[0] < 2:
            return 0.0
        return float(np.abs(np.diff(self.weights, axis=0)).sum(axis=1).mean() / 2.0)

    @property
    def sharpe_shrinkage(self) -> float:
        """``in-sample Sharpe - out-of-sample Sharpe``: the overfitting gap."""
        return self.in_sample_sharpe - self.sharpe


def performance(
    name: str,
    period_returns: np.ndarray,
    weights: np.ndarray,
    periods_per_year: float,
    in_sample_sharpe: float = float("nan"),
) -> StrategyPerformance:
    return StrategyPerformance(
        name, np.asarray(period_returns, dtype=np.float64), np.asarray(weights), periods_per_year, in_sample_sharpe
    )


# --------------------------------------------------------------------------
# The walk
# --------------------------------------------------------------------------


@dataclass
class BacktestResult:
    strategies: dict[str, StrategyPerformance]
    window: int
    horizon: int
    benchmark: str = "equal_weight"
    detail: dict = field(default_factory=dict)

    def excess_over_benchmark(self, name: str) -> tuple[float, float]:
        """Mean per-period excess return over the benchmark and its t-statistic.

        A paired test -- same periods, same prices -- so the market's common
        moves cancel and only the allocation difference is scored.
        """
        r = self.strategies[name].period_returns
        b = self.strategies[self.benchmark].period_returns
        d = r - b
        if d.size < 2:
            return float(d.mean()) if d.size else 0.0, float("nan")
        se = d.std(ddof=1) / math.sqrt(d.size)
        return float(d.mean()), float(d.mean() / se) if se > 0 else float("nan")

    def report(self) -> str:
        n = next(iter(self.strategies.values())).n_periods
        lines = [
            f"walk-forward: window {self.window}, horizon {self.horizon}, "
            f"{n} out-of-sample periods",
            "",
            f"{'strategy':<34}{'ann.ret':>9}{'ann.vol':>9}{'sharpe':>8}"
            f"{'IS sharpe':>11}{'maxDD':>8}{'turnover':>10}{'t vs 1/N':>10}",
            "-" * 99,
        ]
        for name, p in self.strategies.items():
            _, t = self.excess_over_benchmark(name)
            t_str = "-" if name == self.benchmark else f"{t:>+.2f}"
            lines.append(
                f"{name:<34}{p.annual_return:>9.2%}{p.annual_volatility:>9.2%}"
                f"{p.sharpe:>8.2f}{p.in_sample_sharpe:>11.2f}{p.max_drawdown:>8.1%}"
                f"{p.turnover:>10.1%}{t_str:>10}"
            )
        lines.append("")
        lines.append(
            "IS sharpe is the Sharpe the optimiser *believed* on its fitting window; "
            "the gap to the realised column is the overfit."
        )
        lines.append(
            "|t| < 2 means the difference from equal weight is not distinguishable "
            "from luck on this history."
        )
        return "\n".join(lines)


def walk_forward(
    prices: np.ndarray,
    tickers: Sequence[str],
    strategies: dict[str, Strategy],
    window: int = 252,
    horizon: int = 21,
    periods_per_year: int = 252,
    use_shrinkage: bool = True,
    benchmark: str = "equal_weight",
) -> BacktestResult:
    """Fit each strategy on a trailing ``window`` of prices, hold ``horizon`` steps.

    Weights are set at the end of the window and held (drifting with prices,
    no intra-period rebalance) until the next fit.  Realised period return is
    the weighted simple return of the assets over the holding period.  No
    transaction costs are charged; the turnover column lets you price them.
    """
    prices = np.asarray(prices, dtype=np.float64)
    if prices.ndim != 2:
        raise ValueError("prices must be a (T, n_assets) matrix")
    T, n = prices.shape
    if window < 3 or horizon < 1:
        raise ValueError("window must be >= 3 and horizon >= 1")
    if T < window + horizon:
        raise ValueError("not enough history for one fit-and-hold step")
    if benchmark not in strategies:
        strategies = {benchmark: equal_weight, **strategies}

    names = list(strategies)
    returns = {k: [] for k in names}
    weight_hist = {k: [] for k in names}
    is_sharpes = {k: [] for k in names}
    previous: dict[str, np.ndarray | None] = {k: None for k in names}

    for start in range(0, T - window - horizon + 1, horizon):
        fit = prices[start : start + window]
        hold = prices[start + window - 1 : start + window + horizon]
        market = MarketData(
            list(tickers), fit, periods_per_year=periods_per_year, use_shrinkage=use_shrinkage
        )
        asset_return = hold[-1] / hold[0] - 1.0
        for name, strategy in strategies.items():
            w = _normalise(strategy(market, previous[name]))
            previous[name] = w
            returns[name].append(float(w @ asset_return))
            weight_hist[name].append(w)
            mu = float(w @ market.expected_returns)
            vol = math.sqrt(max(float(w @ market.covariance @ w), 0.0))
            is_sharpes[name].append(mu / vol if vol > 0 else float("nan"))

    per_year = periods_per_year / horizon
    result = {
        name: performance(
            name,
            np.array(returns[name]),
            np.array(weight_hist[name]),
            per_year,
            float(np.nanmean(is_sharpes[name])),
        )
        for name in names
    }
    return BacktestResult(result, window, horizon, benchmark)
