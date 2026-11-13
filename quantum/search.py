"""Grover adaptive search -- quadratic speedup over exhaustive portfolio selection.

Grover's algorithm finds a marked item among ``N`` in ``O(sqrt(N))`` oracle
queries instead of ``O(N)``.  Turning that into an *optimiser* is Durr-Hoyer
minimum finding, refined for binary optimisation as Grover Adaptive Search
(Gilliam, Woerner & Gonciulea 2021):

1. Pick any candidate; its cost becomes the threshold.
2. Amplitude-amplify the states costing *less* than the threshold and measure.
3. A better candidate lowers the threshold; repeat.

Each round is a Grover search over an unknown number of marked items, so the
iteration count is drawn at random from a window that grows by ``8/7`` on
failure -- the Boyer-Brassard-Hoyer-Tapp schedule, which keeps the expected
total at ``O(sqrt(N))`` without knowing how many items are marked.

Combined with :mod:`quantum.subspace`, the search runs over the ``C(n, K)``
*feasible* portfolios rather than all ``2**n`` assignments, so the quadratic
speedup applies to an already-reduced set: ``sqrt(C(n, K))`` against ``2**n``.

Read this before quoting the speedup
------------------------------------
``sqrt(N)`` is a **query-complexity** result, and in *simulation* it buys
nothing.  Two measured facts make that concrete, on ``C(18,5) = 8568``
candidates:

* Building the cost table is itself an exhaustive ``O(N)`` scan, and a plain
  ``np.argmin`` over it returns the exact optimum in 57 microseconds.  The
  search cannot beat a scan it already performed.
* Each Grover iteration touches all ``N`` amplitudes, so simulating 140 oracle
  calls costs ~1.2 million element operations against 8,568 for the argmin --
  simulated Grover does roughly **140x more work** than simply looking.

The speedup is real only on hardware, where the oracle evaluates the cost *in
superposition* and a query is genuinely ``O(1)`` in the candidate count.  This
implementation exists to get the algorithm right and to count queries honestly,
not to run faster.

Even on hardware, the comparison is against **exhaustive** search, not against a
good heuristic.  Simulated annealing and simulated bifurcation find these optima
routinely without examining ``N`` candidates.  What Grover offers is a
*worst-case* bound needing no structure in the landscape; a heuristic offers a
good average case with no guarantee.  Those are different products.

The diffusion operator acts directly on the candidate vector rather than a qubit
register, which is exact and works for any ``N`` -- including the
non-power-of-two ``C(n, K)``.  A hardware implementation additionally needs the
cost comparison as a reversible arithmetic circuit, which is the dominant real
cost and the one this simulation skips entirely.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

__all__ = [
    "GroverSearchResult",
    "grover_iterations_for",
    "amplify",
    "grover_adaptive_search",
]


def grover_iterations_for(n_items: int, n_marked: int) -> int:
    """Optimal Grover iteration count, ``(pi/4) sqrt(N/k)``."""
    if n_marked <= 0 or n_items <= 0:
        return 0
    if n_marked >= n_items:
        return 0
    return max(1, int(round((math.pi / 4.0) * math.sqrt(n_items / n_marked))))


def amplify(amplitudes: np.ndarray, marked: np.ndarray, iterations: int) -> np.ndarray:
    """Apply ``iterations`` Grover rotations, in place.

    Two reflections per iteration: a phase flip on the marked set, then the
    inversion-about-the-mean diffusion ``2|s><s| - I``.  Written as an explicit
    mean subtraction, which is both the exact operator and ``O(N)`` per
    iteration with no allocation.
    """
    if iterations <= 0 or not marked.any():
        return amplitudes
    for _ in range(iterations):
        amplitudes[marked] *= -1.0          # oracle: phase flip the good states
        mean = amplitudes.mean()
        np.subtract(2.0 * mean, amplitudes, out=amplitudes)  # diffusion
    return amplitudes


@dataclass
class GroverSearchResult:
    """Outcome of a Grover adaptive search, with its cost accounting."""

    index: int
    value: float
    oracle_calls: int
    rounds: int
    n_items: int
    found_optimum: bool
    detail: dict = field(default_factory=dict)

    @property
    def classical_exhaustive_calls(self) -> int:
        """What a guaranteed classical scan would cost: every item."""
        return self.n_items

    @property
    def query_speedup_vs_exhaustive(self) -> float:
        """Oracle-query ratio against exhaustive search.

        Named for what it is.  This is the *hardware* figure of merit and says
        nothing about wall-clock in simulation -- see
        :attr:`simulated_element_ops`.
        """
        return self.classical_exhaustive_calls / max(self.oracle_calls, 1)

    @property
    def simulated_element_ops(self) -> int:
        """Actual work this simulation did: every iteration touches all N amplitudes."""
        return self.n_items * max(self.oracle_calls, 1)

    @property
    def simulation_overhead_vs_argmin(self) -> float:
        """How much *slower* simulating this was than simply scanning the table."""
        return self.simulated_element_ops / max(self.n_items, 1)

    def hardware_note(self) -> str:
        return (
            "Simulated at the amplitude level, and slower than a plain argmin: "
            f"{self.simulated_element_ops:,} element operations against "
            f"{self.n_items:,} for a scan. The sqrt(N) advantage is in oracle "
            "*queries* and is realisable only on hardware, where the oracle "
            "evaluates the cost in superposition. Such hardware would also need "
            "the cost comparison compiled into a reversible arithmetic circuit "
            "with ancillas -- the dominant real cost, skipped here."
        )

    def __repr__(self) -> str:  # pragma: no cover - display helper
        return (
            f"<Grover value={self.value:.6f} oracle_calls={self.oracle_calls} "
            f"of N={self.n_items} ({self.query_speedup_vs_exhaustive:.1f}x queries) "
            f"optimal={self.found_optimum}>"
        )


def grover_adaptive_search(
    costs: np.ndarray,
    max_oracle_calls: int | None = None,
    rng: np.random.Generator | None = None,
    growth: float = 8.0 / 7.0,
    restart_on_improvement: bool = True,
) -> GroverSearchResult:
    """Minimise ``costs`` by Durr-Hoyer / Grover adaptive search.

    Parameters
    ----------
    costs:
        Objective value of every candidate.  In the portfolio case these are the
        ``C(n, K)`` feasible portfolios, already excluding infeasible ones.
    max_oracle_calls:
        Budget, defaulting to ``ceil(8 * sqrt(N))`` -- comfortably above the
        expected ``O(sqrt(N))`` while still far below an exhaustive ``N``.
    growth:
        Window growth factor on a failed round.  ``8/7`` is the
        Boyer-Brassard-Hoyer-Tapp value.
    """
    rng = rng or np.random.default_rng()
    costs = np.asarray(costs, dtype=np.float64).reshape(-1)
    n_items = int(costs.size)
    if n_items == 0:
        raise ValueError("nothing to search")
    if n_items == 1:
        return GroverSearchResult(0, float(costs[0]), 0, 0, 1, True)

    budget = max_oracle_calls or int(math.ceil(8.0 * math.sqrt(n_items)))
    true_min = float(costs.min())

    best_index = int(rng.integers(n_items))
    best_value = float(costs[best_index])
    oracle_calls = 0
    rounds = 0
    window = 1.0
    limit = math.sqrt(n_items)
    history: list[float] = [best_value]

    uniform = 1.0 / math.sqrt(n_items)

    while oracle_calls < budget:
        marked = costs < best_value
        n_marked = int(marked.sum())
        if n_marked == 0:
            break  # nothing better exists: the threshold is already optimal

        rounds += 1
        iterations = int(rng.integers(0, max(1, int(math.ceil(window)))))
        iterations = min(iterations, budget - oracle_calls)

        amplitudes = np.full(n_items, uniform, dtype=np.float64)
        amplify(amplitudes, marked, iterations)
        oracle_calls += iterations

        probabilities = amplitudes**2
        total = probabilities.sum()
        if total <= 0:
            break
        sampled = int(rng.choice(n_items, p=probabilities / total))
        oracle_calls += 1  # the measurement itself is one evaluation

        if costs[sampled] < best_value:
            best_index, best_value = sampled, float(costs[sampled])
            history.append(best_value)
            if restart_on_improvement:
                window = 1.0
        else:
            # Failed round: widen the window, capped so it cannot exceed sqrt(N).
            window = min(window * growth, limit)

    return GroverSearchResult(
        index=best_index,
        value=best_value,
        oracle_calls=oracle_calls,
        rounds=rounds,
        n_items=n_items,
        found_optimum=abs(best_value - true_min) < 1e-9,
        detail={
            "budget": budget,
            "true_minimum": true_min,
            "gap": best_value - true_min,
            "improvement_history": history,
            "expected_scaling": math.sqrt(n_items),
        },
    )
