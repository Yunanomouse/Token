"""Compile circuits to elementary gates and export them as OpenQASM 3.

Everything in :mod:`quantum.statevector` is built for *simulation*: a
multiplexed ``Ry`` is one array of angles, a QAOA cost layer is one vector of
phases.  Hardware sees neither.  This module is the bridge -- it rewrites those
simulator-native operations into gates that exist on a device, and serialises
the result in a format every vendor toolchain reads (Qiskit, Braket, Cirq,
tket all import OpenQASM 3).

Three rewrites do all the work:

* **Uniformly controlled ``Ry``** (Möttönen, Vartiainen, Bergholm and Salomaa,
  2004): ``2**k`` rotations interleaved with ``2**k`` CNOTs in Gray-code order.
  The rotation angles are the Walsh-Hadamard transform of the angle table.
  That is the optimal CNOT count without ancillas, and it is exact.

* **Diagonal unitaries** as *phase gadgets*: expand the phase function in the
  Walsh basis, ``phi(x) = sum_S c_S prod_{i in S} z_i``, and realise each term
  as a CNOT ladder around a single ``Rz``.  The expansion is exact.  For a
  general diagonal it has ``2**n`` terms -- which is why
  :meth:`Circuit.resource_estimate` charges ``2**n`` for it -- but for an Ising
  cost it has at most ``n(n+1)/2 + 1``, and the compiler keeps only the
  non-zero ones.  That is the difference between "QAOA is exponential to
  compile" and "QAOA is quadratic to compile"; the former is an artefact of
  storing the operator densely.

* **Arbitrary one-qubit unitaries** as OpenQASM's ``U(theta, phi, lambda)``
  via ZYZ Euler angles, with the leftover global phase carried explicitly.
  Uncontrolled, that phase is unobservable and dropped; under controls it is a
  relative phase and becomes a ``p`` gate on the controls -- exactly the case
  canonical amplitude estimation's controlled Grover powers hit.

Multi-controlled gates are *not* decomposed into Toffolis here.  OpenQASM 3's
``ctrl @`` modifier expresses them directly, and each vendor's transpiler does
that lowering better for its own topology than a generic pass would.  The
:func:`elementary_gate_count` accounting still charges them at the standard
``16 (c - 1)`` two-qubit gates, so the numbers the noise model sees are the
numbers hardware would see.

Round trip
----------
:func:`from_qasm` parses the dialect :func:`to_qasm` emits -- and only that
dialect.  It exists so the export can be *tested* against the simulator rather
than trusted: export, parse, run, compare statevectors.
"""

from __future__ import annotations

import cmath
import math
import re
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

from .statevector import (
    Circuit,
    H,
    I2,
    Operation,
    S,
    T,
    X,
    Y,
    Z,
    phase_matrix,
    rx_matrix,
    ry_matrix,
    rz_matrix,
)

_TOL = 1e-10

__all__ = [
    "decompose",
    "elementary_gate_count",
    "from_qasm",
    "gray_code",
    "multiplexed_ry_gates",
    "phase_gadgets",
    "to_qasm",
    "u3_matrix",
    "zyz_angles",
]


# --------------------------------------------------------------------------
# One-qubit unitaries
# --------------------------------------------------------------------------


def u3_matrix(theta: float, phi: float, lam: float) -> np.ndarray:
    """OpenQASM 3's ``U(theta, phi, lambda)``.

    Same convention as Qiskit: ``U(pi, 0, pi) = X``, ``U(pi/2, 0, pi) = H``.
    """
    c, s = math.cos(theta / 2.0), math.sin(theta / 2.0)
    return np.array(
        [
            [c, -cmath.exp(1j * lam) * s],
            [cmath.exp(1j * phi) * s, cmath.exp(1j * (phi + lam)) * c],
        ],
        dtype=np.complex128,
    )


def zyz_angles(matrix: np.ndarray) -> tuple[float, float, float, float]:
    """Return ``(theta, phi, lambda, alpha)`` with ``matrix = e^{i alpha} U(theta, phi, lambda)``.

    Any 2x2 unitary factors this way.  ``alpha`` is the global phase the
    ``U`` gate cannot carry; it matters only when the gate is controlled.
    """
    m = np.asarray(matrix, dtype=np.complex128)
    if m.shape != (2, 2):
        raise ValueError("zyz decomposition needs a 2x2 matrix")
    if not np.allclose(m.conj().T @ m, np.eye(2), atol=1e-8):
        raise ValueError("matrix is not unitary")

    a00, a01, a10, a11 = m[0, 0], m[0, 1], m[1, 0], m[1, 1]
    theta = 2.0 * math.atan2(abs(a10), abs(a00))
    if abs(a00) > _TOL:
        alpha = cmath.phase(a00)
        if abs(a10) > _TOL:
            phi = cmath.phase(a10 * cmath.exp(-1j * alpha))
            lam = cmath.phase(-a01 * cmath.exp(-1j * alpha))
        else:
            phi = 0.0
            lam = cmath.phase(a11 * cmath.exp(-1j * alpha))
    else:
        # theta = pi: no cos term, so anchor the phase on a10 instead.
        alpha = cmath.phase(a10)
        phi = 0.0
        lam = cmath.phase(-a01 * cmath.exp(-1j * alpha))
    return float(theta), float(phi), float(lam), float(alpha)


def _named_gate(matrix: np.ndarray) -> tuple[str, list[float]] | None:
    """Recognise the standard gates so the QASM stays readable.

    Falls through to a generic ``U`` for anything else; recognition is a
    courtesy to the reader, not a correctness requirement.
    """
    m = np.asarray(matrix, dtype=np.complex128)
    for name, ref in (("x", X), ("y", Y), ("z", Z), ("h", H), ("s", S), ("t", T)):
        if np.allclose(m, ref, atol=_TOL):
            return name, []
    if np.allclose(m, I2, atol=_TOL):
        return "id", []
    # Diagonal gates: p(lambda) if the top-left is 1, rz(theta) if symmetric.
    if abs(m[0, 1]) < _TOL and abs(m[1, 0]) < _TOL:
        if abs(m[0, 0] - 1.0) < _TOL:
            return "p", [cmath.phase(m[1, 1])]
        if abs(m[0, 0] - np.conj(m[1, 1])) < _TOL and abs(abs(m[0, 0]) - 1.0) < _TOL:
            return "rz", [2.0 * cmath.phase(m[1, 1])]
        return None
    # Real rotations about Y.
    if np.all(np.abs(m.imag) < _TOL):
        r = m.real
        if abs(r[0, 0] - r[1, 1]) < _TOL and abs(r[0, 1] + r[1, 0]) < _TOL:
            return "ry", [2.0 * math.atan2(r[1, 0], r[0, 0])]
    # Rotations about X: real diagonal, purely imaginary off-diagonal.
    if (
        abs(m[0, 0].imag) < _TOL
        and abs(m[0, 0] - m[1, 1]) < _TOL
        and abs(m[0, 1] - m[1, 0]) < _TOL
        and abs(m[0, 1].real) < _TOL
    ):
        return "rx", [2.0 * math.atan2(-m[1, 0].imag, m[0, 0].real)]
    return None


# --------------------------------------------------------------------------
# Multiplexed Ry -> Ry + CNOT (Möttönen et al.)
# --------------------------------------------------------------------------


def gray_code(k: int) -> list[int]:
    """The ``2**k`` Gray-code integers in sequence order."""
    return [i ^ (i >> 1) for i in range(2**k)]


def _walsh_signs(k: int) -> np.ndarray:
    """Matrix ``M[j, i] = (-1)^{popcount(j & gray(i))}`` used by the rotation solve."""
    size = 2**k
    g = gray_code(k)
    m = np.empty((size, size), dtype=np.float64)
    for j in range(size):
        for i in range(size):
            m[j, i] = -1.0 if bin(j & g[i]).count("1") % 2 else 1.0
    return m


def multiplexed_ry_gates(
    angles: np.ndarray, controls: Sequence[int], target: int
) -> list[Operation]:
    """Exact decomposition of a uniformly controlled ``Ry`` into ``Ry`` and ``CX``.

    ``angles[j]`` is the rotation for control pattern ``j`` with
    ``controls[0]`` as the most significant bit -- the convention of
    :meth:`Circuit.multiplexed_ry`.  Returns ``2**k`` rotations and ``2**k``
    CNOTs.  With no controls it is a single ``Ry``.
    """
    angles = np.asarray(angles, dtype=np.float64).reshape(-1)
    ctrls = list(controls)
    k = len(ctrls)
    if angles.size != 2**k:
        raise ValueError("angle table must have one entry per control pattern")
    if k == 0:
        return [Operation("ry", ry_matrix(float(angles[0])), (int(target),))]

    m = _walsh_signs(k)
    # M is orthogonal up to a factor 2**k, so M^{-1} = M^T / 2**k.
    rotated = (m.T @ angles) / (2**k)
    g = gray_code(k)

    ops: list[Operation] = []
    for i in range(2**k):
        ops.append(Operation("ry", ry_matrix(float(rotated[i])), (int(target),)))
        # Which control bit flips between this Gray code and the next?  Bit
        # position p (LSB = 0) belongs to controls[k - 1 - p].
        nxt = g[(i + 1) % (2**k)]
        changed = g[i] ^ nxt
        p = changed.bit_length() - 1
        ops.append(Operation("cx", X, (int(target),), (int(ctrls[k - 1 - p]),)))
    return ops


# --------------------------------------------------------------------------
# Diagonal -> phase gadgets
# --------------------------------------------------------------------------


def _walsh_hadamard(values: np.ndarray, n_qubits: int) -> np.ndarray:
    """Unnormalised Walsh-Hadamard transform along every qubit axis."""
    t = np.array(values, dtype=np.float64).reshape([2] * n_qubits)
    for axis in range(n_qubits):
        a = np.take(t, 0, axis=axis)
        b = np.take(t, 1, axis=axis)
        t = np.stack([a + b, a - b], axis=axis)
    return t.reshape(-1)


def phase_gadgets(
    phases: np.ndarray,
    n_qubits: int,
    controls: Sequence[int] = (),
    control_values: Sequence[int] = (),
    tolerance: float = 1e-12,
) -> list[Operation]:
    """Compile ``diag(exp(i * phases))`` into CNOT ladders around ``Rz`` gates.

    ``phases[x]`` is indexed with qubit 0 as the most significant bit.  Every
    Walsh coefficient below ``tolerance`` is dropped, so a quadratic cost
    function compiles to ``O(n**2)`` gadgets rather than ``2**n``.

    ``controls`` gate the whole operator.  A control may lie inside the
    diagonal's own register (that is what :meth:`Circuit.control` produces):
    only the phases on the slice where the controls take ``control_values``
    are then physical, and the expansion runs over the remaining qubits.
    Inside each gadget only the ``Rz`` (and the constant term, which becomes a
    phase on the controls) is controlled -- the CNOT ladders cancel pairwise
    when the control is off, so they need not be.
    """
    phases = np.asarray(phases, dtype=np.float64).reshape(-1)
    if phases.size != 2**n_qubits:
        raise ValueError("phase vector must cover the full computational basis")
    ctrls = tuple(int(c) for c in controls)
    vals = tuple(int(v) for v in control_values) if control_values else (1,) * len(ctrls)

    # Restrict to the controlled slice and to the qubits the diagonal still
    # acts on.
    tensor = phases.reshape([2] * n_qubits)
    key: list = [slice(None)] * n_qubits
    for c, v in zip(ctrls, vals):
        key[c] = v
    free = [q for q in range(n_qubits) if q not in ctrls]
    sub = tensor[tuple(key)].reshape(-1)
    m = len(free)
    coeffs = _walsh_hadamard(sub, m) / (2**m)

    ops: list[Operation] = []
    for mask in range(2**m):
        c = float(coeffs[mask])
        if abs(c) < tolerance:
            continue
        qubits = [free[i] for i in range(m) if (mask >> (m - 1 - i)) & 1]
        if not qubits:
            # Constant term: e^{i c}.  Global uncontrolled; a phase on the
            # controls otherwise.
            if ctrls:
                ops.append(
                    Operation("p", phase_matrix(c), (ctrls[-1],), ctrls[:-1], vals[:-1])
                )
            else:
                ops.append(Operation("gphase", cmath.exp(1j * c) * I2, (0,)))
            continue
        last = qubits[-1]
        ladder = [Operation("cx", X, (last,), (q,)) for q in qubits[:-1]]
        ops.extend(ladder)
        # exp(i c Z...Z) = Rz(-2c) on the parity qubit.
        ops.append(Operation("rz", rz_matrix(-2.0 * c), (last,), ctrls, vals))
        ops.extend(reversed(ladder))
    return ops


# --------------------------------------------------------------------------
# Whole-circuit compilation
# --------------------------------------------------------------------------


def decompose(circuit: Circuit) -> Circuit:
    """Rewrite multiplexed rotations and diagonals into elementary gates.

    The result runs on the same simulator and produces the same statevector
    (bit for bit up to floating point), so the compilation is checkable.
    Multi-controlled one-qubit gates pass through unchanged.
    """
    out = Circuit(circuit.n_qubits, name=circuit.name + "/compiled")
    for op in circuit.ops:
        if op.angles is not None:
            for g in multiplexed_ry_gates(op.angles, op.controls, op.targets[0]):
                out.append(g)
        elif op.diagonal is not None:
            for g in phase_gadgets(op.diagonal, circuit.n_qubits, op.controls, op.control_values):
                out.append(g)
        elif op.matrix is not None and len(op.targets) == 1:
            out.append(op)
        else:
            raise NotImplementedError(
                f"cannot compile multi-target matrix operation {op.name!r}"
            )
    return out


def elementary_gate_count(circuit: Circuit) -> dict[str, int]:
    """Count one- and two-qubit gates after compilation.

    A gate with ``c >= 2`` controls is charged ``16 (c - 1)`` two-qubit gates,
    the standard ancilla-free Toffoli-ladder figure.  This is what a noise
    model should multiply its per-gate error by -- not the logical count.
    """
    compiled = circuit if circuit.name.endswith("/compiled") else decompose(circuit)
    one = two = 0
    for op in compiled.ops:
        c = op.n_controls
        if c == 0:
            one += 1
        elif c == 1:
            two += 1
        else:
            two += 16 * (c - 1)
    return {
        "qubits": circuit.n_qubits,
        "one_qubit": one,
        "two_qubit": two,
        "total": one + two,
    }


# --------------------------------------------------------------------------
# OpenQASM 3 serialisation
# --------------------------------------------------------------------------


def _fmt(x: float) -> str:
    return repr(float(x))


def _emit_op(op: Operation) -> list[str]:
    """QASM statements for one (possibly controlled) one-qubit operation."""
    if op.matrix is None:
        raise ValueError("decompose() the circuit before exporting")
    if len(op.targets) != 1:
        raise NotImplementedError("multi-target gates are not exported")
    target = op.targets[0]
    ctrls = list(op.controls)
    vals = list(op.control_values) if op.control_values else [1] * len(ctrls)

    if not ctrls and np.allclose(op.matrix, op.matrix[0, 0] * I2, atol=_TOL):
        # Pure global phase.  Unobservable uncontrolled, but keep it so the
        # round trip is exact.
        alpha = cmath.phase(op.matrix[0, 0])
        return [f"gphase({_fmt(alpha)});"] if abs(alpha) > _TOL else []

    named = _named_gate(op.matrix)
    lines: list[str] = []
    if named is not None:
        gate, params = named
        alpha = 0.0
    else:
        theta, phi, lam, alpha = zyz_angles(op.matrix)
        gate, params = "U", [theta, phi, lam]

    pos = [c for c, v in zip(ctrls, vals) if v == 1]
    neg = [c for c, v in zip(ctrls, vals) if v == 0]
    mods = ""
    if pos:
        mods += f"ctrl({len(pos)}) @ " if len(pos) > 1 else "ctrl @ "
    if neg:
        mods += f"negctrl({len(neg)}) @ " if len(neg) > 1 else "negctrl @ "
    args = ", ".join(f"q[{q}]" for q in pos + neg + [target])
    pstr = f"({', '.join(_fmt(p) for p in params)})" if params else ""
    lines.append(f"{mods}{gate}{pstr} {args};")

    if ctrls and abs(alpha) > _TOL:
        # The global phase of the target gate is a relative phase under
        # control: apply p(alpha) on the controls, itself controlled by the
        # remaining controls.
        lines.extend(
            _emit_op(Operation("p", phase_matrix(alpha), (ctrls[-1],), tuple(ctrls[:-1]), tuple(vals[:-1])))
        )
    return lines


def to_qasm(circuit: Circuit, measure: bool = True, compile: bool = True) -> str:
    """Serialise ``circuit`` as OpenQASM 3.

    ``compile=True`` runs :func:`decompose` first, which is required for any
    circuit holding multiplexed rotations or diagonal operators.
    """
    c = decompose(circuit) if compile else circuit
    n = c.n_qubits
    lines = [
        "OPENQASM 3.0;",
        'include "stdgates.inc";',
        f"// {circuit.name}: {n} qubits, {len(c.ops)} gates after compilation",
        f"qubit[{n}] q;",
    ]
    if measure:
        lines.append(f"bit[{n}] c;")
    for op in c.ops:
        lines.extend(_emit_op(op))
    if measure:
        lines.append("c = measure q;")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Parser for the emitted dialect (test support)
# --------------------------------------------------------------------------

_GATE_RE = re.compile(
    r"^(?P<mods>(?:(?:ctrl|negctrl)(?:\(\d+\))?\s*@\s*)*)"
    r"(?P<gate>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?:\((?P<params>[^)]*)\))?\s+(?P<args>[^;]+);$"
)
_MOD_RE = re.compile(r"(ctrl|negctrl)(?:\((\d+)\))?")

_FIXED = {"x": X, "y": Y, "z": Z, "h": H, "s": S, "t": T, "id": I2}
_PARAM = {
    "rx": lambda p: rx_matrix(p[0]),
    "ry": lambda p: ry_matrix(p[0]),
    "rz": lambda p: rz_matrix(p[0]),
    "p": lambda p: phase_matrix(p[0]),
    "U": lambda p: u3_matrix(p[0], p[1], p[2]),
}


def from_qasm(text: str) -> Circuit:
    """Parse the subset of OpenQASM 3 that :func:`to_qasm` emits.

    Supports a single ``qubit[n] q;`` register, ``gphase``, the standard
    gates, ``U``, and ``ctrl``/``negctrl`` modifiers.  This is a test oracle,
    not a general parser.
    """
    circuit: Circuit | None = None
    for raw in text.splitlines():
        line = raw.split("//", 1)[0].strip()
        if not line or line.startswith(("OPENQASM", "include", "bit[")):
            continue
        if line.startswith("qubit["):
            n = int(re.match(r"qubit\[(\d+)\]", line).group(1))
            circuit = Circuit(n, name="from_qasm")
            continue
        if line.endswith("= measure q;"):
            continue
        if circuit is None:
            raise ValueError("gate before qubit declaration")
        if line.startswith("gphase("):
            phi = float(line[len("gphase(") : line.index(")")])
            circuit.global_phase(phi)
            continue
        m = _GATE_RE.match(line)
        if m is None:
            raise ValueError(f"unparsed statement: {line!r}")
        gate = m.group("gate")
        params = [float(p) for p in m.group("params").split(",")] if m.group("params") else []
        args = [int(a.strip()[2:-1]) for a in m.group("args").split(",")]

        n_pos = n_neg = 0
        for kind, count in _MOD_RE.findall(m.group("mods")):
            k = int(count) if count else 1
            if kind == "ctrl":
                n_pos += k
            else:
                n_neg += k
        controls = tuple(args[: n_pos + n_neg])
        values = (1,) * n_pos + (0,) * n_neg
        target = args[n_pos + n_neg]
        if gate == "cx":
            controls, values, target = (args[0],), (1,), args[1]
            matrix = X
        elif gate in _FIXED:
            matrix = _FIXED[gate]
        elif gate in _PARAM:
            matrix = _PARAM[gate](params)
        else:
            raise ValueError(f"unknown gate {gate!r}")
        circuit.append(Operation(gate, matrix, (target,), controls, values))
    if circuit is None:
        raise ValueError("no qubit register declared")
    return circuit
