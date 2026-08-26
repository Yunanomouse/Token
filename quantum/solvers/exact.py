"""Exhaustive solver -- ground truth for validating every heuristic."""

from __future__ import annotations

import time

import numpy as np

from ..qubo import QUBO
from .base import Solver, SolverResult

__all__ = ["ExactSolver"]


class ExactSolver(Solver):
    """Enumerate all ``2**n`` assignments.

    Exponential by construction, so it is capped at 22 variables.  Its purpose is
    not to compete but to tell you whether the heuristics are actually finding
    the optimum on problems small enough to check.
    """

    name = "exact"

    def solve(self, problem: QUBO, max_vars: int = 22, **kwargs) -> SolverResult:
        if problem.n_vars > max_vars:
            raise ValueError(
                f"exact solver refuses {problem.n_vars} variables (limit {max_vars}); "
                "use simulated annealing or bifurcation instead"
            )
        start = time.perf_counter()
        energies = problem.energies_all()
        best = int(np.argmin(energies))
        n = problem.n_vars
        bits = np.array([(best >> (n - 1 - i)) & 1 for i in range(n)], dtype=int)
        return SolverResult(
            assignment=bits,
            energy=float(energies[best]),
            solver=self.name,
            runtime_seconds=time.perf_counter() - start,
            samples_evaluated=2**n,
            detail={"proven_optimal": True},
        )
