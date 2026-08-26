"""Quantum Amplitude Estimation -- the engine behind quantum risk and pricing.

Given a state-preparation operator ``A`` acting on ``n+1`` qubits such that

.. math:: A|0\\rangle = \\sqrt{1-a}\\,|\\psi_{bad}\\rangle|0\\rangle + \\sqrt{a}\\,|\\psi_{good}\\rangle|1\\rangle

amplitude estimation recovers ``a`` -- the probability that the *objective
qubit* reads 1.  Classical Monte Carlo needs ``O(1/eps^2)`` samples to reach
error ``eps``; amplitude estimation needs ``O(1/eps)`` applications of the
Grover operator.  That quadratic speedup (Brassard-Hoyer-Mosca-Tapp 2002;
Montanaro 2015) is the single strongest theoretical result in quantum finance,
and every expectation value -- an option price, a VaR, a CVaR -- is an ``a``.

Two estimators are provided:

``canonical_amplitude_estimation``
    Phase estimation on the Grover operator.  Exact and textbook, but needs
    ``m`` extra evaluation qubits and controlled-``Q`` powers, so it is the
    most hardware-expensive option and only reachable with error correction.

``maximum_likelihood_amplitude_estimation`` (MLAE, Suzuki et al. 2020)
    Runs ``Q^k`` for a schedule of powers, measures the objective qubit, and
    fits ``a`` by maximum likelihood.  No evaluation register and no controlled
    operations, which makes it the realistic near-term choice.  This is the
    default used elsewhere in the package.

Reality check
-------------
The speedup is in *oracle queries*, not wall-clock time.  Reaching the crossover
against a classical Monte Carlo running on a CPU requires fault-tolerant
hardware that does not exist yet.  These implementations are for building and
validating the algorithms, not for beating a classical simulation today.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from .statevector import Circuit, probability_of_one, marginal

__all__ = [
    "AmplitudeEstimationResult",
    "grover_operator",
    "canonical_amplitude_estimation",
    "maximum_likelihood_amplitude_estimation",
    "estimate_amplitude",
    "classical_monte_carlo_error",
]


@dataclass
class AmplitudeEstimationResult:
    """Outcome of an amplitude-estimation run."""

    estimate: float
    method: str
    oracle_calls: int
    shots: int
    confidence_interval: tuple[float, float] | None = None
    detail: dict = field(default_factory=dict)

    def __repr__(self) -> str:  # pragma: no cover - display helper
        ci = ""
        if self.confidence_interval is not None:
            lo, hi = self.confidence_interval
            ci = f" ci=[{lo:.5f}, {hi:.5f}]"
        return (
            f"<AE {self.method} a={self.estimate:.6f}{ci} "
            f"oracle_calls={self.oracle_calls} shots={self.shots}>"
        )


# --------------------------------------------------------------------------
# The Grover / amplitude-amplification operator
# --------------------------------------------------------------------------


def grover_operator(state_prep: Circuit, objective_qubit: int) -> Circuit:
    """Build ``Q = -A S_0 A^dagger S_chi`` for the given preparation circuit.

    ``S_chi`` flips the sign of states where the objective qubit is |1>, and
    ``S_0`` flips the sign of |0...0>.  Applying ``Q`` ``k`` times rotates the
    prepared state so that

    .. math:: P(\\text{objective}=1) = \\sin^2\\big((2k+1)\\theta\\big),\\quad a = \\sin^2\\theta

    The overall ``-1`` is a global phase when ``Q`` is used alone, but becomes
    physically meaningful under the controlled-``Q`` powers that canonical
    amplitude estimation applies, so it is included explicitly.
    """
    n = state_prep.n_qubits
    if not 0 <= objective_qubit < n:
        raise ValueError("objective qubit outside the register")

    q = Circuit(n, name="grover")

    # S_chi: phase flip on the "good" subspace.
    q.z(objective_qubit)

    # A^dagger
    q.compose(state_prep.inverse())

    # S_0 = I - 2|0><0|, built by conjugating a multi-controlled Z with X gates.
    for i in range(n):
        q.x(i)
    if n == 1:
        q.z(0)
    else:
        q.mcz(list(range(n - 1)), n - 1)
    for i in range(n):
        q.x(i)

    # A
    q.compose(state_prep)

    # Global -1.
    q.global_phase(math.pi)
    return q


def _grover_power_state(state_prep: Circuit, grover: Circuit, power: int) -> np.ndarray:
    """Return the statevector of ``Q^power A |0>``."""
    state = state_prep.run()
    for _ in range(power):
        state = grover.run(state)
    return state


# --------------------------------------------------------------------------
# Canonical (phase-estimation) amplitude estimation
# --------------------------------------------------------------------------


def canonical_amplitude_estimation(
    state_prep: Circuit,
    objective_qubit: int,
    n_eval_qubits: int = 5,
) -> AmplitudeEstimationResult:
    """Textbook QAE: phase estimation on the Grover operator.

    Uses ``n_eval_qubits`` ancillas, giving a discrete grid of ``2**m``
    resolvable amplitudes.  The returned estimate is the grid point with the
    highest measurement probability, which is why the error floor is the grid
    spacing rather than shot noise.
    """
    n_state = state_prep.n_qubits
    m = int(n_eval_qubits)
    if m < 1:
        raise ValueError("need at least one evaluation qubit")

    total = m + n_state
    # Evaluation register occupies qubits 0..m-1, state register follows.
    state_qubits = list(range(m, total))

    circuit = Circuit(total, name="canonical_qae")
    for i in range(m):
        circuit.h(i)
    circuit.compose(state_prep, state_qubits)

    base_grover = grover_operator(state_prep, objective_qubit)
    wide = Circuit(total, name="grover_wide")
    wide.compose(base_grover, state_qubits)

    # Controlled-Q^(2^j), most significant evaluation qubit first.
    for j in range(m):
        power = 2 ** (m - 1 - j)
        controlled = wide.control(j)
        for _ in range(power):
            circuit.ops.extend(controlled.ops)

    circuit.qft(list(range(m)), inverse=True)

    state = circuit.run()
    probs = marginal(state, total, list(range(m)))

    best = int(np.argmax(probs))
    amplitudes = np.sin(np.pi * np.arange(2**m) / (2**m)) ** 2
    estimate = float(amplitudes[best])

    oracle_calls = 2**m - 1
    return AmplitudeEstimationResult(
        estimate=estimate,
        method="canonical",
        oracle_calls=oracle_calls,
        shots=0,
        detail={
            "eval_qubits": m,
            "grid_resolution": float(np.pi / (2**m)),
            "measured_index": best,
            "index_probability": float(probs[best]),
        },
    )


# --------------------------------------------------------------------------
# Maximum-likelihood amplitude estimation
# --------------------------------------------------------------------------


def _mlae_log_likelihood(
    theta: np.ndarray,
    powers: Sequence[int],
    hits: Sequence[int],
    shots: Sequence[int],
) -> np.ndarray:
    """Log-likelihood of ``theta`` given per-power measurement counts."""
    eps = 1e-12
    total = np.zeros_like(theta)
    for k, h, n in zip(powers, hits, shots):
        angle = (2 * k + 1) * theta
        p1 = np.clip(np.sin(angle) ** 2, eps, 1.0 - eps)
        total += h * np.log(p1) + (n - h) * np.log(1.0 - p1)
    return total


def maximum_likelihood_amplitude_estimation(
    state_prep: Circuit,
    objective_qubit: int,
    n_powers: int = 6,
    shots_per_power: int = 512,
    schedule: str = "exponential",
    rng: np.random.Generator | None = None,
    grid_points: int = 20001,
) -> AmplitudeEstimationResult:
    """Estimate ``a`` by fitting ``sin^2((2k+1)theta)`` across Grover powers.

    Parameters
    ----------
    n_powers:
        How many Grover powers to run.  With the exponential schedule the
        largest power is ``2**(n_powers-2)``, and the total oracle cost grows
        like ``2**n_powers`` while the error falls like ``1/2**n_powers`` --
        that ratio *is* the quadratic speedup.
    schedule:
        ``"exponential"`` gives powers ``0, 1, 2, 4, 8, ...`` (Suzuki et al.'s
        LIS schedule, the one with the proven Heisenberg-limited scaling);
        ``"linear"`` gives ``0, 1, 2, 3, ...``.
    """
    rng = rng or np.random.default_rng()
    if n_powers < 1:
        raise ValueError("need at least one Grover power")

    if schedule == "exponential":
        powers = [0] + [2**j for j in range(n_powers - 1)]
    elif schedule == "linear":
        powers = list(range(n_powers))
    else:
        raise ValueError("schedule must be 'exponential' or 'linear'")

    grover = grover_operator(state_prep, objective_qubit)
    n = state_prep.n_qubits

    hits: list[int] = []
    shot_counts: list[int] = []
    oracle_calls = 0
    for k in powers:
        state = _grover_power_state(state_prep, grover, k)
        p1 = probability_of_one(state, n, objective_qubit)
        # Sampling the Born-rule outcome keeps this an honest shot-based
        # estimator rather than reading the amplitude straight off the vector.
        observed = int(rng.binomial(shots_per_power, min(max(p1, 0.0), 1.0)))
        hits.append(observed)
        shot_counts.append(shots_per_power)
        oracle_calls += (2 * k + 1) * shots_per_power

    theta_grid = np.linspace(1e-9, math.pi / 2 - 1e-9, grid_points)
    ll = _mlae_log_likelihood(theta_grid, powers, hits, shot_counts)
    best_idx = int(np.argmax(ll))

    # Local refinement around the grid maximum.
    lo = theta_grid[max(0, best_idx - 1)]
    hi = theta_grid[min(grid_points - 1, best_idx + 1)]
    fine = np.linspace(lo, hi, 2001)
    ll_fine = _mlae_log_likelihood(fine, powers, hits, shot_counts)
    theta_hat = float(fine[int(np.argmax(ll_fine))])
    estimate = float(math.sin(theta_hat) ** 2)

    # Likelihood-ratio interval: drop of 1.92 in log-likelihood ~ 95% for 1 dof.
    peak = float(ll_fine.max())
    inside = theta_grid[ll >= peak - 1.92]
    if inside.size:
        ci = (
            float(math.sin(float(inside.min())) ** 2),
            float(math.sin(float(inside.max())) ** 2),
        )
    else:
        ci = None

    return AmplitudeEstimationResult(
        estimate=estimate,
        method=f"mlae/{schedule}",
        oracle_calls=oracle_calls,
        shots=int(sum(shot_counts)),
        confidence_interval=ci,
        detail={
            "powers": powers,
            "hits": hits,
            "theta": theta_hat,
            "max_power": max(powers),
        },
    )


def estimate_amplitude(
    state_prep: Circuit,
    objective_qubit: int,
    method: str = "mlae",
    **kwargs,
) -> AmplitudeEstimationResult:
    """Dispatch to an amplitude-estimation method by name."""
    if method in ("mlae", "ml", "maximum_likelihood"):
        return maximum_likelihood_amplitude_estimation(state_prep, objective_qubit, **kwargs)
    if method in ("canonical", "phase", "qpe"):
        return canonical_amplitude_estimation(state_prep, objective_qubit, **kwargs)
    raise ValueError(f"unknown amplitude estimation method: {method!r}")


def classical_monte_carlo_error(a: float, samples: int) -> float:
    """Standard error of a classical Monte Carlo estimate of ``a``.

    The reference point for any claimed quantum advantage: this falls as
    ``1/sqrt(N)`` while amplitude estimation falls as ``1/N`` in oracle calls.
    """
    if samples <= 0:
        raise ValueError("samples must be positive")
    a = min(max(float(a), 0.0), 1.0)
    return math.sqrt(max(a * (1.0 - a), 0.0) / samples)
