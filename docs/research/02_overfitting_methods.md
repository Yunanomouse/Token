# 02 — Making the indicator-duel referee statistically sound

Research date: 2026-09-30. Scope: methods and tools to estimate how much of a training result is selection luck, and to harden the pass bar
(train 29 sessions -> pick best of 20 configs -> test 20 sessions -> forward 20 sessions).

URL check legend: **[OK]** = loaded with WebFetch during this research (PDFs count as OK if the file downloaded);
**[403]** = publisher blocks automated fetch (bibliographic data confirmed through search results and other indexes).

---

## 0. What the current numbers already say

Formulas are in the sections below. These numbers come from Python/scipy calculations run during this research.

| Quantity | Value | Meaning |
|---|---|---|
| Expected max z-score of 20 independent pure-noise configs, `E[max_20]` (Bailey & López de Prado eq. 1) | **1.90** | The best of 20 useless configs shows t ≈ 1.9 on average |
| Implied best-of-20 noise daily Sharpe on 29 training sessions: 1.90/√29 | **0.35/day ≈ 5.6 annualised** | A +27% training result on 29 sessions is **what noise alone should produce** for 20 configs with moderate volatility |
| Spearman train-vs-test rank corr −0.19 over 20 configs; SE ≈ 1/√19 = 0.23; t ≈ −0.82 | not different from 0 | Training rank has **no measurable predictive power**. This is the PBO ≥ 0.5 regime |
| Daily Sharpe needed on 20 test sessions for one-sided t = 2 | 0.45/day ≈ 7.1 annualised | 20 sessions can only confirm very large edges |
| Power of a 20-session test (α = 5%) if the true annual Sharpe = 2 / 3 / 5 | 14% / 21% / 41% | The test window is **badly underpowered**: most real edges fail, and noise sometimes passes |
| P(at least one of 20 null configs beats 90% of random entries) | 1 − 0.9^20 = **88%** | A 90th-percentile gate means nothing if you apply it after choosing among 20 configs |
| Monte Carlo SE of the p-value at the 90th percentile with 40 random runs | ±0.047 | 40 runs is too coarse. Use ≥1,000 |

**Bottom line:** the train +27% / test −7.5% outcome is the expected result of picking the best of 20 on 29 sessions. The referee needs to (a) put the selection step into the null distribution and (b) use far more trades or sessions, or pool evidence across folds.

---

## 1. Deflated Sharpe Ratio (DSR) and Probabilistic Sharpe Ratio (PSR)

- **Bailey, D.H. & López de Prado, M. (2014). "The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting and Non-Normality." *Journal of Portfolio Management* 40(5), 94–107.**
  PDF: https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf **[OK]** · SSRN 2460551 **[403]**
- **Bailey & López de Prado (2012). "The Sharpe Ratio Efficient Frontier." *Journal of Risk* 15(2).** Defines PSR and MinTRL.
  https://www.davidhbailey.com/dhbpapers/sharpe-frontier.pdf (listed in https://www.davidhbailey.com/dhbpapers/ **[OK]**) · SSRN 1821643

**Key formulas** (γ = 0.5772 Euler–Mascheroni, Z = standard normal CDF, SR̂ per observation, not annualised):
```
PSR(SR*) = Z( (SR̂ − SR*)·√(T−1) / √(1 − γ3·SR̂ + (γ4−1)/4·SR̂²) )        γ3 = skew, γ4 = kurtosis (non-excess)
SR0      = √V[{SR̂_n}] · ( (1−γ)·Z⁻¹(1 − 1/N) + γ·Z⁻¹(1 − 1/(N·e)) )          expected max SR of N null trials
DSR      = PSR(SR0)
MinTRL   = 1 + (1 − γ3·SR̂ + (γ4−1)/4·SR̂²) · ( Z⁻¹(1−α) / (SR̂ − SR*) )²     observations needed
```
Paper's worked example: N=100 trials, T=1250 days, annualised SR 2.5 gives DSR ≈ 0.90, so the result is rejected at the 95% level.

**How to use it in the duel**
- Compute DSR for the chosen config on training with **N = 20** (or more; see the note below). Use per-session returns (T=29) **and** per-trade returns (T = number of trades) and report both. Use `V[{SR̂_n}]` = the cross-sectional variance of the 20 configs' training Sharpes, which is what the paper prescribes. With T=29 and noise-level variance (≈1/T), SR0 ≈ 0.35/day. DSR ≥ 0.95 then needs a training daily SR ≈ 0.67 (≈10.6 annualised). In practice no 29-session result will pass, and that is the honest conclusion.
- **N must count every trial**, including configs tried and thrown away, indicator families other contestants considered, earlier duel rounds and parameter tweaks. If the 20 configs are correlated (e.g. neighbouring lookbacks), estimate the *effective* N by clustering the configs' return series (López de Prado & Lewis's ONC method, or number of eigenvalues that explain ~95% of variance). Effective N is usually smaller than 20, which lowers SR0.
- Report DSR on the **test** window too, with N=1 (no selection there): that is plain PSR(0).

## 2. Probability of Backtest Overfitting (PBO) via CSCV

- **Bailey, D.H., Borwein, J.M., López de Prado, M. & Zhu, Q.J. (2017). "The Probability of Backtest Overfitting." *Journal of Computational Finance* 20(4), 39–69.** (working version Feb 2015)
  PDF: https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf **[OK]** · SSRN 2326253 **[403]**

**Procedure (CSCV)**
1. Build matrix M (T rows = time blocks such as sessions, N columns = configs) of per-period P&L.
2. Split rows into an even number S of contiguous blocks. For every combination of S/2 blocks (C(S,S/2) of them; S=16 gives 12,870), use it as IS and the complement as OOS.
3. Pick the IS-best config, find its relative OOS rank ω̄ ∈ (0,1), and compute the logit λ = ln(ω̄/(1−ω̄)).
4. **PBO = fraction of combinations with λ ≤ 0** (the IS winner lands below the OOS median). The paper also gives performance degradation (a regression of OOS on IS performance), probability of OOS loss, and a stochastic-dominance check. The authors suggest rejecting when PBO > 0.05.

**How to use it in the duel**
- Each contestant supplies the **full 20-config P&L matrix**, not only the winner. Run CSCV on the 29 training sessions **plus** the 20 test sessions (49 sessions, S = 8 blocks of ~6 sessions → C(8,4) = 70 splits; or S = 14 blocks of 3–4 sessions → 3,432 splits). Use session blocks so intraday autocorrelation stays inside a block.
- Gate: PBO ≤ 0.2 (practical) or ≤ 0.05 (the paper's suggestion). A rank correlation of −0.19 implies PBO ≈ 0.5–0.6, so this gate would have rejected the pick *before* the test window was spent.
- Also report the slope of OOS-vs-IS Sharpe (performance degradation) and P(OOS loss).

## 3. Minimum Backtest Length (MinBTL)

- **Bailey, Borwein, López de Prado & Zhu (2014). "Pseudo-Mathematics and Financial Charlatanism: The Effects of Backtest Overfitting on Out-of-Sample Performance." *Notices of the AMS* 61(5), 458–471.**
  PDF: https://www.davidhbailey.com/dhbpapers/backtest-pseudo.pdf **[OK]** · https://www.ams.org/notices/201405/rnoti-p458.pdf **[403]** · SSRN 2308659

**Theorem 3.1** (in years when SR is annualised):
```
MinBTL ≈ ( ((1−γ)·Z⁻¹(1−1/N) + γ·Z⁻¹(1−1/(N·e))) / E[max_N] )²  <  2·ln(N) / E[max_N]²
```
The paper's example: with 5 years of data, try no more than 45 independent configs, or you will find an in-sample annualised SR of 1 whose expected OOS SR is 0. MinBTL is a necessary, not a sufficient, condition.

**Applied to the duel (N=20, multiplier 1.90):** the minimum training length at which 20 noise configs would *not* be expected to show a given annualised SR:
- SR 1 → ≈ 910 sessions
- SR 2 → ≈ 228 sessions
- SR 3 → ≈ 101 sessions

29 sessions only keeps noise below SR ≈ 5.6. **Either cut N to 3–5 configs or lengthen training to ≥ 120–250 sessions.** With N=5 (multiplier 1.19), the length needed for SR 3 drops to ≈ 40 sessions.

## 4. False Strategy Theorem

- **López de Prado, M. & Bailey, D.H. (2021). "The False Strategy Theorem: A Financial Application of Experimental Mathematics." *American Mathematical Monthly* 128(9), 825–831.**
  https://www.tandfonline.com/doi/full/10.1080/00029890.2021.1965068 (paywalled) · open copy https://escholarship.org/uc/item/95t7k79q **[OK]** · SSRN 3221798 **[403]**
- Statement: given N skill-less strategies whose SR̂ have cross-sectional variance V, `E[max SR̂] ≈ √V·((1−γ)Z⁻¹(1−1/N) + γZ⁻¹(1−1/(Ne)))`. The maximum is right-unbounded in N, so with enough trials any Sharpe ratio can be reached, and no fixed Sharpe threshold works unless you know N.
- **Duel use:** this is the theoretical basis of the SR0 in §1. Log N for every contestant and publish it. A result reported without its trial count is not scoreable.
- Related: López de Prado & Lewis (2019), "Detection of false investment strategies using unsupervised learning methods," *Quantitative Finance* 19(9). Gives ONC clustering for estimating effective N. Copy: https://codemacher.com/wp-content/uploads/2021/02/Detection-of-false-investment-strategies-using-unsupervised-learning-methods_M.LopezDePrado_and_M.Lewis_2018.pdf (from search results, not fetched).

## 5. White's Reality Check (RC)

- **White, H. (2000). "A Reality Check for Data Snooping." *Econometrica* 68(5), 1097–1126.** https://ideas.repec.org/a/ecm/emetrp/v68y2000i5p1097-1126.html **[OK]**
- Procedure: let d_k,t = P&L of config k minus benchmark (0, or buy-and-hold/random entry). Statistic `V = max_k √T·mean(d_k)`. Get its null distribution by stationary block bootstrap (Politis–Romano 1994) of the **joint** (T × K) matrix, recentred by subtracting the sample means. p = share of bootstrap maxima ≥ V.
- **Duel use:** run it on the 20 configs over training with benchmark = 0 (flat) after costs. It answers "is the best of 20 better than nothing, after accounting for choosing it?" In `arch` this is the `SPA` class's "upper" p-value.
- Caveat: RC is conservative when there are many clearly bad configs. Prefer Hansen's SPA.

## 6. Hansen's Test for Superior Predictive Ability (SPA)

- **Hansen, P.R. (2005). "A Test for Superior Predictive Ability." *Journal of Business & Economic Statistics* 23(4), 365–380.** https://ideas.repec.org/a/bes/jnlbes/v23y2005p365-380.html **[OK]**
- Improves on RC in two ways. It uses a studentised statistic `max_k √T·d̄_k/ω̂_k`. It also recentres only models that are not clearly inferior: models with `d̄_k ≤ −ω̂_k·√(2·loglog T / T)` are dropped from the null. This gives more power and less sensitivity to junk configs. Three p-values: lower, consistent (recommended), upper (= RC).
- **Duel use:** primary gate on training, `SPA(benchmark=zeros, models=−PnL_matrix)`. `arch` works with *losses*, so pass negative P&L. Require consistent p ≤ 0.05 on training **and** a repeat on the test window with the single chosen config (with K=1 this reduces to a block-bootstrap t-test).

## 7. Romano–Wolf stepdown (StepM)

- **Romano, J.P. & Wolf, M. (2005). "Stepwise Multiple Testing as Formalized Data Snooping." *Econometrica* 73(4), 1237–1282.** https://ideas.repec.org/a/ecm/emetrp/v73y2005i4p1237-1282.html **[OK]** · PDF https://users.ssc.wisc.edu/~behansen/718/RomanoWolf2005.pdf **[OK]**
- Algorithm 3.1: sort the test statistics from largest to smallest. Reject every H_s whose statistic exceeds the bootstrap (1−α) quantile of the max over *all remaining* hypotheses. Remove the rejected ones, recompute the quantile over the rest and repeat until nothing more is rejected. It controls FWER and has more power than single-step RC. Studentised version recommended.
- **Duel use:** use it when the duel wants to know **which** configs (or which contestants' indicators) beat the benchmark, not just whether any do. For example, run it across all contestants' finalists on the forward window to decide whether the winner beats the others or flat. `arch.bootstrap.StepM`.

## 8. Harvey–Liu–Zhu t > 3 hurdle and Harvey–Liu haircut Sharpe

- **Harvey, C.R., Liu, Y. & Zhu, H. (2016). "…and the Cross-Section of Expected Returns." *Review of Financial Studies* 29(1), 5–68.** NBER w20592: https://www.nber.org/papers/w20592 **[OK]**
  With hundreds of factors tested, a new factor needs **t > 3.0**. They use Bonferroni, Holm and BHY (false-discovery-rate) adjustments and prefer BHY.
- **Harvey, C.R. & Liu, Y. (2015). "Backtesting." *Journal of Portfolio Management* (Fall 2015), pp. 13–28.** MATLAB code (Haircut_SR.m, Profit_Hurdle.m): https://people.duke.edu/~charvey/backtesting/ **[OK]**. R port: `quantstrat::SharpeRatio.haircut`.
  Haircut SR: convert SR to a p-value, adjust for N tests (Bonferroni/Holm/BHY), and convert back to a "haircut" SR. They argue the rule-of-thumb 50% haircut is wrong: the haircut is nonlinear and larger for marginal Sharpes.
- **Duel use:** with N=20, the one-sided Bonferroni hurdle is **z ≈ 2.81**, and DSR-95 needs ≈ 3.55 (1.90 + 1.645). Use **t ≥ 3 on the training per-trade P&L** (Newey–West or block-bootstrap SE) as a simple, explainable gate. Report the haircut SR next to the raw SR.

## 9. Monte Carlo permutation tests (MCPT) for trading rules

- **Aronson, D. (2006). *Evidence-Based Technical Analysis: Applying the Scientific Method and Statistical Inference to Trading Signals.* Wiley.** https://www.wiley.com/en-us/shop/general-finance-investments/evidence-based-technical-analysis-applying-the-scientific-method-and-statistical-inference-to-trading-signals-p-9781118268315 **[OK]**
  Tests 6,402 rules on the S&P 500 with White's RC and Masters' MCP method. After data-mining correction, none of the rules is significant.
- **Masters, T. (2020). *Permutation and Randomization Tests for Trading System Development: Algorithms in C++.* Independently published, ISBN 9798607808105.** https://openlibrary.org/works/OL30520499W **[OK]**
- **Procedure (Masters):** (1) Permute the **bar-to-bar log changes** (intrabar open/high/low/close offsets kept together, first bar fixed). This destroys any time-series structure while keeping the return distribution and the net drift. (2) **Re-run the whole selection process** (all 20 configs, pick the best) on each permuted series. (3) p = (1 + #{perm best ≥ real best}) / (1 + n_perm). Because the optimiser runs inside the loop, the p-value accounts for selection bias. A walk-forward variant permutes only the OOS segment. Masters also splits total gain into "skill", "training bias" and "trend" components.
- Open-source Python: **neurotrader888/mcpt** (MIT) — https://github.com/neurotrader888/mcpt **[OK]**. Includes `bar_permute.py` (multi-market OHLC bar permutation), in-sample MCPT and walk-forward MCPT (Donchian and tree examples). 425 stars; only 2 commits, so treat it as reference code and port the ~50-line permutation function.
- **Duel use (highest value):** replace the "40 random-entry runs" check with **≥1,000 permutations of the training sessions (bars permuted within each session, sessions kept separate so the overnight gap is not reshuffled) → re-run the contestant's full 20-config search → compare their best training P&L.** Gate p ≤ 0.05. Then run a single-config permutation test on the test window (no re-selection).

## 10. Random-entry baselines (current gate)

- Currently "beats 90% of 40 random-entry runs": (a) SE ≈ ±4.7 percentage points on the percentile, (b) a null config passes 10% of the time, and (c) with best-of-20 selection some config passes 88% of the time.
- **Better design:** random entries matched to the strategy on **number of trades, long/short split, holding-time distribution and time-of-day distribution** (sample entry timestamps from the same session buckets). Apply identical costs. n ≥ 1,000. Gate: strategy exceeds the **95th percentile** (p ≤ 0.05), evaluated on the **test** window. For training, use the MCPT in §9, because random entry does not simulate the selection step.
- Random-entry P&L after 0.25%/side costs is strongly negative (−0.5% per round trip). Also report the gross version so the edge is not just "trades less than random".

## 11. Walk-forward vs combinatorial purged cross-validation (CPCV), purging and embargo

- **López de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley.** https://www.wiley.com/en-us/Advances+in+Financial+Machine+Learning-p-9781119482086 **[OK]**. Ch. 7 covers purging and embargo, Ch. 11 the dangers of backtesting, Ch. 12 CPCV, Ch. 14 backtest statistics (PSR/DSR).
- **Purging:** drop training observations whose label or holding window overlaps a test window. **Embargo:** also drop a buffer *after* each test block, because serial correlation leaks. **CPCV:** split T into N groups, test on every k-subset (C(N,k) splits), which gives φ = k·C(N,k)/N full OOS backtest paths. The result is a *distribution* of OOS Sharpe instead of one walk-forward path.
- **Arian, H.R., Norouzi Mobarekeh, D. & Seco, L.A. (2024). "Backtest overfitting in the machine learning era: A comparison of out-of-sample testing methods in a synthetic controlled environment." *Knowledge-Based Systems*.** https://www.sciencedirect.com/science/article/abs/pii/S0950705124011110 **[403]**, SSRN 4686376 **[403]**. In synthetic tests, CPCV had lower PBO and better DSR statistics than walk-forward, K-fold and purged K-fold. Walk-forward showed more false discoveries and higher variance.
- **Duel use:** the duel is a single walk-forward split (train → test → forward), which has the highest variance of all these designs. Suggested approach: pool train and test (49 sessions), split into 7 groups of 7 sessions, CPCV with k=2 → 21 splits, 6 paths. Embargo **1 full session** after each test group (and purge any indicator warm-up that reads across the boundary; intraday rules flat at the close need little purging). Score the contestant's **selection procedure** (choose the best of 20 on the train folds) by the median and 10th percentile of its OOS path Sharpes. Keep the 20-session forward window as the untouched final exam.

## 12. How many trades or sessions for significance (5-minute strategy)

t = SR_per_obs·√n, where n = trades or sessions. Required n = (z_req / SR_per_obs)². Required z values: one test at 95% = 1.645; Harvey–Liu–Zhu = 3.0; DSR-95 with N=20 independent configs ≈ 3.55.

| Per-trade net Sharpe (mean/sd per trade) | n for z=1.645 | n for t=3 | n for DSR-95, N=20 |
|---|---|---|---|
| 0.05 | 1,083 | 3,600 | 5,029 |
| 0.10 | 271 | 900 | 1,258 |
| 0.15 | 121 | 400 | 559 |
| 0.20 | 68 | 225 | 315 |
| 0.30 | 31 | 100 | 140 |

| Annualised Sharpe (per-session P&L) | sessions, z=1.645 | sessions, t=3 | sessions, DSR-95 N=20 |
|---|---|---|---|
| 1 | 682 | 2,269 | 3,168 |
| 2 | 171 | 568 | 792 |
| 3 | 76 | 253 | 352 |
| 5 | 28 | 91 | 127 |

Interpretation for 5-minute bars:
- The ≥30-trade rule is only enough if the per-trade Sharpe is ≥ 0.3, which is rare for a single indicator after costs. Realistic intraday per-trade Sharpes are 0.05–0.15. The test window then needs **≈ 300–1,300 trades** (if trades are close to independent), or the verdict should be "inconclusive".
- **0.25%/side = 0.50% per round trip.** For many liquid instruments this is larger than a typical 5-minute return's standard deviation. A rule holding 1–6 bars must predict moves of several σ just to break even, so most 5-minute rules will fail on costs whatever the statistics say. Report the break-even cost per side for each finalist.
- Trades within one session are correlated (same regime). Use the **session** as the unit, or cluster by session with a block bootstrap. Then the second table applies: with 20 test sessions only edges of annualised SR ≥ 5–6 can reach significance.
- Requiring profitability in "both test halves" (10 sessions each) mostly adds noise. For SR 3 annual, P(10-session mean > 0) ≈ Z(0.19·√10) ≈ 0.73 per half, so a real edge fails the both-halves check about 47% of the time. Replace it with a CPCV path-consistency criterion (e.g. ≥ 5 of 6 paths positive, or 10th-percentile path SR > 0).
- Also see Lo, A.W. (2002). "The Statistics of Sharpe Ratios." *Financial Analysts Journal* 58(4), 36–52. https://traders.studentorg.berkeley.edu/papers/The-Statistics-of-Sharpe-Ratios.pdf **[OK]**. IID SE(SR̂) ≈ √((1 + SR̂²/2)/T). Serial correlation changes the √q annualisation, so do not annualise 5-minute Sharpe by √(bars/year) without a correction.

---

## 13. Open-source implementations

| Tool | What it provides | Licence | Status (checked 2026-09-30) | URL |
|---|---|---|---|---|
| **arch** (Kevin Sheppard) | `SPA` (Hansen SPA; "upper" p = White RC), `StepM` (Romano–Wolf), `MCS` (Hansen–Lunde–Nason); `StationaryBootstrap`, `CircularBlockBootstrap`, `optimal_block_length` | NCSA (per PyPI; GitHub page shows a LICENSE.md) | **Active**: v8.0.0 released 2025-10-21, Python ≥3.10 | https://github.com/bashtage/arch **[OK]** · docs https://arch.readthedocs.io/en/latest/multiple-comparison/multiple-comparison_examples.html **[OK]** |
| **pypbo** (esvhd) | PBO/CSCV, performance degradation, P(OOS loss), stochastic dominance, PSR, DSR, MinTRL | **AGPL-3.0** (copyleft; watch this if the project is closed) | Last commit 2026-07-06 (bug-fix PR); not on PyPI, install from GitHub | https://github.com/esvhd/pypbo **[OK]** |
| **skfolio** | `CombinatorialPurgedCV(n_folds, n_test_folds, purged_size, embargo_size)`, `WalkForward`, `optimal_folds_number` | BSD-3-Clause | **Very active**: v1.4.9, 2026-09-29 | https://skfolio.org/generated/skfolio.model_selection.CombinatorialPurgedCV.html **[OK]** |
| **purgedcv** (eslazarev) | Purged K-fold, embargo, walk-forward, CPCV, PSR, DSR; sklearn-compatible | MIT | Active: v0.1.8, 2026-09-26; small (35 stars) | https://github.com/eslazarev/purged-cross-validation **[OK]** · https://pypi.org/project/purgedcv/ **[OK]** |
| **neurotrader888/mcpt** | Masters-style OHLC bar permutation, in-sample and walk-forward MCPT | MIT | Reference code, 2 commits, 425 stars | https://github.com/neurotrader888/mcpt **[OK]** |
| **iqueipopg/backtest-overfitting** | PSR, DSR, E[max SR], MinTRL/MinBTL, PBO/CSCV, effective-N via participation ratio and clustering | MIT | Small (4 commits), complete | https://github.com/iqueipopg/backtest-overfitting **[OK]** |
| **DaruFinance/lopez-de-prado-work-review** | Large-scale reproductions of DSR, PBO, CPCV on crypto/equities/FX. Finding: "almost nothing clears deflated significance" | MIT | 18 commits; research code | https://github.com/DaruFinance/lopez-de-prado-work-review **[OK]** |
| **timeseriescv** | `PurgedWalkForwardCV`, `CombPurgedKFoldCV` | MIT | **Stale**: v0.2 from 2018-09 | https://github.com/sam31415/timeseriescv **[OK]** |
| **mlfinpy** | Open port of parts of mlfinlab (AFML) | MIT | v0.1.2, 2024-10; low activity | PyPI `mlfinpy` (metadata checked through the PyPI JSON API) |
| **mlfinlab** (Hudson & Thames) | Original AFML implementations (CPCV, PBO, DSR) | **Proprietary, all rights reserved**; commercial licence | The public repo is only an issue tracker; not usable as open source | https://github.com/hudson-and-thames/mlfinlab **[OK]** |
| **R `pbo`** | PBO, degradation, P(loss), stochastic dominance | MIT | v1.3.5, 2022-05 (stable) | https://cran.r-project.org/package=pbo **[OK]** |
| **Harvey–Liu MATLAB** | Haircut Sharpe, profit hurdle (Bonferroni/Holm/BHY) | Academic code, no explicit licence | Static | https://people.duke.edu/~charvey/backtesting/ **[OK]** |
| BacktestAudit (Leo-Y-Zhang) | PSR/DSR/PBO "default-deny" verdict | **Proprietary** | New, 0 stars | https://github.com/Leo-Y-Zhang/BacktestAudit **[OK]**. Do not use (licence) |

Recommended stack: **arch** (SPA/StepM/bootstrap) + **skfolio** or **purgedcv** (CPCV with embargo) + about 60 lines of own code for DSR, CSCV-PBO and bar-permutation MCPT. The formulas are short, and writing them avoids pypbo's AGPL.

---

## 14. Proposed referee protocol (drop-in)

1. **Trial registry:** each contestant declares N (all configs tried, including discarded ones) and submits the full T×N P&L matrix. Cap N at 5–10 per contestant, or require training to scale with MinBTL.
2. **Training-stage gates (selection-aware):**
   - Hansen SPA consistent p ≤ 0.05 (arch, stationary bootstrap, block ≈ 1 session of bars, 5,000 reps)
   - DSR ≥ 0.95 with the declared N
   - MCPT (≥1,000 within-session bar permutations with the full re-optimisation) p ≤ 0.05
   - PBO (CSCV on session blocks) ≤ 0.2
3. **Test stage (no selection):**
   - PSR(0) ≥ 0.95 on session P&L after 0.25%/side costs
   - Beats the 95th percentile of ≥1,000 **matched** random-entry runs
   - Replace "both halves profitable" with a CPCV path-consistency check
   - Minimum trade count derived from §12 (≥ ~300), not 30. If it is not reached, the verdict is "inconclusive", not a pass or fail
4. **Forward window:** decide the winner between contestants with Romano–Wolf StepM or pairwise block-bootstrap on the P&L difference. Declare a tie unless p ≤ 0.10.
5. **Always report:** raw vs deflated/haircut SR, break-even cost per side, effective N, PBO, the number of sessions a true SR of 2 would need (MinTRL), and the power of the test window.

---

## Five highest-value changes

1. **Put the selection step inside the null.** Run a Masters-style MCPT: ≥1,000 within-session bar permutations, re-run all 20 configs on each and compare best to best. Use Hansen SPA (`arch.bootstrap.SPA`) on the 20-config P&L matrix alongside it. This directly measures the selection luck behind the +27% training result.
2. **Deflate using the true trial count.** Require DSR ≥ 0.95 with N = all configs tried, using effective N if they are correlated. Report the Harvey–Liu haircut SR. With N=20 the hurdle is z ≈ 3.5 instead of 1.65. Cut N per contestant to ≤ 5, or lengthen training toward MinBTL (≈ 100–230 sessions for SR 2–3).
3. **Compute PBO with CSCV** on the 20-config matrix over session blocks before spending the test window. Reject if PBO > 0.2. The observed rank correlation of −0.19 implies PBO ≈ 0.5+, so this would have caught the failed pick.
4. **Fix the sample-size and random-baseline rules.** Replace ≥30 trades with a power-based minimum (≈ 300–1,300 trades, or session-clustered equivalents), and label under-powered results "inconclusive". Replace 40 random-entry runs at the 90th percentile with ≥1,000 matched runs (same trade count, holding times and time of day) at the 95th percentile.
5. **Replace the single train/test/halves split with CPCV plus embargo** (skfolio `CombinatorialPurgedCV`, 1-session embargo) over the pooled 49 sessions. Score the median and 10th-percentile path Sharpe instead of "both halves profitable". Keep the forward window untouched and decide the winner there with Romano–Wolf StepM or a bootstrap P&L-difference test.
