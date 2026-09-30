"""Loading classical probability distributions into quantum amplitudes.

Every quantum finance algorithm starts the same way: encode a distribution
``p(x)`` over ``2**n`` grid points into an ``n``-qubit state

.. math::  |p\\rangle = \\sum_x \\sqrt{p(x)}\\, |x\\rangle

so that measuring the register reproduces ``p``.  Because the amplitudes are
real and non-negative, the exact loader below is a binary tree of multiplexed
``Ry`` rotations -- the standard Grover-Rudolph construction.

Cost caveat
-----------
Exact loading of an arbitrary distribution takes ``O(2**n)`` gates, which cancels
the quadratic advantage of amplitude estimation if the distribution has to be
loaded from scratch every run.  This is the well-known "input problem".  It is
not a defect of this implementation -- it is the central open obstacle for
quantum finance, and it is why the speedups here are asymptotic rather than
practical today.  Distributions with efficient analytic structure (or ones
prepared once and reused) avoid it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .statevector import Circuit

__all__ = [
    "prepare_distribution",
    "GridDistribution",
    "lognormal_grid",
    "normal_grid",
    "multivariate_normal_grid",
]

_TOL = 1e-12


def prepare_distribution(
    probabilities: np.ndarray,
    n_qubits: int | None = None,
    circuit: Circuit | None = None,
    qubits: list[int] | None = None,
) -> Circuit:
    """Build a circuit mapping |0...0> to ``sum_x sqrt(p(x)) |x>``.

    Parameters
    ----------
    probabilities:
        Non-negative weights over ``2**n`` grid points; normalised internally.
    n_qubits:
        Width of the register.  Inferred from ``probabilities`` when omitted.
    circuit, qubits:
        Append into an existing circuit on the given qubits instead of building
        a standalone one.
    """
    p = np.asarray(probabilities, dtype=np.float64).reshape(-1)
    if np.any(p < -_TOL):
        raise ValueError("probabilities must be non-negative")
    p = np.clip(p, 0.0, None)
    total = p.sum()
    if total <= 0:
        raise ValueError("probabilities sum to zero")
    p = p / total

    inferred = int(math.log2(p.size))
    if 2**inferred != p.size:
        raise ValueError("probability vector length must be a power of two")
    n = inferred if n_qubits is None else int(n_qubits)
    if n < inferred:
        raise ValueError("register too small for this distribution")
    if n > inferred:  # pad with zero-probability high states
        p = np.concatenate([p, np.zeros(2**n - p.size)])

    if circuit is None:
        circuit = Circuit(n, name="prepare")
    qs = list(range(n)) if qubits is None else list(qubits)
    if len(qs) != n:
        raise ValueError("qubit list length must match register width")

    amps = np.sqrt(p)
    # Walk the binary tree level by level.  At each node the rotation angle is
    # set by how the node's probability mass splits between its two children.
    #
    # Every node at a given level shares the same controls and target and differs
    # only in its angle, so the whole level is one *multiplexed* Ry rather than
    # 2**level separate multi-controlled gates.  That turns the circuit from
    # O(2**n) Operation objects into n of them holding O(2**n) floats between
    # them -- same physics, a fraction of the Python object overhead.
    for level in range(n):
        block = 2 ** (n - level)
        half = block // 2
        norms = np.linalg.norm(amps.reshape(2**level, block), axis=1)
        left = np.linalg.norm(amps.reshape(2**level, 2, half), axis=2)[:, 0]
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(norms > _TOL, left / np.where(norms > _TOL, norms, 1.0), 1.0)
        angles = 2.0 * np.arccos(np.clip(ratio, 0.0, 1.0))

        if not np.any(np.abs(angles) > _TOL):
            continue
        if level == 0:
            circuit.ry(float(angles[0]), qs[0])
            continue

        controls = qs[:level]
        if list(controls) == sorted(controls):
            circuit.multiplexed_ry(angles, controls, qs[level])
        else:
            # Custom qubit orderings break the angle table's bit convention;
            # fall back to explicit gates rather than silently mis-indexing.
            for prefix, theta in enumerate(angles):
                if abs(float(theta)) < _TOL:
                    continue
                bits = [(prefix >> (level - 1 - b)) & 1 for b in range(level)]
                circuit.mcry(float(theta), controls, qs[level], control_values=bits)
    return circuit


# --------------------------------------------------------------------------
# Grids for the distributions finance actually uses
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class GridDistribution:
    """A distribution discretised onto ``2**n_qubits`` evenly spaced points."""

    values: np.ndarray          # grid points in the modelled variable
    probabilities: np.ndarray   # probability mass at each point
    n_qubits: int

    @property
    def mean(self) -> float:
        return float(np.dot(self.values, self.probabilities))

    @property
    def variance(self) -> float:
        m = self.mean
        return float(np.dot((self.values - m) ** 2, self.probabilities))

    @property
    def stdev(self) -> float:
        return math.sqrt(max(0.0, self.variance))

    def circuit(self) -> Circuit:
        """The state-preparation circuit for this distribution."""
        return prepare_distribution(self.probabilities, self.n_qubits)

    def expectation(self, fn) -> float:
        """Classical reference value of ``E[fn(X)]`` on the same grid.

        Comparing against this isolates *estimation* error from *discretisation*
        error, which matters when validating the quantum routines.
        """
        vals = np.array([fn(v) for v in self.values], dtype=np.float64)
        return float(np.dot(vals, self.probabilities))


def _discretise(values: np.ndarray, density: np.ndarray, n_qubits: int) -> GridDistribution:
    density = np.clip(np.asarray(density, dtype=np.float64), 0.0, None)
    total = density.sum()
    if total <= 0:
        raise ValueError("degenerate density on this grid")
    return GridDistribution(values=values, probabilities=density / total, n_qubits=n_qubits)


def normal_grid(mu: float, sigma: float, n_qubits: int, n_sigma: float = 3.0) -> GridDistribution:
    """Truncated normal on ``2**n_qubits`` points spanning ``mu +/- n_sigma*sigma``."""
    if sigma <= 0:
        raise ValueError("sigma must be positive")
    lo, hi = mu - n_sigma * sigma, mu + n_sigma * sigma
    x = np.linspace(lo, hi, 2**n_qubits)
    pdf = np.exp(-0.5 * ((x - mu) / sigma) ** 2)
    return _discretise(x, pdf, n_qubits)


def lognormal_grid(
    mu: float,
    sigma: float,
    n_qubits: int,
    n_sigma: float = 3.0,
) -> GridDistribution:
    """Log-normal price grid: ``log S ~ N(mu, sigma^2)``.

    This is the terminal-price distribution of geometric Brownian motion, i.e.
    the Black-Scholes model, so it is the natural input for option pricing.
    """
    if sigma <= 0:
        raise ValueError("sigma must be positive")
    lo = math.exp(mu - n_sigma * sigma)
    hi = math.exp(mu + n_sigma * sigma)
    s = np.linspace(lo, hi, 2**n_qubits)
    s = np.clip(s, 1e-12, None)
    pdf = np.exp(-0.5 * ((np.log(s) - mu) / sigma) ** 2) / s
    return _discretise(s, pdf, n_qubits)


def multivariate_normal_grid(
    mean: np.ndarray,
    cov: np.ndarray,
    n_qubits_per_asset: int,
    n_sigma: float = 3.0,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Joint normal over ``d`` assets on a tensor-product grid.

    Returns ``(grid_points, joint_probabilities, total_qubits)`` where
    ``grid_points`` has shape ``(2**total_qubits, d)``.  The register is the
    concatenation of the per-asset registers, so the qubit cost is
    ``d * n_qubits_per_asset`` -- this grows fast, which is precisely why
    multi-asset problems are the interesting quantum target.
    """
    mean = np.asarray(mean, dtype=np.float64).reshape(-1)
    cov = np.asarray(cov, dtype=np.float64)
    d = mean.size
    if cov.shape != (d, d):
        raise ValueError("covariance shape does not match the mean vector")

    sigmas = np.sqrt(np.clip(np.diag(cov), 1e-18, None))
    axes = [
        np.linspace(mean[i] - n_sigma * sigmas[i], mean[i] + n_sigma * sigmas[i], 2**n_qubits_per_asset)
        for i in range(d)
    ]
    mesh = np.meshgrid(*axes, indexing="ij")
    points = np.stack([m.reshape(-1) for m in mesh], axis=1)

    # Full joint density (not the product of marginals) so correlation is kept.
    inv = np.linalg.pinv(cov)
    delta = points - mean
    quad = np.einsum("ij,jk,ik->i", delta, inv, delta)
    density = np.exp(-0.5 * quad)
    total = density.sum()
    if total <= 0:
        raise ValueError("degenerate joint density")
    return points, density / total, d * n_qubits_per_asset
