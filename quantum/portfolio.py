"""Constrained portfolio optimisation compiled to QUBO.

Why this problem, and not plain Markowitz
-----------------------------------------
Unconstrained mean-variance optimisation is a *solved convex problem*: the
optimal weights are ``Sigma^-1 mu / 2q`` in closed form, and no quantum computer
will ever improve on a matrix solve.  :func:`unconstrained_mean_variance` is
included here precisely to make that concrete.

What breaks classical solvers is the **discrete** structure real mandates carry:

* hold *exactly* K names (cardinality),
* trade in whole lots, not fractional weights,
* respect per-sector caps,
* honour a minimum position size when a name is held at all,
* pay transaction costs on every change from current holdings.

Each of these turns a convex program into a combinatorial one -- NP-hard in
general, and exactly the shape that maps onto an Ising ground state.  That is
the honest case for quantum optimisation in finance, and it is what this module
builds.

Two encodings
-------------
``"select"``
    One bit per asset, equal weight across the chosen names.  ``n`` variables.
    Compact and the right default for a screening or cardinality mandate.

``"lots"``
    ``B`` bits per asset encoding an integer number of lots.  ``n * B``
    variables.  Expresses genuine position sizing at a real cost in width, which
    is what actually limits problem size on hardware.
"""

from __future__ import annotations

import itertools
import math
import time
from dataclasses import dataclass, field

import numpy as np

from .qubo import QUBO
from .solvers import get_solver
from .solvers.base import SolverResult

__all__ = [
    "PortfolioConstraints",
    "PortfolioProblem",
    "PortfolioResult",
    "unconstrained_mean_variance",
    "exhaustive_cardinality",
    "solve_portfolio",
]


# --------------------------------------------------------------------------
# Classical references
# --------------------------------------------------------------------------


def unconstrained_mean_variance(
    expected_returns: np.ndarray,
    covariance: np.ndarray,
    risk_aversion: float = 1.0,
    long_only: bool = False,
) -> np.ndarray:
    """Closed-form Markowitz weights, normalised to sum to one.

    This is the "quantum computers will not help here" baseline.  It is a single
    linear solve; on thousands of assets it takes milliseconds.
    """
    mu = np.asarray(expected_returns, dtype=np.float64).reshape(-1)
    cov = np.asarray(covariance, dtype=np.float64)
    if risk_aversion <= 0:
        raise ValueError("risk aversion must be positive")

    raw = np.linalg.pinv(2.0 * risk_aversion * cov) @ mu
    if long_only:
        raw = np.clip(raw, 0.0, None)
    total = raw.sum()
    if abs(total) < 1e-12:
        return np.full(mu.size, 1.0 / mu.size)
    return raw / total


def exhaustive_cardinality(
    expected_returns: np.ndarray,
    covariance: np.ndarray,
    cardinality: int,
    risk_aversion: float = 1.0,
) -> tuple[np.ndarray, float]:
    """True optimum over all ``C(n, K)`` equal-weighted subsets.

    Exponential, so it is only usable on small universes -- but it is the only
    way to *prove* a heuristic found the right portfolio rather than a plausible
    one.  Returns ``(selection_mask, objective_value)``.
    """
    mu = np.asarray(expected_returns, dtype=np.float64).reshape(-1)
    cov = np.asarray(covariance, dtype=np.float64)
    n = mu.size
    if not 1 <= cardinality <= n:
        raise ValueError("cardinality must be between 1 and the number of assets")
    if math.comb(n, cardinality) > 2_000_000:
        raise ValueError("too many subsets to enumerate exhaustively")

    best_mask, best_value = None, np.inf
    for combo in itertools.combinations(range(n), cardinality):
        idx = np.array(combo)
        w = np.zeros(n)
        w[idx] = 1.0 / cardinality
        value = risk_aversion * float(w @ cov @ w) - float(mu @ w)
        if value < best_value:
            best_value, best_mask = value, w > 0
    assert best_mask is not None
    return best_mask.astype(int), float(best_value)


# --------------------------------------------------------------------------
# Problem definition
# --------------------------------------------------------------------------


@dataclass
class PortfolioConstraints:
    """The discrete constraints that make this problem hard."""

    cardinality: int | None = None
    """Hold exactly this many names."""

    sectors: list[str] | None = None
    """Sector label per asset; required if ``sector_caps`` is used."""

    sector_caps: dict[str, float] = field(default_factory=dict)
    """Maximum total weight per sector.  Each cap costs slack bits."""

    max_weight: float = 1.0
    """Cap on any single position (``lots`` encoding)."""

    current_holdings: np.ndarray | None = None
    """Existing weights, for transaction-cost accounting."""

    transaction_cost: float = 0.0
    """Proportional cost charged on any change from ``current_holdings``."""

    def validate(self, n_assets: int) -> None:
        if self.cardinality is not None and not 1 <= self.cardinality <= n_assets:
            raise ValueError("cardinality must lie between 1 and the asset count")
        if self.sector_caps and self.sectors is None:
            raise ValueError("sector_caps requires a sectors list")
        if self.sectors is not None and len(self.sectors) != n_assets:
            raise ValueError("sectors list length must match the asset count")
        if self.current_holdings is not None and len(self.current_holdings) != n_assets:
            raise ValueError("current_holdings length must match the asset count")
        if not 0.0 < self.max_weight <= 1.0:
            raise ValueError("max_weight must lie in (0, 1]")
        if self.transaction_cost < 0:
            raise ValueError("transaction cost cannot be negative")


@dataclass
class PortfolioProblem:
    """A constrained mean-variance problem, compilable to QUBO."""

    expected_returns: np.ndarray
    covariance: np.ndarray
    tickers: list[str] = field(default_factory=list)
    risk_aversion: float = 1.0
    constraints: PortfolioConstraints = field(default_factory=PortfolioConstraints)
    encoding: str = "select"
    n_lot_bits: int = 2
    penalty: float | None = None
    slack_bits: int = 3

    def __post_init__(self) -> None:
        self.expected_returns = np.asarray(self.expected_returns, dtype=np.float64).reshape(-1)
        self.covariance = np.asarray(self.covariance, dtype=np.float64)
        n = self.n_assets
        if self.covariance.shape != (n, n):
            raise ValueError("covariance shape does not match the expected-return vector")
        if not self.tickers:
            self.tickers = [f"A{i+1}" for i in range(n)]
        if len(self.tickers) != n:
            raise ValueError("ticker count does not match the asset count")
        if self.encoding not in ("select", "lots"):
            raise ValueError("encoding must be 'select' or 'lots'")
        if self.risk_aversion <= 0:
            raise ValueError("risk aversion must be positive")
        self.constraints.validate(n)

    @property
    def n_assets(self) -> int:
        return int(self.expected_returns.size)

    # -- weight encoding ---------------------------------------------------
    def _weight_matrix(self) -> np.ndarray:
        """Matrix ``A`` mapping the binary vector to portfolio weights, ``w = A y``."""
        n = self.n_assets
        if self.encoding == "select":
            k = self.constraints.cardinality or n
            return np.eye(n) / float(k)

        b = self.n_lot_bits
        levels = 2**b - 1
        unit = self.constraints.max_weight / levels
        A = np.zeros((n, n * b))
        for i in range(n):
            for bit in range(b):
                A[i, i * b + bit] = unit * (2**bit)
        return A

    def variable_labels(self) -> list[str]:
        if self.encoding == "select":
            return list(self.tickers)
        return [
            f"{self.tickers[i]}:2^{bit}"
            for i in range(self.n_assets)
            for bit in range(self.n_lot_bits)
        ]

    # -- compilation -------------------------------------------------------
    def to_qubo(self, include_cardinality_penalty: bool = True) -> QUBO:
        """Compile the problem, penalties and all, into a single QUBO.

        Set ``include_cardinality_penalty=False`` for a solver that enforces
        cardinality structurally rather than by penalty -- see
        :func:`quantum.subspace.subspace_qaoa`.  The penalty is constant across
        the feasible set, so including it there would add only a fixed offset.
        """
        n = self.n_assets
        A = self._weight_matrix()
        n_vars = A.shape[1]
        q = self.risk_aversion

        # Objective: q * w' Sigma w - mu' w, with w = A y.
        Q = q * (A.T @ self.covariance @ A)
        linear = -(self.expected_returns @ A)

        # Transaction costs. For binary y, |w_i - w0_i| is not quadratic in
        # general, so we charge the cost against distance from current holdings
        # in the linear term, which is exact for the "select" encoding (where a
        # position is either on or off) and a first-order approximation for lots.
        c = self.constraints
        if c.transaction_cost > 0 and c.current_holdings is not None:
            held = np.asarray(c.current_holdings, dtype=np.float64).reshape(-1)
            per_unit = A.sum(axis=0) if self.encoding == "lots" else np.ones(n_vars)
            direction = np.sign(A.T @ np.ones(n) * 0 + 1.0)  # all positions are buys/sells alike
            asset_of = (
                np.arange(n)
                if self.encoding == "select"
                else np.repeat(np.arange(n), self.n_lot_bits)
            )
            # Turning a position on costs when it is currently off, and vice versa.
            linear = linear + c.transaction_cost * per_unit * direction * (1.0 - 2.0 * held[asset_of])

        problem = QUBO(
            Q=Q,
            offset=0.0,
            labels=self.variable_labels(),
            metadata={"encoding": self.encoding, "n_assets": n},
        )
        problem.Q[np.diag_indices(n_vars)] += linear

        # Size penalties against the objective's own magnitude, per constraint.
        objective_scale = max(
            float(np.abs(problem.Q).max()), float(np.abs(linear).max()), 1e-12
        )

        def weight_for(coefficients: np.ndarray) -> float:
            if self.penalty is not None:
                return float(self.penalty)
            return problem.suggest_penalty_for(
                coefficients, scale=4.0, objective_scale=objective_scale
            )

        penalties: dict[str, float] = {}

        # Cardinality: sum of selection bits == K.
        if (
            c.cardinality is not None
            and self.encoding == "select"
            and include_cardinality_penalty
        ):
            coeffs = np.ones(n_vars)
            penalties["cardinality"] = weight_for(coeffs)
            problem.add_equality_penalty(coeffs, float(c.cardinality), penalties["cardinality"])
        elif self.encoding == "lots":
            # Fully invested: weights sum to one.  Coefficients here are lot
            # weights (O(0.05)), so the penalty must be scaled up accordingly.
            coeffs = A.sum(axis=0)
            penalties["budget"] = weight_for(coeffs)
            problem.add_equality_penalty(coeffs, 1.0, penalties["budget"])

        # Sector caps become inequalities, each paid for in slack bits.
        if c.sector_caps:
            assert c.sectors is not None
            asset_of = (
                np.arange(n)
                if self.encoding == "select"
                else np.repeat(np.arange(n), self.n_lot_bits)
            )
            for sector, cap in c.sector_caps.items():
                members = np.array([1.0 if c.sectors[a] == sector else 0.0 for a in asset_of])
                if members.sum() == 0:
                    continue
                weights_of_vars = A.sum(axis=0) * members
                # Each cap appends its own slack bits, so the problem widens as
                # we go; pad earlier coefficient vectors out to the current width
                # rather than assuming it is still the decision-variable count.
                coeffs = np.zeros(problem.n_vars)
                coeffs[: weights_of_vars.size] = weights_of_vars
                penalties[f"sector:{sector}"] = weight_for(coeffs)
                problem, _ = problem.add_inequality_penalty_upper(
                    coeffs, float(cap), penalties[f"sector:{sector}"], n_slack_bits=self.slack_bits
                )

        problem.metadata.update(
            {
                "penalties": penalties,
                "objective_scale": objective_scale,
                "n_slack": problem.n_vars - n_vars,
                "n_decision_vars": n_vars,
            }
        )
        return problem

    # -- decoding ----------------------------------------------------------
    def decode(self, assignment: np.ndarray) -> np.ndarray:
        """Raw weights implied by a binary assignment, *before* any budget repair.

        These satisfy the encoded per-asset cap exactly but need not sum to one:
        the budget is enforced by a soft penalty, and on a coarse lot grid an
        exact sum of one may not even be representable.  Use
        :meth:`decode_normalised` for the weights you would actually trade.
        """
        A = self._weight_matrix()
        y = np.asarray(assignment, dtype=np.float64).reshape(-1)[: A.shape[1]]
        return A @ y

    def decode_normalised(self, assignment: np.ndarray) -> tuple[np.ndarray, float]:
        """Tradeable weights plus the rescaling factor applied to reach them.

        Returns ``(weights, raw_sum)``.  Rescaling is a *repair*, not part of the
        optimisation: it can push an individual position above ``max_weight``
        even though the encoding respected the cap, so callers must re-check.
        Reporting the factor makes that visible instead of hiding it.
        """
        w = self.decode(assignment)
        raw_sum = float(w.sum())
        if raw_sum > 1e-12:
            w = w / raw_sum
        return w, raw_sum

    def lot_grid(self) -> np.ndarray:
        """The weights a single asset can take under the current encoding."""
        if self.encoding == "select":
            k = self.constraints.cardinality or self.n_assets
            return np.array([0.0, 1.0 / k])
        levels = 2**self.n_lot_bits - 1
        unit = self.constraints.max_weight / levels
        return unit * np.arange(levels + 1)


# --------------------------------------------------------------------------
# Result
# --------------------------------------------------------------------------


@dataclass
class PortfolioResult:
    """A decoded portfolio with its risk/return profile and feasibility report."""

    weights: np.ndarray
    tickers: list[str]
    expected_return: float
    volatility: float
    objective: float
    solver_result: SolverResult
    qubo: QUBO
    feasibility: dict = field(default_factory=dict)
    detail: dict = field(default_factory=dict)

    @property
    def sharpe(self) -> float:
        return self.expected_return / self.volatility if self.volatility > 0 else float("nan")

    @property
    def holdings(self) -> dict[str, float]:
        return {t: float(w) for t, w in zip(self.tickers, self.weights) if w > 1e-9}

    @property
    def feasible(self) -> bool:
        return all(self.feasibility.values()) if self.feasibility else True

    def report(self) -> str:
        lines = [
            f"solver          : {self.solver_result.solver} "
            f"({self.solver_result.runtime_seconds:.3f}s)",
            f"expected return : {self.expected_return:>8.2%}",
            f"volatility      : {self.volatility:>8.2%}",
            f"sharpe          : {self.sharpe:>8.2f}",
            f"objective       : {self.objective:>8.4f}",
            f"raw budget      : {self.detail.get('raw_weight_sum', float('nan')):>8.4f}"
            f"  (rescaled by {self.detail.get('rescale_factor', float('nan')):.4f})",
            f"feasible        : {self.feasible}",
            "",
            "holdings:",
        ]
        for ticker, weight in sorted(self.holdings.items(), key=lambda kv: -kv[1]):
            bar = "#" * max(1, int(round(weight * 40)))
            lines.append(f"  {ticker:<10}{weight:>7.2%}  {bar}")
        if self.feasibility:
            lines.append("\nconstraint checks:")
            for name, ok in self.feasibility.items():
                lines.append(f"  {'PASS' if ok else 'FAIL'}  {name}")
        return "\n".join(lines)

    def __repr__(self) -> str:  # pragma: no cover - display helper
        return (
            f"<Portfolio ret={self.expected_return:.2%} vol={self.volatility:.2%} "
            f"sharpe={self.sharpe:.2f} n={len(self.holdings)} feasible={self.feasible}>"
        )


def solve_portfolio(
    problem: PortfolioProblem,
    solver: str = "simulated_annealing",
    **solver_kwargs,
) -> PortfolioResult:
    """Compile, solve, decode and check a constrained portfolio problem.

    ``solver="subspace_qaoa"`` takes the constraint-preserving route: the
    cardinality penalty is dropped and the search runs inside the
    ``C(n, K)``-dimensional feasible subspace instead.  Every candidate it can
    produce holds exactly ``K`` names, so feasibility is structural rather than
    something a penalty weight has to buy.
    """
    if solver in ("subspace_qaoa", "xy_qaoa"):
        return _solve_portfolio_subspace(problem, **solver_kwargs)
    if solver in ("grover", "grover_search"):
        return _solve_portfolio_grover(problem, **solver_kwargs)

    qubo = problem.to_qubo()
    result = get_solver(solver).solve(qubo, **solver_kwargs)
    return _finalise_portfolio(problem, qubo, result)


def _solve_portfolio_subspace(problem: PortfolioProblem, **kwargs) -> "PortfolioResult":
    """Cardinality-constrained portfolio via Hamming-weight-preserving QAOA."""
    from .solvers.base import SolverResult
    from .subspace import subspace_qaoa

    cardinality = problem.constraints.cardinality
    if cardinality is None:
        raise ValueError("subspace_qaoa requires a cardinality constraint")
    if problem.encoding != "select":
        raise ValueError("subspace_qaoa requires the 'select' encoding")

    bare = problem.to_qubo(include_cardinality_penalty=False)
    started = time.perf_counter()
    outcome = subspace_qaoa(bare, cardinality, **kwargs)
    elapsed = time.perf_counter() - started

    result = SolverResult(
        assignment=outcome.assignment,
        energy=outcome.energy,
        solver="subspace_qaoa",
        runtime_seconds=elapsed,
        samples_evaluated=outcome.subspace_dimension,
        detail={
            "compression": outcome.compression,
            "expectation_value": outcome.expectation,
            "ground_state_probability": outcome.ground_state_probability,
            **outcome.detail,
        },
    )
    return _finalise_portfolio(problem, bare, result)


def _solve_portfolio_grover(problem: PortfolioProblem, **kwargs) -> "PortfolioResult":
    """Cardinality-constrained portfolio by Grover adaptive search.

    Searches the ``C(n, K)`` feasible portfolios directly, so the quadratic
    query advantage applies to an already-reduced candidate set.

    In simulation this is **slower** than scanning the table -- building the cost
    vector is already an exhaustive pass, and each Grover iteration touches every
    amplitude.  The advantage is a hardware query bound, and the guarantee is
    against exhaustive search rather than against a good heuristic.  See
    :mod:`quantum.search`.
    """
    from .search import grover_adaptive_search
    from .solvers.base import SolverResult
    from .subspace import HammingSubspace

    cardinality = problem.constraints.cardinality
    if cardinality is None:
        raise ValueError("grover search requires a cardinality constraint")
    if problem.encoding != "select":
        raise ValueError("grover search requires the 'select' encoding")

    bare = problem.to_qubo(include_cardinality_penalty=False)
    subspace = HammingSubspace.build(problem.n_assets, cardinality)
    costs = subspace.costs(bare)

    started = time.perf_counter()
    outcome = grover_adaptive_search(costs, **kwargs)
    elapsed = time.perf_counter() - started

    result = SolverResult(
        assignment=subspace.bitstring(outcome.index),
        energy=outcome.value,
        solver="grover",
        runtime_seconds=elapsed,
        samples_evaluated=outcome.oracle_calls,
        detail={
            "oracle_calls": outcome.oracle_calls,
            "feasible_candidates": outcome.n_items,
            "exhaustive_calls": outcome.classical_exhaustive_calls,
            "query_speedup_vs_exhaustive": outcome.query_speedup_vs_exhaustive,
            "simulated_element_ops": outcome.simulated_element_ops,
            "hardware_note": outcome.hardware_note(),
            "found_optimum": outcome.found_optimum,
            "rounds": outcome.rounds,
            **outcome.detail,
        },
    )
    return _finalise_portfolio(problem, bare, result)


def _finalise_portfolio(problem, qubo, result):
    """Decode a solver assignment and verify it against the stated constraints."""
    raw_weights = problem.decode(result.assignment)
    weights, raw_sum = problem.decode_normalised(result.assignment)
    expected_return = float(problem.expected_returns @ weights)
    variance = float(weights @ problem.covariance @ weights)
    volatility = math.sqrt(max(variance, 0.0))
    objective = problem.risk_aversion * variance - expected_return

    # Verify constraints on the decoded portfolio rather than trusting that the
    # penalty terms were large enough -- soft penalties can and do get violated.
    c = problem.constraints
    checks: dict[str, bool] = {}
    n_held = int(np.sum(weights > 1e-9))
    if c.cardinality is not None:
        checks[f"cardinality == {c.cardinality}"] = n_held == c.cardinality
    checks["long only"] = bool(np.all(weights >= -1e-12))
    # The budget is a soft penalty, so record how far the raw solution actually
    # landed from fully invested rather than hiding it behind the rescale.
    checks["budget within 5% before rescale"] = abs(raw_sum - 1.0) <= 0.05 + 1e-9
    if problem.encoding == "lots":
        checks[f"max weight <= {c.max_weight:.0%} (encoded)"] = bool(
            np.all(raw_weights <= c.max_weight + 1e-9)
        )
        checks[f"max weight <= {c.max_weight:.0%} (after rescale)"] = bool(
            np.all(weights <= c.max_weight + 1e-6)
        )
    if c.sector_caps and c.sectors is not None:
        for sector, cap in c.sector_caps.items():
            mask = np.array([s == sector for s in c.sectors])
            exposure = float(weights[mask].sum())
            checks[f"sector {sector} <= {cap:.0%}"] = exposure <= cap + 1e-6

    return PortfolioResult(
        weights=weights,
        tickers=list(problem.tickers),
        expected_return=expected_return,
        volatility=volatility,
        objective=objective,
        solver_result=result,
        qubo=qubo,
        feasibility=checks,
        detail={
            "n_held": n_held,
            "encoding": problem.encoding,
            "n_qubo_vars": qubo.n_vars,
            "qubo_metadata": qubo.metadata,
            "raw_weights": raw_weights.tolist(),
            "raw_weight_sum": raw_sum,
            "rescale_factor": (1.0 / raw_sum) if raw_sum > 1e-12 else float("nan"),
            "lot_grid": problem.lot_grid().tolist(),
        },
    )
