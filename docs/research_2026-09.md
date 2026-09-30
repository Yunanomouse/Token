# Research study, September 2026

Five research tracks, run 2026-09-30, on what would most help this project:
brokers, the strategy's evidence, price data, running the bot safely, and
where quantum finance actually stands.

**How far to trust it.** The research environment blocked most official
websites (broker, regulator, CRA, NYSE, arXiv, Nature). Many claims rest on
search-engine summaries of the cited page rather than the page itself; those
are marked *(summary)*. Items nobody could confirm are marked *(unverified)*.
GitHub, PyPI and the GitHub docs source were read directly. Check anything
money depends on against the linked page before acting.

---

## The ten things that matter most

1. **Questrade has fractional shares (since April 2025) and $0 commissions
   on US stocks (since February 2025).** The $40 bot's whole-share limit and
   its switch to cheap stocks were built on the opposite assumption. With
   fractional shares the $40 bot could run the original, tested 8 stocks.
   *(summary: questrade.com fractional-shares and pricing pages)*
2. **Currency conversion is the biggest cost, not commissions.** Questrade
   charges about 1.5% to convert CAD to USD. Converting on every trade could
   cost 18-36% a year on a monthly-rebalanced $40 account. Holding US
   dollars in the account (convert once when depositing) removes nearly all
   of it.
3. **Questrade's API still cannot place orders for personal programs**
   ("partner developers only"). Placing the bot's orders by hand stays
   necessary there. *(summary: questrade.com/api)*
4. **Interactive Brokers Canada is the only mainstream Canadian option with
   a real retail trading API.** About US$0.35-1.00 per order, fractional US
   shares, no inactivity fee. Unattended use needs an always-on home PC with
   a phone approval about once a week; GitHub-only operation relies on an
   officially unsupported login method.
5. **Both of the bot's free price sources are failing from cloud servers in
   2026.** Stooq has required a captcha-issued key since about April 2026;
   Yahoo returns HTTP 429 to cloud IPs (reports dated 2026-09-24 and 09-27).
   Official keyed APIs (Financial Modeling Prep, Twelve Data) are the fix.
6. **Committing vendor price data to a public repo is almost certainly
   against the vendors' terms**, and a public repo also publishes a real
   account's holdings permanently (forks keep history even if the repo is
   later made private).
7. **The schedule shifts in November.** The bot's cron is in UTC; from
   2026-11-01 it runs 30 minutes after the close instead of 90. GitHub now
   supports `timezone: "America/New_York"` on schedules.
8. **No track record will separate this strategy from equal weight in any
   useful time.** Even a genuinely good strategy (Sharpe 0.5) needs about 11
   years of results to show skill; beating equal weight at the backtest's
   margin would take decades. Judge it against equal weight with a stop rule
   set in advance.
9. **The evidence favours dropping the expected-return estimate.** A
   12-month sample mean is the least reliable input; minimum-variance or a
   shrunk mean, with a Ledoit-Wolf covariance, is what the literature
   supports.
10. **No bank has shown quantum advantage on a real finance task.** The
    project's QOBLIB failure is the problem's QUBO encoding, not the solver:
    classical local search in the problem's own variables now beats the
    Gurobi reference on some instances.

---

## 1. Brokers a Canadian can drive from their own program

| Broker | Trading API for personal use | Fractional US shares | ~US$20 order cost | Runs unattended? |
|---|---|---|---|---|
| Questrade | No (partner-only) | Yes, since Apr 2025 | $0 commission; 1.5% FX if paid in CAD, $0 from USD | No |
| Interactive Brokers Canada | Yes | Yes (since Aug 2023) | ~US$0.35-1.00; FX US$2 minimum per conversion | Home PC + weekly phone 2FA; OAuth route unofficial |
| Moomoo Canada | Likely (SDK lists "Moomoo CA") | Yes (US) | ~US$1.99 minimum (~10% of $20) | Needs its OpenD program logged in |
| Webull Canada | Not directly; possibly via SnapTrade | *(unverified)* | *(unverified)* | Via SnapTrade only |
| Wealthsimple | No (unofficial library is read-only) | Yes | $0; ~1.5% FX | No |
| Alpaca | Not for Canadian live accounts; paper only | — | — | — |

Details and sources:

- **Questrade** API: order placement "only available for partner
  developers". https://www.questrade.com/api/documentation/authorization
  *(summary)*. SnapTrade's Questrade connection is also read-only.
  https://snaptrade.com/brokerage-integrations/questrade-api *(summary)*.
  Fractional shares: https://www.questrade.com/learning/investment-concepts/fractional-shares/understanding-fractional-shares
  *(summary)*; some Canadian ETFs added July 2026 (moneyengineer.ca,
  2026-07-10). Commissions and FX: https://www.questrade.com/pricing/self-directed-commissions-plans-fees/
  *(summary)*. Norbert's gambit is not worth it below roughly US$1,000.
- **IBKR Canada**: no minimum; IBKR Lite not offered in Canada; Fixed pricing
  US$0.005/share, US$1 minimum, capped at 1% of trade value (sources
  disagree on whether the cap applies to tiny orders).
  https://www.interactivebrokers.ca/en/pricing/commissions-stocks.php
  *(summary)*. Inactivity fee abolished 2021. API routes:
  - TWS / IB Gateway: 2FA needed once a week after Sunday 01:00 ET; the IBC
    tool automates the rest. https://github.com/IbcAlpha/IBC/blob/master/userguide.md (read directly)
  - Client Portal Gateway: re-authenticate daily; official route for
    retail. IBKR's Web API docs *(summary)*.
  - OAuth 1.0a: officially institutional, but individuals report it works
    and it needs no interactive 2FA.
    https://github.com/Voyz/ibind/blob/master/docs/oauth/oauth_1a.md (read directly)
  - Paper account available.
- **Moomoo CA**: `futu-api` on PyPI defines `SecurityFirm.FUTUCA = "Moomoo CA"`
  (read directly). Fees: US$0.99 commission minimum + US$1.00 platform fee
  minimum. https://www.moomoo.com/ca/support/topic10_122 *(summary)*.
- **TradingView**: Questrade is on its trading panel
  (https://www.tradingview.com/blog/en/questrade-on-tradingview-44778).
  TradingView alerts cannot place Questrade orders (no retail API behind
  them). Its terms are believed to prohibit automated access to the site
  *(unverified; tradingview.com was blocked)*, which is one more reason the
  order helper only fills the ticket and never clicks Buy/Sell.

**What this means here:** keep placing orders by hand at Questrade from a
USD balance; IBKR is the only realistic path to full automation, at the
cost of a weekly phone approval on a home computer.

## 2. What the evidence says about the strategy

- **Concentration.** Most individual stocks underperform Treasury bills over
  their lifetimes; the best 4% of US listed companies created all the net
  gain since 1926. Bessembinder (2018), *JFE* 129(3):440-457,
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2900447. With
  positively skewed returns, a 1-2 stock pick trails the index more often
  than not (Heaton, Polson & Witte 2017). Holding 2 of 8 roughly doubles
  single-stock risk compared with holding all 8.
- **Mean-variance out of sample.** None of 14 optimisers consistently beat
  1/N; sample mean-variance needs thousands of months of data to win.
  DeMiguel, Garlappi & Uppal (2009), *RFS* 22(5):1915-1953. Errors in
  expected returns cost about 10x more than errors in variances (Chopra &
  Ziemba 1993). No evidence was found that picking 2 of 8 with a sample-mean
  objective adds value out of sample, consistent with this project's own
  16.9% vs 17.3% result.
- **Cheap share price** is not an edge; the documented low-price effect is
  in microcaps, and investors overestimate the upside of low-priced stocks
  (Birru & Wang 2016, *JFE* 119:578-598; Kumar 2009).
- **Honest evaluation** (Bailey & López de Prado). Minimum track record
  length, one-sided 95%, Sharpe 0 as the bar:

  | True annual Sharpe | Years of results needed |
  |---|---|
  | 0.5 | about 11 |
  | 1.0 | about 3 |

  To show it beats equal weight: about (1.645 / information ratio)² years,
  which is 11 years at IR 0.5 and 271 years at IR 0.1. The formulas for the
  probabilistic and deflated Sharpe ratio, minimum backtest length and the
  probability of backtest overfitting are in Bailey & López de Prado
  (2012, 2014) and Bailey, Borwein, López de Prado & Zhu (2014, 2017).
- **Costs.** Spreads on these liquid $5-20 names are about one cent. The
  SEC's half-cent tick for tick-constrained stocks takes effect in November
  2026 *(summary: sec.gov tick-size guide)*. The closing auction is the
  deepest point of the day; a limit 1% above the prior close will usually
  fill, and the misses are the stocks that ran up (adverse selection,
  Linnainmaa 2010). Log fill rates rather than assume them.
- **ADR costs** (NOK, VALE, ITUB): depositary fees of 1-5 cents per share a
  year; Brazil has withheld 10% on dividends to non-residents since
  2026-01-01 *(summary: BDO)*.

## 3. Canadian tax points (not tax advice)

- Capital gains inclusion rate is still **50%**; the increase was cancelled
  on 2025-03-21. https://www.pm.gc.ca/en/news/news-releases/2025/03/21/prime-minister-mark-carney-cancels-proposed-capital-gains-tax-increase
- **TFSA**: US dividends lose 15% (unrecoverable). A TFSA found to be
  "carrying on a business" is taxable and the holder is jointly liable
  (ITA s.146.2(6), (6.1); *Ahamed v The King* 2023 TCC 17, affirmed 2024 FCA
  108). Monthly rebalancing of two positions is low-frequency, but it is a
  facts-and-circumstances test.
- **RRSP**: US dividends are not withheld (treaty Article XXI); ADR
  dividends from Brazil or Finland still are.
- **Superficial loss** (taxable accounts): selling at a loss and rebuying
  within 30 days denies the loss. The bot's monthly re-picks can trigger it.
- 2026 TFSA limit: $7,000; cumulative room since 2009: $109,000 *(summary)*.
- Keep a W-8BEN on file with the broker for the 15% treaty rate.

## 4. Price data

- **Stooq** needs an API key (captcha) since about April 2026, and returns
  errors as normal-looking pages: https://github.com/pydata/pandas-datareader/issues/1012
  (read directly). No TSX coverage.
- **Yahoo** blocks cloud servers with HTTP 429 as of September 2026:
  https://github.com/TauricResearch/TradingAgents/issues/1425 (read
  directly). yfinance is still patched often (latest 1.7.0, 2026-08-26).
- **Free keyed alternatives** (limits from vendor pages, *summary*):

  | Source | Free limit | Adjusted | TSX | Public display allowed |
  |---|---|---|---|---|
  | Financial Modeling Prep | 250 calls/day, ~5 years | Yes (dividend-adjusted endpoint) | Paid | No |
  | Twelve Data | 800 credits/day, 8/min | `adjust=all` (default is splits only) | Paid (~$29/mo) | No |
  | Massive (was Polygon) | 5/min, 2 years | Splits only | No | No |
  | EODHD | 20/day free; $19.99/mo | Yes (CRSP method) | Yes | No |
  | Tiingo | 1,000/day | Yes | No | **Free tier forbids storing data** |
  | Alpha Vantage | 25/day, 100 bars | Premium | Yes | No |
  | Alpaca (Canadians) | IEX feed only | — | No | Not a consolidated close |

- **Recommendation:** Financial Modeling Prep as primary and Twelve Data as
  fallback (both free, keys in GitHub secrets); keep yfinance as a
  last-resort third source; stop committing raw prices to a public repo.
- **Never splice adjusted series from two vendors**: they adjust dividends
  differently, and adjusted history rewrites itself after each dividend.
  Store raw closes plus dividend and split events, or re-download the whole
  window when an event appears.
- **Market holidays** (from `exchange_calendars` 4.13.2, matches the NYSE
  calendar): closed 2026-11-26 and 12-25; 1 pm closes 2026-11-27 and 12-24.
  2027 closed: 01-01, 01-18, 02-15, 03-26, 05-31, 06-18, 07-05, 09-06,
  11-25, 12-24; 1 pm close 11-26.

## 5. Running the bot safely on GitHub

Source for GitHub facts: the GitHub docs source (github.com/github/docs,
read directly 2026-09-30).

- Schedules run only from the default branch, can be late or dropped at
  busy times, and in a public repo are **switched off after 60 days with no
  repository activity, without an email**. Whether the bot's own commits
  count as activity is undocumented. A third-party "keepalive" action was
  itself disabled by GitHub for a terms violation.
- Failure emails go to whoever last edited the schedule line, and only if
  Actions notifications are on (profile Settings > Notifications > Actions >
  Email, "Only notify for failed workflows"). A disabled schedule sends
  nothing, so the dashboard should flag a report older than one trading day.
- GitHub's terms say hosted Actions should be used for the project's
  software, not unrelated activity; a daily trading run is a grey area.
  Keep a way to run the bot locally.
- Before any broker key goes in: least-privilege `permissions`, actions
  pinned to commit SHAs, keys in an Environment limited to the main branch,
  never `pull_request_target`, a `TRADING_ENABLED` switch, hard limits per
  order and per day, deterministic order IDs, and reconciliation with the
  broker before trading.
- **Regulation.** No CIRO rule found that stops an individual automating
  their own account through their dealer's API *(summary)*. The US "pattern
  day trader" rule was replaced by intraday margin standards effective
  2026-06-04 (FINRA Notice 26-10, *summary*); irrelevant to a bot that
  trades once a day after the close.

## 6. Quantum finance, 2024-2026

- **Claims and critiques.**
  - HSBC + IBM bond-trading "34% better" (Sep 2025, arXiv 2509.17715): the
    gain appeared only with hardware noise; publicly criticised (Aaronson,
    https://scottaaronson.blog/?p=9170).
  - JPMorgan + Quantinuum certified randomness (Nature, Mar 2025): real, but
    not a finance computation.
  - JPMorgan portfolio selection on the 98-qubit Helios (arXiv 2607.01037,
    Jul 2026): plain QAOA failed; the hybrid helped; no claim of beating
    classical methods.
  - Kipu Quantum "runtime advantage": disputed (arXiv 2510.06337).
  - D-Wave's hybrid portfolio solver matches Gurobi, but the quantum part is
    about 0.7% of the run time (arXiv 2605.17623).
  - An independent 250-instance benchmark found "only very limited room for
    a potential quantum advantage" (arXiv 2509.17876).
- **Quantum-inspired methods are the only ones in production**: Toshiba's
  simulated bifurcation (the same family as this project's SB solver) runs
  SMBC equity indices (May 2026).
- **Option-pricing advantage** needs about 4,700-8,000 logical qubits and
  about 10⁹ T gates at tens of MHz (Chakrabarti et al. 2021; Stamatopoulos &
  Zeng 2024). Roadmaps promise about 100-500 logical qubits by 2029 (IBM
  Starling, Quantinuum Apollo). Realistically the 2030s.
- **Hardware figures in this project:**
  - Quantinuum Helios 7.9e-4: correct (99.921% two-qubit fidelity).
  - IonQ 1e-4: correct but a lab prototype, not a commercial system.
  - "IBM Nighthawk 2.2e-3" is really **Heron r3**; Nighthawk's median is
    about 2.8e-3 *(summary)*.
- **QOBLIB.** The portfolio instances are multi-period with long/short
  positions and slack registers, not a single-period cardinality QUBO. Open
  pull requests: #44 proves optimality for all 160 small instances by
  dynamic programming; #64's classical local search beats the Gurobi
  reference on 8 a050 instances. The failure of penalty-QUBO heuristics is
  an encoding problem.
- **Free solvers worth adding:** `dwave-samplers` (SA, tabu, simulated
  quantum annealing), PySA (parallel tempering), the `simulated-bifurcation`
  package as a cross-check, PySCIPOpt for exact small instances. HiGHS
  cannot solve non-convex MIQP directly.

---

## Recommended next steps, in order

For the owner (decisions, no code):

1. Keep US dollars in the Questrade account and place the bot's orders from
   that balance, so no trade pays the 1.5% conversion.
2. Decide whether the $40 bot should switch to **fractional shares of the
   original 8 tested stocks** now that Questrade supports them.
3. Decide whether the bot's real-money records should stay in a public repo.
4. Merge PR #4 so the daily schedule starts, and turn on GitHub's failure
   emails for Actions.

For Claude (code, each small and testable). Done 2026-09-30: 5, 6 (except
moving prices out of the public repo, an owner decision), 7 and 9; 8 and 10
still open (8 needs 2019-2026 price data this environment cannot download):

5. Pin the schedule to New York time (`timezone: "America/New_York"`, off
   the hour) before 2026-11-01.
6. Move price fetching to Financial Modeling Prep + Twelve Data with keys in
   secrets; validate response bodies; check the market calendar; cross-check
   two sources; stop committing raw prices publicly.
7. Report the bot against equal weight (information ratio, deflated Sharpe)
   with a stop rule fixed in advance.
8. Backtest minimum-variance / shrunk-mean variants on 2019-2026 data the
   bot has never seen, with realistic costs.
9. Fix the IBM hardware figure; add a quasi-Monte Carlo (Sobol) baseline
   next to amplitude estimation.
10. Re-run QOBLIB with a native (swap-move) local search and the free
    solvers above; score with the official checker.
