"""Simulated annealing on the Ising model.

The classical ancestor of quantum annealing, and the baseline any quantum
optimiser has to beat.  A Metropolis walk explores spin configurations while the
temperature is lowered geometrically; at high temperature it crosses energy
barriers freely, at low temperature it settles into a minimum.

Quantum annealing replaces thermal hopping with quantum tunnelling through
barriers.  That is a genuinely different escape mechanism, and it is the physical
basis of the whole D-Wave line -- but on most real instances well-tuned
simulated annealing remains competitive, which is why this baseline is here
rather than hidden.
"""

from __future__ import annotations

import time

import numpy as np

from ..qubo import QUBO
from .base import Solver, SolverResult

__all__ = ["SimulatedAnnealingSolver"]


class SimulatedAnnealingSolver(Solver):
    """Metropolis annealing with geometric cooling and random restarts."""

    name = "simulated_annealing"

    def solve(
        self,
        problem: QUBO,
        n_sweeps: int = 2000,
        n_restarts: int = 8,
        beta_min: float | None = None,
        beta_max: float | None = None,
        rng: np.random.Generator | None = None,
        **kwargs,
    ) -> SolverResult:
        rng = rng or np.random.default_rng()
        start = time.perf_counter()

        ising = problem.to_ising()
        n = ising.n_vars
        h = ising.h
        # Symmetrise the coupling matrix so a single row lookup gives the full
        # local field on a spin.
        J = ising.J + ising.J.T

        # Two scales, not one.  The hot end must melt the *largest* barrier, and
        # the cold end must resolve the *finest* energy difference that matters.
        # Deriving both from the maximum coupling looks natural but fails badly
        # on constrained problems: a large penalty term inflates the maximum, the
        # final temperature stays far above the objective's own differences, and
        # the walk returns a feasible but visibly sub-optimal answer.
        couplings = np.concatenate([h, J[np.triu_indices(n, 1)]]) if n > 1 else h
        magnitudes = np.abs(couplings)
        nonzero = magnitudes[magnitudes > 1e-12]
        hot_scale = max(float(magnitudes.max()) if magnitudes.size else 1.0, 1e-12)
        fine_scale = max(
            float(np.percentile(nonzero, 10)) if nonzero.size else hot_scale, 1e-12
        )
        b_min = beta_min if beta_min is not None else 0.1 / hot_scale
        b_max = beta_max if beta_max is not None else 10.0 / fine_scale
        if b_max <= b_min:
            b_max = b_min * 1e3
        betas = np.geomspace(b_min, b_max, n_sweeps)

        best_spins: np.ndarray | None = None
        best_energy = np.inf
        history: list[float] = []
        evaluated = 0

        for _ in range(max(1, n_restarts)):
            spins = rng.choice([-1.0, 1.0], size=n)
            energy = ising.energy(spins)

            for beta in betas:
                order = rng.permutation(n)
                for i in order:
                    # Flipping s_i changes the energy by -2 s_i (h_i + sum_j J_ij s_j).
                    local_field = h[i] + float(J[i] @ spins)
                    delta = -2.0 * spins[i] * local_field
                    if delta <= 0.0 or rng.random() < np.exp(-beta * delta):
                        spins[i] = -spins[i]
                        energy += delta
                        # Keep the best configuration *ever visited*, not just the
                        # one the walk happens to end on.  On constrained problems
                        # the penalty terms dominate the coupling magnitudes, so no
                        # cooling schedule drives the final temperature below the
                        # objective's own differences -- the chain keeps hopping
                        # between near-optima to the last sweep, and reading off the
                        # final state throws away the optimum it already found.
                        if energy < best_energy:
                            best_energy = energy
                            best_spins = spins.copy()
                evaluated += n
                history.append(float(energy))

            # Guard against drift in the incremental energy over ~10^6 updates.
            if best_spins is not None:
                best_energy = ising.energy(best_spins)

        assert best_spins is not None
        bits = ((best_spins + 1) / 2).astype(int)
        return SolverResult(
            assignment=bits,
            energy=float(problem.energy(bits)),
            solver=self.name,
            runtime_seconds=time.perf_counter() - start,
            samples_evaluated=evaluated,
            energy_history=history[-n_sweeps:],
            detail={
                "restarts": n_restarts,
                "sweeps": n_sweeps,
                "beta_range": (b_min, b_max),
                "hot_scale": hot_scale,
                "fine_scale": fine_scale,
            },
        )
