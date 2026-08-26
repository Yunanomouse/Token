# Quantum methods for trading

An honest guide to what the `quantum/` package does, what the physics actually
buys you, and where each approach stops working.

## The one-paragraph summary

Quantum mechanics has a defensible role in finance in exactly four places:
**constrained portfolio optimisation**, **risk simulation**, **derivatives
pricing**, and **combinatorial arbitrage search**. None of them is signal
generation, and none of them beats a CPU today. What this package provides is a
correct, tested implementation of each, with the classical baseline printed
alongside every result so the comparison stays visible.

---

## 1. Portfolio optimisation — the strongest case

**The common misconception** is that quantum computers help because portfolios
are large. They do not. Unconstrained mean-variance optimisation is convex, with
a closed-form solution `Σ⁻¹μ / 2q`; on thousands of assets a classical solver
finishes in milliseconds. `unconstrained_mean_variance()` is in the package
specifically to make that concrete.

**What is actually hard** is the discrete structure real mandates carry:

| Constraint | Why it breaks convexity |
|---|---|
| Hold exactly K names | cardinality — combinatorial |
| Trade whole lots | integer variables |
| Sector caps | inequality, needs slack bits |
| Minimum position size | semi-continuous variables |
| Transaction costs | path dependence on current holdings |

Each turns a convex program into an NP-hard combinatorial one — and *that* maps
onto an Ising ground state. That is the real argument for quantum optimisation
in finance.

```bash
python3 -m quantum portfolio --assets 10 --cardinality 4 --solver simulated_bifurcation
```

The compilation path is `PortfolioProblem` → `QUBO` → Ising → solver. Two
encodings are available: `select` (one bit per asset, equal weight, `n`
variables) and `lots` (`B` bits per asset for genuine position sizing, `n·B`
variables). Problem width is what limits you on hardware, so the choice matters.

### Two modelling traps this package hit and fixes

**Penalty scaling.** Constraints enter as `λ·g(x)²`. The naive choice — set `λ`
to the largest objective coefficient — is wrong whenever the constraint's own
coefficients are small. The smallest step a constraint can take is its smallest
non-zero coefficient `c_min`, contributing `λ·c_min²`. With portfolio weights
around 0.05 that under-penalises by a factor of ~400, and the solver returns a
portfolio that quietly ignores its budget. `suggest_penalty_for()` scales as
`objective_scale / c_min²`.

**Silent budget repair.** Weights from a coarse lot grid need not sum to 1, and
rescaling them can push a position above a `max_weight` the encoding respected.
`decode()` returns raw weights; `decode_normalised()` returns the tradeable ones
*plus the rescale factor*, and feasibility is reported for both. Rescaling is a
repair, not part of the optimisation, and hiding it hides constraint violations.

---

## 2. Risk — best-proven theory, worst-ready hardware

Value at Risk is a quantile; CVaR is a conditional mean. Both are expectations,
and every expectation is an amplitude estimation problem.

The theory here is the strongest in quantum finance: **amplitude estimation
needs `O(1/ε)` oracle calls where Monte Carlo needs `O(1/ε²)` samples**
(Brassard–Høyer–Mosca–Tapp; Montanaro 2015). That quadratic speedup is proven,
not conjectural.

```bash
python3 -m quantum risk --confidence 0.95 --qubits 6
```

VaR is found by bisecting on amplitude-estimated CDF values — `O(log N)`
estimations for an `N`-point grid. CVaR reuses the option-payoff rotation,
restricted to the tail.

**The catch**: that speedup counts *oracle calls*, and each call is a full
distribution load plus a comparator. Deep coherent circuits mean fault-tolerant
hardware, which does not exist. On today's machines a classical Monte Carlo
finishes first by many orders of magnitude.

---

## 3. Derivatives pricing — the multi-asset case is the real one

For a single vanilla option this is far slower than Black–Scholes, which is
included purely as a correctness oracle. The asymptotic payoff is in
**multi-asset and path-dependent** contracts where no closed form exists and
classical Monte Carlo cost explodes with dimension.

```bash
python3 -m quantum price --spot 100 --strike 105 --volatility 0.2 --qubits 6
```

### Grid convergence — the part that bites

Two independent errors, responding to different knobs:

- **Estimation error** → add Grover powers or shots.
- **Discretisation error** → grid resolution (`n_qubits`) *and* domain
  truncation (`n_sigma`), bounded below by whichever is worse.

Truncation is the one people miss. Measured discretisation error for a
100/105 one-year call:

| qubits | n_sigma=3 | n_sigma=4 | n_sigma=5 |
|---|---|---|---|
| 5 | 0.105 | 0.009 | 0.022 |
| 6 | 0.092 | 0.011 | 0.021 |
| 7 | 0.097 | 0.004 | 0.001 |
| 8 | 0.097 | 0.003 | **0.0005** |

At `n_sigma=3` the error **plateaus around 0.10 and adding qubits does nothing** —
the tail beyond the grid is simply absent. Widen the domain before adding
qubits. The default is `n_sigma=4.0` for this reason.

### The payoff linearisation bias

The payoff is encoded through `sin²(π/4 + u) ≈ ½ + u`, wrong at order `u³`.
Dividing by `c_approx` to recover the price turns that into an error of order
**`c²`** — and because it is *systematic*, adding shots or Grover powers cannot
remove it. Adding powers actually makes the measured estimation error look
worse, because it strips away the noise that was partially masking the bias.

Measured price bias, exact amplitude, zero shot noise:

| c_approx | price bias | bias / c² |
|---|---|---|
| 0.02 | 0.0045 | 11.21 |
| 0.05 | 0.0280 | 11.21 |
| 0.10 | 0.1120 | 11.20 |
| 0.25 | 0.6984 | 11.17 |
| 0.35 | 1.3650 | 11.14 |

The ratio is constant to three digits, so the leading term is a clean `c²` and
two runs cancel it exactly by Richardson extrapolation:

```
price = (4·price(c/2) − price(c)) / 3
```

That is `bias_correction=True`. **It is not always a win.** Recovering the price
divides by `c`, so the `c/2` run carries twice the shot noise and the combination
amplifies the standard error by roughly 2.7×:

| c_approx | plain error | corrected error |
|---|---|---|
| 0.05 | 0.123 | 0.603 — worse |
| 0.10 | 0.064 | 0.094 — worse |
| 0.25 | 0.640 | **0.002 — 335× better** |

Use it with `c_approx ≥ 0.2` where bias dominates; below that, keep `c` small and
spend the shots instead. Best configuration found: 8 qubits, `n_sigma=5`,
`c_approx=0.15`, 8 powers, bias-corrected — **0.03% from Black–Scholes**.

### The input problem

Loading an arbitrary distribution into `n` qubits costs `O(2ⁿ)` gates, which
cancels the quadratic advantage if you reload every run. This is not a defect of
the implementation — it is the central open obstacle in quantum finance, and the
reason these speedups remain asymptotic.

---

## 4. Arbitrage — where quantum is structurally the wrong tool

A profitable conversion cycle is a **negative cycle** under `w = -log(rate)`.
That has an exact polynomial classical algorithm — Bellman–Ford — included as
`bellman_ford_negative_cycle()`. **Use it.**

```bash
python3 -m quantum arbitrage --cycle-length 3 --fee 0.0005
```

The QUBO formulation earns its keep only for the constrained variants: bounded
cycle length, per-venue capacity, size-dependent slippage, or selecting multiple
non-overlapping cycles.

**On HFT specifically**: real arbitrage runs on FPGAs colocated in the exchange,
in nanoseconds. A gate-based quantum computer needs milliseconds for state
preparation and readout alone — roughly six orders of magnitude too slow, and
that gap is imposed by physics, not engineering backlog. The realistic
deployment is simulated bifurcation on classical silicon.

Note also that fees dominate: at 10bp per leg, the demo's arbitrage disappears
entirely. A detector that ignores costs reports opportunities that cannot be traded.

---

## The solver comparison

```bash
python3 -m quantum benchmark --vars 10 --trials 10
```

| Solver | Family | Realistic today? |
|---|---|---|
| `exact` | exhaustive | only below ~22 variables |
| `simulated_annealing` | classical thermal | yes — the baseline to beat |
| `simulated_bifurcation` | quantum-derived, classical | **yes — ships on FPGAs/GPUs now** |
| `qaoa` | gate-based quantum | no — research scale only |

**Simulated bifurcation** deserves attention. It discretises the equations of
motion of Kerr-nonlinear parametric oscillators (Goto et al., *Science Advances*
2019) — the derivation is quantum, the execution is entirely classical. This is
the algorithm behind Toshiba's SQBM+ and Fujitsu's Digital Annealer, in
production today. It sidesteps both the qubit ceiling and the latency wall, and
in this package's own benchmarks it is roughly 20× faster than simulated
annealing at comparable quality.

**QAOA** has no proven advantage over good classical heuristics on these
problems. At low depth it is frequently *worse* than the annealing baseline here.
It is included because it is what the field is betting on, and because a
head-to-head comparison beats taking anyone's word for it.

### Two solver bugs worth knowing about

Both were found by testing against exhaustively proven optima, and both are easy
to reproduce in any from-scratch implementation:

1. **Bifurcation scaling.** Goto's prescription is `c0 = 0.5·√(n−1)/‖J‖_F`.
   Scaling off the coupling *standard deviation* instead looks equivalent but is
   not: on problems with uniformly small couplings — a covariance matrix — it
   inflates `c0` by orders of magnitude and every oscillator slams into the same
   wall on step one. Symptom: the solver returns all-ones.

2. **Annealing readout.** Returning the *final* spin configuration rather than
   the best one ever visited costs real solution quality. On constrained
   problems the penalty terms dominate the coupling magnitudes, so no cooling
   schedule drives the final temperature below the objective's own differences —
   the chain keeps hopping between near-optima to the last sweep.

---

## Validation

```bash
python3 -m unittest discover -s tests -v
```

67 tests. The principle throughout: **every quantum routine is checked against
an exact classical reference**, never against itself.

- Physics — Bell/GHZ states, unitarity, adjoint identity, QFT against `numpy.fft`,
  Born-rule sampling, exact distribution loading to 1e-12.
- Grover rotation law — `P(good) = sin²((2k+1)θ)` verified exactly for k = 0…5.
- Amplitude estimation — MLAE beats the classical standard error at equal shots.
- QUBO ↔ Ising equivalence over 50 random instances, every assignment.
- Portfolio — all four solvers must match the `C(n,K)`-exhaustive optimum.
- Pricing — Black–Scholes, put-call parity, error decomposition, grid convergence,
  and the `c²` bias law verified against exact amplitudes.
- Risk — VaR within one grid spacing of the exact quantile at 90/95/99%.
- Arbitrage — no false positives on a consistent market; planted mispricings found.

---

## What this package will not do

It will not predict prices, generate trading signals, or make money on a day
trade. Nothing here runs faster than its classical equivalent on current
hardware. "Quantum" in most retail trading products is branding: check for
`qiskit`, `cirq`, `pennylane`, or `dwave` in the imports before believing
otherwise.

The value of building it is that the formulations are hardware-ready. A QUBO
compiled today runs unchanged on an annealer tomorrow, and runs on classical
simulated bifurcation right now.

## References

- Brassard, Høyer, Mosca & Tapp (2002), *Quantum Amplitude Amplification and Estimation*
- Montanaro (2015), *Quantum speedup of Monte Carlo methods*
- Suzuki et al. (2020), *Amplitude estimation without phase estimation* (MLAE)
- Woerner & Egger (2019), *Quantum risk analysis*
- Stamatopoulos et al. (2020), *Option pricing using quantum computers*
- Goto, Tatsumura & Dixon (2019), *Combinatorial optimization by simulating adiabatic bifurcations*
- Farhi, Goldstone & Gutmann (2014), *A Quantum Approximate Optimization Algorithm*
- Grover & Rudolph (2002), *Creating superpositions that correspond to efficiently integrable probability distributions*
- Ledoit & Wolf (2004), *A well-conditioned estimator for large-dimensional covariance matrices*
