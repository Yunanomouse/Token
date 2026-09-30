"""A dependency-free Nelder-Mead simplex optimiser.

QAOA needs a derivative-free optimiser for its variational angles, and pulling
in SciPy for one routine is not worth the dependency.  Nelder-Mead is the right
shape for the job: the parameter count is small (``2p``), the objective is noisy
and gradient-free, and the landscape is non-convex enough that a local method
with restarts beats anything fancier at this scale.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np

__all__ = ["NelderMeadResult", "nelder_mead", "multi_start_nelder_mead"]


@dataclass
class NelderMeadResult:
    x: np.ndarray
    fun: float
    iterations: int
    evaluations: int
    converged: bool


def nelder_mead(
    func: Callable[[np.ndarray], float],
    x0: Sequence[float],
    step: float = 0.4,
    max_iter: int = 400,
    tol_f: float = 1e-8,
    tol_x: float = 1e-8,
) -> NelderMeadResult:
    """Minimise ``func`` from ``x0`` using the standard simplex updates."""
    x0 = np.asarray(x0, dtype=np.float64).reshape(-1)
    n = x0.size
    alpha, gamma, rho, sigma = 1.0, 2.0, 0.5, 0.5

    simplex = [x0.copy()]
    for i in range(n):
        pt = x0.copy()
        pt[i] += step if pt[i] == 0 else step * (1.0 + abs(pt[i]))
        simplex.append(pt)
    simplex = np.array(simplex)

    values = np.array([func(p) for p in simplex], dtype=np.float64)
    evaluations = n + 1
    converged = False
    iteration = 0

    for iteration in range(1, max_iter + 1):
        order = np.argsort(values)
        simplex, values = simplex[order], values[order]

        if (np.abs(values[-1] - values[0]) <= tol_f
                and np.max(np.abs(simplex[1:] - simplex[0])) <= tol_x):
            converged = True
            break

        centroid = simplex[:-1].mean(axis=0)

        reflected = centroid + alpha * (centroid - simplex[-1])
        f_ref = func(reflected); evaluations += 1

        if values[0] <= f_ref < values[-2]:
            simplex[-1], values[-1] = reflected, f_ref
            continue

        if f_ref < values[0]:
            expanded = centroid + gamma * (reflected - centroid)
            f_exp = func(expanded); evaluations += 1
            if f_exp < f_ref:
                simplex[-1], values[-1] = expanded, f_exp
            else:
                simplex[-1], values[-1] = reflected, f_ref
            continue

        contracted = centroid + rho * (simplex[-1] - centroid)
        f_con = func(contracted); evaluations += 1
        if f_con < values[-1]:
            simplex[-1], values[-1] = contracted, f_con
            continue

        # Shrink towards the best vertex.
        simplex[1:] = simplex[0] + sigma * (simplex[1:] - simplex[0])
        for i in range(1, n + 1):
            values[i] = func(simplex[i])
        evaluations += n

    best = int(np.argmin(values))
    return NelderMeadResult(
        x=simplex[best].copy(),
        fun=float(values[best]),
        iterations=iteration,
        evaluations=evaluations,
        converged=converged,
    )


def multi_start_nelder_mead(
    func: Callable[[np.ndarray], float],
    n_params: int,
    n_starts: int = 8,
    bounds: tuple[float, float] = (0.0, np.pi),
    rng: np.random.Generator | None = None,
    **kwargs,
) -> NelderMeadResult:
    """Random restarts, because variational landscapes are riddled with local minima."""
    rng = rng or np.random.default_rng()
    lo, hi = bounds
    best: NelderMeadResult | None = None
    for _ in range(max(1, n_starts)):
        x0 = rng.uniform(lo, hi, size=n_params)
        result = nelder_mead(func, x0, **kwargs)
        if best is None or result.fun < best.fun:
            best = result
    assert best is not None
    return best
