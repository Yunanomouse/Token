# Token

Two independent workstreams live in this repository:

1. **[Quantum methods for trading](#quantum-methods-for-trading)** — `quantum/`
2. **[Canada tax system data (2026)](#canada-tax-system-data-2026)** — `data/`, `docs/`, `examples/`

---

# Quantum methods for trading

A working, tested implementation of the four applications where quantum
mechanics has a defensible role in finance — with the classical baseline printed
beside every result.

```bash
python3 -m quantum demo                 # everything, end to end
python3 -m quantum portfolio --cardinality 4 --solver simulated_bifurcation
python3 -m quantum price --spot 100 --strike 105 --volatility 0.2
python3 -m quantum risk --confidence 0.95
python3 -m quantum arbitrage --fee 0.0005
python3 -m quantum benchmark --vars 10 --trials 10
```

Requires **numpy only**. No Qiskit, no Cirq, no cloud account — the statevector
simulator, Grover operator and amplitude estimation are implemented from the
postulates up in `quantum/statevector.py` and `quantum/amplitude.py`.

## What it does

| Module | Application | Status today |
|---|---|---|
| `quantum/portfolio.py` | Cardinality, lot-size and sector-cap constrained optimisation → QUBO | Strongest case |
| `quantum/risk.py` | VaR / CVaR by amplitude estimation | Proven theory, hardware-limited |
| `quantum/pricing.py` | European and multi-asset basket options | Same |
| `quantum/arbitrage.py` | Cyclic arbitrage as an Ising ground state | Deployable now, quantum-*inspired* |

Four solvers consume the same `QUBO`: `exact` (proves the optimum below ~22
variables), `simulated_annealing`, `simulated_bifurcation` (the Toshiba SQBM+
algorithm — quantum-derived, runs on classical silicon), and `qaoa` on the
built-in simulator.

## Verified results

- **Portfolio** — all four solvers match the `C(n,K)`-exhaustive proven optimum.
- **Amplitude estimation** — the Grover rotation law `P = sin²((2k+1)θ)` holds
  exactly; MLAE reaches 1.3×10⁻⁴ error where classical Monte Carlo at the same
  shot count gives 9.5×10⁻³.
- **Pricing** — within **0.03%** of Black–Scholes; put-call parity exact.
- **Risk** — VaR matches the exact quantile at 90/95/99% confidence.
- **Arbitrage** — no false positives on an arbitrage-free market; planted
  mispricings recovered; opportunities correctly vanish once fees are applied.

105 tests: `python3 -m unittest discover -s tests -v`

## Memory

Simulating `n` qubits costs `2ⁿ` amplitudes and nothing changes that — but a
large avoidable constant sat on top. Profiling found three hotspots; all are
measured, and no numerical result changed.

| Hotspot | Before | After | Gain |
|---|---|---|---|
| `energies_all` (n=16) | 18.9 MB | 1.05 MB | **18×**, 42× faster |
| Statevector, `complex64` (n=20) | 50 MB | 17 MB | **3×** |
| Distribution loading (n=12) | 4095 ops | 12 ops | **11×**, 30× faster |

The one that changes the asymptotics is **constraint-preserving subspaces**. A
cardinality mandate is normally a soft penalty; an XY mixer started from a Dicke
state simply cannot leave the feasible set, so the register carries only the
`C(n,K)` valid portfolios:

| n | K | full 2ⁿ | C(n,K) | saving |
|---|---|---|---|---|
| 20 | 5 | 1,048,576 | 15,504 | 68× |
| 32 | 4 | 4,294,967,296 | 35,960 | **119,437×** |

Verified exact against a full-register simulation to `1.3×10⁻¹⁵` with zero
leakage, and *more* accurate than the penalty formulation — 25/25 proven optima
against 18/25 at K=5.

Two well-known techniques were measured and rejected: **light cones** need a
sparse coupling graph, and **MPS** loses below ~24 qubits and saturates its bond
dimension on dense couplings. The light-cone case, and `quantum/locality.py`
ships the measurement that shows why: a covariance matrix couples every asset to
every other, so the coupling graph is complete (density 0.92–1.00) and the
radius-1 cone is already the whole problem.

`python3 -m quantum memory` prints every limit for your own configuration.

## What it will not do

Predict prices, generate signals, or make money on a day trade. Nothing here
runs faster than its classical equivalent on current hardware, and the module
docstrings say exactly where each limit bites — the `O(2ⁿ)` input problem,
circuit depth, and the ~six-order-of-magnitude latency gap that rules gate-based
hardware out of high-frequency execution.

Three findings from building it that are easy to get wrong:

- **Penalty weights must scale as `1/c_min²`** against the constraint's own
  coefficients. With portfolio weights near 0.05, the naive choice
  under-penalises by ~400× and the solver silently ignores its budget.
- **Option-price convergence is limited by domain truncation, not resolution.**
  At `n_sigma=3` the error plateaus at ~0.10 from 5 qubits to 8; at `n_sigma=5`
  the same sweep converges to 5×10⁻⁴.
- **The payoff linearisation bias is systematic and scales as `c²`**, so more
  shots cannot remove it — but Richardson extrapolation cancels it exactly
  (335× improvement at `c=0.25`).

Full write-up, including the two solver bugs found by testing against proven
optima: **[docs/quantum_trading.md](docs/quantum_trading.md)**.
Worked walkthrough: `python3 examples/quantum_trading_demo.py`.

---

# Canada Tax System Data (2026)

Machine-readable dataset of Canada's tax system for the **2026 tax year**: personal income tax for all 14 jurisdictions (federal + 10 provinces + 3 territories), payroll contributions, sales taxes, corporate income tax, and key credits/limits.

## Contents

| File | What it covers |
|---|---|
| `data/json/personal_income_tax_2026.json` | Federal + provincial/territorial brackets, rates, basic personal amounts, Ontario surtax & health premium, indexation factors |
| `data/json/payroll_contributions_2026.json` | CPP/CPP2, QPP/QPP2, EI (federal & Quebec), QPIP rates and maximums |
| `data/json/sales_tax_2026.json` | GST, HST, PST/RST/QST rates by province |
| `data/json/corporate_income_tax_2026.json` | Federal + provincial general and small-business rates and limits |
| `data/json/credits_and_limits_2026.json` | TFSA/RRSP/FHSA limits, OAS clawback, capital gains inclusion, Quebec abatement |
| `data/csv/*.csv` | Flat CSV exports of the above, generated by `scripts/generate_csv.py` |
| `examples/income_tax_calculator.py` | Working demo: estimates total 2026 tax + payroll deductions for any income and province |
| `examples/trader_scenario_comparison.py` | Compares sole-proprietor / max-RRSP / CCPC outcomes for full-time trading income |
| `docs/trader_taxation.md` | How Canada taxes active ("scalp") trading and the legitimate levers to reduce it |
| `docs/incorporation_checklist.md` | Step-by-step checklist for moving personal trading into a corporate brokerage account |

## Quick start

```bash
# Estimate taxes for $90,000 in Ontario
python3 examples/income_tax_calculator.py 90000 ON

# Regenerate the CSVs after editing the JSON
python3 scripts/generate_csv.py
```

All JSON files are plain UTF-8 with no dependencies; rates are decimals (0.14 = 14%), amounts are CAD, and bracket `up_to: null` means no upper bound.

## Data provenance

Collected 2026-08-18. The execution environment could not reach canada.ca or provincial government sites directly, so figures were gathered via web search from tax-reference publishers (TaxTips.ca, KPMG/EY/BDO tax tables, Wealthsimple, provincial budget analyses, CRA announcements as reported) and **cross-verified two ways**:

1. Independent confirmation of headline figures across multiple sources.
2. Arithmetic check against known 2025 statutory values × each jurisdiction's confirmed 2026 indexation factor (federal 2.0%, BC 2.2%, ON 1.9%, QC 2.05%, NS 1.6%, MB 1.2%, NL 1.1%, PE 1.8%, most others 2.0%).

Fields that could only be computed (not independently confirmed) are flagged in per-jurisdiction `notes`, e.g. some upper-bracket thresholds and several provincial BPAs. PEI's 2026 BPA is left `null` rather than guessed. Nunavut's middle threshold differs by $1 between sources ($111,601 vs $111,602).

### Notable 2025–2026 changes captured

- Federal bottom rate cut to **14%** (first full year in 2026)
- Alberta's new **8% bracket** on the first $61,200
- BC's bottom rate raised to **5.6%** (Budget 2026); BC indexation paused 2027–2030
- Nova Scotia HST cut to **14%** (April 2025)
- CPP YMPE **$74,600** / YAMPE **$85,000**; QPP first-tier rate reduced to **6.30%**
- EI employee rate **1.63%** on MIE of $68,900 (Quebec 1.30%)
- ON & QC small-business corporate rates dropping 3.2% → 2.2% (mid-2026 effective dates)
- Capital gains inclusion rate remains **50%** (2024 proposal cancelled); consumer carbon price ended April 2025

## Canonical sources (verify before filing)

- CRA — [current-year tax rates and brackets](https://www.canada.ca/en/revenue-agency/services/tax/individuals/tax-rates-brackets/current-year.html)
- CRA — [CPP contribution rates, maximums and exemptions](https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/payroll/payroll-deductions-contributions/canada-pension-plan-cpp/cpp-contribution-rates-maximums-exemptions.html)
- ESDC — [EI premium rates](https://www.canada.ca/en/employment-social-development/programs/ei/ei-list/reports/premium-rates.html)
- CRA — [GST/HST rates](https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/gst-hst-businesses/charge-collect-which-rate.html)
- [Revenu Québec](https://www.revenuquebec.ca/en/) (Quebec income tax, QPP, QPIP)
- [TaxTips.ca](https://www.taxtips.ca/marginal-tax-rates-in-canada.htm) (comprehensive independent reference)

## Disclaimer

This dataset is for information and software-development purposes only and is **not tax advice**. Tax law changes through the year via federal and provincial budgets. Verify against CRA / Revenu Québec / provincial finance departments before relying on any figure for filing or payroll.
