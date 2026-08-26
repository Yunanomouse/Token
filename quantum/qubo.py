"""QUBO / Ising models -- the common language of quantum optimisation.

Every discrete optimisation problem in this package (portfolio selection with
cardinality and lot constraints, arbitrage cycle detection) is compiled into a
single canonical form:

.. math:: \\min_{x \\in \\{0,1\\}^n}\\ x^T Q x + \\text{offset}

Quadratic Unconstrained Binary Optimisation.  It maps one-to-one onto the Ising
model of statistical physics,

.. math:: E(s) = \\sum_i h_i s_i + \\sum_{i<j} J_{ij} s_i s_j,\\quad s_i \\in \\{-1, +1\\}

via ``x = (1 + s) / 2``.  That equivalence is why this form matters: an Ising
ground state is exactly what a quantum annealer relaxes into, what QAOA prepares,
and what simulated bifurcation integrates towards.  Compile once, then run the
same problem on any of them.

Constraints become penalties.  A requirement ``g(x) = 0`` enters as
``lambda * g(x)^2``, which is why the penalty weight matters: too small and the
optimum violates the constraint, too large and it swamps the objective and
flattens the energy landscape.  :meth:`QUBO.suggest_penalty` gives a scale-aware
starting point.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np

__all__ = ["QUBO", "IsingModel"]


@dataclass
class IsingModel:
    """Ising form ``E(s) = h.s + s^T J s + offset`` with ``J`` strictly upper triangular."""

    h: np.ndarray
    J: np.ndarray
    offset: float = 0.0

    @property
    def n_vars(self) -> int:
        return int(self.h.size)

    def energy(self, spins: np.ndarray) -> float:
        s = np.asarray(spins, dtype=np.float64).reshape(-1)
        return float(self.h @ s + s @ self.J @ s + self.offset)

    def energies_all(self) -> np.ndarray:
        """Energy of every spin configuration, indexed by basis-state integer.

        Variable ``0`` sits at the *most significant* bit of the integer, matching
        the simulator's qubit convention, so the returned vector can be handed
        straight to :meth:`Circuit.diagonal_phase` as QAOA's cost operator.

        Delegates to :meth:`QUBO.energies_all`, which builds the vector by
        recursive doubling instead of materialising a ``(2**n, n)`` bit matrix.
        """
        return QUBO.from_ising(self).energies_all()


@dataclass
class QUBO:
    """A QUBO instance plus optional variable names and problem metadata."""

    Q: np.ndarray
    offset: float = 0.0
    labels: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.Q = np.asarray(self.Q, dtype=np.float64)
        if self.Q.ndim != 2 or self.Q.shape[0] != self.Q.shape[1]:
            raise ValueError("Q must be a square matrix")
        # Work with the symmetric part; x^T Q x is unchanged by symmetrisation.
        self.Q = 0.5 * (self.Q + self.Q.T)
        if not self.labels:
            self.labels = [f"x{i}" for i in range(self.n_vars)]
        elif len(self.labels) != self.n_vars:
            raise ValueError("label count must match the number of variables")

    @property
    def n_vars(self) -> int:
        return int(self.Q.shape[0])

    # -- evaluation -------------------------------------------------------
    def energy(self, x: Sequence[int] | np.ndarray) -> float:
        """Objective value ``x^T Q x + offset``."""
        v = np.asarray(x, dtype=np.float64).reshape(-1)
        if v.size != self.n_vars:
            raise ValueError("assignment length does not match the problem")
        return float(v @ self.Q @ v + self.offset)

    def energies_all(self, dtype: np.dtype = np.float64) -> np.ndarray:
        """Objective value for every binary assignment, by recursive doubling.

        The obvious implementation enumerates the bits of every basis state into
        a ``(2**n, n)`` matrix and contracts it against ``Q``.  That is correct
        but allocates ``n`` times the memory of its own answer -- measured at
        **36x** the result size for ``n=16``, since the bit matrix, the spin
        matrix and the einsum temporaries all coexist.

        This version adds one variable at a time instead.  Appending variable
        ``k`` to a table already covering ``2**t`` assignments costs

        .. math:: E(x, x_k{=}1) = E(x) + Q_{kk} + \sum_{i} (Q_{ik} + Q_{ki}) x_i

        and that correction is itself linear in the bits, so it is built by the
        same doubling.  Variables are processed from last to first so each new
        one lands in the *most significant* position, which makes every step a
        contiguous in-place append rather than an interleave.

        Peak memory is the result plus one scratch buffer -- **2x** the answer,
        against 36x before -- and no intermediate is ever wider than 1-D.
        """
        n = self.n_vars
        if n > 27:
            raise ValueError(
                f"refusing to enumerate 2**{n} states; use iter_energy_chunks() "
                "or a heuristic solver"
            )
        Q = self.Q
        size = 1 << n
        energies = np.empty(size, dtype=dtype)
        energies[0] = self.offset
        scratch = np.empty(size, dtype=dtype)

        filled = 1  # number of assignments currently tabulated
        for k in range(n - 1, -1, -1):
            # Correction contributed by switching variable k on, across every
            # assignment of the variables already in the table (k+1 .. n-1,
            # most significant first).
            scratch[0] = Q[k, k]
            width = 1
            for i in range(n - 1, k, -1):
                weight = Q[i, k] + Q[k, i]
                np.add(scratch[:width], weight, out=scratch[width : 2 * width])
                width *= 2
            np.add(energies[:filled], scratch[:filled], out=energies[filled : 2 * filled])
            filled *= 2
        return energies

    def iter_energy_chunks(
        self,
        chunk_bits: int = 16,
        dtype: np.dtype = np.float64,
    ):
        """Stream the energy landscape in chunks, bounding peak memory.

        Yields ``(start_index, energies_chunk)``.  Memory is ``O(2**chunk_bits)``
        regardless of ``n``, so an argmin over a landscape far larger than RAM
        stays feasible -- at the cost of recomputing rather than storing.

        Used by :meth:`brute_force` once the full table would be large.
        """
        n = self.n_vars
        chunk_bits = max(1, min(int(chunk_bits), n))
        chunk = 1 << chunk_bits
        n_high = n - chunk_bits
        Q = self.Q

        # Split the variables: the high ones are fixed per chunk, the low ones
        # vary within it.  The low block's table is built once and reused.
        low_self = QUBO(Q=Q[n_high:, n_high:].copy(), offset=0.0)
        low_table = low_self.energies_all(dtype=dtype)

        low_bits = np.empty((chunk, chunk_bits), dtype=np.int8)
        idx = np.arange(chunk)
        for j in range(chunk_bits):
            low_bits[:, j] = (idx >> (chunk_bits - 1 - j)) & 1
        # Cross terms couple each high variable to the whole low block.
        cross = (Q[:n_high, n_high:] + Q[n_high:, :n_high].T) @ low_bits.T.astype(dtype)

        high_q = QUBO(Q=Q[:n_high, :n_high].copy(), offset=self.offset) if n_high else None
        for high in range(1 << n_high):
            high_bits = np.array(
                [(high >> (n_high - 1 - j)) & 1 for j in range(n_high)], dtype=dtype
            )
            base = float(high_bits @ Q[:n_high, :n_high] @ high_bits) + self.offset
            yield high * chunk, low_table + base + high_bits @ cross

    # -- conversions ------------------------------------------------------
    def to_ising(self) -> IsingModel:
        """Exact QUBO -> Ising conversion under ``x = (1 + s) / 2``."""
        n = self.n_vars
        Q = self.Q
        h = np.zeros(n)
        J = np.zeros((n, n))
        offset = float(self.offset)

        diag = np.diag(Q)
        h += diag / 2.0
        offset += float(diag.sum()) / 2.0

        for i in range(n):
            for j in range(i + 1, n):
                qij = Q[i, j] + Q[j, i]  # = 2 * Q[i, j] after symmetrisation
                if qij == 0.0:
                    continue
                J[i, j] += qij / 4.0
                h[i] += qij / 4.0
                h[j] += qij / 4.0
                offset += qij / 4.0

        return IsingModel(h=h, J=J, offset=offset)

    @staticmethod
    def from_ising(model: IsingModel) -> "QUBO":
        """Inverse conversion, ``s = 2x - 1``."""
        n = model.n_vars
        Q = np.zeros((n, n))
        offset = float(model.offset)
        h, J = model.h, model.J

        for i in range(n):
            Q[i, i] += 2.0 * h[i]
            offset -= h[i]
        for i in range(n):
            for j in range(i + 1, n):
                if J[i, j] == 0.0:
                    continue
                Q[i, j] += 2.0 * J[i, j]
                Q[j, i] += 2.0 * J[i, j]
                Q[i, i] -= 2.0 * J[i, j]
                Q[j, j] -= 2.0 * J[i, j]
                offset += J[i, j]
        return QUBO(Q=Q, offset=offset)

    # -- construction helpers --------------------------------------------
    def add_linear(self, index: int, weight: float) -> "QUBO":
        """Add ``weight * x_i`` (binary, so ``x_i^2 = x_i`` lands on the diagonal)."""
        self.Q[index, index] += float(weight)
        return self

    def add_quadratic(self, i: int, j: int, weight: float) -> "QUBO":
        """Add ``weight * x_i * x_j``, split symmetrically."""
        if i == j:
            return self.add_linear(i, weight)
        self.Q[i, j] += float(weight) / 2.0
        self.Q[j, i] += float(weight) / 2.0
        return self

    def add_equality_penalty(
        self,
        coefficients: Sequence[float],
        target: float,
        weight: float,
    ) -> "QUBO":
        """Add ``weight * (sum_i c_i x_i - target)^2``.

        This is how hard constraints -- "hold exactly K names", "spend the whole
        budget" -- enter an unconstrained model.
        """
        c = np.asarray(coefficients, dtype=np.float64).reshape(-1)
        if c.size != self.n_vars:
            raise ValueError("coefficient vector length mismatch")
        w = float(weight)
        # (c.x - t)^2 = sum_ij c_i c_j x_i x_j - 2t sum_i c_i x_i + t^2
        self.Q += w * np.outer(c, c)
        # x_i^2 = x_i for binaries: fold the linear term onto the diagonal.
        self.Q[np.diag_indices(self.n_vars)] -= w * 2.0 * target * c
        self.offset += w * target**2
        return self

    def add_inequality_penalty_upper(
        self,
        coefficients: Sequence[float],
        limit: float,
        weight: float,
        n_slack_bits: int = 3,
    ) -> tuple["QUBO", list[int]]:
        """Add ``sum_i c_i x_i <= limit`` using binary slack variables.

        Returns the extended problem and the indices of the slack bits.  Slack
        encoding is what makes inequalities expensive in QUBO form: each one adds
        ``n_slack_bits`` variables, so sector caps and position limits are the
        main driver of problem width.
        """
        c = np.asarray(coefficients, dtype=np.float64).reshape(-1)
        if c.size != self.n_vars:
            raise ValueError("coefficient vector length mismatch")

        n_old = self.n_vars
        slack_weights = np.array([2.0**b for b in range(n_slack_bits)], dtype=np.float64)
        # Cap slack resolution at the constraint's own span.
        span = max(float(limit), 1e-12)
        slack_weights = slack_weights * (span / max(slack_weights.sum(), 1e-12))

        n_new = n_old + n_slack_bits
        Q = np.zeros((n_new, n_new))
        Q[:n_old, :n_old] = self.Q
        labels = list(self.labels) + [f"slack{b}" for b in range(n_slack_bits)]
        extended = QUBO(Q=Q, offset=self.offset, labels=labels, metadata=dict(self.metadata))

        full_c = np.concatenate([c, slack_weights])
        extended.add_equality_penalty(full_c, limit, weight)
        return extended, list(range(n_old, n_new))

    def suggest_penalty(self, scale: float = 2.0) -> float:
        """A penalty weight on the order of the objective's own coefficients.

        Adequate only when the constraint coefficients are themselves O(1) --
        a cardinality count, for instance.  For constraints whose coefficients
        are small (portfolio weights, say) use :meth:`suggest_penalty_for`, which
        accounts for the coefficient scale.
        """
        largest = float(np.abs(self.Q).max()) if self.Q.size else 1.0
        return max(scale * largest, 1e-9)

    def suggest_penalty_for(
        self,
        coefficients: Sequence[float],
        scale: float = 4.0,
        objective_scale: float | None = None,
    ) -> float:
        """A penalty weight sized against a *specific* constraint's coefficients.

        A penalty only binds if breaking the constraint costs more than the
        objective gain from breaking it.  The smallest step a constraint can take
        is its smallest non-zero coefficient ``c_min``, and that step contributes
        ``lambda * c_min**2`` to the penalty -- so the weight has to scale as
        ``objective_scale / c_min**2``.

        Ignoring the ``c_min**2`` factor is the classic QUBO modelling error: with
        weights around 0.05 it under-penalises by a factor of ~400, and the solver
        returns a portfolio that quietly ignores its budget.
        """
        c = np.abs(np.asarray(coefficients, dtype=np.float64).reshape(-1))
        nonzero = c[c > 1e-12]
        c_min = float(nonzero.min()) if nonzero.size else 1.0
        if objective_scale is None:
            objective_scale = float(np.abs(self.Q).max()) if self.Q.size else 1.0
        objective_scale = max(float(objective_scale), 1e-12)
        return max(scale * objective_scale / (c_min**2), 1e-9)

    # -- exact reference ---------------------------------------------------
    def brute_force(self, max_materialise_bits: int = 22) -> tuple[np.ndarray, float]:
        """Exhaustive minimisation -- ground truth for validating solvers.

        Materialises the full landscape while that is cheap, and streams it in
        chunks beyond ``max_materialise_bits`` so peak memory stays flat as ``n``
        grows.  The work is still ``O(2**n)``; only the memory is bounded.
        """
        n = self.n_vars
        if n > 30:
            raise ValueError("brute force is limited to 30 variables")

        if n <= max_materialise_bits:
            energies = self.energies_all()
            best = int(np.argmin(energies))
            best_energy = float(energies[best])
        else:
            best, best_energy = 0, np.inf
            for start, chunk in self.iter_energy_chunks(chunk_bits=max_materialise_bits):
                local = int(np.argmin(chunk))
                if float(chunk[local]) < best_energy:
                    best_energy = float(chunk[local])
                    best = start + local

        bits = np.array([(best >> (n - 1 - i)) & 1 for i in range(n)], dtype=int)
        return bits, best_energy

    def describe(self, x: Sequence[int] | np.ndarray) -> dict:
        """Human-readable view of an assignment."""
        v = np.asarray(x, dtype=int).reshape(-1)
        return {
            "energy": self.energy(v),
            "selected": [self.labels[i] for i in range(self.n_vars) if v[i] == 1],
            "bits": v.tolist(),
        }
