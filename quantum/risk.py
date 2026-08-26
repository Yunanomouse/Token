"""Risk measures by quantum amplitude estimation.

Value at Risk and Expected Shortfall are both expectations over a loss
distribution, so both reduce to amplitude estimation:

* **VaR** is a *quantile*.  Estimating ``P(loss <= x)`` for a candidate ``x`` is
  one amplitude estimation; a bisection over ``x`` finds the quantile in
  ``O(log N)`` such estimations.
* **CVaR / Expected Shortfall** is a conditional mean, which is the same payoff
  rotation used for option pricing, restricted to the tail.

The classical cost of a Monte Carlo VaR is ``O(1/eps^2)`` paths.  Amplitude
estimation needs ``O(1/eps)`` oracle calls.  Because risk engines re-run these
overnight across thousands of scenarios, this is the application banks quote most
often when justifying quantum research budgets.

The caveat that quote usually omits
-----------------------------------
The speedup counts *oracle calls*, and each oracle call here is a full
distribution load plus a comparator.  On any hardware that exists today a
classical Monte Carlo finishes first by many orders of magnitude.  Every function
below returns the classical answer alongside the quantum one so the comparison
stays visible rather than assumed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .amplitude import AmplitudeEstimationResult, estimate_amplitude
from .preparation import GridDistribution, prepare_distribution
from .pricing import integer_comparator
from .statevector import Circuit

__all__ = [
    "RiskResult",
    "portfolio_loss_distribution",
    "classical_var_cvar",
    "parametric_var",
    "quantum_value_at_risk",
    "quantum_expected_shortfall",
]


@dataclass
class RiskResult:
    """A risk number with its classical counterpart and the cost of each."""

    value: float
    classical_value: float
    measure: str
    confidence: float
    oracle_calls: int = 0
    detail: dict = field(default_factory=dict)

    @property
    def absolute_error(self) -> float:
        return abs(self.value - self.classical_value)

    def __repr__(self) -> str:  # pragma: no cover - display helper
        return (
            f"<{self.measure} @{self.confidence:.0%} quantum={self.value:.5f} "
            f"classical={self.classical_value:.5f} oracle_calls={self.oracle_calls}>"
        )


# --------------------------------------------------------------------------
# Loss distributions
# --------------------------------------------------------------------------


def portfolio_loss_distribution(
    weights: np.ndarray,
    expected_returns: np.ndarray,
    covariance: np.ndarray,
    n_qubits: int = 5,
    horizon: float = 1.0 / 252.0,
    n_sigma: float = 4.0,
) -> GridDistribution:
    """Discretised distribution of portfolio *loss* over one horizon.

    Losses are expressed as a positive fraction of portfolio value, under a
    normal approximation to the aggregate return.  For a day-horizon book that
    approximation is defensible; for anything with optionality in it, it is not,
    and a full revaluation grid would be needed instead.
    """
    w = np.asarray(weights, dtype=np.float64).reshape(-1)
    mu = float(w @ np.asarray(expected_returns, dtype=np.float64).reshape(-1)) * horizon
    var = float(w @ np.asarray(covariance, dtype=np.float64) @ w) * horizon
    sd = math.sqrt(max(var, 1e-24))

    # Loss = -return, so the loss distribution is N(-mu, sd^2).
    loss_mean = -mu
    lo = loss_mean - n_sigma * sd
    hi = loss_mean + n_sigma * sd
    grid = np.linspace(lo, hi, 2**n_qubits)
    pdf = np.exp(-0.5 * ((grid - loss_mean) / sd) ** 2)
    pdf = pdf / pdf.sum()
    return GridDistribution(values=grid, probabilities=pdf, n_qubits=n_qubits)


def classical_var_cvar(
    losses: np.ndarray,
    probabilities: np.ndarray | None = None,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Exact VaR and CVaR on a discrete loss distribution.

    Used as the reference the quantum routines are graded against, and as the
    fast path anyone should actually use today.
    """
    losses = np.asarray(losses, dtype=np.float64).reshape(-1)
    if probabilities is None:
        probabilities = np.full(losses.size, 1.0 / losses.size)
    probabilities = np.asarray(probabilities, dtype=np.float64).reshape(-1)
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must lie strictly between 0 and 1")

    order = np.argsort(losses)
    sorted_losses = losses[order]
    sorted_probs = probabilities[order]
    cdf = np.cumsum(sorted_probs)

    idx = int(np.searchsorted(cdf, confidence, side="left"))
    idx = min(idx, sorted_losses.size - 1)
    var = float(sorted_losses[idx])

    tail_mask = sorted_losses >= var
    tail_prob = float(sorted_probs[tail_mask].sum())
    if tail_prob <= 0:
        cvar = var
    else:
        cvar = float((sorted_losses[tail_mask] * sorted_probs[tail_mask]).sum() / tail_prob)
    return var, cvar


def parametric_var(
    weights: np.ndarray,
    expected_returns: np.ndarray,
    covariance: np.ndarray,
    confidence: float = 0.95,
    horizon: float = 1.0 / 252.0,
) -> float:
    """Closed-form Gaussian VaR -- the industry's fastest baseline."""
    w = np.asarray(weights, dtype=np.float64).reshape(-1)
    mu = float(w @ np.asarray(expected_returns, dtype=np.float64).reshape(-1)) * horizon
    sd = math.sqrt(max(float(w @ np.asarray(covariance, dtype=np.float64) @ w) * horizon, 1e-24))
    # Inverse standard normal CDF by bisection -- avoids a SciPy dependency.
    lo, hi = -10.0, 10.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if 0.5 * (1.0 + math.erf(mid / math.sqrt(2.0))) < confidence:
            lo = mid
        else:
            hi = mid
    z = 0.5 * (lo + hi)
    return float(-mu + z * sd)


# --------------------------------------------------------------------------
# Quantum estimators
# --------------------------------------------------------------------------


def _cdf_circuit(distribution: GridDistribution, threshold_index: int) -> tuple[Circuit, int]:
    """Circuit whose objective qubit reads 1 exactly when ``loss <= threshold``."""
    n = distribution.n_qubits
    total = n + 1
    objective = n
    circuit = Circuit(total, name="loss_cdf")
    prepare_distribution(distribution.probabilities, n, circuit=circuit, qubits=list(range(n)))
    # Comparator marks "index >= threshold+1"; invert it to get "index <= threshold".
    integer_comparator(circuit, list(range(n)), threshold_index + 1, objective)
    circuit.x(objective)
    return circuit, objective


def quantum_value_at_risk(
    distribution: GridDistribution,
    confidence: float = 0.95,
    method: str = "mlae",
    **ae_kwargs,
) -> RiskResult:
    """Find the loss quantile by bisecting on amplitude-estimated CDF values.

    Each bisection step costs one full amplitude estimation, so the total is
    ``O(log N)`` estimations for an ``N``-point grid -- the quantile search adds
    only a logarithmic factor on top of the quadratic sampling advantage.
    """
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must lie strictly between 0 and 1")

    n_points = 2**distribution.n_qubits
    lo, hi = 0, n_points - 1
    oracle_calls = 0
    evaluations: list[tuple[int, float]] = []

    while lo < hi:
        mid = (lo + hi) // 2
        circuit, objective = _cdf_circuit(distribution, mid)
        ae = estimate_amplitude(circuit, objective, method=method, **ae_kwargs)
        oracle_calls += ae.oracle_calls
        evaluations.append((mid, float(ae.estimate)))
        if ae.estimate >= confidence:
            hi = mid
        else:
            lo = mid + 1

    var_quantum = float(distribution.values[lo])
    var_classical, _ = classical_var_cvar(
        distribution.values, distribution.probabilities, confidence
    )

    return RiskResult(
        value=var_quantum,
        classical_value=var_classical,
        measure="VaR",
        confidence=confidence,
        oracle_calls=oracle_calls,
        detail={
            "grid_index": lo,
            "grid_points": n_points,
            "bisection_steps": len(evaluations),
            "cdf_evaluations": evaluations,
            "grid_spacing": float(distribution.values[1] - distribution.values[0]),
        },
    )


def quantum_expected_shortfall(
    distribution: GridDistribution,
    confidence: float = 0.95,
    c_approx: float = 0.20,
    method: str = "mlae",
    var_index: int | None = None,
    **ae_kwargs,
) -> RiskResult:
    """Expected loss conditional on breaching VaR, via a tail payoff rotation.

    The tail mean is encoded exactly as an option payoff is: a comparator selects
    the tail, and a linear ramp of controlled rotations writes the normalised
    loss into the objective qubit's amplitude.
    """
    n = distribution.n_qubits
    values = distribution.values
    probs = distribution.probabilities

    if var_index is None:
        var_result = quantum_value_at_risk(distribution, confidence, method=method, **ae_kwargs)
        var_index = int(var_result.detail["grid_index"])
        oracle_calls = var_result.oracle_calls
    else:
        oracle_calls = 0

    tail_prob = float(probs[var_index:].sum())
    var_level = float(values[var_index])
    _, cvar_classical = classical_var_cvar(values, probs, confidence)

    if tail_prob <= 0 or var_index >= 2**n - 1:
        return RiskResult(
            value=var_level,
            classical_value=cvar_classical,
            measure="CVaR",
            confidence=confidence,
            oracle_calls=oracle_calls,
            detail={"degenerate_tail": True, "tail_probability": tail_prob},
        )

    total = n + 2
    ancilla, objective = n, n + 1
    register = list(range(n))
    lo, hi = float(values[0]), float(values[-1])
    step = (hi - lo) / (2**n - 1)
    scale = float(values[-1] - var_level)

    circuit = Circuit(total, name="expected_shortfall")
    prepare_distribution(probs, n, circuit=circuit, qubits=register)
    circuit.ry(math.pi / 2 - c_approx, objective)

    if scale > 0:
        integer_comparator(circuit, register, var_index, ancilla)
        # f_hat(x) = (loss(x) - VaR) / (max_loss - VaR), affine in the register bits.
        circuit.mcry(2.0 * c_approx * (lo - var_level) / scale, [ancilla], objective)
        for i, q in enumerate(register):
            weight = 2.0 ** (n - 1 - i)
            circuit.mcry(2.0 * c_approx * step * weight / scale, [ancilla, q], objective)

    ae = estimate_amplitude(circuit, objective, method=method, **ae_kwargs)
    oracle_calls += ae.oracle_calls

    # a ~ 1/2 + c * (E[f_hat] - 1/2) over the *whole* distribution, and f_hat is
    # zero off the tail -- so this expectation is already probability-weighted.
    normalised = (ae.estimate - 0.5) / c_approx + 0.5
    excess = normalised * scale                     # E[(loss - VaR)^+]
    cvar = var_level + (excess / tail_prob if tail_prob > 0 else 0.0)

    return RiskResult(
        value=float(cvar),
        classical_value=cvar_classical,
        measure="CVaR",
        confidence=confidence,
        oracle_calls=oracle_calls,
        detail={
            "var_level": var_level,
            "var_index": var_index,
            "tail_probability": tail_prob,
            "expected_excess": float(excess),
            "circuit_resources": circuit.resource_estimate(),
        },
    )
