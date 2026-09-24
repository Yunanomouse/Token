"""Simulated Bifurcation -- quantum-derived optimisation on classical hardware.

Simulated Bifurcation (Goto et al., *Science Advances* 2019) discretises the
classical equations of motion of a network of **Kerr-nonlinear parametric
oscillators**.  Each oscillator's position bifurcates towards one of two stable
branches as a pump parameter is ramped, and the branch it picks is read off as a
spin.  Coupled through the Ising matrix, the network settles into a
low-energy spin configuration.

Why this matters commercially
-----------------------------
This is the algorithm behind Toshiba's SQBM+ and the family of "quantum-inspired"
machines that are **in production today** on FPGAs and GPUs.  The physics is
quantum -- the derivation starts from a quantum adiabatic Hamiltonian -- but the
execution is entirely classical, which sidesteps both the qubit-count ceiling and
the microsecond-scale latency that rules real QPUs out of anything fast.  For
arbitrage-cycle search and constrained portfolio construction, this is the
variant that is realistic to deploy now.

The *ballistic* variant (bSB) is implemented here: it replaces the original
quartic Kerr term with perfectly inelastic walls at ``|x| = 1``, which is both
faster and more accurate in practice.
"""

from __future__ import annotations

import math
import time

import numpy as np

from ..qubo import QUBO
from .base import Solver, SolverResult

__all__ = ["SimulatedBifurcationSolver"]


class SimulatedBifurcationSolver(Solver):
    """Ballistic simulated bifurcation with a batch of independent trajectories.

    Trajectories are integrated as a batch (a matrix-matrix product per step),
    which is exactly the structure that makes this algorithm map so well onto
    GPUs and FPGAs.
    """

    name = "simulated_bifurcation"

    def solve(
        self,
        problem: QUBO,
        n_steps: int = 1000,
        n_trajectories: int = 32,
        dt: float = 0.5,
        a0: float = 1.0,
        c0: float | None = None,
        rng: np.random.Generator | None = None,
        **kwargs,
    ) -> SolverResult:
        rng = rng or np.random.default_rng()
        start = time.perf_counter()

        ising = problem.to_ising()
        n = ising.n_vars
        h = ising.h
        J = ising.J + ising.J.T  # symmetric couplings

        # Goto's prescription: c0 = 0.5 * sqrt(n-1) / ||J||_F.  Scaling off the
        # *standard deviation* of the couplings instead looks equivalent but is
        # not -- on problems whose couplings are uniformly small (a covariance
        # matrix, say) it inflates c0 by orders of magnitude, the coupling term
        # swamps the pump, and every oscillator slams into the same wall on the
        # first step.  The Frobenius norm is scale-correct.
        frobenius = float(np.linalg.norm(J))
        if c0 is None:
            c0 = 0.5 * math.sqrt(max(n - 1, 1)) / frobenius if frobenius > 1e-12 else 0.5

        # Positions and momenta of every oscillator, one row per trajectory.
        x = 0.1 * (rng.random((n_trajectories, n)) - 0.5)
        y = 0.1 * (rng.random((n_trajectories, n)) - 0.5)

        history: list[float] = []
        pump = np.linspace(0.0, a0, n_steps)  # ramps the system through bifurcation

        # Track the best configuration seen anywhere along each trajectory. The
        # final resting state is not always the lowest point visited, and
        # throwing away the good ones costs solution quality for free.
        best_energy = np.inf
        best_bits: np.ndarray | None = None

        def batch_energies(spins: np.ndarray) -> np.ndarray:
            return (
                np.einsum("ki,i->k", spins, h)
                + np.einsum("ki,ij,kj->k", spins, ising.J, spins)
                + ising.offset
            )

        probe_every = max(1, n_steps // 200)
        for step in range(n_steps):
            a_t = pump[step]
            # Force on each oscillator: detuning/pump term plus the Ising field.
            force = -(a0 - a_t) * x - c0 * (x @ J + h[None, :])
            y = y + force * dt
            x = x + a0 * y * dt

            # Inelastic walls: clamp the position and kill the momentum. This is
            # what makes the variant "ballistic" and keeps trajectories bounded.
            outside = np.abs(x) > 1.0
            if outside.any():
                x = np.where(outside, np.sign(x), x)
                y = np.where(outside, 0.0, y)

            if step % probe_every == 0 or step == n_steps - 1:
                spins = np.where(x >= 0, 1.0, -1.0)
                energies = batch_energies(spins)
                idx = int(np.argmin(energies))
                if energies[idx] < best_energy:
                    best_energy = float(energies[idx])
                    best_bits = ((spins[idx] + 1) / 2).astype(int)
                history.append(float(best_energy))

        assert best_bits is not None
        return SolverResult(
            assignment=best_bits,
            energy=float(problem.energy(best_bits)),
            solver=self.name,
            runtime_seconds=time.perf_counter() - start,
            samples_evaluated=n_trajectories * n_steps,
            energy_history=history,
            detail={
                "trajectories": n_trajectories,
                "steps": n_steps,
                "c0": float(c0),
                "coupling_frobenius": frobenius,
            },
        )
