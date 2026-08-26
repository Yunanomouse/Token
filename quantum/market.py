"""Market data: loading prices, estimating returns and covariance.

Deliberately numpy-only.  The estimation choices here matter more to the final
portfolio than the choice of optimiser does -- a quantum solver fed a bad
covariance matrix returns a confidently wrong answer -- so the shrinkage
estimator is the default rather than an option.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

__all__ = [
    "MarketData",
    "load_price_csv",
    "log_returns",
    "simple_returns",
    "sample_covariance",
    "ledoit_wolf_shrinkage",
    "synthetic_prices",
    "TRADING_DAYS",
]

TRADING_DAYS = 252


# --------------------------------------------------------------------------
# Return and covariance estimation
# --------------------------------------------------------------------------


def log_returns(prices: np.ndarray) -> np.ndarray:
    """Continuously compounded returns; shape ``(T-1, n_assets)``."""
    p = np.asarray(prices, dtype=np.float64)
    if p.ndim == 1:
        p = p[:, None]
    if np.any(p <= 0):
        raise ValueError("prices must be strictly positive for log returns")
    return np.diff(np.log(p), axis=0)


def simple_returns(prices: np.ndarray) -> np.ndarray:
    """Arithmetic returns; shape ``(T-1, n_assets)``."""
    p = np.asarray(prices, dtype=np.float64)
    if p.ndim == 1:
        p = p[:, None]
    return p[1:] / p[:-1] - 1.0


def sample_covariance(returns: np.ndarray, ddof: int = 1) -> np.ndarray:
    """Plain sample covariance.

    Included mainly as the thing to compare against: when the number of assets
    approaches the number of observations this estimator is badly conditioned,
    and any optimiser will happily exploit its noise.
    """
    r = np.asarray(returns, dtype=np.float64)
    return np.cov(r, rowvar=False, ddof=ddof)


def ledoit_wolf_shrinkage(returns: np.ndarray) -> tuple[np.ndarray, float]:
    """Ledoit-Wolf shrinkage towards a scaled identity.

    Returns ``(covariance, shrinkage_intensity)``.  Shrinking the sample
    covariance towards a well-conditioned target is what keeps mean-variance
    optimisation from concentrating on estimation noise -- the classic
    "error maximisation" failure mode.
    """
    r = np.asarray(returns, dtype=np.float64)
    t, n = r.shape
    if t < 2:
        raise ValueError("need at least two observations")

    centred = r - r.mean(axis=0, keepdims=True)
    sample = centred.T @ centred / t

    mu = float(np.trace(sample) / n)
    target = mu * np.eye(n)

    # Squared Frobenius distance from the sample covariance to the target.
    d2 = float(np.sum((sample - target) ** 2))

    # Expected estimation error of the sample covariance entries.
    b2 = 0.0
    for k in range(t):
        outer = np.outer(centred[k], centred[k])
        b2 += float(np.sum((outer - sample) ** 2))
    b2 /= t**2
    b2 = min(b2, d2)

    intensity = 0.0 if d2 <= 0 else max(0.0, min(1.0, b2 / d2))
    shrunk = intensity * target + (1.0 - intensity) * sample
    return shrunk, float(intensity)


# --------------------------------------------------------------------------
# Container
# --------------------------------------------------------------------------


@dataclass
class MarketData:
    """Prices plus the annualised moments an optimiser needs."""

    tickers: list[str]
    prices: np.ndarray                 # shape (T, n_assets)
    returns: np.ndarray = field(init=False)
    expected_returns: np.ndarray = field(init=False)
    covariance: np.ndarray = field(init=False)
    shrinkage: float = field(init=False, default=0.0)
    periods_per_year: int = TRADING_DAYS
    use_shrinkage: bool = True

    def __post_init__(self) -> None:
        self.prices = np.asarray(self.prices, dtype=np.float64)
        if self.prices.ndim == 1:
            self.prices = self.prices[:, None]
        if self.prices.shape[1] != len(self.tickers):
            raise ValueError("ticker count does not match the price matrix")
        if self.prices.shape[0] < 3:
            raise ValueError("need at least three price observations")
        # Reject bad data loudly. A NaN or a non-positive price propagates
        # silently through log-returns into every covariance entry, and the
        # optimiser then returns a portfolio built on NaN without raising --
        # the worst failure mode there is. load_price_csv() drops such rows;
        # a MarketData built directly must not accept them.
        if not np.all(np.isfinite(self.prices)):
            bad = int(np.count_nonzero(~np.isfinite(self.prices)))
            raise ValueError(
                f"price matrix contains {bad} non-finite value(s); "
                "drop or impute them before constructing MarketData"
            )
        if np.any(self.prices <= 0):
            bad = int(np.count_nonzero(self.prices <= 0))
            raise ValueError(
                f"price matrix contains {bad} non-positive price(s); "
                "log returns are undefined there"
            )

        self.returns = log_returns(self.prices)
        # Annualise: log returns add over time, covariance scales linearly.
        self.expected_returns = self.returns.mean(axis=0) * self.periods_per_year
        if self.use_shrinkage:
            cov, intensity = ledoit_wolf_shrinkage(self.returns)
            self.shrinkage = intensity
        else:
            cov, self.shrinkage = sample_covariance(self.returns), 0.0
        self.covariance = cov * self.periods_per_year

    @property
    def n_assets(self) -> int:
        return len(self.tickers)

    @property
    def volatilities(self) -> np.ndarray:
        return np.sqrt(np.clip(np.diag(self.covariance), 0.0, None))

    @property
    def correlation(self) -> np.ndarray:
        vol = self.volatilities
        denom = np.outer(vol, vol)
        with np.errstate(divide="ignore", invalid="ignore"):
            corr = np.where(denom > 0, self.covariance / denom, 0.0)
        np.fill_diagonal(corr, 1.0)
        return corr

    def summary(self) -> str:
        lines = [
            f"{'ticker':<10}{'ann.return':>12}{'ann.vol':>10}{'sharpe':>9}",
            "-" * 41,
        ]
        for i, t in enumerate(self.tickers):
            vol = self.volatilities[i]
            sharpe = self.expected_returns[i] / vol if vol > 0 else float("nan")
            lines.append(f"{t:<10}{self.expected_returns[i]:>11.2%}{vol:>10.2%}{sharpe:>9.2f}")
        lines.append(f"\nobservations: {self.returns.shape[0]}, shrinkage: {self.shrinkage:.3f}")
        return "\n".join(lines)


def load_price_csv(
    path: str | Path,
    date_column: str | None = None,
    tickers: list[str] | None = None,
) -> MarketData:
    """Load a wide CSV -- one date column, one price column per ticker.

    Rows with any missing or non-positive price are dropped, since log returns
    are undefined there and silently forward-filling would fabricate data.
    """
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise ValueError(f"{path} contains no rows")

    header = list(rows[0].keys())
    if date_column is None:
        date_column = next(
            (c for c in header if c.lower() in ("date", "timestamp", "time", "day")),
            None,
        )
    cols = tickers or [c for c in header if c != date_column]
    if not cols:
        raise ValueError("no price columns found")

    values: list[list[float]] = []
    for row in rows:
        try:
            parsed = [float(row[c]) for c in cols]
        except (TypeError, ValueError):
            continue
        if any(v <= 0 or not math.isfinite(v) for v in parsed):
            continue
        values.append(parsed)

    if len(values) < 3:
        raise ValueError(f"{path} has fewer than three usable rows")
    return MarketData(tickers=list(cols), prices=np.array(values))


def synthetic_prices(
    n_assets: int = 6,
    n_days: int = 504,
    seed: int | None = 0,
    drift: tuple[float, float] = (0.02, 0.18),
    vol: tuple[float, float] = (0.12, 0.45),
    market_beta: float = 0.55,
    start_price: float = 100.0,
) -> MarketData:
    """Correlated geometric Brownian motion with a common market factor.

    A single shared factor produces the positively correlated block structure
    real equity returns show -- which is what makes the covariance term in
    portfolio optimisation non-trivial in the first place.  Useful for demos and
    tests where real price data is not available.
    """
    rng = np.random.default_rng(seed)
    mu = rng.uniform(drift[0], drift[1], size=n_assets)
    sigma = rng.uniform(vol[0], vol[1], size=n_assets)

    dt = 1.0 / TRADING_DAYS
    market = rng.standard_normal(n_days)
    idio = rng.standard_normal((n_days, n_assets))
    betas = market_beta * rng.uniform(0.5, 1.5, size=n_assets)

    shocks = betas[None, :] * market[:, None] + np.sqrt(
        np.clip(1.0 - betas**2, 0.05, None)
    )[None, :] * idio

    increments = (mu - 0.5 * sigma**2)[None, :] * dt + sigma[None, :] * math.sqrt(dt) * shocks
    log_paths = np.cumsum(increments, axis=0)
    prices = start_price * np.exp(np.vstack([np.zeros(n_assets), log_paths]))

    tickers = [f"SYN{i+1:02d}" for i in range(n_assets)]
    return MarketData(tickers=tickers, prices=prices)
