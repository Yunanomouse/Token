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

## Memory: the exponential wall and what actually moves it

Simulating `n` qubits costs `2ⁿ` amplitudes. Nothing changes that — but a large
constant factor sat on top of it, and most of it was avoidable. Everything below
is measured before and after, with no change to any numerical result.

### What was fixed

| Hotspot | Before | After | Gain |
|---|---|---|---|
| `energies_all` (n=16) | 18.9 MB | 1.05 MB | **18×**, and 42× faster |
| Statevector (n=20) | 3.1× theory | 2.0× theory | 1.6× |
| …with `complex64` | 50 MB | 17 MB | **3×** total |
| Distribution loading (n=12) | 4095 ops / 2.53 MB | 12 ops / 0.23 MB | **11×**, 30× faster |
| QAOA loop (n=12) | 1.02 MB | 0.45 MB | 2.3× |

**`energies_all` was the worst offender**, using 36× its own result: it built a
`(2ⁿ, n)` bit matrix, a spin copy and einsum temporaries to produce a `2ⁿ`
vector. Recursive doubling replaces it — appending variable `k` costs
`E(x) + Q_kk + Σᵢ(Q_ik+Q_ki)xᵢ`, and that correction is itself linear in the
bits, so it builds the same way. Peak is now exactly 2×: one result, one scratch.

**Gate application** went from `tensordot` + `moveaxis` (a fresh `2ⁿ` array per
gate) to in-place updates through views. A one-qubit unitary only mixes the two
amplitude slices differing in the target bit, so those slices are taken as views
and rewritten against a reusable scratch pair. Peak is flat in circuit depth.

**Diagonal phase layers** were chunked. `state *= np.exp(1j * phases)`
materialises a full `2ⁿ` complex temporary — an entire extra statevector, on
every cost layer of every QAOA evaluation. Streaming it in 4 MB blocks caps the
temporary regardless of `n`, and runs faster because the working set stays in
cache.

**State preparation** stopped emitting `2ⁿ` gate objects. Every node at one level
of the loading tree shares controls and target and differs only in its angle, so
a level is one *multiplexed* `Ry` holding an angle array, applied in a single
broadcast pass. `resource_estimate()` still reports the true hardware gate count —
the physics is unchanged, only the Python object overhead is gone.

### A bug this surfaced

Integer indexing that reduces a numpy view to rank 0 returns a **scalar, not a
view**. In-place writes through it silently vanish — which broke 1-qubit circuits
and fully-controlled gates, producing wrong answers rather than errors. All
subspace selection now uses length-1 slices, which preserve rank. The old
`tensordot` path had been hiding this.

### Precision

`complex64` halves memory for a measured `7×10⁻⁸` maximum amplitude error over
200 gates — negligible against the shot noise of any sampled estimator here, but
*not* negligible if you are comparing exact statevectors or reading an
exponentially small overlap. Google's qsim defaults to single precision; Qiskit
Aer exposes it as `precision="single"`. Use `complex128` for the final expectation
reduction regardless — that is where precision loss would actually bite.

### Matrix Product States — also measured, also not applicable

MPS stores a state as a chain of tensors, costing `O(n·χ²)` instead of `O(2ⁿ)`,
where `χ` is the bond dimension. It is the standard answer to "the statevector is
too big". Two measurements rule it out here:

**It loses below ~24 qubits.** The crossover is roughly `n·χ² > 2ⁿ/2`. At n=16
with a random circuit, χ saturates at its exact maximum `2^(n/2)=256` and MPS
costs 2.80 MB against 1.05 MB for a plain statevector. This package operates
well below that crossover.

**Sparsity is not the criterion — bandwidth under the 1D ordering is.** A random
3-regular MaxCut graph is maximally sparse and still saturates χ at `2^(n/2)` by
p=3, with entanglement entropy 8.35 of a possible 10 bits. A path graph of the
same degree stays at χ=32 through p=5 with zero truncation error. Dense
covariance couplings are the bad case twice over.

Worth recording, since it corrects a common assumption: **Grover is near-*best*
case for MPS**, not worst. The state `a|marked⟩ + b|rest⟩` has Schmidt rank
exactly 2 across any cut, so entanglement is bounded by 1 bit independent of `n` —
verified to 30 qubits at χ=2 exactly. The genuine MPS killers are QFT-based
algorithms, where the required bond dimension grows super-polynomially.

### The technique that changes the asymptotics — and why it is not used here

For a p-layer QAOA with a local mixer, `⟨Z_i Z_j⟩` depends only on qubits within
graph distance `p` of edge `(i,j)`. The energy becomes a sum of independent
`2^k` simulations where `k` is **independent of n** — around 1000× less memory on
sparse MaxCut at n=24.

It requires a *sparse* coupling graph, and finance does not supply one. The
quadratic term of a portfolio problem is a covariance matrix: every asset
correlates with every other, so the graph is complete and the radius-1 cone is
already the whole problem. Measured on this package's own QUBOs:

| Problem | density | cone at p=1 | benefit |
|---|---|---|---|
| portfolio, cardinality | 1.00 | all n | none |
| portfolio, lots + sector caps | 0.92 | all n | none |
| arbitrage cycle QUBO | 0.81 | all n | none |
| ring graph (sparse contrast) | 0.13 | 6 of 16 | 1,024× |

So `quantum/locality.py` ships the *measurement* rather than the machinery. Run
`locality_report(problem)` before assuming either way.

### What works instead: constraint-preserving subspaces

The cardinality mandate — *hold exactly K names* — is normally a penalty term.
That wastes the register (at n=20, K=5, 98.5% of basis states are portfolios the
mandate forbids) and it is *soft*, so a mis-scaled penalty returns an infeasible
portfolio that looks optimal.

An **XY mixer** `½Σ(XᵢXⱼ + YᵢYⱼ)` swaps `|01⟩↔|10⟩` and annihilates `|00⟩` and
`|11⟩`: it moves weight between assets without changing how many are held.
Started from a Dicke state, the evolution never leaves the feasible subspace.
This is the Quantum Alternating *Operator* Ansatz (Hadfield et al. 2019).

| n | K | full 2ⁿ | C(n,K) | saving |
|---|---|---|---|---|
| 20 | 5 | 1,048,576 | 15,504 | 68× |
| 24 | 6 | 16,777,216 | 134,596 | 125× |
| 32 | 4 | 4,294,967,296 | 35,960 | **119,437×** |

Verified exact against a full-register simulation to `1.3×10⁻¹⁵` with **zero
leakage** outside the feasible set. And it is more accurate: on 25 seeds ×
3 cardinalities, subspace QAOA found the proven optimum **25/25 every time**
where penalty QAOA fell to 18/25 at K=5. The penalty-scaling trap documented
above does not merely get easier here — it stops existing.

### Files on disk

`quantum/storage.py` handles the other meaning of "compress". Measured on
50 assets × 5040 days of prices:

| codec | precision | ratio | rel. error |
|---|---|---|---|
| lzma | float64, 12-bit mantissa | 5.64× | 1.2×10⁻⁴ |
| zlib | float32, 12-bit mantissa | 3.26× | 1.2×10⁻⁴ |
| zlib | float32, 20-bit mantissa | 2.30× | 4.8×10⁻⁷ |
| zlib | float32 | 2.21× | 6.0×10⁻⁸ |

Mantissa shaving is the lever: the low bits of a float are effectively random,
and random bits are incompressible. Zeroing them leaves runs a codec can collapse.

Three details that decide whether this is safe:

**Round to nearest, never truncate.** Masking low bits always rounds toward
zero, and that bias compounds through a return series or a covariance sum.
Measured here, adding half a ULP before masking cuts the mean relative error by
~1000× at identical compression ratio — there is no reason to accept the bias:

| kept bits | truncation (mean) | round-to-nearest (mean) |
|---|---|---|
| 23 | −4.2×10⁻⁸ | **+3.7×10⁻¹¹** |
| 12 | −8.6×10⁻⁵ | **+2.4×10⁻⁸** |

**Byte-shuffle, but measure it.** Transposing bytes so all exponent bytes sit
together gives a compressor long low-entropy runs. It is worth +17% on prices
and +19% on float32 prices — but it *hurt* an unshaved covariance matrix by 29%,
because a covariance spans a wide dynamic range and its exponents are
high-entropy too. `save_compressed(shuffle="auto")` measures both on a sample and
keeps the winner rather than assuming.

**Deflate level 1, not 9.** Measured on prices: level 1 gives 1.056×, level 6
gives 1.064×, level 9 is identical to level 6. A 0.8% ratio gain for 25% more
time. High deflate levels buy nothing on float data — the entropy is in the
mantissas, not in repeated substrings.

### The float32 trap in covariance storage

Downcasting a covariance matrix can turn a valid one into a matrix that is no
longer positive semi-definite — which breaks Cholesky and makes the optimiser
return nonsense rather than an error. A relative perturbation of `eps` shifts
eigenvalues by about `eps·λ_max`, so the matrix survives only while
`cond(C) ≲ 0.1/eps` — roughly 10⁶ for float32, 10⁴ for float16.

Measured on constructed spectra at n=200: float32 Cholesky succeeds through
cond 10⁸ and fails at 10¹⁰. `recommended_dtype()` flags at 10⁶ — deliberately
conservative, since the failure is silent. This is exactly the case a sample
covariance walks into when observations are scarce relative to assets, which is
why shrinkage comes first and downcasting second.

Storage precision and *arithmetic* precision are separate decisions: computing
in float64 while storing in float32 is fine, and is what this package does.

**float16 is not usable for finance at all** — its 65504 ceiling breaks on
unscaled prices and its 6.1×10⁻⁵ subnormal floor destroys daily returns and
off-diagonal covariance entries.

One distinction worth keeping straight: **compression saves disk, not RAM** — a
decompressed array is full size. For RAM use `load_mmap()` + `iter_chunks()`, and
those cannot be combined with compression, because random access and compression
are mutually exclusive.

`python3 -m quantum memory` prints all of the above for your own configuration.

## Validation

```bash
python3 -m unittest discover -s tests -v
```

105 tests. The principle throughout: **every quantum routine is checked against
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
- Memory — the optimised paths must reproduce the naive ones exactly: recursive
  doubling against the bit-matrix contraction, the in-place kernel against
  `tensordot`, multiplexed `Ry` against explicit `mcry` gates, and subspace QAOA
  against a full-register simulation.

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
- Hadfield et al. (2019), *From the QAOA to a Quantum Alternating Operator Ansatz*
- Lykov et al. (2023), *Fast Simulation of High-Depth QAOA Circuits* (QOKit)
- Lykov, Schutski & Alexeev (2020), *Tensor Network Quantum Simulator with Step-Dependent Parallelization* (QTensor)
- Farhi, Gamarnik & Gutmann (2020), *The QAOA Needs to See the Whole Graph* (locality)
