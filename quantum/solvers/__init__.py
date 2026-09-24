"""QUBO solver registry.

Three families, all consuming the same :class:`~quantum.qubo.QUBO`:

===========================  ==========================  =================================
Solver                       Family                      Realistic today?
===========================  ==========================  =================================
``exact``                    exhaustive                  only below ~22 variables
``simulated_annealing``      classical thermal           yes -- the baseline to beat
``simulated_bifurcation``    quantum-derived, classical  yes -- ships on FPGAs/GPUs now
``qaoa``                     gate-based quantum          no -- research scale only
===========================  ==========================  =================================
"""

from __future__ import annotations

from .annealing import SimulatedAnnealingSolver
from .base import Solver, SolverResult
from .bifurcation import SimulatedBifurcationSolver
from .exact import ExactSolver
from .qaoa import QAOASolver

__all__ = [
    "Solver",
    "SolverResult",
    "ExactSolver",
    "SimulatedAnnealingSolver",
    "SimulatedBifurcationSolver",
    "QAOASolver",
    "get_solver",
    "available_solvers",
    "SOLVERS",
]

SOLVERS: dict[str, type[Solver]] = {
    ExactSolver.name: ExactSolver,
    SimulatedAnnealingSolver.name: SimulatedAnnealingSolver,
    SimulatedBifurcationSolver.name: SimulatedBifurcationSolver,
    QAOASolver.name: QAOASolver,
}

_ALIASES = {
    "sa": "simulated_annealing",
    "anneal": "simulated_annealing",
    "annealing": "simulated_annealing",
    "sb": "simulated_bifurcation",
    "bifurcation": "simulated_bifurcation",
    "brute": "exact",
    "bruteforce": "exact",
}


def available_solvers() -> list[str]:
    return sorted(SOLVERS)


def get_solver(name: str) -> Solver:
    """Instantiate a solver by name or alias."""
    key = _ALIASES.get(name.strip().lower(), name.strip().lower())
    if key not in SOLVERS:
        raise ValueError(
            f"unknown solver {name!r}; available: {', '.join(available_solvers())}"
        )
    return SOLVERS[key]()
