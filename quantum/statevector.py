"""Exact statevector simulator for gate-based quantum circuits.

This is the physics layer everything else in the package sits on. It implements
the postulates of quantum mechanics directly:

* **State**   -- a unit vector in the Hilbert space (C^2)^(x)n.
* **Evolution** -- unitary operators applied to that vector.
* **Measurement** -- the Born rule, P(x) = |<x|psi>|^2.

Qubit/bit-order convention
--------------------------
Qubit ``0`` is the **most significant** bit of a basis-state integer, so for a
3-qubit register the integer ``6 = 0b110`` means ``q0=1, q1=1, q2=0``.  The
statevector is stored as a rank-``n`` tensor of shape ``[2]*n`` where axis ``i``
belongs to qubit ``i``, which makes gate application a tensor contraction.

Scaling
-------
Memory is ``2**n`` complex128 values: 20 qubits ~ 16 MB, 24 qubits ~ 256 MB.
Circuits here stay well under that.

Honesty note on multi-controlled gates
--------------------------------------
Controlled operations are applied directly to the controlled subspace rather
than decomposed into one- and two-qubit gates.  This is exact and fast for
simulation, but it means :attr:`Circuit.gate_count` counts *logical* gates. Real
hardware would need each multi-controlled gate compiled down, which inflates the
true depth substantially.  :meth:`Circuit.resource_estimate` reports both.
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np

__all__ = [
    "Circuit",
    "Operation",
    "statevector",
    "sample",
    "expectation_z",
    "probabilities",
    "H",
    "X",
    "Y",
    "Z",
    "S",
    "T",
    "ry_matrix",
    "rz_matrix",
    "rx_matrix",
    "phase_matrix",
]

# --------------------------------------------------------------------------
# Gate matrices
# --------------------------------------------------------------------------

_SQRT1_2 = 1.0 / math.sqrt(2.0)

H = np.array([[_SQRT1_2, _SQRT1_2], [_SQRT1_2, -_SQRT1_2]], dtype=np.complex128)
X = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.complex128)
Y = np.array([[0.0, -1.0j], [1.0j, 0.0]], dtype=np.complex128)
Z = np.array([[1.0, 0.0], [0.0, -1.0]], dtype=np.complex128)
S = np.array([[1.0, 0.0], [0.0, 1.0j]], dtype=np.complex128)
T = np.array([[1.0, 0.0], [0.0, cmath.exp(1j * math.pi / 4)]], dtype=np.complex128)
I2 = np.eye(2, dtype=np.complex128)


def rx_matrix(theta: float) -> np.ndarray:
    """Rotation by ``theta`` about the X axis of the Bloch sphere."""
    c, s = math.cos(theta / 2.0), math.sin(theta / 2.0)
    return np.array([[c, -1j * s], [-1j * s, c]], dtype=np.complex128)


def ry_matrix(theta: float) -> np.ndarray:
    """Rotation by ``theta`` about the Y axis (real-valued, used everywhere here)."""
    c, s = math.cos(theta / 2.0), math.sin(theta / 2.0)
    return np.array([[c, -s], [s, c]], dtype=np.complex128)


def rz_matrix(theta: float) -> np.ndarray:
    """Rotation by ``theta`` about the Z axis."""
    e = cmath.exp(-1j * theta / 2.0)
    return np.array([[e, 0.0], [0.0, e.conjugate()]], dtype=np.complex128)


def phase_matrix(lam: float) -> np.ndarray:
    """Relative phase ``lam`` on |1>."""
    return np.array([[1.0, 0.0], [0.0, cmath.exp(1j * lam)]], dtype=np.complex128)


# --------------------------------------------------------------------------
# Core application kernel
# --------------------------------------------------------------------------


def _contract(tensor: np.ndarray, matrix: np.ndarray, axes: Sequence[int]) -> np.ndarray:
    """Apply ``matrix`` (2^k x 2^k) to the given ``axes`` of a rank-n tensor."""
    k = len(axes)
    op = matrix.reshape([2] * (2 * k))
    out = np.tensordot(op, tensor, axes=(list(range(k, 2 * k)), list(axes)))
    # tensordot puts the k new axes in front; put them back where they belong.
    return np.moveaxis(out, list(range(k)), list(axes))


def _apply(
    state: np.ndarray,
    n_qubits: int,
    matrix: np.ndarray,
    targets: Sequence[int],
    controls: Sequence[int] = (),
    control_values: Sequence[int] = (),
) -> np.ndarray:
    """Apply a (possibly controlled) unitary to ``state``, returning the new state."""
    tensor = state.reshape([2] * n_qubits)
    if not controls:
        return _contract(tensor, matrix, targets).reshape(-1)

    if not control_values:
        control_values = [1] * len(controls)

    # Integer (basic) indexing yields a writable view, so we can operate on the
    # controlled subspace in place.
    index: list = [slice(None)] * n_qubits
    for ctrl, val in zip(controls, control_values):
        index[ctrl] = val
    sub = tensor[tuple(index)]

    remaining = [q for q in range(n_qubits) if q not in set(controls)]
    sub_axes = [remaining.index(t) for t in targets]
    tensor[tuple(index)] = _contract(sub, matrix, sub_axes)
    return tensor.reshape(-1)


# --------------------------------------------------------------------------
# Operations and circuits
# --------------------------------------------------------------------------


def _apply_diagonal(
    state: np.ndarray,
    n_qubits: int,
    phases: np.ndarray,
    controls: Sequence[int] = (),
    control_values: Sequence[int] = (),
) -> np.ndarray:
    """Apply ``diag(exp(i * phases))``, optionally gated on control qubits."""
    factor = np.exp(1j * np.asarray(phases, dtype=np.float64))
    if not controls:
        return state * factor
    if not control_values:
        control_values = [1] * len(controls)
    idx = np.arange(state.size)
    mask = np.ones(state.size, dtype=bool)
    for ctrl, val in zip(controls, control_values):
        bit = (idx >> (n_qubits - 1 - ctrl)) & 1
        mask &= bit == val
    out = state.copy()
    out[mask] = out[mask] * factor[mask]
    return out


@dataclass(frozen=True)
class Operation:
    """A single unitary instruction: a matrix, its targets, and its controls."""

    name: str
    matrix: np.ndarray | None
    targets: tuple[int, ...]
    controls: tuple[int, ...] = ()
    control_values: tuple[int, ...] = ()
    diagonal: np.ndarray | None = None
    """Phase angles per basis state, for operators diagonal in the computational
    basis.  Stored as a length-``2**n`` vector rather than a ``2**n x 2**n``
    matrix -- QAOA's cost operator is diagonal, and materialising it densely
    would be quadratically wasteful (16 variables alone would need a 65536x65536
    array)."""

    @property
    def n_controls(self) -> int:
        return len(self.controls)

    def dagger(self) -> "Operation":
        """The inverse operation (used when building Grover reflections)."""
        if self.diagonal is not None:
            return Operation(
                name=self.name + "^dg",
                matrix=None,
                targets=self.targets,
                controls=self.controls,
                control_values=self.control_values,
                diagonal=-self.diagonal,
            )
        return Operation(
            name=self.name + "^dg",
            matrix=self.matrix.conj().T,
            targets=self.targets,
            controls=self.controls,
            control_values=self.control_values,
        )


class Circuit:
    """A mutable sequence of unitary operations on ``n_qubits`` qubits.

    The builder methods return ``self`` so circuits can be chained::

        Circuit(2).h(0).cx(0, 1)
    """

    def __init__(self, n_qubits: int, name: str = "circuit") -> None:
        if n_qubits < 1:
            raise ValueError("a circuit needs at least one qubit")
        self.n_qubits = int(n_qubits)
        self.name = name
        self.ops: list[Operation] = []

    # -- introspection ----------------------------------------------------
    def __len__(self) -> int:
        return len(self.ops)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Circuit {self.name!r} qubits={self.n_qubits} ops={len(self.ops)}>"

    @property
    def gate_count(self) -> int:
        """Number of logical operations (multi-controlled gates count as one)."""
        return len(self.ops)

    def resource_estimate(self) -> dict[str, int]:
        """Logical vs. roughly-decomposed gate counts.

        A gate with ``c >= 2`` controls costs about ``16 * (c - 1)`` elementary
        gates once compiled with ancilla-free Toffoli ladders.  That factor is a
        standard order-of-magnitude figure, not an exact compilation.
        """
        logical = len(self.ops)
        elementary = 0
        max_controls = 0
        for op in self.ops:
            c = op.n_controls
            max_controls = max(max_controls, c)
            if op.diagonal is not None:
                # A dense diagonal is a black box: compiling it in general costs
                # O(2**n) gates.  Count it that way rather than flattering it.
                elementary += 2**self.n_qubits
            elif c <= 1:
                elementary += 1
            else:
                elementary += 16 * (c - 1)
        return {
            "qubits": self.n_qubits,
            "logical_gates": logical,
            "estimated_elementary_gates": elementary,
            "max_controls": max_controls,
        }

    # -- composition ------------------------------------------------------
    def append(self, op: Operation) -> "Circuit":
        if op.matrix is None and op.diagonal is None:
            raise ValueError("an operation needs either a matrix or a diagonal")
        for q in tuple(op.targets) + tuple(op.controls):
            if not 0 <= q < self.n_qubits:
                raise ValueError(f"qubit {q} out of range for {self.n_qubits}-qubit circuit")
        if set(op.targets) & set(op.controls):
            raise ValueError("a qubit cannot be both control and target")
        self.ops.append(op)
        return self

    def compose(self, other: "Circuit", qubits: Sequence[int] | None = None) -> "Circuit":
        """Append ``other``'s operations, optionally remapped onto ``qubits``."""
        mapping = list(range(other.n_qubits)) if qubits is None else list(qubits)
        if len(mapping) != other.n_qubits:
            raise ValueError("qubit mapping length must match the sub-circuit width")
        for op in other.ops:
            if op.diagonal is not None and len(mapping) != self.n_qubits:
                raise ValueError("diagonal operators cannot be remapped onto a subset")
            self.append(
                Operation(
                    name=op.name,
                    matrix=op.matrix,
                    targets=tuple(mapping[t] for t in op.targets),
                    controls=tuple(mapping[c] for c in op.controls),
                    control_values=op.control_values,
                    diagonal=op.diagonal,
                )
            )
        return self

    def inverse(self) -> "Circuit":
        """Return the adjoint circuit (operations reversed and daggered)."""
        inv = Circuit(self.n_qubits, name=self.name + "^dg")
        for op in reversed(self.ops):
            inv.append(op.dagger())
        return inv

    def control(self, control_qubit: int) -> "Circuit":
        """Return a copy with every operation additionally controlled.

        Used to build the controlled-``Q`` powers that canonical amplitude
        estimation needs.
        """
        out = Circuit(self.n_qubits, name="c-" + self.name)
        for op in self.ops:
            if control_qubit in op.targets:
                raise ValueError("control qubit overlaps an operation target")
            out.append(
                Operation(
                    name="c-" + op.name,
                    matrix=op.matrix,
                    targets=op.targets,
                    controls=tuple(op.controls) + (control_qubit,),
                    control_values=tuple(op.control_values or (1,) * len(op.controls)) + (1,),
                    diagonal=op.diagonal,
                )
            )
        return out

    # -- one-qubit gates --------------------------------------------------
    def _one(self, name: str, matrix: np.ndarray, qubit: int) -> "Circuit":
        return self.append(Operation(name, matrix, (int(qubit),)))

    def h(self, qubit: int) -> "Circuit":
        return self._one("h", H, qubit)

    def x(self, qubit: int) -> "Circuit":
        return self._one("x", X, qubit)

    def y(self, qubit: int) -> "Circuit":
        return self._one("y", Y, qubit)

    def z(self, qubit: int) -> "Circuit":
        return self._one("z", Z, qubit)

    def s(self, qubit: int) -> "Circuit":
        return self._one("s", S, qubit)

    def t(self, qubit: int) -> "Circuit":
        return self._one("t", T, qubit)

    def rx(self, theta: float, qubit: int) -> "Circuit":
        return self._one("rx", rx_matrix(theta), qubit)

    def ry(self, theta: float, qubit: int) -> "Circuit":
        return self._one("ry", ry_matrix(theta), qubit)

    def rz(self, theta: float, qubit: int) -> "Circuit":
        return self._one("rz", rz_matrix(theta), qubit)

    def p(self, lam: float, qubit: int) -> "Circuit":
        return self._one("p", phase_matrix(lam), qubit)

    def global_phase(self, phi: float) -> "Circuit":
        """Multiply the state by ``exp(i * phi)``.

        A global phase is unobservable on its own, but it becomes a *relative*
        phase once the circuit is controlled -- which is exactly what canonical
        amplitude estimation does to the Grover operator, so it must be carried
        explicitly rather than dropped.
        """
        return self.append(Operation("gphase", cmath.exp(1j * phi) * I2, (0,)))

    def barrier_all_h(self) -> "Circuit":
        """Hadamard every qubit -- the uniform superposition primitive."""
        for q in range(self.n_qubits):
            self.h(q)
        return self

    # -- controlled gates -------------------------------------------------
    def cx(self, control: int, target: int) -> "Circuit":
        return self.append(Operation("cx", X, (int(target),), (int(control),)))

    def cz(self, control: int, target: int) -> "Circuit":
        return self.append(Operation("cz", Z, (int(target),), (int(control),)))

    def cry(self, theta: float, control: int, target: int) -> "Circuit":
        return self.append(Operation("cry", ry_matrix(theta), (int(target),), (int(control),)))

    def cp(self, lam: float, control: int, target: int) -> "Circuit":
        return self.append(Operation("cp", phase_matrix(lam), (int(target),), (int(control),)))

    def mcx(
        self,
        controls: Iterable[int],
        target: int,
        control_values: Sequence[int] | None = None,
    ) -> "Circuit":
        ctrls = tuple(int(c) for c in controls)
        vals = tuple(control_values) if control_values is not None else (1,) * len(ctrls)
        return self.append(Operation("mcx", X, (int(target),), ctrls, vals))

    def mcry(
        self,
        theta: float,
        controls: Iterable[int],
        target: int,
        control_values: Sequence[int] | None = None,
    ) -> "Circuit":
        ctrls = tuple(int(c) for c in controls)
        vals = tuple(control_values) if control_values is not None else (1,) * len(ctrls)
        return self.append(Operation("mcry", ry_matrix(theta), (int(target),), ctrls, vals))

    def mcz(
        self,
        controls: Iterable[int],
        target: int,
        control_values: Sequence[int] | None = None,
    ) -> "Circuit":
        ctrls = tuple(int(c) for c in controls)
        vals = tuple(control_values) if control_values is not None else (1,) * len(ctrls)
        return self.append(Operation("mcz", Z, (int(target),), ctrls, vals))

    # -- diagonal / multi-qubit helpers -----------------------------------
    def diagonal_phase(self, phases: np.ndarray) -> "Circuit":
        """Apply ``diag(exp(i * phases))`` across the whole register.

        This is how QAOA's cost unitary is applied: the Ising cost operator is
        diagonal in the computational basis, so it is a pure phase per basis
        state and needs no decomposition to be simulated exactly.
        """
        phases = np.asarray(phases, dtype=np.float64)
        if phases.shape != (2**self.n_qubits,):
            raise ValueError("phase vector must cover the full computational basis")
        return self.append(
            Operation("diag", None, tuple(range(self.n_qubits)), diagonal=phases)
        )

    def qft(self, qubits: Sequence[int] | None = None, inverse: bool = False) -> "Circuit":
        """Quantum Fourier transform (or its inverse) over ``qubits``."""
        qs = list(range(self.n_qubits)) if qubits is None else list(qubits)
        sub = Circuit(self.n_qubits, name="qft")
        m = len(qs)
        for j in range(m):
            sub.h(qs[j])
            for k in range(j + 1, m):
                sub.cp(math.pi / (2 ** (k - j)), qs[k], qs[j])
        for j in range(m // 2):
            a, b = qs[j], qs[m - 1 - j]
            sub.cx(a, b).cx(b, a).cx(a, b)  # SWAP
        if inverse:
            sub = sub.inverse()
        self.ops.extend(sub.ops)
        return self

    # -- execution --------------------------------------------------------
    def run(self, initial_state: np.ndarray | None = None) -> np.ndarray:
        """Evolve a state through the circuit and return the final statevector."""
        dim = 2**self.n_qubits
        if initial_state is None:
            state = np.zeros(dim, dtype=np.complex128)
            state[0] = 1.0
        else:
            state = np.asarray(initial_state, dtype=np.complex128).reshape(-1).copy()
            if state.size != dim:
                raise ValueError("initial state has the wrong dimension")
        for op in self.ops:
            if op.diagonal is not None:
                state = _apply_diagonal(
                    state, self.n_qubits, op.diagonal, op.controls, op.control_values
                )
            else:
                state = _apply(
                    state,
                    self.n_qubits,
                    op.matrix,
                    op.targets,
                    op.controls,
                    op.control_values,
                )
        return state


# --------------------------------------------------------------------------
# Measurement helpers
# --------------------------------------------------------------------------


def statevector(circuit: Circuit) -> np.ndarray:
    """Run ``circuit`` from |0...0> and return the final statevector."""
    return circuit.run()


def probabilities(state: np.ndarray) -> np.ndarray:
    """Born-rule probabilities |<x|psi>|^2 for every basis state."""
    return np.abs(np.asarray(state)) ** 2


def marginal(state: np.ndarray, n_qubits: int, qubits: Sequence[int]) -> np.ndarray:
    """Marginal distribution over ``qubits`` (qubit 0 = most significant)."""
    probs = probabilities(state).reshape([2] * n_qubits)
    keep = list(qubits)
    trace_out = [q for q in range(n_qubits) if q not in set(keep)]
    reduced = probs.sum(axis=tuple(trace_out)) if trace_out else probs
    # sum() collapses axes but keeps relative order of the survivors
    survivors = [q for q in range(n_qubits) if q in set(keep)]
    order = [survivors.index(q) for q in keep]
    return np.transpose(reduced, order).reshape(-1)


def sample(
    state: np.ndarray,
    shots: int,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Draw ``shots`` computational-basis measurements via the Born rule.

    Returns an array of basis-state integers.
    """
    rng = rng or np.random.default_rng()
    probs = probabilities(state)
    total = probs.sum()
    if total <= 0:
        raise ValueError("cannot sample from a zero-norm state")
    probs = probs / total
    return rng.choice(probs.size, size=int(shots), p=probs)


def expectation_z(state: np.ndarray, n_qubits: int, qubit: int) -> float:
    """<psi| Z_qubit |psi>."""
    probs = probabilities(state).reshape([2] * n_qubits)
    axes = tuple(q for q in range(n_qubits) if q != qubit)
    marg = probs.sum(axis=axes) if axes else probs
    return float(marg[0] - marg[1])


def probability_of_one(state: np.ndarray, n_qubits: int, qubit: int) -> float:
    """P(qubit measures |1>) -- the quantity amplitude estimation targets."""
    probs = probabilities(state).reshape([2] * n_qubits)
    axes = tuple(q for q in range(n_qubits) if q != qubit)
    marg = probs.sum(axis=axes) if axes else probs
    return float(marg[1])
