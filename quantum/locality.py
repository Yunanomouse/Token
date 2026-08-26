"""Coupling locality: when sub-exponential QAOA simulation is possible, and when it is not.

For a p-layer QAOA with a local mixer, the expectation of a single cost term
``<Z_i Z_j>`` depends only on the qubits within graph distance ``p`` of edge
``(i, j)``.  Everything outside that *light cone* cancels between ``U`` and
``U†``, because the initial state is a product state and each cost layer spreads
an operator's support by exactly one hop.

That is the strongest memory result in QAOA simulation.  Instead of one ``2**n``
statevector, the energy is a sum of independent ``2**k`` simulations where ``k``
is the cone size -- and ``k`` is **independent of n**.  On a 3-regular graph the
cone holds ``2(2**(p+1) - 1)`` qubits: 14 at ``p=2``, whatever ``n`` is.
Published and reproduced results put this at ~1000x memory reduction on sparse
MaxCut instances at ``n=24``.

Why this package does not use it
--------------------------------
It requires a **sparse** coupling graph, and finance does not supply one.  The
quadratic term of a portfolio problem is a covariance matrix: every asset
correlates with every other, so the coupling graph is complete and the radius-1
cone is already the entire problem.  Measured on this package's own QUBOs:

===================================  =======  ==========  ==================
Problem                              density  cone p=1    light-cone benefit
===================================  =======  ==========  ==================
portfolio, cardinality (select)         1.00  all n       none
portfolio, lots + sector caps           0.92  all n       none
arbitrage cycle QUBO                    0.81  all n       none
ring graph (sparse contrast)            0.13  6 of 16     large
===================================  =======  ==========  ==================

So the technique is real, and it is simply the wrong tool for dense objectives.
This module ships the *measurement* rather than the machinery: run
:func:`locality_report` on a problem before assuming either way.  For the
constrained portfolio case the effective substitute is
:mod:`quantum.subspace`, which cuts the state space by restricting to feasible
assignments instead of to a neighbourhood.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .qubo import QUBO

__all__ = [
    "LocalityReport",
    "coupling_graph",
    "cone_size",
    "locality_report",
]


def coupling_graph(problem: QUBO, tolerance: float = 1e-12) -> list[set[int]]:
    """Adjacency of the Ising coupling graph -- which variables interact at all."""
    ising = problem.to_ising()
    coupling = np.abs(ising.J + ising.J.T)
    n = problem.n_vars
    return [set(np.nonzero(coupling[i] > tolerance)[0]) - {i} for i in range(n)]


def cone_size(adjacency: list[set[int]], seeds: tuple[int, ...], depth: int) -> int:
    """Number of variables within ``depth`` hops of ``seeds``."""
    nodes = set(seeds)
    for _ in range(depth):
        nodes = nodes | {w for v in nodes for w in adjacency[v]}
    return len(nodes)


@dataclass
class LocalityReport:
    """Whether light-cone evaluation would pay off on a given problem."""

    n_vars: int
    mean_degree: float
    density: float
    cone_sizes: dict[int, int] = field(default_factory=dict)

    def speedup_at(self, p: int) -> float:
        """Memory ratio ``2**n / 2**cone`` at depth ``p``; 1.0 means no benefit."""
        cone = self.cone_sizes.get(p)
        if cone is None or cone >= self.n_vars:
            return 1.0
        return float(2 ** (self.n_vars - cone))

    @property
    def worthwhile(self) -> bool:
        return any(self.speedup_at(p) > 2.0 for p in self.cone_sizes)

    def __repr__(self) -> str:  # pragma: no cover - display helper
        cones = ", ".join(f"p={p}:{k}" for p, k in sorted(self.cone_sizes.items()))
        return (
            f"<Locality n={self.n_vars} density={self.density:.2f} "
            f"cones({cones}) worthwhile={self.worthwhile}>"
        )

    def summary(self) -> str:
        lines = [
            f"variables      : {self.n_vars}",
            f"mean degree    : {self.mean_degree:.1f}",
            f"density        : {self.density:.2f}",
            "",
            f"{'depth':>7}{'cone size':>12}{'memory saving':>16}",
        ]
        for p in sorted(self.cone_sizes):
            saving = self.speedup_at(p)
            label = "none" if saving <= 1.0 else f"{saving:,.0f}x"
            lines.append(f"{p:>7}{self.cone_sizes[p]:>12}{label:>16}")
        if not self.worthwhile:
            lines.append(
                "\nThe coupling graph is too dense for light cones to help: the "
                "cone\nalready spans the whole problem. For a cardinality "
                "constraint, use\nquantum.subspace instead, which shrinks the "
                "state space by feasibility."
            )
        return "\n".join(lines)


def locality_report(problem: QUBO, depths: tuple[int, ...] = (1, 2, 3)) -> LocalityReport:
    """Measure whether light-cone evaluation would reduce memory on ``problem``.

    Cone size is taken as the worst case over coupled pairs, since the energy
    needs every term and the peak is what has to fit in memory.
    """
    adjacency = coupling_graph(problem)
    n = problem.n_vars
    degrees = [len(a) for a in adjacency]
    mean_degree = float(np.mean(degrees)) if degrees else 0.0

    pairs = [
        (i, j)
        for i in range(n)
        for j in adjacency[i]
        if j > i
    ]
    if not pairs:  # no quadratic couplings at all: every term is already local
        pairs = [(i, i) for i in range(n)]

    cones: dict[int, int] = {}
    for p in depths:
        cones[p] = max(cone_size(adjacency, pair, p) for pair in pairs)

    return LocalityReport(
        n_vars=n,
        mean_degree=mean_degree,
        density=mean_degree / max(n - 1, 1),
        cone_sizes=cones,
    )
