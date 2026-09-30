# Web research for the bots and the indicator duel (2026-09-30)

Five research tracks were run in parallel and cover about 150 sources. Each track has a full
report in `docs/research/`, with every source cited, its link checked, and a verdict. This page
is the summary: what the research says about this project, and what to change. The bots stay
paper trading. Nothing here recommends a broker or broker automation.

Before this summary was written, the most surprising claims were re-checked against primary sources:
- the new day-trading margin rule;
- GitHub's time-zone setting for scheduled runs;
- Alpaca's free-plan terms;
- the End-of-Day Reversal paper;
- the 2026 falsification study.

Two corrections came out of that check. Polygon.io was renamed Massive on 2025-10-30, not in
early 2026. The Mesfin (2026) falsification study tested Micro Nasdaq futures, not stocks.

| Report | Question |
|---|---|
| [01 Intraday evidence](research/01_intraday_evidence.md) | Is there published, net-of-cost evidence for an intraday rule a $50 long-only bot could use? |
| [02 Overfitting methods](research/02_overfitting_methods.md) | How much of a training result is selection luck, and how should the duel referee account for it? |
| [03 Data sources](research/03_data_sources.md) | What better free or cheap data exists than Yahoo's unofficial endpoint? |
| [04 Tooling](research/04_tooling.md) | What open-source engines, indicator references and CI practices can check this code? |
| [05 Rules and costs](research/05_rules_costs.md) | Which rules and real costs would a tiny real account face, and are the simulation's assumptions right? |

## 1. The headline: the edge is smaller than the costs

- **Published intraday stock effects are about 1–15 bps gross.** They are measured on long-short
  portfolios of hundreds of stocks. The bot pays about 20 bps per round trip in simulated
  slippage alone. For cheap and volatile stocks, real spreads are higher still (section 4).
- **Strategies with large published net returns** either trade futures or ETFs at near-zero
  cost, or count commissions but no slippage, often with leverage. That includes the
  opening-range "stocks in play" paper this project already replicated and saw fail.
- **Most of the US equity premium has historically been earned overnight** (Cliff, Cooper and
  Gulen 2008; Lou, Polk and Skouras 2019). A bot that is flat by 15:55 sits in the part of the
  day that has averaged about zero. That is consistent with this project's repeated
  "no better than random" results.
- **Independent 2026 falsification studies found nothing that passed:**
  - Mesfin (arXiv 2605.04004, verified) tested 14 families of 5-minute signals on Micro Nasdaq futures over 947 days.
  - Darmanin (arXiv 2607.20093) tested popular retail signal families.
- **Retail day-trader outcomes:**
  - Fewer than 1% of Taiwanese day traders are predictably profitable (Barber, Lee, Liu and Odean 2014).
  - 97% of Brazilian futures day traders who kept going for more than 300 days lost money (Chague, De-Losso and Giovannetti).
  - SEBI (2024): 71% of Indian intraday equity traders lost money.

**The one candidate worth a pre-registered test** is End-of-Day Reversal (Baltussen, Da and
Soebhag, April 2025, paper read and confirmed). Stocks that fell from the prior close to about
15:00 tend to rebound over the last half-hour.
- The gain comes mostly from intraday losers, so it works long-only.
- It still holds when the window ends at 15:55, which matches the bot's cutoff.
- It is one trade a day, which suits T+1 settled cash.
- The gross edge is small: about 4 bps a day on a value-weighted basis, about 15 bps in small caps. Expect it to fail after costs.
- It is still the best-supported rule found, and a cheap test.

**The evidence also supports a change in stock selection.** In the stocks-in-play paper, almost
all of the performance came from choosing stocks with unusual opening volume, not from the
breakout rule. Separately, buyers of attention-grabbing stocks near the open lose money:
Berkman et al. 2012, and Barber et al. 2022 on Robinhood's "Top Movers".
- Screen on relative volume rather than on the "most volatile" names alone.
- Don't enter those names in the first hour.

## 2. What this means for the duel referee

With the Bailey and López de Prado formulas (report 02), the duel's numbers look like this:

- **The failed pick's training result is about what luck produces.** The best of 20 useless
  configurations is expected to score z ≈ 1.87. Over 29 sessions that is an annualised Sharpe
  of about 5.6, which easily covers +27% on training.
- **The train/test rank correlation of −0.19 carries no information.** Its standard error is
  about 0.23, so it is indistinguishable from zero.
- **The 20-session test window is badly underpowered.** At a one-sided 5% level, a strategy
  with a true annualised Sharpe of 2 would pass it only about 14% of the time.
- **"Beats 90% of 40 random runs" is too weak after choosing the best of 20.** The chance that
  some pure-noise configuration clears it is 1 − 0.9^20 ≈ 88%.
- **Trades needed** at a per-trade Sharpe of 0.1:
  - about 271 for a single test at 95%;
  - about 900 for the Harvey–Liu–Zhu t = 3 hurdle;
  - about 1,260 for a Deflated Sharpe of 95% with 20 configurations.

  The current "at least 30 trades" rule assumes a per-trade Sharpe of 0.3 or more.

Recommended changes. The current duel's rules were registered in advance, so these would apply
to the next round, not this one.
1. **Put the selection step inside the null test.** Shuffle bars within each session at least
   1,000 times, re-run all 20 configurations each time, and compare the real best against the
   shuffled bests. Also run Hansen's SPA test on the 20-configuration P&L matrix
   (`arch.bootstrap.SPA`, actively maintained, NCSA licence).
2. **Require a Deflated Sharpe of at least 0.95** using the true number of configurations tried,
   or cap each contestant at about 5 configurations.
3. **Compute the probability of backtest overfitting** by combinatorially symmetric
   cross-validation on the training data, and reject above 0.2.
4. **Size the sample by power.** Below roughly 300–1,300 trades the verdict is "inconclusive".
   Use at least 1,000 random runs at the 95th percentile, matched to the strategy on trade
   count, holding time and time of day.
5. **Add a warm-up check.** Recompute each indicator on the last N bars for several N and
   compare, as Freqtrade's `recursive-analysis` does. Truncation catches look-ahead but not
   warm-up sensitivity.

## 3. Data sources (report 03)

| Need | Best free option found | Notes |
|---|---|---|
| Daily closes with splits and dividends | **Tiingo** free tier | Raw and adjusted prices with `divCash` and `splitFactor` in the same rows. Only finished sessions, so no unfinished bar like the one on 09-29. 1,000 requests a day. Internal use only. |
| Years of 5-minute bars | **Alpaca** market data, free Basic plan | History since 2016 (confirmed on Alpaca's plans page). Basic excludes the latest 15 minutes of history and allows 200 calls a minute. The consolidated `sip` feed can be queried for data older than 15 minutes, per Alpaca's forum, not the docs page. A 10-year backfill for 58 tickers is about 1,150 requests. The bot's Alpaca adapter already uses the same key. |
| Quotes while paper trading | Alpaca Basic | Real-time IEX quotes, about 2.5% of volume. Consolidated quotes are 15 minutes delayed on the free plan. |

- **Discontinued or much worse since last checked:**
  - IEX Cloud shut down on 2024-08-31.
  - Alpha Vantage now charges for intraday and adjusted daily data, and the free tier is 25 calls a day.
  - Stooq has needed a captcha-issued key since about April 2026.
  - Massive (formerly Polygon) free tier: end-of-day only, 2 years of history, split adjustment only.
- **Redistribution:** every commercial source, and Yahoo, forbids redistributing raw data. So
  the repo's practice of never committing bar data is correct: keep raw bars in an Actions cache
  or private storage, and commit only state and results.
- **One-off purchase options:**
  - Databento's $125 of free credits would cover roughly 5 years of 1-minute bars for 58 tickers.
  - FirstRate Data sells adjusted 1-minute history back to 2000.
- API keys go in GitHub secrets, never in the repo or in chat.

## 4. Simulation assumptions to fix (report 05)

This section is general information, not tax or legal advice.

| Assumption now | What the sources say | Suggested change |
|---|---|---|
| Flat 0.1% slippage per side | A one-cent tick alone costs 0.5% per side at $1, 0.25% at $2 and 0.10% at $5. A 2025 *Journal of Finance* field study (Schwarz et al., real $100–$5,000 orders) found a median quoted spread of 0.28% and mean 0.64%, wider outside the S&P 500 and right after the open. | Make slippage depend on price: at least half a tick, plus half the typical spread, plus 5–10 bps. Use 1.5–2× that in the first 5-minute bar. |
| No minimum price in the intraday screen (`min_price` 0) | Stocks under $1 face the widest spreads, trading pauses, and Nasdaq's new rule (from 2026-01-19) that delists a stock whose closing bid is $0.10 or less for 10 days. | Set `min_price` to at least $1, or preferably $2–5. |
| Zero costs, results in USD | A CAD-funded account pays about 1.5–2% each way on currency conversion. Sell orders also carry the SEC fee ($20.60 per $1M since 2026-04-04) and FINRA's per-share fee. | Report a CAD result net of currency conversion alongside the USD one. |
| Pre-tax results | CRA may treat frequent trading as business income, even inside a TFSA (*Ahamed*, 2023 TCC 17, upheld in 2024 FCA 108). US dividends carry 15% withholding with a W-8BEN, with no exemption in a TFSA. | Show an after-tax figure for the intraday bot, and take the withholding off dividends in the $100k bot. |
| Fills during trading pauses | Stocks priced $0.75–$3 have 20% price bands with 5-minute pauses when they hit one. | Don't fill on bars inside a pause. |

Assumptions that hold:
- **T+1 settlement:** the US since 2024-05-28 and Canada since 2024-05-27.
- **Settled cash only** in the intraday bot (`settled_cash_only: true`). This already avoids
  good-faith violations, where unsettled sale proceeds fund a buy that is sold before they settle.
- **Whole shares** for the $40 bot.
- **Leaving out the pattern day trader rule.** It never applied to cash accounts, and it is now
  gone. The SEC approved FINRA's replacement, SR-FINRA-2025-017, in mid-April 2026 (sources give
  April 14 and 15). It takes effect 2026-06-04, with phase-in allowed to 2027-10-20 (FINRA Regulatory Notice 26-10).
- **No other rules pending:** the half-penny tick and lower access-fee caps are delayed to November 2027.

## 5. Tooling and CI (report 04)

- **Indicator cross-checks:** TA-Lib 0.8.1 (September 2026, BSD) now ships wheels for
  Python 3.9–3.14 and adds `SUPERTREND` and `ER`. Add it as a test-only dependency (runtime
  stays numpy-only) and write parity tests for ATR, Supertrend, ER and KAMA. Compare only after
  warm-up, since the seeds differ. TA-Lib's Supertrend direction sign is the opposite of
  TradingView's.
- **pandas-ta:** its GitHub repo is gone and paid releases have been announced. The MIT fork
  `pandas-ta-classic` is maintained, but its Supertrend differs from TradingView's, so it can't
  be the exact check.
- **Engines to check the bots against:**
  - **LEAN** (Apache-2.0, active) is closest in behaviour to this project: next-open fills, T+1
    settled cash, and cash in lieu on splits.
  - **zipline-reloaded** is the reference for split and dividend ledger rules: shares floored,
    cash in lieu rounded to the cent, dividends paid on the pay date.
  - **bt** (`integer_positions=True`) and **vectorbt** (`size_granularity=1`) can cross-check
    whole-share rebalancing.
- **Pine:** v5 scripts keep working, so no migration to v6 is needed. For alerts, use
  `alert.freq_once_per_bar_close` or `barstate.isconfirmed`. Recreate alerts after every edit,
  because each one stores a snapshot of the script.
- **GitHub Actions:**
  - Scheduled runs can be delayed or dropped around the top of the hour.
  - On a public repo, schedules are switched off after 60 days without activity. Don't rely on
    "keepalive" dummy commits.
  - `on.schedule` now accepts `timezone:` with DST handling (confirmed in GitHub's workflow syntax
    docs). That would let `live-bot.yml` run at a fixed New York time, off the hour, instead of
    at 21:30 UTC.
  - Add an alert for when the state goes stale.

## 6. Suggested order of work

1. Change slippage to depend on price and set a minimum price. These are small, testable
   changes, and they make every later result honest.
2. Add the TA-Lib parity tests and the golden Supertrend tests.
3. For the next duel round, add the permutation and SPA tests, the Deflated Sharpe, and the
   power-based trade minimums.
4. Get years of intraday history from Alpaca, keeping raw bars private and applying corporate
   actions from its endpoint. Then re-test with far more sessions.
5. Run End-of-Day Reversal as one pre-registered test, with relative-volume selection and no
   entries in the first hour.

None of these changes has been made yet. They are proposals for the user to choose from.
