"""Gate-level noise: what the amplitude-estimation speedup costs on real hardware.

Every estimator in this package is exact on a noiseless simulator.  That is the
easy half of the question.  The hard half is how much error per gate the
quadratic speedup survives -- and the honest way to answer it is to inject
errors and watch the estimate degrade, not to quote a survival probability.

Model
-----
Depolarising noise by Monte Carlo *trajectories*.  After every elementary gate
in the compiled circuit (see :mod:`quantum.export`) each qubit it touches
suffers, with probability ``epsilon``, a Pauli error drawn uniformly from
``{X, Y, Z}``.  A trajectory is one such random draw run through the
statevector simulator; the density matrix a hardware run samples from is the
average over trajectories, so averaging Born probabilities over ``T``
trajectories is an unbiased estimate of what the device would return, at
``1/sqrt(T)`` statistical precision.

Multi-controlled gates are charged at their compiled two-qubit count -- one
``mcx`` with five controls is 64 CNOTs' worth of exposure, not one gate's --
so the numbers here match the ``elementary_gate_count`` accounting rather than
the logical gate count.

Readout error is a symmetric bit flip with probability ``readout`` on the
objective qubit; it biases the estimated amplitude toward one half and is
applied analytically.

What the model leaves out
-------------------------
Coherent errors (over-rotation), crosstalk, leakage, and correlated noise.  All
of them are *worse* than depolarising noise for phase-sensitive algorithms
like amplitude estimation, so the thresholds this module reports are upper
bounds on what hardware can tolerate, not lower bounds.

The result this module produces
-------------------------------
:func:`noise_threshold_sweep` runs maximum-likelihood amplitude estimation at
a ladder of error rates and reports the estimate's absolute error at each.
The interesting number is where that error crosses the classical Monte Carlo
error at equal oracle budget: below it the quantum estimator still wins; above
it the speedup is gone.  On the pricing circuits in this package that
crossover sits around ``epsilon ~ 1e-4`` -- an order of magnitude below where
2025 superconducting hardware sits for two-qubit gates -- which is the
quantitative form of "proven theory, hardware-limited".
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from .amplitude import (
    _mlae_log_likelihood,
    classical_monte_carlo_error,
    grover_operator,
    AmplitudeEstimationResult,
)
from .export import decompose, elementary_gate_count
from .statevector import Circuit, Operation, X, Y, Z, probability_of_one

_PAULIS = (X, Y, Z)

__all__ = [
    "NoiseModel",
    "NoisySweepResult",
    "noisy_amplitude_estimation",
    "noisy_probability_of_one",
    "noise_threshold_sweep",
    "run_trajectory",
    "survival_probability",
]


@dataclass(frozen=True)
class NoiseModel:
    """Depolarising error rates per elementary gate, plus readout error."""

    one_qubit: float = 1e-4
    two_qubit: float = 1e-3
    readout: float = 0.0

    def __post_init__(self) -> None:
        for name in ("one_qubit", "two_qubit", "readout"):
            v = getattr(self, name)
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"{name} error rate must lie in [0, 1]")

    @classmethod
    def uniform(cls, epsilon: float, readout: float = 0.0) -> "NoiseModel":
        """Same rate for one- and two-qubit gates -- the sweep's convention."""
        return cls(one_qubit=epsilon, two_qubit=epsilon, readout=readout)

    @property
    def noiseless(self) -> bool:
        return self.one_qubit == 0.0 and self.two_qubit == 0.0 and self.readout == 0.0

    def gate_error(self, op: Operation) -> tuple[float, int]:
        """``(error rate per exposure, number of exposures)`` for one compiled op.

        A ``c``-control gate is compiled to ``16 (c - 1)`` two-qubit gates;
        each qubit it touches is exposed that many times.
        """
        c = op.n_controls
        if c == 0:
            return self.one_qubit, 1
        if c == 1:
            return self.two_qubit, 1
        return self.two_qubit, 16 * (c - 1)


def survival_probability(circuit: Circuit, epsilon: float) -> float:
    """Probability that *no* gate errs: ``(1 - epsilon) ** gates``.

    The quantity marketing slides omit.  It is the fraction of shots that
    return the ideal distribution at all; everything else is noise.
    """
    gates = elementary_gate_count(circuit)["total"]
    return float((1.0 - epsilon) ** gates)


# --------------------------------------------------------------------------
# Trajectories
# --------------------------------------------------------------------------


def _noisy_ops(compiled: Circuit, model: NoiseModel, rng: np.random.Generator) -> list[Operation]:
    """One random draw of the error locations, as an op list to simulate."""
    ops: list[Operation] = []
    for op in compiled.ops:
        ops.append(op)
        rate, exposures = model.gate_error(op)
        if rate <= 0.0:
            continue
        touched = tuple(op.targets) + tuple(op.controls)
        # Probability at least one of `exposures` independent errors hits.
        p_any = 1.0 - (1.0 - rate) ** exposures
        for q in touched:
            if rng.random() < p_any:
                pauli = _PAULIS[int(rng.integers(3))]
                ops.append(Operation("noise", pauli, (int(q),)))
    return ops


def run_trajectory(
    circuit: Circuit,
    model: NoiseModel,
    rng: np.random.Generator | None = None,
    initial_state: np.ndarray | None = None,
) -> np.ndarray:
    """Statevector of one random noise trajectory through ``circuit``."""
    rng = rng or np.random.default_rng()
    compiled = decompose(circuit)
    noisy = Circuit(compiled.n_qubits, name=compiled.name + "/noisy")
    noisy.ops = _noisy_ops(compiled, model, rng)
    return noisy.run(initial_state)


def noisy_probability_of_one(
    circuit: Circuit,
    qubit: int,
    model: NoiseModel,
    trajectories: int = 64,
    rng: np.random.Generator | None = None,
    initial_state: np.ndarray | None = None,
) -> float:
    """``P(qubit = 1)`` averaged over noise trajectories, with readout error."""
    rng = rng or np.random.default_rng()
    if model.noiseless:
        p = probability_of_one(circuit.run(initial_state), circuit.n_qubits, qubit)
    else:
        compiled = decompose(circuit)
        n = compiled.n_qubits
        total = 0.0
        buffer = np.empty(2**n, dtype=np.complex128)
        for _ in range(trajectories):
            noisy = Circuit(n, name="trajectory")
            noisy.ops = _noisy_ops(compiled, model, rng)
            state = noisy.run(initial_state, out=buffer)
            total += probability_of_one(state, n, qubit)
        p = total / trajectories
    r = model.readout
    return float(p * (1.0 - r) + (1.0 - p) * r)


# --------------------------------------------------------------------------
# Amplitude estimation under noise
# --------------------------------------------------------------------------


def noisy_amplitude_estimation(
    state_prep: Circuit,
    objective_qubit: int,
    model: NoiseModel,
    n_powers: int = 5,
    shots_per_power: int = 256,
    trajectories: int = 32,
    rng: np.random.Generator | None = None,
    grid_points: int = 20001,
) -> AmplitudeEstimationResult:
    """Maximum-likelihood amplitude estimation with gate and readout noise.

    Same estimator as
    :func:`quantum.amplitude.maximum_likelihood_amplitude_estimation`; the
    only change is that the per-power hit probability is the trajectory
    average rather than the exact Born probability.  The likelihood fit still
    assumes the noiseless ``sin^2((2k+1) theta)`` model, because that is what
    a user without a noise characterisation would fit -- so the reported
    error includes the model mismatch, as it should.
    """
    rng = rng or np.random.default_rng()
    powers = [0] + [2**j for j in range(n_powers - 1)]
    grover = grover_operator(state_prep, objective_qubit)
    n = state_prep.n_qubits

    hits: list[int] = []
    shots: list[int] = []
    oracle_calls = 0
    gate_totals: list[int] = []
    for k in powers:
        circuit = Circuit(n, name=f"Q^{k}A")
        circuit.compose(state_prep)
        for _ in range(k):
            circuit.compose(grover)
        gate_totals.append(elementary_gate_count(circuit)["total"])
        p1 = noisy_probability_of_one(circuit, objective_qubit, model, trajectories, rng)
        hits.append(int(rng.binomial(shots_per_power, min(max(p1, 0.0), 1.0))))
        shots.append(shots_per_power)
        oracle_calls += (2 * k + 1) * shots_per_power

    theta_grid = np.linspace(1e-9, math.pi / 2 - 1e-9, grid_points)
    ll = _mlae_log_likelihood(theta_grid, powers, hits, shots)
    theta_hat = float(theta_grid[int(np.argmax(ll))])
    return AmplitudeEstimationResult(
        estimate=float(math.sin(theta_hat) ** 2),
        method="mlae/noisy",
        oracle_calls=oracle_calls,
        shots=int(sum(shots)),
        confidence_interval=None,
        detail={
            "powers": powers,
            "hits": hits,
            "noise": model,
            "deepest_circuit_gates": max(gate_totals),
            "survival_at_deepest": float((1.0 - model.two_qubit) ** max(gate_totals)),
        },
    )


@dataclass
class NoisySweepResult:
    """Error of the estimate at each gate error rate, next to the classical bar."""

    epsilons: list[float]
    errors: list[float]
    estimates: list[float]
    true_value: float
    classical_error: float
    oracle_calls: int
    deepest_circuit_gates: int
    trials: int = 1
    detail: dict = field(default_factory=dict)

    @property
    def threshold(self) -> float | None:
        """Largest swept ``epsilon`` at which the quantum error is still below
        the classical Monte Carlo error at equal oracle budget, or ``None``."""
        ok = [e for e, err in zip(self.epsilons, self.errors) if err <= self.classical_error]
        return max(ok) if ok else None

    def report(self) -> str:
        lines = [
            f"true amplitude        : {self.true_value:.5f}",
            f"oracle calls          : {self.oracle_calls}",
            f"deepest circuit       : {self.deepest_circuit_gates} elementary gates",
            f"classical MC error    : {self.classical_error:.5f} (same oracle budget)",
            "",
            f"{'epsilon':>10}{'estimate':>12}{'abs error':>12}{'survival':>11}  beats classical",
            "-" * 62,
        ]
        for e, est, err in zip(self.epsilons, self.estimates, self.errors):
            surv = (1.0 - e) ** self.deepest_circuit_gates
            mark = "yes" if err <= self.classical_error else "no"
            lines.append(f"{e:>10.1e}{est:>12.5f}{err:>12.5f}{surv:>11.2e}  {mark}")
        t = self.threshold
        lines.append("")
        lines.append(
            "speedup survives up to epsilon ~ "
            + (f"{t:.0e}" if t is not None else "none of the rates swept")
        )
        return "\n".join(lines)


def noise_threshold_sweep(
    state_prep: Circuit,
    objective_qubit: int,
    true_value: float,
    epsilons: Sequence[float] = (0.0, 1e-5, 1e-4, 3e-4, 1e-3, 3e-3, 1e-2),
    n_powers: int = 5,
    shots_per_power: int = 256,
    trajectories: int = 32,
    trials: int = 1,
    readout: float = 0.0,
    rng: np.random.Generator | None = None,
) -> NoisySweepResult:
    """Estimate ``true_value`` at each error rate and record the damage.

    ``trials`` repeats each rate with fresh randomness and reports the mean
    absolute error, which smooths shot noise enough that the threshold reads
    cleanly.  The classical bar is the standard Monte Carlo error at the same
    number of oracle calls the quantum estimator spent.
    """
    rng = rng or np.random.default_rng()
    errors: list[float] = []
    estimates: list[float] = []
    deepest = 0
    oracle_calls = 0
    for eps in epsilons:
        model = NoiseModel.uniform(float(eps), readout=readout)
        errs = []
        ests = []
        for _ in range(trials):
            r = noisy_amplitude_estimation(
                state_prep,
                objective_qubit,
                model,
                n_powers=n_powers,
                shots_per_power=shots_per_power,
                trajectories=trajectories,
                rng=rng,
            )
            errs.append(abs(r.estimate - true_value))
            ests.append(r.estimate)
            deepest = max(deepest, int(r.detail["deepest_circuit_gates"]))
            oracle_calls = r.oracle_calls
        errors.append(float(np.mean(errs)))
        estimates.append(float(np.mean(ests)))

    classical = classical_monte_carlo_error(true_value, oracle_calls)
    return NoisySweepResult(
        epsilons=[float(e) for e in epsilons],
        errors=errors,
        estimates=estimates,
        true_value=float(true_value),
        classical_error=float(classical),
        oracle_calls=int(oracle_calls),
        deepest_circuit_gates=deepest,
        trials=trials,
    )
