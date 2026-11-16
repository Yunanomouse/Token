"""Common result type and interface for every QUBO solver."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..qubo import QUBO

__all__ = ["SolverResult", "Solver"]


@dataclass
class SolverResult:
    """The best assignment a solver found, plus enough context to judge it."""

    assignment: np.ndarray
    energy: float
    solver: str
    runtime_seconds: float = 0.0
    samples_evaluated: int = 0
    energy_history: list[float] = field(default_factory=list)
    detail: dict = field(default_factory=dict)

    @property
    def selected(self) -> list[int]:
        return [i for i, v in enumerate(self.assignment) if v == 1]

    def gap_to(self, optimal_energy: float) -> float:
        """Absolute energy gap to a known optimum (0.0 means the solver found it)."""
        return float(self.energy - optimal_energy)

    def __repr__(self) -> str:  # pragma: no cover - display helper
        return (
            f"<{self.solver} energy={self.energy:.6f} "
            f"selected={self.selected} time={self.runtime_seconds:.3f}s>"
        )


class Solver:
    """Interface every solver implements.

    Keeping this uniform is the point of the QUBO layer: the same portfolio
    problem can be handed to a classical annealer, a quantum-inspired
    bifurcation machine, or QAOA on a simulated QPU without being rewritten.
    """

    name = "solver"

    def solve(self, problem: QUBO, **kwargs) -> SolverResult:  # pragma: no cover - abstract
        raise NotImplementedError
