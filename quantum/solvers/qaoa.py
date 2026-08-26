"""QAOA -- the Quantum Approximate Optimisation Algorithm, on the built-in simulator.

QAOA (Farhi, Goldstone & Gutmann 2014) prepares

.. math:: |\\gamma, \\beta\\rangle = \\prod_{l=1}^{p} e^{-i\\beta_l B} e^{-i\\gamma_l C} H^{\\otimes n}|0\\rangle

where ``C`` is the diagonal Ising cost operator and ``B = sum_i X_i`` is the
mixer.  A classical optimiser tunes the ``2p`` angles to minimise ``<C>``, then
the register is measured and the best sampled bitstring returned.

Honest expectations
-------------------
* Cost is ``O(2**n)`` here because this is an exact statevector simulation --
  there is no speedup being demonstrated, only a correct implementation.
* Even on real hardware, QAOA has **no proven advantage** over good classical
  heuristics for these problems.  At ``p = 1`` it is frequently *worse* than the
  simulated annealing baseline in this same package.
* Its real constraint is depth: each layer needs the full cost Hamiltonian
  applied through two-qubit gates, and current devices decohere long before ``p``
  gets large enough to matter.

It is included because it is the algorithm the field is actually betting on for
constrained portfolio optimisation, and because comparing it head-to-head with
the classical solvers here is more informative than taking anyone's word for it.
"""

from __future__ import annotations

import time

import numpy as np

from ..optimize import multi_start_nelder_mead
from ..qubo import QUBO
from ..statevector import Circuit, probabilities
from .base import Solver, SolverResult

__all__ = ["QAOASolver"]


class QAOASolver(Solver):
    """Variational QAOA with a Nelder-Mead outer loop."""

    name = "qaoa"

    def solve(
        self,
        problem: QUBO,
        p: int = 2,
        n_starts: int = 6,
        max_vars: int = 16,
        shots: int = 2048,
        rng: np.random.Generator | None = None,
        max_iter: int = 200,
        **kwargs,
    ) -> SolverResult:
        rng = rng or np.random.default_rng()
        n = problem.n_vars
        if n > max_vars:
            raise ValueError(
                f"QAOA simulation refuses {n} variables (limit {max_vars}); "
                "statevector memory grows as 2**n"
            )
        start = time.perf_counter()

        # The cost operator is diagonal, so its action is a phase per basis state.
        costs = problem.energies_all()
        # Rescale angles against the cost spread so gamma stays O(1) regardless
        # of how the problem happens to be scaled.
        spread = float(np.abs(costs - costs.mean()).max())
        scale = 1.0 / spread if spread > 0 else 1.0

        history: list[float] = []
        evaluations = 0

        def prepare(params: np.ndarray) -> np.ndarray:
            gammas, betas = params[:p], params[p:]
            circuit = Circuit(n, name="qaoa")
            circuit.barrier_all_h()
            for layer in range(p):
                circuit.diagonal_phase(-gammas[layer] * costs * scale)
                for q in range(n):
                    circuit.rx(2.0 * betas[layer], q)
            return circuit.run()

        def objective(params: np.ndarray) -> float:
            nonlocal evaluations
            evaluations += 1
            probs = probabilities(prepare(params))
            value = float(np.dot(probs, costs))
            history.append(value)
            return value

        best = multi_start_nelder_mead(
            objective,
            n_params=2 * p,
            n_starts=n_starts,
            bounds=(0.0, np.pi),
            rng=rng,
            max_iter=max_iter,
        )

        # Measure the optimised state and keep the best bitstring actually seen.
        probs = probabilities(prepare(best.x))
        counts = rng.multinomial(shots, probs / probs.sum())
        observed = np.nonzero(counts)[0]
        energies = costs[observed]
        winner = int(observed[int(np.argmin(energies))])
        bits = np.array([(winner >> (n - 1 - i)) & 1 for i in range(n)], dtype=int)

        expectation = float(np.dot(probs, costs))
        ground = float(costs.min())
        return SolverResult(
            assignment=bits,
            energy=float(problem.energy(bits)),
            solver=self.name,
            runtime_seconds=time.perf_counter() - start,
            samples_evaluated=shots,
            energy_history=history,
            detail={
                "p": p,
                "optimal_params": best.x.tolist(),
                "expectation_value": expectation,
                # Fraction of the gap from a random guess to the true ground
                # state that the optimised state closes -- the standard QAOA
                # quality metric, and usually humbling at low p.
                "approximation_ratio": float(
                    (float(costs.mean()) - expectation) / (float(costs.mean()) - ground)
                ) if costs.mean() != ground else 1.0,
                "ground_state_probability": float(probs[np.argmin(costs)]),
                "optimizer_evaluations": evaluations,
            },
        )
