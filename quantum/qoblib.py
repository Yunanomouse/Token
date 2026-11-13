"""Reader for QOBLIB's portfolio benchmark, and a scorer against its optima.

QOBLIB -- the Quantum Optimization Benchmarking Library (Koch et al., *Nature
Computational Science*, 2026; https://github.com/ZIB-AOPT/QOBLIB) -- is the
first community benchmark with certified answers for quantum optimisation.
Its problem class 06 is a multi-period portfolio model with transaction costs,
short selling, borrowing costs and per-period capital and cardinality limits,
built on real S&P 500 prices, shipped as ready-made QUBO matrices, and solved
to *proven* optimality by Gurobi for the small instances.

That makes it the one external yardstick this package can be held to.  The
solvers in :mod:`quantum.solvers` are validated everywhere else against
exhaustive enumeration, which caps the test at ~22 variables.  The smallest
QOBLIB instance has 710.

File formats
------------
``uqo_*.qs[.xz]`` -- one header of ``n_vars n_entries``, then ``i j c`` lines
(1-based, ``i <= j``) meaning ``c * x_i * x_j``.  The constant term of the
squared penalties is not stored, so energies read from the file sit below the
portfolio objective by a fixed offset; :func:`qubo_offset` recovers it from a
known feasible solution.

Variable order (from ``misc/lp_sol_to_canonical.py`` in the library):
``asset (price-file order) -> copy m in 1..ub -> direction (+1, -1) ->
period``, then the capital slack register ``y`` (4 bits per period), then the
cardinality slack register ``s2`` (7 bits per period).

Canonical solutions (``*.opt.sol``, ``*.bst.sol``) list per period and symbol
the number of unit copies held long and short; ``.opt`` means proven optimal.
"""

from __future__ import annotations

import gzip
import lzma
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from .qubo import QUBO

__all__ = [
    "QoblibInstance",
    "QoblibSolution",
    "load_instance",
    "load_qs",
    "load_solution",
    "qubo_offset",
    "solution_bits",
    "decode_bits",
]

CAPITAL_BITS = 4      # |CS1|
CARDINALITY_BITS = 7  # |CS2|


def _open_text(path: str | Path):
    p = str(path)
    if p.endswith(".xz"):
        return lzma.open(p, "rt")
    if p.endswith(".gz"):
        return gzip.open(p, "rt")
    return open(p, "rt", encoding="utf-8")


# --------------------------------------------------------------------------
# Instance data (prices) -- fixes the asset order and the number of periods
# --------------------------------------------------------------------------


@dataclass
class QoblibInstance:
    name: str
    symbols: list[str]
    prices: np.ndarray      # (n_periods, n_assets) raw prices
    ub: int = 3
    capital: int = 10
    budget: int | None = None

    @property
    def n_assets(self) -> int:
        return len(self.symbols)

    @property
    def n_periods(self) -> int:
        return int(self.prices.shape[0])

    @property
    def n_variables(self) -> int:
        t = self.n_periods
        return self.n_assets * self.ub * 2 * t + (CAPITAL_BITS + CARDINALITY_BITS) * t

    def variable_order(self) -> list[tuple]:
        """1-based index minus one -> ``("x", symbol, copy, tau, period)`` or a slack tag."""
        t_count = self.n_periods
        order: list[tuple] = []
        for sym in self.symbols:
            for m in range(1, self.ub + 1):
                for tau in (1, -1):
                    for t in range(t_count):
                        order.append(("x", sym, m, tau, t))
        # Zimpl creates y[CS1*TX] and s2[CS2*TX] with the bit index outer
        # and the period inner -- verified against a certified optimum, which
        # is a strict local minimum only under this order.
        for c in range(CAPITAL_BITS):
            for t in range(t_count):
                order.append(("y", c, t))
        for b in range(CARDINALITY_BITS):
            for t in range(t_count):
                order.append(("s", b, t))
        return order


def load_instance(instance_dir: str | Path, ub: int = 3, capital: int = 10) -> QoblibInstance:
    """Read ``stock_prices.txt[.gz]`` from an instance directory."""
    d = Path(instance_dir)
    path = next((d / n for n in ("stock_prices.txt.gz", "stock_prices.txt") if (d / n).exists()), None)
    if path is None:
        raise FileNotFoundError(f"no stock_prices file in {d}")
    symbols: list[str] = []
    table: dict[tuple[int, str], float] = {}
    with _open_text(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            t, sym, price = line.split()
            if sym not in symbols:
                symbols.append(sym)
            table[(int(t), sym)] = float(price)
    periods = sorted({t for t, _ in table})
    prices = np.array([[table[(t, s)] for s in symbols] for t in periods])
    return QoblibInstance(d.name, symbols, prices, ub=ub, capital=capital)


# --------------------------------------------------------------------------
# QUBO file
# --------------------------------------------------------------------------


def load_qs(path: str | Path) -> QUBO:
    """Read a ``.qs`` (optionally ``.xz``/``.gz``) file into a :class:`QUBO`.

    Entries are stored once per unordered pair, but the matrix they describe
    is *symmetric*: an off-diagonal line ``i j c`` contributes ``c`` to both
    ``Q[i, j]`` and ``Q[j, i]``, so the term is ``2 c x_i x_j``.  That is the
    reading under which the library's certified optimal solutions are strict
    local minima with every single-bit flip costing at least the penalty
    weight; the upper-triangular reading is not.  (The library's own
    ``metrics.csv`` density figures also count each pair twice.)
    """
    with _open_text(path) as fh:
        lines = [l for l in fh if l.strip() and not l.lstrip().startswith("#")]
    n, m = (int(v) for v in lines[0].split())
    Q = np.zeros((n, n), dtype=np.float64)
    count = 0
    for line in lines[1:]:
        i, j, c = line.split()
        i, j = int(i) - 1, int(j) - 1
        Q[i, j] += float(c)
        if i != j:
            Q[j, i] += float(c)
        count += 1
    if count != m:
        raise ValueError(f"{path}: header promised {m} entries, found {count}")
    return QUBO(Q=Q)


# --------------------------------------------------------------------------
# Canonical solutions
# --------------------------------------------------------------------------


@dataclass
class QoblibSolution:
    instance: str
    budget: int
    risk_weight: float
    objective: float | None
    positions: dict[tuple[int, str], tuple[int, int]] = field(default_factory=dict)
    """``(period, symbol) -> (long units, short units)``."""
    proven_optimal: bool = False


def load_solution(path: str | Path) -> QoblibSolution:
    p = Path(path)
    header: dict[str, str] = {}
    positions: dict[tuple[int, str], tuple[int, int]] = {}
    with _open_text(p) as fh:
        for raw in fh:
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) == 2 and parts[0] in ("instance", "budget", "lambda", "objective"):
                header[parts[0]] = parts[1]
            elif len(parts) == 4:
                positions[(int(parts[0]), parts[1])] = (int(parts[2]), int(parts[3]))
            else:
                raise ValueError(f"{p}: unparsed line {line!r}")
    return QoblibSolution(
        instance=header.get("instance", ""),
        budget=int(header["budget"]),
        risk_weight=float(header["lambda"]),
        objective=float(header["objective"]) if "objective" in header else None,
        positions=positions,
        proven_optimal=".opt." in p.name,
    )


def solution_bits(instance: QoblibInstance, solution: QoblibSolution, budget: int | None = None) -> np.ndarray:
    """Binary vector in ``.qs`` variable order realising a canonical solution.

    Copies are filled ``1..u`` (the canonical slot assignment the checker
    assumes) and the slack registers are set so both equality constraints hold
    exactly, so the penalty terms vanish and the QUBO energy equals the
    portfolio objective plus the file's missing constant.
    """
    budget = solution.budget if budget is None else budget
    order = instance.variable_order()
    bits = np.zeros(len(order), dtype=np.int8)
    index = {entry: k for k, entry in enumerate(order)}
    for (t, sym), (long_u, short_u) in solution.positions.items():
        if sym not in instance.symbols:
            raise ValueError(f"symbol {sym!r} not in instance {instance.name}")
        for m in range(1, instance.ub + 1):
            if m <= long_u:
                bits[index[("x", sym, m, 1, t)]] = 1
            if m <= short_u:
                bits[index[("x", sym, m, -1, t)]] = 1
    for t in range(instance.n_periods):
        net = sum(l - s for (tt, _), (l, s) in solution.positions.items() if tt == t)
        total = sum(l + s for (tt, _), (l, s) in solution.positions.items() if tt == t)
        y = instance.capital - net
        s = budget - total
        if not 0 <= y < 2**CAPITAL_BITS or not 0 <= s < 2**CARDINALITY_BITS:
            raise ValueError(f"period {t}: slack out of range (capital {y}, cardinality {s})")
        for c in range(CAPITAL_BITS):
            bits[index[("y", c, t)]] = (y >> c) & 1
        for b in range(CARDINALITY_BITS):
            bits[index[("s", b, t)]] = (s >> b) & 1
    return bits


def decode_bits(instance: QoblibInstance, bits: np.ndarray, budget: int) -> dict:
    """Positions, per-period constraint residuals, and feasibility of a bit vector."""
    order = instance.variable_order()
    bits = np.asarray(bits).reshape(-1)
    if bits.size != len(order):
        raise ValueError("bit vector length does not match the instance")
    positions: dict[tuple[int, str], list[int]] = {}
    y = np.zeros(instance.n_periods, dtype=int)
    s = np.zeros(instance.n_periods, dtype=int)
    for k, entry in enumerate(order):
        if not bits[k]:
            continue
        if entry[0] == "x":
            _, sym, _m, tau, t = entry
            positions.setdefault((t, sym), [0, 0])[0 if tau == 1 else 1] += 1
        elif entry[0] == "y":
            y[entry[2]] += 2 ** entry[1]
        else:
            s[entry[2]] += 2 ** entry[1]
    capital_residual = []
    budget_residual = []
    for t in range(instance.n_periods):
        net = sum(l - sh for (tt, _), (l, sh) in positions.items() if tt == t)
        tot = sum(l + sh for (tt, _), (l, sh) in positions.items() if tt == t)
        capital_residual.append(net + int(y[t]) - instance.capital)
        budget_residual.append(tot + int(s[t]) - budget)
    return {
        "positions": {k: tuple(v) for k, v in positions.items()},
        "capital_residual": capital_residual,
        "budget_residual": budget_residual,
        "feasible": not any(capital_residual) and not any(budget_residual),
    }


def qubo_offset(qubo: QUBO, instance: QoblibInstance, solution: QoblibSolution) -> float:
    """``objective - energy`` for a feasible reference solution: the constant
    the ``.qs`` file leaves out.  Add it to any energy to get a portfolio
    objective comparable to the library's best-known values."""
    if solution.objective is None:
        raise ValueError("reference solution carries no objective value")
    bits = solution_bits(instance, solution)
    return float(solution.objective - qubo.energy(bits))
