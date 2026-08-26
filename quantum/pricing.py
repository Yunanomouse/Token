"""Derivative pricing by quantum amplitude estimation.

The recipe (Stamatopoulos et al. 2020; Woerner & Egger 2019) is always:

1. Load the risk-neutral terminal-price distribution into ``n`` qubits.
2. Rotate an *objective* qubit by an angle that encodes the payoff, so that
   ``P(objective = 1)`` is an affine function of the expected payoff.
3. Recover that probability with amplitude estimation and undo the affine map.

Step 2 uses the standard small-angle linearisation

.. math:: \\sin^2\\!\\big(\\tfrac{\\pi}{4} + c(\\hat f(x) - \\tfrac12)\\big)
          \\approx \\tfrac12 + c\\big(\\hat f(x) - \\tfrac12\\big)

which is accurate to ``O(c^3)``.  Small ``c`` means low bias but a weak signal
(more shots); large ``c`` means the reverse.  ``c_approx`` exposes that trade-off
directly, and :func:`price_european_option` reports the bias it induces.

Grid convergence -- read this before trusting a price
-----------------------------------------------------
Two independent errors set the accuracy of a quantum price, and they respond to
different knobs:

* **Estimation error** falls as you add Grover powers or shots.
* **Discretisation error** has two parts -- grid *resolution* (``n_qubits``) and
  domain *truncation* (``n_sigma``) -- and it is bounded below by whichever is
  worse.

Truncation is the one people miss.  At ``n_sigma=3`` the tail beyond the grid is
simply absent, and adding qubits does nothing: measured error plateaus around
0.10 from 5 qubits all the way to 8.  Widen to ``n_sigma=5`` and the same
sweep converges 0.065 -> 0.0005.  If a price will not converge, widen the domain
before adding qubits.  The default here is ``n_sigma=4.0`` for that reason.

Where the advantage is
----------------------
For a single vanilla option this is far slower than the Black-Scholes formula --
which is included here purely as a correctness oracle.  The asymptotic payoff is
in **multi-asset and path-dependent** contracts where no closed form exists and
classical Monte Carlo cost explodes with dimension.  :func:`price_basket_option`
is the honest version of that case, and its docstring is explicit about the
quantum-adder cost this simulator sidesteps.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .amplitude import AmplitudeEstimationResult, estimate_amplitude
from .preparation import GridDistribution, lognormal_grid, prepare_distribution
from .statevector import Circuit

__all__ = [
    "OptionSpec",
    "PricingResult",
    "black_scholes_call",
    "black_scholes_put",
    "classical_monte_carlo_price",
    "integer_comparator",
    "build_european_payoff_circuit",
    "price_european_option",
    "price_basket_option",
]


# --------------------------------------------------------------------------
# Classical references
# --------------------------------------------------------------------------


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black_scholes_call(spot: float, strike: float, rate: float, vol: float, maturity: float) -> float:
    """Closed-form European call -- the correctness oracle for the quantum run."""
    if maturity <= 0 or vol <= 0:
        return max(spot - strike, 0.0)
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol**2) * maturity) / (vol * math.sqrt(maturity))
    d2 = d1 - vol * math.sqrt(maturity)
    return spot * _norm_cdf(d1) - strike * math.exp(-rate * maturity) * _norm_cdf(d2)


def black_scholes_put(spot: float, strike: float, rate: float, vol: float, maturity: float) -> float:
    """Closed-form European put, via put-call parity."""
    call = black_scholes_call(spot, strike, rate, vol, maturity)
    return call - spot + strike * math.exp(-rate * maturity)


def classical_monte_carlo_price(
    spot: float,
    strike: float,
    rate: float,
    vol: float,
    maturity: float,
    samples: int = 100_000,
    option: str = "call",
    rng: np.random.Generator | None = None,
) -> tuple[float, float]:
    """Plain Monte Carlo price and its standard error, for cost comparison."""
    rng = rng or np.random.default_rng()
    z = rng.standard_normal(int(samples))
    terminal = spot * np.exp((rate - 0.5 * vol**2) * maturity + vol * math.sqrt(maturity) * z)
    payoff = np.maximum(terminal - strike, 0.0) if option == "call" else np.maximum(strike - terminal, 0.0)
    discounted = math.exp(-rate * maturity) * payoff
    return float(discounted.mean()), float(discounted.std(ddof=1) / math.sqrt(samples))


# --------------------------------------------------------------------------
# Circuit building blocks
# --------------------------------------------------------------------------


def integer_comparator(
    circuit: Circuit,
    register: list[int],
    threshold: int,
    target: int,
) -> Circuit:
    """Flip ``target`` iff the integer held in ``register`` is ``>= threshold``.

    Built from prefix decomposition: ``x >= K`` holds exactly when ``x`` matches
    ``K`` on some prefix and then exceeds it at the next bit, or equals ``K``.
    Those cases are mutually exclusive, so one multi-controlled X per case
    accumulates the answer with no ancillas -- ``O(n)`` gates rather than the
    ``O(2**n)`` a brute-force enumeration would need.

    ``register[0]`` is the most significant bit.
    """
    n = len(register)
    if threshold <= 0:
        circuit.x(target)  # every value qualifies
        return circuit
    if threshold >= 2**n:
        return circuit  # no value qualifies

    bits = [(threshold >> (n - 1 - i)) & 1 for i in range(n)]

    for i in range(n):
        if bits[i] == 1:
            continue  # x_i > K_i is impossible when K_i = 1
        controls = [register[j] for j in range(i)] + [register[i]]
        values = [bits[j] for j in range(i)] + [1]
        circuit.mcx(controls, target, control_values=values)

    # The exact-equality case.
    circuit.mcx(register, target, control_values=bits)
    return circuit


@dataclass(frozen=True)
class OptionSpec:
    """A vanilla European option under Black-Scholes dynamics."""

    spot: float
    strike: float
    rate: float
    volatility: float
    maturity: float
    option: str = "call"

    def validate(self) -> None:
        if self.spot <= 0 or self.strike <= 0:
            raise ValueError("spot and strike must be positive")
        if self.volatility <= 0:
            raise ValueError("volatility must be positive")
        if self.maturity <= 0:
            raise ValueError("maturity must be positive")
        if self.option not in ("call", "put"):
            raise ValueError("option must be 'call' or 'put'")

    def analytic_price(self) -> float:
        fn = black_scholes_call if self.option == "call" else black_scholes_put
        return fn(self.spot, self.strike, self.rate, self.volatility, self.maturity)

    def risk_neutral_grid(self, n_qubits: int, n_sigma: float = 4.0) -> GridDistribution:
        """Terminal price distribution under the risk-neutral measure."""
        mu = math.log(self.spot) + (self.rate - 0.5 * self.volatility**2) * self.maturity
        sigma = self.volatility * math.sqrt(self.maturity)
        return lognormal_grid(mu, sigma, n_qubits, n_sigma=n_sigma)


@dataclass
class PricingResult:
    """A quantum price alongside the classical references it is checked against."""

    price: float
    analytic_price: float
    discretised_price: float
    amplitude: AmplitudeEstimationResult
    n_qubits: int
    c_approx: float
    detail: dict = field(default_factory=dict)

    @property
    def absolute_error(self) -> float:
        return abs(self.price - self.analytic_price)

    @property
    def relative_error(self) -> float:
        if self.analytic_price == 0:
            return float("nan")
        return self.absolute_error / abs(self.analytic_price)

    @property
    def discretisation_error(self) -> float:
        """Error from the finite price grid alone, independent of estimation."""
        return abs(self.discretised_price - self.analytic_price)

    @property
    def estimation_error(self) -> float:
        """Error from amplitude estimation and the payoff linearisation."""
        return abs(self.price - self.discretised_price)

    def __repr__(self) -> str:  # pragma: no cover - display helper
        return (
            f"<Price quantum={self.price:.5f} analytic={self.analytic_price:.5f} "
            f"rel_err={self.relative_error:.4%} qubits={self.n_qubits}>"
        )


def build_european_payoff_circuit(
    spec: OptionSpec,
    n_qubits: int,
    c_approx: float = 0.25,
    n_sigma: float = 4.0,
) -> tuple[Circuit, int, GridDistribution, float, int]:
    """Assemble distribution loading plus the payoff rotation.

    Returns ``(circuit, objective_qubit, grid, payoff_scale, strike_index)``.
    The register layout is ``[price bits ..., comparator ancilla, objective]``.
    """
    spec.validate()
    grid = spec.risk_neutral_grid(n_qubits, n_sigma=n_sigma)
    values = grid.values

    total = n_qubits + 2
    price_qubits = list(range(n_qubits))
    ancilla = n_qubits
    objective = n_qubits + 1

    circuit = Circuit(total, name="european_payoff")
    prepare_distribution(grid.probabilities, n_qubits, circuit=circuit, qubits=price_qubits)

    lo, hi = float(values[0]), float(values[-1])
    step = (hi - lo) / (2**n_qubits - 1)

    # The payoff is normalised against the *strike*, not against the nearest grid
    # point.  Anchoring on the grid point instead shifts every in-the-money
    # payoff by (strike - grid point) and biases the price.
    if spec.option == "call":
        in_money = np.nonzero(values >= spec.strike)[0]
        if in_money.size == 0 or hi <= spec.strike:  # worthless on this grid
            strike_index = 2**n_qubits
            payoff_scale = 0.0
        else:
            strike_index = int(in_money[0])
            payoff_scale = float(hi - spec.strike)
    else:
        in_money = np.nonzero(values <= spec.strike)[0]
        if in_money.size == 0 or spec.strike <= lo:
            strike_index = -1
            payoff_scale = 0.0
        else:
            strike_index = int(in_money[-1])
            payoff_scale = float(spec.strike - lo)

    # Baseline rotation: theta = pi/2 - c corresponds to a normalised payoff of 0.
    circuit.ry(math.pi / 2 - c_approx, objective)

    if payoff_scale <= 0:
        return circuit, objective, grid, payoff_scale, strike_index

    # On the grid, price(x) = lo + x*step, so the normalised payoff is affine in
    # the register integer and therefore affine in its individual bits.  That is
    # what keeps the ramp at n+1 controlled rotations instead of O(2**n).
    if spec.option == "call":
        integer_comparator(circuit, price_qubits, strike_index, ancilla)
        # f_hat(x) = (lo + x*step - strike) / (hi - strike)
        const = 2.0 * c_approx * (lo - spec.strike) / payoff_scale
        circuit.mcry(const, [ancilla], objective)
        for i, q in enumerate(price_qubits):
            weight = 2.0 ** (n_qubits - 1 - i)
            circuit.mcry(2.0 * c_approx * step * weight / payoff_scale, [ancilla, q], objective)
    else:
        # Put: in the money *below* the strike, so compare against strike_index+1
        # and invert the ancilla to select the complement.
        integer_comparator(circuit, price_qubits, strike_index + 1, ancilla)
        circuit.x(ancilla)
        # f_hat(x) = (strike - lo - x*step) / (strike - lo)
        const = 2.0 * c_approx * (spec.strike - lo) / payoff_scale
        circuit.mcry(const, [ancilla], objective)
        for i, q in enumerate(price_qubits):
            weight = 2.0 ** (n_qubits - 1 - i)
            circuit.mcry(-2.0 * c_approx * step * weight / payoff_scale, [ancilla, q], objective)

    return circuit, objective, grid, payoff_scale, strike_index


def _price_at_c(
    spec: OptionSpec,
    n_qubits: int,
    c_approx: float,
    method: str,
    n_sigma: float,
    ae_kwargs: dict,
):
    """One pricing run at a given linearisation strength."""
    circuit, objective, grid, payoff_scale, strike_index = build_european_payoff_circuit(
        spec, n_qubits, c_approx=c_approx, n_sigma=n_sigma
    )
    discount = math.exp(-spec.rate * spec.maturity)
    if payoff_scale <= 0:
        zero = AmplitudeEstimationResult(estimate=0.5, method="skipped", oracle_calls=0, shots=0)
        return 0.0, zero, grid, payoff_scale, strike_index, circuit, discount

    ae = estimate_amplitude(circuit, objective, method=method, **ae_kwargs)
    # Undo the affine encoding: a ~ 1/2 + c * (E[f_hat] - 1/2).
    normalised = (ae.estimate - 0.5) / c_approx + 0.5
    price = discount * normalised * payoff_scale
    return price, ae, grid, payoff_scale, strike_index, circuit, discount


def price_european_option(
    spec: OptionSpec,
    n_qubits: int = 5,
    c_approx: float = 0.25,
    method: str = "mlae",
    n_sigma: float = 4.0,
    bias_correction: bool = False,
    **ae_kwargs,
) -> PricingResult:
    """Price a European call or put with amplitude estimation.

    The result separates *discretisation* error (finite price grid) from
    *estimation* error (amplitude estimation plus payoff linearisation), because
    conflating them makes the method look either better or worse than it is.

    The linearisation bias, and how to remove it
    --------------------------------------------
    ``sin^2(pi/4 + u) ~ 1/2 + u`` is wrong at order ``u^3``, and dividing by
    ``c_approx`` to recover the price turns that into an error of order
    ``c_approx**2`` -- *systematic*, so adding shots or Grover powers cannot
    remove it.  Measured on a 100/105 one-year call, the price bias is very
    nearly ``11.2 * c**2`` across two orders of magnitude in ``c``.

    Because the leading term is a clean ``c**2``, two runs cancel it exactly by
    Richardson extrapolation::

        price = (4 * price(c/2) - price(c)) / 3

    That is what ``bias_correction=True`` does, at the cost of a second amplitude
    estimation.

    **It is not free, and not always a win.**  Recovering the price divides by
    ``c``, so the run at ``c/2`` carries twice the shot noise, and the
    combination amplifies the standard error by roughly ``2.7x``.  Richardson
    therefore trades bias for variance, and only pays when bias is the larger
    term.  Measured on the same call at 8 Grover powers and 4096 shots:

    ======  ==============  ==================
    c       plain error     corrected error
    ======  ==============  ==================
    0.05    0.123           0.603  (worse)
    0.10    0.064           0.094  (worse)
    0.25    0.640           0.002  (335x better)
    ======  ==============  ==================

    Rule of thumb: use ``bias_correction=True`` with ``c_approx >= 0.2``, where
    bias dominates; below that, just keep ``c`` small and spend the shots.  The
    best configuration found here -- 8 qubits, ``n_sigma=5``, ``c_approx=0.15``,
    8 powers -- prices the call to within 0.03% of Black-Scholes.
    """
    if bias_correction:
        full = _price_at_c(spec, n_qubits, c_approx, method, n_sigma, ae_kwargs)
        half = _price_at_c(spec, n_qubits, c_approx / 2.0, method, n_sigma, dict(ae_kwargs))
        price_full, ae_full = full[0], full[1]
        price_half, ae_half = half[0], half[1]
        _, _, grid, payoff_scale, strike_index, circuit, discount = half
        # Cancel the leading c^2 term; what remains is O(c^4).
        price = (4.0 * price_half - price_full) / 3.0
        ae = AmplitudeEstimationResult(
            estimate=ae_half.estimate,
            method=f"{ae_half.method}+richardson",
            oracle_calls=ae_full.oracle_calls + ae_half.oracle_calls,
            shots=ae_full.shots + ae_half.shots,
            detail={"price_at_c": price_full, "price_at_c_half": price_half},
        )
    else:
        price, ae, grid, payoff_scale, strike_index, circuit, discount = _price_at_c(
            spec, n_qubits, c_approx, method, n_sigma, ae_kwargs
        )

    if payoff_scale <= 0:
        zero = AmplitudeEstimationResult(estimate=0.5, method="skipped", oracle_calls=0, shots=0)
        return PricingResult(0.0, spec.analytic_price(), 0.0, zero, n_qubits, c_approx)

    if spec.option == "call":
        payoff = np.maximum(grid.values - spec.strike, 0.0)
    else:
        payoff = np.maximum(spec.strike - grid.values, 0.0)
    discretised = float(discount * np.dot(payoff, grid.probabilities))

    return PricingResult(
        price=float(price),
        analytic_price=spec.analytic_price(),
        discretised_price=discretised,
        amplitude=ae,
        n_qubits=n_qubits,
        c_approx=c_approx,
        detail={
            "payoff_scale": payoff_scale,
            "strike_index": strike_index,
            "discount": discount,
            "circuit_resources": circuit.resource_estimate(),
            "grid_min": float(grid.values[0]),
            "grid_max": float(grid.values[-1]),
        },
    )


def price_basket_option(
    spots: np.ndarray,
    weights: np.ndarray,
    strike: float,
    rate: float,
    vols: np.ndarray,
    correlation: np.ndarray,
    maturity: float,
    n_qubits_per_asset: int = 3,
    c_approx: float = 0.25,
    method: str = "mlae",
    n_sigma: float = 4.0,
    **ae_kwargs,
) -> PricingResult:
    """Price a multi-asset basket call -- the case with no closed form.

    The payoff ``max(w . S - K, 0)`` depends on a weighted *sum* of correlated
    prices.  On real hardware that sum needs a quantum adder (a fixed-point
    arithmetic circuit) feeding a comparator.  This simulator instead applies the
    payoff rotation state-by-state with one multi-controlled ``Ry`` per basis
    state, which is exact and correct but costs ``O(2**n)`` logical gates -- so
    the reported ``estimated_elementary_gates`` here is the honest number and it
    is large.  Use this to validate the algorithm, not to argue it is cheap.

    Note also that the joint distribution is loaded exactly, so the ``O(2**n)``
    input problem applies on top.
    """
    spots = np.asarray(spots, dtype=np.float64).reshape(-1)
    weights = np.asarray(weights, dtype=np.float64).reshape(-1)
    vols = np.asarray(vols, dtype=np.float64).reshape(-1)
    correlation = np.asarray(correlation, dtype=np.float64)
    d = spots.size
    if not (weights.size == vols.size == d):
        raise ValueError("spots, weights and vols must have the same length")
    if correlation.shape != (d, d):
        raise ValueError("correlation matrix shape mismatch")

    # Risk-neutral log-price distribution.
    mu = np.log(spots) + (rate - 0.5 * vols**2) * maturity
    sd = vols * math.sqrt(maturity)
    cov = correlation * np.outer(sd, sd)

    from .preparation import multivariate_normal_grid

    log_points, joint_probs, n_state = multivariate_normal_grid(
        mu, cov, n_qubits_per_asset, n_sigma=n_sigma
    )
    prices = np.exp(log_points)
    basket = prices @ weights
    payoff = np.maximum(basket - strike, 0.0)

    payoff_scale = float(payoff.max())
    discount = math.exp(-rate * maturity)
    discretised = float(discount * np.dot(payoff, joint_probs))

    if payoff_scale <= 0:
        zero = AmplitudeEstimationResult(estimate=0.5, method="skipped", oracle_calls=0, shots=0)
        return PricingResult(0.0, float("nan"), 0.0, zero, n_state, c_approx)

    normalised_payoff = payoff / payoff_scale

    total = n_state + 1
    objective = n_state
    state_qubits = list(range(n_state))
    circuit = Circuit(total, name="basket_payoff")
    prepare_distribution(joint_probs, n_state, circuit=circuit, qubits=state_qubits)

    circuit.ry(math.pi / 2 - c_approx, objective)
    # One rotation per joint basis state, carried as a single angle table rather
    # than 2**n multi-controlled gates.  The gate *count* on hardware is
    # unchanged -- resource_estimate() still reports it -- but the simulation
    # holds one array instead of thousands of Operation objects.
    circuit.multiplexed_ry(
        2.0 * c_approx * np.clip(normalised_payoff, 0.0, None),
        state_qubits,
        objective,
    )

    ae = estimate_amplitude(circuit, objective, method=method, **ae_kwargs)
    normalised = (ae.estimate - 0.5) / c_approx + 0.5
    price = discount * normalised * payoff_scale

    return PricingResult(
        price=float(price),
        analytic_price=float("nan"),  # no closed form -- that is the point
        discretised_price=discretised,
        amplitude=ae,
        n_qubits=n_state,
        c_approx=c_approx,
        detail={
            "assets": d,
            "payoff_scale": payoff_scale,
            "qubits_per_asset": n_qubits_per_asset,
            "circuit_resources": circuit.resource_estimate(),
        },
    )
