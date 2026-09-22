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

### The "quantum binomial model", tested

Popular write-ups point to this as the case where quantum pricing gives
*different* answers, because the underlying is "treated as a boson". The model
distributes the `N` time steps as `N` particles over two states (up/down) and
prices under the resulting occupancy statistics. Both variants are implemented
in `quantum/pricing.py` and both are tested:

| Statistics | Result |
|---|---|
| Maxwell–Boltzmann (distinguishable) | reproduces Cox–Ross–Rubinstein **exactly**, to 8 decimals at every step count |
| Bose–Einstein, CRR probability | **not risk-neutral** — `E[S_T]/S₀e^{rT}` reaches 59 at 800 steps |
| Bose–Einstein, recalibrated | risk-neutral, converges to the **arbitrage upper bound** |

The Maxwell–Boltzmann equivalence is the model's own validation and is asserted
in the test suite. It is also the giveaway: classical statistics give the
classical price, so nothing quantum has entered yet.

The Bose–Einstein variant is where "different answers" come from, and they do not
survive inspection. Keeping the CRR up-probability breaks the martingale
property outright — by 200 steps it quotes a one-year call on a $100 stock above
$100, which is an immediate arbitrage, and by 800 steps it quotes $5,858.

Re-solving the up-probability so the measure *is* risk-neutral fixes the
arbitrage and the price then converges — to the no-arbitrage **upper bound**.
Verified across strikes and both option types at 12,800 steps: a call converges
to the entire spot, a put to the discounted strike.

| | K=60 | K=105 | K=150 |
|---|---|---|---|
| BE call | 100.00 | 100.00 | 100.00 |
| bound (S₀) | 100.00 | 100.00 | 100.00 |
| BE put | 58.23 | 101.90 | 145.57 |
| bound (Ke^{-rT}) | 58.23 | 101.90 | 145.57 |

That is the most expensive an option can be without admitting arbitrage — a
degenerate limit, not a refined price. The Bose–Einstein weighting concentrates
terminal mass at the extremes, so the payoff ends up tracking the underlying
itself.

The distinction worth carrying: amplitude estimation computes **the same number
faster**; the Bose–Einstein binomial model computes **a different number**, with
no arbitrage argument behind it. Only the first kind is a quantum advantage.

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

## Grover search for portfolio selection

Grover finds a marked item among `N` in `O(√N)` queries instead of `O(N)`.
Turned into an optimiser — Dürr–Høyer minimum finding, refined as Grover
Adaptive Search — it lowers a cost threshold round by round, amplitude-amplifying
whatever still beats it.

Run over the `C(n,K)` *feasible* portfolios from `quantum/subspace.py`, the
quadratic query advantage applies to an already-reduced set. On `C(18,5) = 8568`
candidates it found the proven optimum **10/10** using ~140 oracle calls.

### The caveat that makes the headline number meaningless in simulation

Two measured facts:

- **Building the cost table is itself an exhaustive `O(N)` scan.** A plain
  `np.argmin` over it then returns the exact optimum in 57 microseconds. The
  search cannot beat a scan it has already performed.
- **Each Grover iteration touches all `N` amplitudes.** Simulating 140 oracle
  calls costs ~1.2 million element operations against 8,568 for the argmin —
  roughly **140× more work than simply looking**.

`√N` is a *query-complexity* result. It is real only on hardware, where the
oracle evaluates the cost in superposition and a query is genuinely `O(1)` in
the candidate count. The API names this honestly: `query_speedup_vs_exhaustive`
is the hardware figure of merit, `simulation_overhead_vs_argmin` is what the
simulation actually costs, and `hardware_note()` spells out that a real device
additionally needs the cost comparison compiled into a reversible arithmetic
circuit — the dominant cost, skipped here entirely.

And even on hardware the comparison is against **exhaustive** search, not
against a good heuristic. Simulated bifurcation finds these same optima without
examining `N` candidates. Grover offers a *worst-case* bound needing no
structure in the landscape; a heuristic offers a good average case with no
guarantee. Those are different products, and the honest pitch for Grover is the
guarantee, not the speed.

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
| `subspace_qaoa` | constraint-preserving QAOA | no — but the smallest state space here |
| `grover` | amplitude amplification | no — query bound only, slower in simulation |

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

## The five postulates, implemented and checked

The package builds its physics from the postulates rather than wrapping an SDK,
so `quantum/postulates.py` states them and tests them as physics — separately
from the finance references everything else is graded against.

| Postulate | Where it lives | Verified by |
|---|---|---|
| 1. States are unit vectors | `statevector.py` | norm preserved through arbitrary circuits |
| 2. Born's rule **and collapse** | `postulates.measure` | sampled frequencies match \|⟨φ\|ψ⟩\|²; re-measuring a collapsed state is certain |
| 3. Evolution is unitary | every gate | `U†U = I` for all gates and rotation angles |
| 4. Composition by tensor product | `postulates.kron` | product states separable, Bell states maximally entangled |
| 5. Observables are Hermitian | `postulates.Observable` | non-Hermitian input rejected; eigenvalues real |

Two halves were missing before and are now filled in. **Collapse** — sampling
gave outcomes but never the post-measurement state, so no adaptive protocol was
expressible. And **Postulate 5** — there was only `expectation_z`, no general
observable. That one connects directly: a QUBO objective *is* a Hermitian
observable diagonal in the computational basis, and its eigenvalue spectrum *is*
the energy landscape. `Observable.from_diagonal(problem.energies_all())`
reproduces it exactly.

### Correlation is not entanglement — and the encoding is where people go wrong

Popular quantum-finance writing routinely claims market correlation is a form of
entanglement. Postulate 4 makes the question measurable, and the answer is more
interesting than a flat "no".

**Bell's theorem, by exhaustion.** A local hidden-variable model assigns each
party a deterministic outcome per setting; with two settings and two outcomes
there are `2⁴ = 16` such strategies, and every classical correlation is a
probabilistic mixture of them. CHSH is linear in the mixture, so the maximum over
all classical correlations is the maximum over 16 cases — computed, exactly
**2.0**. Correlation *strength* is not the axis: ρ = 0.999 is still a mixture,
still bounded by 2. Entangled states reach **2.828**.

**But amplitude-encoding manufactures entanglement.** Loading a correlated joint
distribution as √p(x,y) produces a genuinely entangled pure state:

| system | entanglement (bits) | CHSH |
|---|---|---|
| product state \|00⟩ | 0.000 | 1.414 |
| market ρ = 0.0, encoded | 0.000 | 1.414 |
| market ρ = 0.9, **encoded** | 1.000 | **2.828** |
| Bell \|Φ⁺⟩ | 1.000 | 2.828 |
| market ρ = 0.99, **sampled classically** | — | **2.0 (bound)** |

The last two rows are the whole point. The same market correlation is bounded by
2 when sampled, and reaches 2.828 once amplitude-encoded. **The entanglement is
created by the encoding step, not discovered in the market.** It is a property of
a state you chose to prepare on a quantum computer, and it says nothing about
whether the underlying asset returns are entangled — they are not, and Bell's
theorem says they cannot be.

This is a sharper claim than "correlation isn't entanglement", and it is the one
that survives measurement.

## Out of sample, under noise, and on hardware

The first version of this package answered "is the physics right?" and "does
the finance match a classical reference?".  It left three questions open, and
its own PR said so: does the optimiser's portfolio survive out of sample, how
much gate error does the speedup survive, and can any of it leave the
simulator.  All three are now measured.

### Walk-forward validation — the optimiser does not beat 1/N

`quantum/backtest.py` fits each strategy on a trailing window, holds the
portfolio for the next period, rolls forward, and reports what it actually
earned.  Everything is scored against equal weight, which needs no forecast
and which DeMiguel, Garlappi and Uppal (2009) showed is very hard to beat.

Eight synthetic assets, six years, 252-day window, 21-day hold, 60 out-of-sample
periods (`python3 -m quantum backtest --assets 8 --days 1512`):

| strategy | ann. return | ann. vol | Sharpe | *in-sample* Sharpe | max DD | turnover | t vs 1/N |
|---|---|---|---|---|---|---|---|
| equal weight | 5.11% | 14.77% | 0.35 | −0.16 | 32.6% | 0.0% | — |
| Markowitz long-only | 9.07% | 18.31% | 0.50 | 1.30 | 32.5% | 21.7% | +0.88 |
| cardinality 4, simulated annealing | 3.06% | 16.22% | 0.19 | 0.91 | 31.8% | 17.4% | −0.44 |
| cardinality 4, exhaustive | 3.06% | 16.22% | 0.19 | 0.91 | 31.8% | 17.4% | −0.44 |

Three things to read off that table:

1. **The overfit is the story.** The cardinality optimiser *believed* a Sharpe
   of 0.91 on every fitting window and realised 0.19.  Mean-variance
   optimisation is a machine for finding the noise in a return estimate and
   betting on it; the in-sample column is that noise.
2. **Nothing beats equal weight with any confidence.**  The paired t-statistics
   are +0.88 and −0.44.  Anything inside ±2 is indistinguishable from luck on
   this history.
3. **The solver is not the problem.**  Simulated annealing and exhaustive
   search produce identical portfolios at every one of the 60 rebalances, so
   the backtest is scoring the true optimum of the stated problem.  A quantum
   solver that reached the same optimum faster would earn exactly the same
   0.19.

And this is the *friendly* case: synthetic prices have a constant, real drift,
so a long enough window recovers it.  Real equity drift is neither constant nor
real in that sense.  Whatever the optimiser does on live data, it will be worse
than this, not better.

The backtest charges no transaction costs; the turnover column is there so you
can.  At 17% one-way turnover per month and 10 bp per trade, the cardinality
strategy gives back another ~0.4% a year.

### Noise threshold — where the amplitude-estimation speedup dies

`quantum/noise.py` injects depolarising errors by Monte Carlo trajectories:
after every elementary gate of the *compiled* circuit, each qubit it touches
takes a random Pauli with probability ε.  Averaging Born probabilities over
trajectories is an unbiased estimate of what a device would return.  Readout
error is a symmetric bit flip applied analytically.  Multi-controlled gates are
charged at their compiled two-qubit count — an `mcx` with five controls is 64
CNOTs of exposure, not one gate.

Maximum-likelihood amplitude estimation on the 3-qubit option-pricing circuit,
five Grover powers, 256 shots each, 32 trajectories, six trials per rate
(`python3 -m quantum noise --trials 6`):

| ε per gate | estimate | abs error | survival of deepest circuit | beats classical MC? |
|---|---|---|---|---|
| 0 | 0.39592 | 0.00104 | 1.00 | yes |
| 1e-5 | 0.39639 | 0.00095 | 0.98 | yes |
| 3e-5 | 0.39655 | 0.00260 | 0.94 | yes |
| 1e-4 | 0.39459 | 0.00172 | 0.81 | yes |
| 3e-4 | 0.49510 | 0.09963 | 0.53 | no |
| 1e-3 | 0.49563 | 0.10015 | 0.12 | no |
| 1e-2 | 0.49936 | 0.10388 | 6e-10 | no |

True amplitude 0.39547; classical Monte Carlo at the same 8,960 oracle calls:
0.00517.  Deepest circuit: 2,112 elementary gates.

Two findings, one of them not obvious:

- **The threshold sits at ε ≈ 1e-4** for this circuit.  2025 superconducting
  hardware reports two-qubit error rates of a few times 1e-3; trapped ions
  reach 1e-3 with a handful of qubits.  The gap is about an order of magnitude
  for the *smallest* useful pricing circuit; the 6-qubit one in `price` is
  ten times deeper and needs a threshold ten times lower.
- **It is a cliff, not a slope.**  Between 1e-4 and 3e-4 the error jumps from
  0.002 to 0.100 — the estimate lands on 0.5 and stays there.  Once the deep
  Grover powers are depolarised their measured probability sits near ½, and a
  likelihood fit built on the noiseless `sin²((2k+1)θ)` model reads that as
  θ = π/4.  A user without a noise characterisation would fit exactly that
  model, so the reported error includes the model mismatch, as it should.
  Error-aware likelihoods (fitting a per-power damping factor) push the cliff
  out but do not remove it.

Depolarising noise is the *kind* case.  Coherent over-rotation and correlated
errors are worse for a phase-sensitive algorithm, so these thresholds are an
upper bound on what hardware can tolerate.

### Hardware export — OpenQASM 3, verified by round trip

`quantum/export.py` rewrites the two simulator-native operations into gates
that exist on a device and serialises the result as OpenQASM 3, which Qiskit,
Braket, Cirq and tket all import:

- **Multiplexed `Ry`** → `2ᵏ` rotations and `2ᵏ` CNOTs in Gray-code order,
  angles given by the Walsh–Hadamard transform of the angle table (Möttönen
  et al., 2004).  Exact, and the ancilla-free optimum.
- **Diagonal unitaries** → phase gadgets: expand the phase function in the
  Walsh basis and realise each term as a CNOT ladder around one `Rz`.  A
  general diagonal has `2ⁿ` terms, but an Ising cost has at most
  `n(n+1)/2 + 1`, and the compiler keeps only the non-zero ones.  The 7-variable
  QAOA cost layer that `resource_estimate` charges at 128 gates compiles to
  71.  "QAOA is exponential to compile" was an artefact of storing the operator
  densely.
- **Arbitrary one-qubit unitaries** → `U(θ, φ, λ)` by ZYZ decomposition, with
  the global phase carried as a `p` gate on the controls when the gate is
  controlled — the case canonical amplitude estimation's controlled Grover
  powers hit.

Multi-controlled gates are left as `ctrl @` modifiers: every vendor transpiler
lowers those to its own topology better than a generic pass would.  The gate
accounting still charges them at `16(c−1)` two-qubit gates, so the counts the
noise model sees are the counts hardware would see.

Verification is by round trip: export, parse back with the module's own reader
for the dialect it emits, simulate, compare statevectors.  Every circuit family
in the package — distribution loading, comparator, payoff rotation, Grover
operator, the full canonical phase-estimation circuit — round-trips at ~1e-15.

The 4-qubit European call with two Grover powers is 6 qubits and 1,036 gates,
928 of them two-qubit.  That number is the point of the export: it is what the
noise section's ε multiplies.

### A simulator bug this surfaced

Building the canonical phase-estimation circuit on a real state preparation
crashed.  `Circuit.control()` appended the new control to a multiplexed `Ry`
without doubling its angle table, so the operation claimed `k+1` controls and
held `2ᵏ` angles.  The existing canonical-QAE test used a trivial one-qubit
preparation and never hit it.  Fixed by doubling the table (the old angles
where the new control reads 1, zero rotation where it reads 0), checked against
the equivalent `2ᵏ` explicit multi-controlled rotations to 1e-12, and the test
now runs canonical QAE on a loaded lognormal.

## Data from outside this repository

Everything above was measured on synthetic prices and synthetic error rates.
This section replaces each with a released, citable external source and
reports what changed.  The datasets are bundled under `data/` with their
licences and provenance in [`data/README.md`](../data/README.md).

### Real prices — the optimiser beats 1/N on this history, with a caveat

Twenty US tickers of adjusted daily closes from 1989 to 2018, MIT-licensed,
taken from PyPortfolioOpt's test resources (Yahoo Finance originally).
Seventeen have complete coverage from 2006-05-25, which gives 2,990 trading
days through the 2008 crash, the 2011 and 2015 corrections and the 2018
volatility spike.  Same walk as before: 252-day fit, 21-day hold, 130
out-of-sample periods:

| strategy | ann. return | ann. vol | Sharpe | *in-sample* Sharpe | max DD | turnover | t vs 1/N |
|---|---|---|---|---|---|---|---|
| equal weight | 11.13% | 19.97% | 0.56 | 0.57 | 49.9% | 0.0% | — |
| Markowitz long-only | 17.43% | 18.73% | 0.93 | 2.06 | 36.5% | 20.8% | +1.73 |
| cardinality 4, simulated annealing | 23.32% | 22.11% | 1.06 | 2.05 | 42.4% | 19.8% | +2.14 |
| cardinality 4, exhaustive | 23.32% | 22.11% | 1.06 | 2.05 | 42.4% | 19.8% | +2.14 |

Different from the synthetic result in one respect: the cardinality
optimiser beat equal weight, and the paired t-statistic of +2.14 clears the
conventional threshold.  Unchanged in the other two: the in-sample Sharpe of
2.05 realised 1.06 (the overfit halved it), and simulated annealing matched
exhaustive search at all 130 rebalances, so once again what is being scored
is the optimum, not the solver.

The caveat is the universe.  These twenty names were picked in 2018 by
someone writing a portfolio library, and they include Apple, Amazon, Google
and Mastercard over the decade those four compounded fastest.  A momentum-
tilted optimiser holding four names out of seventeen is well placed to ride
that; it also held Sears to near zero.  The excess return is real on this
history and would not survive a universe chosen in 2006.  To run it on a
universe of your own: `python3 -m quantum backtest --csv prices.csv`, with
any wide CSV of a date column plus one adjusted-close column per ticker.

### QOBLIB — the first certified benchmark, and the solvers do not pass it

The Quantum Optimization Benchmarking Library (Koch et al., *Nature
Computational Science*, 2026) is the community's answer to unverifiable
quantum-optimisation claims: ten problem classes, instances with real data,
QUBO files ready to load, and answers proven optimal by Gurobi where the
instance is small enough.  Problem class 06 is a multi-period portfolio model
with transaction costs, short selling, borrowing costs and per-period capital
and cardinality limits, on real S&P 500 prices.  Its smallest instance —
ten names, ten periods, budget four — is 710 binary variables.

Every solver in this package had been validated against exhaustive
enumeration, which stops at about 22 variables.  This is the first test at
scale, and against an external answer.

| solver | budget | objective | proven optimum | feasible |
|---|---|---|---|---|
| simulated annealing | default (2,000 sweeps × 8 restarts) | −7,983 | −110,541 | yes |
| simulated annealing | 20,000 sweeps × 4 restarts | −19,299 | −110,541 | yes |
| simulated annealing | 100,000 sweeps × 2 restarts (345 s) | −22,926 | −110,541 | yes |
| simulated bifurcation | default | +1,100,001,085 | −110,541 | no |
| simulated bifurcation | 5,000 steps | +1,050,005,322 | −110,541 | no |
| simulated bifurcation | 20,000 steps, 64 trajectories, dt 0.1 or 0.02 | +1.1 × 10⁹ | −110,541 | no |

Simulated annealing finds feasible portfolios and captures a fifth of the
optimum's objective with fifty times the default budget, and the curve is
flattening.  Simulated bifurcation never reaches feasibility at any budget
or step size tried.  The structural reason is the
penalty wall: the QUBO encodes the two equality constraints with weight
10⁷ against an objective of order 10⁵, so the landscape is a hundred times
steeper in the constraint directions than in the ones that matter, and a
solver tuned to the objective's scale — which is what the Frobenius-norm
normalisation in simulated bifurcation does — cannot resolve the objective
at all.  This is the same lesson as the `1/c_min²` penalty finding earlier
in this document, seen from the other side: a penalty large enough to hold
the constraints is large enough to flatten the objective.

What this says about the package: the solver comparison in the section
above, where all four solvers tie on random 10-variable instances, was
never going to transfer.  A benchmark with a certified answer at 710
variables is a different test, and on it the honest answer today is that
the heuristics are far from competitive with a MIP solver.  QOBLIB's own
baseline submissions reach the optimum with Gurobi in seconds.

Three file-format facts were needed to score against the certified
optimum, none documented in the library beyond its converter script, and
all three are pinned by a test that requires the certified solution to be a
strict local minimum with every single-bit flip costing at least the
penalty weight: off-diagonal entries in the `.qs` file are symmetric (each
pair counts twice), the slack registers are ordered bit-outer and
period-inner, and the file omits the constant 10⁷ × (C² + B²) × T =
1.16 × 10¹⁰.  Under the natural upper-triangular reading the certified
solution is not a local minimum in either direction.

Reproduce: `python3 -m quantum qoblib --risk-weight l0` (proven optimal
instances: `l0`, `l1e-5`, `l1e-6`).

### Published hardware — one machine, on paper, on the smallest circuit

The noise sweep gave a threshold near ε ≈ 10⁻⁴ per gate.  Here it is run
against the error rates the vendors publish, as gathered from the sources
named in `quantum.noise.HARDWARE_PROFILES` (the primary documents were not
reachable from the environment this was written in; the figures are as
reported by the search summaries and should be checked against the data
sheets before being quoted further):

| profile | two-qubit | one-qubit | readout | abs error | classical | survival | beats classical |
|---|---|---|---|---|---|---|---|
| Quantinuum Helios (98 qubits, Nature 2026) | 7.9e-4 | 2.5e-5 | 3.3e-4 | 0.1005 | 0.0052 | 0.19 | no |
| IonQ two-qubit record (Oct 2025) | 1.0e-4 | 2.5e-5 | 3.3e-4 | 0.0041 | 0.0052 | 0.81 | yes |
| IBM Nighthawk (120 qubits, Jan 2026) | 2.2e-3 | 2.5e-4 | 1.0e-2 | 0.1030 | 0.0052 | 0.01 | no |

Same 3-qubit pricing circuit, five Grover powers, deepest circuit 2,112
gates.  The two commercial systems lose to classical Monte Carlo outright —
both sit past the cliff, at an estimate of ½.  The one profile that wins is
IonQ's 99.99% two-qubit demonstration, and it wins by 20% on a circuit that
needs five qubits when the demonstration used two.  So the position as of
2026: the best *published gate* clears the bar for the *smallest useful
circuit*; no *system* does; and the 6-qubit circuit the `price` command
runs by default is ten times deeper again.  `python3 -m quantum noise
--hardware` reruns it.

### Where else to look

Searched but not used, with the reason:

- **Qiskit Finance** — unsupported by IBM since November 2023; its
  amplitude-estimation pricing is the same construction as
  `quantum/pricing.py`.
- **IBM calibration snapshots on Zenodo** (records 18045662, 20768087) —
  real T1/T2/gate/readout histories per qubit, which would let the noise
  model use a device's actual worst pairs rather than a median; the host
  was not reachable from here.
- **QOBLIB's instance generator** ships raw daily OHLCV for ~500 S&P 500
  names over January–May 2024 — five months, too short to fit a 252-day
  window.
- **QuFinBench** — a README describing a benchmark, with no data and no
  results.

---

## Validation

```bash
python3 -m pytest tests -q        # or: python3 -m unittest discover -s tests -v
```

169 tests. The principle throughout: **every quantum routine is checked against
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
- Export — ZYZ reconstructs random unitaries; every decomposition reproduces the
  simulator's statevector; QASM round-trips on the full pricing and canonical
  QAE circuits; a quadratic cost compiles to at most `n + 3·n(n−1)/2 + 1` gates.
- Noise — the noiseless model reproduces the exact Born probability; readout
  bias is exact; heavy depolarising drives the objective to ½; trajectories
  stay normalised.
- Backtest — the 1/N period return equals the mean asset return; every weight
  vector is long-only and sums to one; simulated annealing and exhaustive search
  produce identical out-of-sample returns.
- External data — the QOBLIB certified optimum decodes as feasible and is a
  strict local minimum of the loaded QUBO with every flip costing ≥ 10⁶; the
  omitted constant equals 1.16 × 10¹⁰ on two instances; a solver result never
  beats the proven optimum; the real price file loads with a date window and
  drops rows with missing cells rather than filling them.

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
- Laforest (2015), *The Mathematics of Quantum Mechanics*, IQC University of Waterloo
- Bell (1964), *On the Einstein Podolsky Rosen Paradox*
- Clauser, Horne, Shimony & Holt (1969), *Proposed Experiment to Test Local Hidden-Variable Theories*
- Chen (2004), *Quantum Theory for the Binomial Model in Finance Theory*, arXiv:quant-ph/0112156
- DeMiguel, Garlappi & Uppal (2009), *Optimal Versus Naive Diversification: How Inefficient is the 1/N Portfolio Strategy?*
- Koch, Bernal Neira, Chen et al. (2026), *The Quantum Optimization Benchmarking Library*, Nature Computational Science 6, 653–671
- Martin (2021), *PyPortfolioOpt: portfolio optimization in Python*, JOSS 6(61), 3066
- Möttönen, Vartiainen, Bergholm & Salomaa (2004), *Transformation of quantum states using uniformly controlled rotations*
- Grover & Rudolph (2002), *Creating superpositions that correspond to efficiently integrable probability distributions*
- Dürr & Høyer (1996), *A Quantum Algorithm for Finding the Minimum*
- Gilliam, Woerner & Gonciulea (2021), *Grover Adaptive Search for Constrained Polynomial Binary Optimization*
- Boyer, Brassard, Høyer & Tapp (1998), *Tight bounds on quantum searching*
- Ledoit & Wolf (2004), *A well-conditioned estimator for large-dimensional covariance matrices*
- Hadfield et al. (2019), *From the QAOA to a Quantum Alternating Operator Ansatz*
- Lykov et al. (2023), *Fast Simulation of High-Depth QAOA Circuits* (QOKit)
- Lykov, Schutski & Alexeev (2020), *Tensor Network Quantum Simulator with Step-Dependent Parallelization* (QTensor)
- Farhi, Gamarnik & Gutmann (2020), *The QAOA Needs to See the Whole Graph* (locality)
