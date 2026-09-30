"""Constraint-preserving QAOA in a Hamming-weight subspace.

The cardinality-constrained portfolio problem -- *hold exactly K names* -- is
normally handled by adding a penalty ``lambda (sum_i x_i - K)^2`` to the QUBO.
That works, but it costs twice:

1. **Memory.** The simulator carries all ``2**n`` basis states even though only
   ``C(n, K)`` of them are feasible.  At ``n=20, K=5`` that is 1,048,576
   amplitudes to represent 15,504 valid portfolios -- 98.5% of the register is
   modelling portfolios the mandate forbids.
2. **Correctness.** The penalty is *soft*.  Getting its weight wrong returns an
   infeasible portfolio that looks optimal, which is exactly the ``1/c_min**2``
   scaling trap documented in :mod:`quantum.qubo`.

Both disappear if the *mixer* preserves the constraint instead of the objective
punishing its violation.  The XY mixer

.. math:: H_{XY} = \\tfrac12 \\sum_{(i,j)} \\big( X_i X_j + Y_i Y_j \\big)

swaps ``|01> <-> |10>`` and annihilates ``|00>`` and ``|11>``, so it moves weight
between assets without ever changing how many are held.  Started in a Dicke state
``|D_K^n>`` -- the uniform superposition over all weight-``K`` strings -- the
evolution never leaves the feasible subspace.  This is the Quantum Alternating
*Operator* Ansatz (Hadfield et al. 2019), and for portfolio selection it means:

* the state vector is ``C(n, K)`` amplitudes, not ``2**n``;
* **every measurement outcome is a feasible portfolio**, so there is no penalty
  weight to tune and no feasibility check to fail.

The saving grows with ``n``: 67x fewer amplitudes at ``n=20, K=5``, 124x at
``n=24, K=6``.  It is not unlimited -- ``C(n, n/2)`` is still exponential -- but
for the small-``K`` mandates that occur in practice it buys several qubits of
headroom and removes a whole class of modelling error.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from .qubo import QUBO

__all__ = [
    "HammingSubspace",
    "SubspaceQAOAResult",
    "dicke_state",
    "subspace_qaoa",
]


# --------------------------------------------------------------------------
# The subspace
# --------------------------------------------------------------------------


def _weight_k_integers(n: int, k: int) -> np.ndarray:
    """Every ``n``-bit integer with exactly ``k`` bits set, ascending.

    Built by Gosper's hack -- the standard next-higher-integer-with-same-popcount
    step -- which emits them in sorted order directly, so no sort is needed and
    ``np.searchsorted`` can be used for lookups.
    """
    if k == 0:
        return np.zeros(1, dtype=np.int64)
    total = math.comb(n, k)
    out = np.empty(total, dtype=np.int64)
    value = (1 << k) - 1
    limit = 1 << n
    for i in range(total):
        out[i] = value
        if value == 0:
            break
        # Gosper's hack: lowest set bit, ripple carry, restore the low ones.
        lowest = value & -value
        ripple = value + lowest
        ones = ((value ^ ripple) >> 2) // lowest
        value = ripple | ones
        if value >= limit:
            break
    return out


@dataclass
class HammingSubspace:
    """The ``C(n, k)``-dimensional space of weight-``k`` bitstrings.

    Holds the basis states and the precomputed index pairings each XY mixer edge
    acts on, so the mixer is a handful of vectorised slices at run time rather
    than a search.
    """

    n_qubits: int
    weight: int
    states: np.ndarray = field(repr=False)
    edges: tuple[tuple[int, int], ...] = ()
    _pairs: list[tuple[np.ndarray, np.ndarray]] = field(default_factory=list, repr=False)

    @property
    def dimension(self) -> int:
        return int(self.states.size)

    @property
    def full_dimension(self) -> int:
        return 1 << self.n_qubits

    @property
    def compression(self) -> float:
        """How many times smaller than the full register this subspace is."""
        return self.full_dimension / max(self.dimension, 1)

    @classmethod
    def build(
        cls,
        n_qubits: int,
        weight: int,
        edges: Sequence[tuple[int, int]] | None = None,
        max_dimension: int = 1 << 22,
    ) -> "HammingSubspace":
        """Enumerate the subspace and precompute the mixer's index pairings.

        ``edges`` defaults to a ring, which is the cheapest connected XY mixer
        (``n`` terms).  A complete graph mixes faster per layer but costs
        ``n(n-1)/2`` terms; connectivity is what matters, since a disconnected
        mixer cannot reach every feasible state.
        """
        if not 0 <= weight <= n_qubits:
            raise ValueError("weight must lie between 0 and the qubit count")
        dimension = math.comb(n_qubits, weight)
        if dimension > max_dimension:
            raise ValueError(
                f"subspace has C({n_qubits},{weight}) = {dimension:,} states, "
                f"above the {max_dimension:,} limit"
            )

        states = _weight_k_integers(n_qubits, weight)
        if edges is None:
            edges = tuple((i, (i + 1) % n_qubits) for i in range(n_qubits))
        edges = tuple((int(a), int(b)) for a, b in edges)

        subspace = cls(n_qubits=n_qubits, weight=weight, states=states, edges=edges)
        subspace._build_pairs()
        return subspace

    def _build_pairs(self) -> None:
        """For each edge, the index pairs the XY term rotates into each other.

        An XY term on ``(i, j)`` couples exactly those states with bit ``i`` set
        and bit ``j`` clear to their bit-swapped partner.  Both members live in
        the subspace, since swapping preserves the weight -- which is the whole
        reason this works.
        """
        self._pairs = []
        states = self.states
        for i, j in self.edges:
            bit_i = (states >> (self.n_qubits - 1 - i)) & 1
            bit_j = (states >> (self.n_qubits - 1 - j)) & 1
            selected = np.nonzero((bit_i == 1) & (bit_j == 0))[0]
            if selected.size == 0:
                self._pairs.append((selected, selected))
                continue
            partners = (
                states[selected]
                - (1 << (self.n_qubits - 1 - i))
                + (1 << (self.n_qubits - 1 - j))
            )
            # Gosper enumeration is sorted, so a binary search resolves partners
            # without a 2**n lookup table -- which would defeat the point.
            partner_idx = np.searchsorted(states, partners)
            self._pairs.append((selected.astype(np.int64), partner_idx.astype(np.int64)))

    # -- state helpers -----------------------------------------------------
    def bitstring(self, index: int) -> np.ndarray:
        """Decode a subspace index to its ``n``-bit assignment."""
        value = int(self.states[index])
        return np.array(
            [(value >> (self.n_qubits - 1 - i)) & 1 for i in range(self.n_qubits)],
            dtype=int,
        )

    def restrict(self, full_vector: np.ndarray) -> np.ndarray:
        """Take the subspace entries of a full ``2**n`` vector."""
        return np.asarray(full_vector)[self.states]

    def costs(self, problem: QUBO) -> np.ndarray:
        """Objective value of every feasible assignment.

        Evaluated directly on the ``C(n, k)`` feasible points rather than by
        building the full ``2**n`` landscape and discarding 98% of it.
        """
        n = self.n_qubits
        if problem.n_vars != n:
            raise ValueError("problem width does not match the subspace")
        bits = np.empty((self.dimension, n), dtype=np.float64)
        for i in range(n):
            bits[:, i] = (self.states >> (n - 1 - i)) & 1
        # Row-wise x^T Q x without forming an intermediate per-pair tensor.
        return np.einsum("ki,ij,kj->k", bits, problem.Q, bits) + problem.offset

    # -- evolution ---------------------------------------------------------
    def apply_cost(self, state: np.ndarray, costs: np.ndarray, gamma: float) -> np.ndarray:
        """Diagonal cost layer ``exp(-i gamma C)``, in place."""
        state *= np.exp(-1j * gamma * costs).astype(state.dtype, copy=False)
        return state

    def apply_mixer(self, state: np.ndarray, beta: float) -> np.ndarray:
        """XY mixer layer, in place.

        On each coupled pair the term acts as the two-level rotation
        ``[[cos b, -i sin b], [-i sin b, cos b]]``; every other amplitude is
        untouched, because ``|00>`` and ``|11>`` are annihilated by ``XX + YY``.
        """
        cos = math.cos(beta)
        sin_i = -1j * math.sin(beta)
        for selected, partners in self._pairs:
            if selected.size == 0:
                continue
            a = state[selected]
            b = state[partners]
            state[selected] = cos * a + sin_i * b
            state[partners] = sin_i * a + cos * b
        return state


def dicke_state(subspace: HammingSubspace, dtype: np.dtype = np.complex128) -> np.ndarray:
    """The uniform superposition over all weight-``k`` strings, ``|D_k^n>``.

    In the subspace representation this is simply a flat vector -- the expensive
    part of Dicke-state preparation on real hardware disappears entirely when the
    basis is already restricted.
    """
    dimension = subspace.dimension
    return np.full(dimension, 1.0 / math.sqrt(dimension), dtype=dtype)


# --------------------------------------------------------------------------
# The solver
# --------------------------------------------------------------------------


@dataclass
class SubspaceQAOAResult:
    """Outcome of a constraint-preserving QAOA run."""

    assignment: np.ndarray
    energy: float
    subspace_dimension: int
    full_dimension: int
    expectation: float
    ground_state_probability: float
    parameters: np.ndarray
    detail: dict = field(default_factory=dict)

    @property
    def compression(self) -> float:
        return self.full_dimension / max(self.subspace_dimension, 1)

    def __repr__(self) -> str:  # pragma: no cover - display helper
        return (
            f"<SubspaceQAOA energy={self.energy:.6f} "
            f"dim={self.subspace_dimension:,}/{self.full_dimension:,} "
            f"({self.compression:.0f}x smaller)>"
        )


def subspace_qaoa(
    problem: QUBO,
    cardinality: int,
    p: int = 2,
    n_starts: int = 6,
    max_iter: int = 200,
    shots: int = 2048,
    edges: Sequence[tuple[int, int]] | None = None,
    rng: np.random.Generator | None = None,
    dtype: np.dtype = np.complex128,
) -> SubspaceQAOAResult:
    """QAOA restricted to assignments with exactly ``cardinality`` bits set.

    ``problem`` should carry the *bare* objective -- no cardinality penalty --
    because the constraint is enforced by construction here.  Passing a
    penalised QUBO still works but wastes the penalty term, which is constant
    across the whole feasible subspace.

    Every sampled bitstring is feasible, so unlike the penalty formulation this
    cannot return an infeasible portfolio.
    """
    from .optimize import multi_start_nelder_mead

    rng = rng or np.random.default_rng()
    subspace = HammingSubspace.build(problem.n_vars, cardinality, edges=edges)
    costs = subspace.costs(problem)

    spread = float(np.abs(costs - costs.mean()).max())
    scale = 1.0 / spread if spread > 0 else 1.0

    initial = dicke_state(subspace, dtype=dtype)
    work = np.empty_like(initial)
    probs = np.empty(subspace.dimension, dtype=np.float64)
    evaluations = 0

    def evolve(params: np.ndarray) -> np.ndarray:
        gammas, betas = params[:p], params[p:]
        np.copyto(work, initial)
        for layer in range(p):
            subspace.apply_cost(work, costs, float(gammas[layer]) * scale)
            subspace.apply_mixer(work, float(betas[layer]))
        return work

    def objective(params: np.ndarray) -> float:
        nonlocal evaluations
        evaluations += 1
        state = evolve(params)
        np.abs(state, out=probs)
        np.square(probs, out=probs)
        # Accumulate in float64 even when the state is single precision: the
        # reduction is where precision loss would actually bite.
        return float(np.dot(probs.astype(np.float64, copy=False), costs))

    best = multi_start_nelder_mead(
        objective, n_params=2 * p, n_starts=n_starts, bounds=(0.0, np.pi),
        rng=rng, max_iter=max_iter,
    )

    state = evolve(best.x)
    np.abs(state, out=probs)
    np.square(probs, out=probs)
    normalised = probs / probs.sum()

    counts = rng.multinomial(shots, normalised)
    observed = np.nonzero(counts)[0]
    winner = int(observed[int(np.argmin(costs[observed]))])

    expectation = float(np.dot(normalised, costs))
    return SubspaceQAOAResult(
        assignment=subspace.bitstring(winner),
        energy=float(costs[winner]),
        subspace_dimension=subspace.dimension,
        full_dimension=subspace.full_dimension,
        expectation=expectation,
        ground_state_probability=float(normalised[int(np.argmin(costs))]),
        parameters=best.x,
        detail={
            "p": p,
            "optimizer_evaluations": evaluations,
            "mixer_edges": len(subspace.edges),
            "subspace_bytes": subspace.dimension * np.dtype(dtype).itemsize,
            "full_bytes": subspace.full_dimension * np.dtype(dtype).itemsize,
            "best_feasible_energy": float(costs.min()),
        },
    )
