"""The five postulates of quantum mechanics, implemented and checkable.

The rest of this package leans on the postulates constantly -- amplitude
estimation is Born's rule, every gate is Postulate 3, the joint distribution of a
basket option is Postulate 4.  Those uses were tested against *finance*
references.  This module closes the loop by implementing the postulates directly
and testing them as physics, in the form Laforest states them:

1. **State** -- a unit vector in a complex Hilbert space.
2. **Measurement** -- Born's rule ``P(phi) = |<phi|psi>|^2``, and *collapse* of
   the state into the measured outcome.
3. **Evolution** -- quantum operations are unitary operators.
4. **Composition** -- the Hilbert space of a composite system is the tensor
   (Kronecker) product of the individual spaces.
5. **Observables** -- physical quantities are eigenvalues of a Hermitian
   operator.

Postulates 1 and 3 were already exercised by :mod:`quantum.statevector`.  The
half of Postulate 2 that this package never used -- collapse -- and the whole of
Postulates 4 and 5 are implemented here.

Why this belongs in a trading package
-------------------------------------
Beyond correctness, Postulate 4 settles a claim that popular quantum-finance
writing repeats: that market correlation is a kind of entanglement.  It is not,
and the distinction is measurable rather than rhetorical.  A joint distribution
built from *any* classical correlation matrix loads into a state whose
entanglement can be computed directly -- see
:func:`entanglement_entropy` and the worked comparison in the test suite.
Classical correlation and entanglement are different objects, and Postulate 4 is
where the difference lives.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

__all__ = [
    "kron",
    "is_unitary",
    "is_hermitian",
    "measure",
    "MeasurementOutcome",
    "reduced_density_matrix",
    "schmidt_coefficients",
    "entanglement_entropy",
    "is_separable",
    "bell_states",
    "Observable",
    "expectation",
    "measure_observable",
    "chsh_value",
    "max_classical_chsh",
    "CHSH_CLASSICAL_BOUND",
    "CHSH_TSIRELSON_BOUND",
]

_TOL = 1e-10


# --------------------------------------------------------------------------
# Postulate 4: composition by tensor product
# --------------------------------------------------------------------------


def kron(*operands: np.ndarray) -> np.ndarray:
    """Kronecker product of states or operators, left to right.

    This is Postulate 4 written down: the joint system of ``|psi>`` and
    ``|phi>`` is ``|psi> (x) |phi>``, and the joint operation of ``U`` and ``V``
    is ``U (x) V``.  The dimension *multiplies*, which is the whole reason a
    quantum register is exponentially large -- and the reason simulating one is
    exponentially expensive.
    """
    if not operands:
        raise ValueError("need at least one operand")
    result = np.asarray(operands[0])
    for operand in operands[1:]:
        result = np.kron(result, np.asarray(operand))
    return result


def is_unitary(matrix: np.ndarray, tolerance: float = _TOL) -> bool:
    """Postulate 3: ``U† U = U U† = I``."""
    m = np.asarray(matrix, dtype=np.complex128)
    if m.ndim != 2 or m.shape[0] != m.shape[1]:
        return False
    identity = np.eye(m.shape[0])
    return bool(
        np.allclose(m.conj().T @ m, identity, atol=tolerance)
        and np.allclose(m @ m.conj().T, identity, atol=tolerance)
    )


def is_hermitian(matrix: np.ndarray, tolerance: float = _TOL) -> bool:
    """Postulate 5: an observable satisfies ``V† = V``, so its eigenvalues are real."""
    m = np.asarray(matrix, dtype=np.complex128)
    if m.ndim != 2 or m.shape[0] != m.shape[1]:
        return False
    return bool(np.allclose(m.conj().T, m, atol=tolerance))


# --------------------------------------------------------------------------
# Postulate 2: Born's rule *and* collapse
# --------------------------------------------------------------------------


@dataclass
class MeasurementOutcome:
    """What a measurement returns: an outcome, and the state left behind."""

    index: int
    probability: float
    collapsed_state: np.ndarray
    label: str = ""

    def __repr__(self) -> str:  # pragma: no cover - display helper
        name = self.label or f"|{self.index}>"
        return f"<Measured {name} p={self.probability:.4f}>"


def measure(
    state: np.ndarray,
    basis: np.ndarray | None = None,
    rng: np.random.Generator | None = None,
) -> MeasurementOutcome:
    """Measure ``state``, returning the outcome *and the collapsed state*.

    The half of Postulate 2 that sampling alone does not capture: after a
    measurement the system is no longer in a superposition.  It is in the state
    that was measured, and a repeat measurement in the same basis returns the
    same answer with certainty.  Any adaptive protocol -- measure, branch,
    measure again -- depends on this.

    ``basis`` is a matrix whose *columns* are an orthonormal basis; omit it to
    measure in the computational basis.
    """
    rng = rng or np.random.default_rng()
    psi = np.asarray(state, dtype=np.complex128).reshape(-1)
    norm = float(np.linalg.norm(psi))
    if norm <= 0:
        raise ValueError("cannot measure a zero-norm state")
    psi = psi / norm

    if basis is None:
        amplitudes = psi
        vectors = None
    else:
        basis = np.asarray(basis, dtype=np.complex128)
        if basis.shape[0] != psi.size:
            raise ValueError("basis dimension does not match the state")
        if not np.allclose(basis.conj().T @ basis, np.eye(basis.shape[1]), atol=1e-8):
            raise ValueError("measurement basis must be orthonormal")
        # <phi_i|psi> for each basis vector.
        amplitudes = basis.conj().T @ psi
        vectors = basis

    probabilities = np.abs(amplitudes) ** 2
    total = probabilities.sum()
    if total <= 0:
        raise ValueError("degenerate measurement")
    probabilities = probabilities / total

    index = int(rng.choice(probabilities.size, p=probabilities))
    if vectors is None:
        collapsed = np.zeros_like(psi)
        collapsed[index] = 1.0
    else:
        collapsed = vectors[:, index].copy()

    return MeasurementOutcome(
        index=index,
        probability=float(probabilities[index]),
        collapsed_state=collapsed,
    )


# --------------------------------------------------------------------------
# Postulate 4 continued: entanglement, the thing correlation is not
# --------------------------------------------------------------------------


def _bipartition(state: np.ndarray, n_qubits: int, cut: int) -> np.ndarray:
    """Reshape a state into the matrix whose SVD gives the Schmidt spectrum."""
    if not 1 <= cut < n_qubits:
        raise ValueError("cut must split the register into two non-empty parts")
    psi = np.asarray(state, dtype=np.complex128).reshape(-1)
    if psi.size != 2**n_qubits:
        raise ValueError("state size does not match the qubit count")
    return psi.reshape(2**cut, 2 ** (n_qubits - cut))


def schmidt_coefficients(state: np.ndarray, n_qubits: int, cut: int = 1) -> np.ndarray:
    """Schmidt coefficients across a bipartition, largest first.

    Every bipartite state can be written ``sum_i lambda_i |a_i>|b_i>``.  The
    number of non-zero ``lambda_i`` -- the Schmidt rank -- is exactly 1 when the
    state is a product state, and greater than 1 when it is entangled.  So this
    single computation decides separability.
    """
    matrix = _bipartition(state, n_qubits, cut)
    values = np.linalg.svd(matrix, compute_uv=False)
    total = float(np.sqrt((values**2).sum()))
    return values / total if total > 0 else values


def reduced_density_matrix(state: np.ndarray, n_qubits: int, cut: int = 1) -> np.ndarray:
    """Trace out the second subsystem, leaving the first's density matrix.

    A product state leaves a *pure* reduced state; an entangled one leaves a
    mixed one.  That loss of purity under tracing is what "the parts have no
    individual state" means concretely.
    """
    matrix = _bipartition(state, n_qubits, cut)
    return matrix @ matrix.conj().T


def entanglement_entropy(state: np.ndarray, n_qubits: int, cut: int = 1) -> float:
    """Von Neumann entropy of the reduced state, in bits.

    Zero exactly when the state is a product across the cut; 1 bit for a Bell
    state, which is the maximum for a single-qubit cut.  This is the quantitative
    answer to "is this entangled", and it is *not* a correlation coefficient:
    a classically correlated joint distribution loaded into a register can carry
    a large correlation and still return zero here.
    """
    values = schmidt_coefficients(state, n_qubits, cut)
    weights = values**2
    weights = weights[weights > _TOL]
    if weights.size <= 1:
        return 0.0
    return float(-np.sum(weights * np.log2(weights)))


def is_separable(state: np.ndarray, n_qubits: int, cut: int = 1, tolerance: float = 1e-8) -> bool:
    """Whether ``state`` factorises across the cut -- Schmidt rank 1."""
    values = schmidt_coefficients(state, n_qubits, cut)
    return bool(np.sum(values > tolerance) <= 1)


def bell_states() -> dict[str, np.ndarray]:
    """The four maximally entangled two-qubit states.

    None of them factorises, and each carries exactly 1 bit of entanglement
    entropy -- the canonical demonstration that a joint state can be fully
    specified while neither part has a state of its own.
    """
    r = 1.0 / math.sqrt(2.0)
    return {
        "Phi+": np.array([r, 0, 0, r], dtype=np.complex128),
        "Phi-": np.array([r, 0, 0, -r], dtype=np.complex128),
        "Psi+": np.array([0, r, r, 0], dtype=np.complex128),
        "Psi-": np.array([0, r, -r, 0], dtype=np.complex128),
    }


# --------------------------------------------------------------------------
# Postulate 5: observables
# --------------------------------------------------------------------------


@dataclass
class Observable:
    """A physical quantity: a Hermitian operator and its spectrum.

    Postulate 5 says a measurement of an observable returns one of its
    *eigenvalues*, with probability given by the overlap with the corresponding
    eigenvector.  Hermiticity is what guarantees those eigenvalues are real --
    which is the whole reason physical quantities must be Hermitian operators
    rather than arbitrary matrices.
    """

    matrix: np.ndarray
    name: str = "observable"
    eigenvalues: np.ndarray = field(init=False)
    eigenvectors: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        self.matrix = np.asarray(self.matrix, dtype=np.complex128)
        if not is_hermitian(self.matrix):
            raise ValueError(f"{self.name} is not Hermitian; its eigenvalues would be complex")
        values, vectors = np.linalg.eigh(self.matrix)
        self.eigenvalues = values.real
        self.eigenvectors = vectors

    @property
    def dimension(self) -> int:
        return int(self.matrix.shape[0])

    @classmethod
    def from_diagonal(cls, values: np.ndarray, name: str = "diagonal") -> "Observable":
        """An observable diagonal in the computational basis.

        The common case in this package: a QUBO objective *is* such an
        observable, with the portfolio's cost as its eigenvalue spectrum.
        """
        values = np.asarray(values, dtype=np.float64).reshape(-1)
        return cls(np.diag(values.astype(np.complex128)), name=name)


def expectation(state: np.ndarray, observable: Observable | np.ndarray) -> float:
    """``<psi| V |psi>`` -- the mean value of an observable, always real."""
    matrix = observable.matrix if isinstance(observable, Observable) else np.asarray(observable)
    if not is_hermitian(matrix):
        raise ValueError("expectation is only defined for Hermitian observables")
    psi = np.asarray(state, dtype=np.complex128).reshape(-1)
    psi = psi / np.linalg.norm(psi)
    return float(np.real(psi.conj() @ (matrix @ psi)))


def measure_observable(
    state: np.ndarray,
    observable: Observable,
    rng: np.random.Generator | None = None,
) -> MeasurementOutcome:
    """Measure an observable: outcome is an eigenvalue, state collapses to its eigenvector."""
    outcome = measure(state, basis=observable.eigenvectors, rng=rng)
    outcome.label = f"{observable.name}={observable.eigenvalues[outcome.index]:.6g}"
    return outcome


# --------------------------------------------------------------------------
# The line between correlation and entanglement, made measurable
# --------------------------------------------------------------------------

CHSH_CLASSICAL_BOUND = 2.0
"""No classically correlated system can exceed this, however strong the correlation."""

CHSH_TSIRELSON_BOUND = 2.0 * math.sqrt(2.0)
"""Tsirelson's bound: the most any quantum state can achieve, ~2.828."""


def _spin_observable(angle: float) -> np.ndarray:
    """Measurement of spin along a direction in the X-Z plane."""
    return np.array(
        [[math.cos(angle), math.sin(angle)], [math.sin(angle), -math.cos(angle)]],
        dtype=np.complex128,
    )


def chsh_value(
    state: np.ndarray,
    angles: tuple[float, float, float, float] = (0.0, math.pi / 2, math.pi / 4, -math.pi / 4),
) -> float:
    """CHSH correlation value for a two-qubit state.

    ``S = |E(a,b) + E(a,b') + E(a',b) - E(a',b')|`` where each ``E`` is the
    correlation of two spin measurements.  The sign placement and the angles must
    match: with settings ``(0, pi/2)`` and ``(pi/4, -pi/4)`` the minus belongs on
    the ``(a', b')`` term, and misplacing it silently returns 0 for a Bell state.

    This is the operational distinction between correlation and entanglement,
    and it is why "market correlation is a kind of entanglement" is false rather
    than merely loose.  **Any** classically correlated system -- any joint
    distribution, any shared randomness, any covariance matrix, however
    extreme -- satisfies ``S <= 2``.  Entangled states reach ``2*sqrt(2)``.

    Correlation strength is not the axis that separates them; a correlation of
    1.0 still yields ``S <= 2``.  Entanglement is a different object, and this
    number tells the two apart.
    """
    psi = np.asarray(state, dtype=np.complex128).reshape(-1)
    if psi.size != 4:
        raise ValueError("CHSH is defined here for two qubits")
    psi = psi / np.linalg.norm(psi)

    a, a_prime, b, b_prime = angles

    def correlation(first: float, second: float) -> float:
        joint = np.kron(_spin_observable(first), _spin_observable(second))
        return float(np.real(psi.conj() @ (joint @ psi)))

    return abs(
        correlation(a, b)
        + correlation(a, b_prime)
        + correlation(a_prime, b)
        - correlation(a_prime, b_prime)
    )


def max_classical_chsh() -> float:
    """The largest CHSH value any classical correlation can produce.

    Proved here by exhaustion rather than assertion.  A local hidden-variable
    model assigns each party a deterministic outcome per measurement setting;
    with two settings and two outcomes each there are ``2**4 = 16`` such
    strategies, and *every* classical correlation -- any joint distribution, any
    covariance matrix, any amount of shared randomness -- is a probabilistic
    mixture of them.  Since CHSH is linear in the mixture, the maximum over
    mixtures is the maximum over the 16 deterministic strategies.

    That maximum is exactly 2.  Correlation *strength* is irrelevant: a
    correlation of 0.999 is still a mixture of these strategies and still bounded
    by 2.  This is Bell's theorem, and it is the precise sense in which
    entanglement is not "strong correlation".
    """
    best = 0.0
    for assignment in range(16):
        a = 1 if (assignment >> 3) & 1 else -1
        a_prime = 1 if (assignment >> 2) & 1 else -1
        b = 1 if (assignment >> 1) & 1 else -1
        b_prime = 1 if assignment & 1 else -1
        value = abs(a * b + a * b_prime + a_prime * b - a_prime * b_prime)
        best = max(best, float(value))
    return best
