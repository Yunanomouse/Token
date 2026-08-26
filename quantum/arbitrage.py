"""Cyclic arbitrage detection as a QUBO.

An arbitrage cycle is a sequence of conversions returning to the starting
currency with more than you began with:

.. math:: \\prod_{k} R_{i_k, i_{k+1}} > 1

Taking logs turns the product into a sum, so a profitable cycle is a *negative
cycle* under edge weights ``w_ij = -log(R_ij)``.  That has an exact polynomial
classical algorithm -- Bellman-Ford -- included here as
:func:`bellman_ford_negative_cycle`, and it should be your default.

So why formulate it as a QUBO?
------------------------------
Bellman-Ford finds *a* negative cycle.  The problems that are actually hard are
the constrained variants: bounded cycle length, per-venue capacity, fees and
slippage that make profit depend on trade size, and simultaneous selection of
*multiple non-overlapping* cycles.  Those are combinatorial, and they are what
quantum-inspired annealers are marketed for.

Latency reality
---------------
Real HFT arbitrage runs on FPGAs colocated in the exchange, in nanoseconds. A
gate-based quantum computer needs milliseconds just for state preparation and
readout -- roughly six orders of magnitude too slow, and that gap is imposed by
physics, not engineering backlog.  The realistic deployment of this formulation
is :class:`~quantum.solvers.bifurcation.SimulatedBifurcationSolver` on classical
silicon, which is exactly what Toshiba's SQBM+ and Fujitsu's Digital Annealer
sell into this use case today.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .qubo import QUBO
from .solvers import get_solver

__all__ = [
    "ArbitrageCycle",
    "build_rate_matrix",
    "bellman_ford_negative_cycle",
    "cycle_profit",
    "build_cycle_qubo",
    "find_arbitrage",
]


@dataclass
class ArbitrageCycle:
    """A conversion cycle and the profit it realises."""

    path: list[int]
    labels: list[str]
    gross_multiple: float
    profit: float
    method: str
    detail: dict = field(default_factory=dict)

    @property
    def named_path(self) -> list[str]:
        return [self.labels[i] for i in self.path]

    @property
    def profitable(self) -> bool:
        return self.profit > 0.0

    def __repr__(self) -> str:  # pragma: no cover - display helper
        route = " -> ".join(self.named_path + [self.named_path[0]]) if self.path else "(none)"
        return f"<Cycle {route} profit={self.profit:+.4%} via {self.method}>"


def build_rate_matrix(
    rates: dict[tuple[str, str], float],
    currencies: list[str],
    fee: float = 0.0,
) -> np.ndarray:
    """Assemble a dense rate matrix, charging ``fee`` on every conversion.

    Fees matter more than they look: most raw triangular "arbitrage" disappears
    once a realistic per-leg cost is applied, so a detector that ignores them
    reports opportunities that cannot be traded.
    """
    n = len(currencies)
    index = {c: i for i, c in enumerate(currencies)}
    matrix = np.zeros((n, n))
    np.fill_diagonal(matrix, 1.0)
    for (a, b), rate in rates.items():
        if a not in index or b not in index:
            raise ValueError(f"unknown currency in pair ({a}, {b})")
        if rate <= 0:
            raise ValueError("rates must be positive")
        matrix[index[a], index[b]] = rate * (1.0 - fee)
    return matrix


def cycle_profit(rate_matrix: np.ndarray, path: list[int]) -> tuple[float, float]:
    """Gross multiple and net profit of traversing ``path`` and returning to its start."""
    if len(path) < 2:
        return 1.0, 0.0
    multiple = 1.0
    for a, b in zip(path, path[1:] + [path[0]]):
        rate = rate_matrix[a, b]
        if rate <= 0:
            return 0.0, -1.0
        multiple *= rate
    return float(multiple), float(multiple - 1.0)


def bellman_ford_negative_cycle(rate_matrix: np.ndarray) -> list[int] | None:
    """Exact negative-cycle detection on ``w = -log(rate)``.

    Polynomial time, exact, and the correct tool for the unconstrained problem.
    Returns the cycle as a list of node indices, or ``None`` if none exists.
    """
    R = np.asarray(rate_matrix, dtype=np.float64)
    n = R.shape[0]
    with np.errstate(divide="ignore"):
        weights = -np.log(np.where(R > 0, R, np.nan))

    dist = np.zeros(n)
    predecessor = np.full(n, -1, dtype=int)
    updated = -1

    for iteration in range(n):
        updated = -1
        for u in range(n):
            for v in range(n):
                if u == v or not np.isfinite(weights[u, v]):
                    continue
                if dist[u] + weights[u, v] < dist[v] - 1e-12:
                    dist[v] = dist[u] + weights[u, v]
                    predecessor[v] = u
                    updated = v
        if updated == -1:
            return None  # settled with no improving edge: no negative cycle

    # An update on the n-th pass proves a negative cycle; walk back into it.
    node = updated
    for _ in range(n):
        node = predecessor[node]
        if node < 0:
            return None

    cycle = [node]
    walker = predecessor[node]
    while walker != node and walker >= 0:
        cycle.append(walker)
        walker = predecessor[walker]
    cycle.reverse()
    return cycle


# --------------------------------------------------------------------------
# QUBO formulation
# --------------------------------------------------------------------------


def build_cycle_qubo(
    rate_matrix: np.ndarray,
    cycle_length: int = 3,
    start: int = 0,
    penalty: float | None = None,
    labels: list[str] | None = None,
) -> tuple[QUBO, dict]:
    """Encode "best profitable cycle of exactly ``cycle_length``" as a QUBO.

    Variables are ``x[t][i] = 1`` when step ``t`` of the cycle sits at currency
    ``i``.  The start node is pinned to break the rotational symmetry that would
    otherwise give every solution ``cycle_length`` identical copies and make the
    energy landscape needlessly degenerate.

    Constraints, both as quadratic penalties:

    * exactly one currency occupies each step,
    * no currency is visited twice.
    """
    R = np.asarray(rate_matrix, dtype=np.float64)
    n = R.shape[0]
    if R.shape[0] != R.shape[1]:
        raise ValueError("rate matrix must be square")
    if not 2 <= cycle_length <= n:
        raise ValueError("cycle length must be between 2 and the number of currencies")

    with np.errstate(divide="ignore"):
        w = -np.log(np.where(R > 0, R, np.nan))
    big = float(np.nanmax(np.abs(w[np.isfinite(w)]))) * 10.0 if np.isfinite(w).any() else 1.0
    w = np.where(np.isfinite(w), w, big)  # forbid impossible legs by pricing them absurdly

    others = [i for i in range(n) if i != start]
    steps = list(range(1, cycle_length))  # step 0 is pinned to `start`
    n_vars = len(steps) * len(others)

    def var(t_idx: int, c_idx: int) -> int:
        return t_idx * len(others) + c_idx

    Q = np.zeros((n_vars, n_vars))
    linear = np.zeros(n_vars)

    # Opening leg: start -> currency at step 1.
    for c_idx, c in enumerate(others):
        linear[var(0, c_idx)] += w[start, c]

    # Interior legs.
    for t_idx in range(len(steps) - 1):
        for a_idx, a in enumerate(others):
            for b_idx, b in enumerate(others):
                if a == b:
                    continue
                i, j = var(t_idx, a_idx), var(t_idx + 1, b_idx)
                Q[i, j] += w[a, b] / 2.0
                Q[j, i] += w[a, b] / 2.0

    # Closing leg: last step -> back to start.
    for c_idx, c in enumerate(others):
        linear[var(len(steps) - 1, c_idx)] += w[c, start]

    problem = QUBO(
        Q=Q,
        labels=[f"t{steps[t]}:{(labels[others[c]] if labels else others[c])}"
                for t in range(len(steps)) for c in range(len(others))],
        metadata={"cycle_length": cycle_length, "start": start, "n_currencies": n},
    )
    problem.Q[np.diag_indices(n_vars)] += linear

    if penalty is None:
        penalty = max(4.0 * float(np.abs(w[np.isfinite(w)]).max()), 1.0)

    # One currency per step.
    for t_idx in range(len(steps)):
        coeffs = np.zeros(n_vars)
        for c_idx in range(len(others)):
            coeffs[var(t_idx, c_idx)] = 1.0
        problem.add_equality_penalty(coeffs, 1.0, penalty)

    # No currency visited twice: penalise every co-occurrence pair.
    for c_idx in range(len(others)):
        for t1 in range(len(steps)):
            for t2 in range(t1 + 1, len(steps)):
                problem.add_quadratic(var(t1, c_idx), var(t2, c_idx), penalty)

    decoder = {
        "steps": steps,
        "others": others,
        "start": start,
        "cycle_length": cycle_length,
        "penalty": penalty,
    }
    problem.metadata["penalty"] = penalty
    return problem, decoder


def _decode_cycle(assignment: np.ndarray, decoder: dict) -> list[int] | None:
    """Read a cycle out of a binary assignment, or ``None`` if it is malformed."""
    others, steps = decoder["others"], decoder["steps"]
    path = [decoder["start"]]
    for t_idx in range(len(steps)):
        block = assignment[t_idx * len(others) : (t_idx + 1) * len(others)]
        chosen = np.nonzero(block)[0]
        if chosen.size != 1:
            return None  # constraint violated: not exactly one currency at this step
        path.append(others[int(chosen[0])])
    if len(set(path)) != len(path):
        return None  # a currency was revisited
    return path


def find_arbitrage(
    rate_matrix: np.ndarray,
    labels: list[str] | None = None,
    cycle_length: int = 3,
    solver: str = "simulated_bifurcation",
    start: int | None = None,
    **solver_kwargs,
) -> ArbitrageCycle:
    """Search for the most profitable cycle of a fixed length.

    Every start node is tried, since pinning the start breaks symmetry but also
    restricts the search. The classical Bellman-Ford answer is computed alongside
    and reported in ``detail`` so the two can be compared directly.
    """
    R = np.asarray(rate_matrix, dtype=np.float64)
    n = R.shape[0]
    names = labels or [f"C{i}" for i in range(n)]

    starts = range(n) if start is None else [start]
    best_path: list[int] | None = None
    best_profit = -np.inf
    infeasible = 0

    for s in starts:
        problem, decoder = build_cycle_qubo(R, cycle_length, start=s, labels=names)
        result = get_solver(solver).solve(problem, **solver_kwargs)
        path = _decode_cycle(result.assignment, decoder)
        if path is None:
            infeasible += 1
            continue
        _, profit = cycle_profit(R, path)
        if profit > best_profit:
            best_profit, best_path = profit, path

    classical = bellman_ford_negative_cycle(R)
    classical_profit = cycle_profit(R, classical)[1] if classical else 0.0

    if best_path is None:
        return ArbitrageCycle(
            path=[],
            labels=names,
            gross_multiple=1.0,
            profit=0.0,
            method=f"qubo/{solver}",
            detail={
                "infeasible_solves": infeasible,
                "classical_cycle": classical,
                "classical_profit": classical_profit,
            },
        )

    multiple, profit = cycle_profit(R, best_path)
    return ArbitrageCycle(
        path=best_path,
        labels=names,
        gross_multiple=multiple,
        profit=profit,
        method=f"qubo/{solver}",
        detail={
            "cycle_length": cycle_length,
            "infeasible_solves": infeasible,
            "classical_cycle": classical,
            "classical_cycle_named": [names[i] for i in classical] if classical else None,
            "classical_profit": classical_profit,
        },
    )
