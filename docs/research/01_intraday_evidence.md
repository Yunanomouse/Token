# Intraday / ≤1-day equity effects: what the published evidence says, and fit for a $50 long-only 5-minute bot

Compiled 2026-09-30. Scope: peer-reviewed papers, SSRN/arXiv working papers and author pages, plus a few clearly flagged practitioner or blog replications where no academic update exists.

**Bot constraints assumed:** $50 in a cash account, long only, whole shares, one position at a time, 5-minute bars, fills at the next bar's open with about 0.1% slippage per side, flat by 15:55 ET, T+1 settlement.

---

## 0. The cost hurdle and structural constraints (read first)

- **Round-trip cost is about 20 bps or more.** That is 0.1% slippage on entry plus 0.1% on exit, before any spread you cross on a small cap. A signal has to earn well over 20 bps gross per trade. Most published intraday cross-sectional effects are **1–15 bps per day gross** and are measured on long-short portfolios of hundreds of stocks. Examples:
  - Heston et al.: about 1.7–3 bps per half-hour.
  - End-of-day reversal: 3.8–6.9 bps per day long-short.
  - LETF and gamma end-of-day effects: about 0.5–4 bps.
- **T+1 in a cash account allows about one round trip per day.** Sale proceeds settle the next business day. Rebuying with unsettled funds and then selling risks a good-faith violation. So at most one "shot" per day, and no averaging across many small trades.
- **Whole shares with $50 of capital** limit the universe to stocks priced at or below about $50. Many names on a 58-ticker "most volatile" list will be low-priced, high-spread stocks. That is exactly where published effects are largest on paper and hardest to capture in practice.
- **Flat by 15:55** rules out the closing auction. It also rules out anything that pays overnight. Most of the US equity premium historically accrues overnight, so the bot sits in the window with roughly zero average drift (see §3).
- **Long only** removes the short leg of every long-short result. Where a paper says which leg drives the effect, this is noted below.

**Bottom line up front:** I found **no** published, cost-inclusive, out-of-sample evidence of an intraday equity rule that clears about 20 bps per round trip for a long-only, one-position, unlevered retail account. The strategies that report large net returns fall into three groups:
- (a) Futures or ETFs with near-zero costs. Examples: Zarattini/Aziz/Barbon on SPY; Baltussen et al. with 1-tick costs.
- (b) Commission-only backtests with no slippage, tight stops assumed to fill at the stop price, 4x leverage and 20 simultaneous names. Example: stocks-in-play ORB.
- (c) Effects that have since decayed. Several 2025–2026 falsification studies find exactly what the project found: nothing survives realistic costs.

---

## 1. Market intraday momentum (first half-hour → last half-hour)

### 1.1 Market Intraday Momentum
- **Authors, year:** Gao, Han, Li, Zhou (2018). *Journal of Financial Economics* 129(2): 394–414.
- **URLs:**
  - https://ideas.repec.org/a/eee/jfinec/v129y2018i2p394-414.html (loads, abstract)
  - SSRN https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2440866 (SSRN returns 403 to automated fetch; existence confirmed via search index)
  - Journal version paywalled (ScienceDirect).
- **Effect:** SPY 1993–2013. The first half-hour return, measured from the prior close, predicts the last half-hour return.
  - Predictive R² about 1.6%.
  - A sign-timing strategy made 6.67% per year with 6.19% volatility (Sharpe about 1.08).
  - Stronger on high-volatility days, high-volume days, recession days and macro-news days.
- **Net of cost:** Not cost-adjusted in a retail sense. The strategy trades SPY for 30 minutes per day, so gross average returns are a few bps per trade.
- **Replication or decay:**
  - Baltussen et al. (2021, below) confirm the effect across 60+ futures, 1974–2020.
  - Li, Sakkas, Urquhart (2022, *Journal of Financial Markets*) confirm it in 16 developed markets. https://centaur.reading.ac.uk/95566/1/Accepted-Version.pdf (loads, open accepted version).
  - A 2026 practitioner test (blog, not peer-reviewed) on 1,085 SPX sessions, April 2022 to August 2026, finds the unconditional slope flat: +0.006, t = 0.6, with signs alternating by year. It survives only on dealer-short-gamma days, about 15% of sessions. https://dev.to/firmtape/intraday-momentum-is-dead-in-the-0dte-era-we-measured-it-on-1085-spx-sessions-43g0 (loads; blog, treat as indicative).
- **Verdict:** Poor fit. It is an index-timing effect worth a few bps. It is not a stock-picking signal. Recent evidence says it has decayed in the 0DTE era, and 20 bps of cost swamps it.

### 1.2 Hedging Demand and Market Intraday Momentum
- **Authors, year:** Baltussen, Da, Lammers, Martens (2021). *Journal of Financial Economics* 142(1): 377–403.
- **URLs:**
  - Author PDF https://academicweb.nd.edu/~zda/intramom.pdf (loads)
  - SSRN 3760365 (403 to bots)
- **Effect:** The rest-of-day return (prior close to 15:30) predicts the last-30-minute return in 60+ futures, 1974–2020. The mechanism is short-gamma hedging by option market makers and leveraged ETFs. The move reverts over the next days.
- **Net of cost:** The authors state explicitly: "we do not consider transaction costs … might not be exploitable to many investors". The effect is positive net only in S&P futures at a cost of about 1 tick.
- **Replication or decay:** Dim, Eraker, Vilkov, "0DTEs: Trading, Gamma Risk and Volatility Propagation" (SSRN 4692190, revised 2025). Market makers' 0DTE gamma is on average **positive**, which favours intraday *reversal*. That is consistent with the unconditional momentum fading after 2022. Paper list: https://www.vilkov.net/research.html (loads).
- **Verdict:** Poor fit. It is an index-futures effect, it needs gamma data, and it is too small after 20 bps of cost.

### 1.3 Beat the Market: An Effective Intraday Momentum Strategy for SPY
- **Authors, year:** Zarattini, Aziz, Barbon (2024; revised April 2025). SSRN 4824172; Swiss Finance Institute RP 24-97.
- **URL:** https://www.sfi.ch/en/publications/n-24-97-beat-the-market-an-effective-intraday-momentum-strategy-for-s-p500-etf-spy (SSRN 403 to bots)
- **Effect:** SPY breakouts from a "noise area" (volatility bands anchored at the open), with VWAP trailing stops and volatility-targeted leverage up to 4x.
  - Reported for 2007 to early 2024: 19.6% per year net, Sharpe 1.33.
- **Replication or decay:** An independent GitHub replication froze its rules before testing (ex-ante). https://github.com/codecat-ops/zarattini-2024-momentum-spy (loads via WebFetch).
  - Full 2020–2026: Sharpe 1.11.
  - 2020–2024: Sharpe 1.4–2.0.
  - **2025–2026: Sharpe about 0 on both SPY and ES.** Walk-forward re-optimisation made it worse.
  - This is a non-academic replication, but the method is transparent.
- **Also relevant:** Pagani and Zarattini, "Improving Performance with Fast Alphas" (Feb 2026, SSRN 6391638). The authors state that short-horizon 5-minute mean-reversion signals on SPY are **unprofitable standalone after costs**. They are useful only as an execution overlay.
- **Verdict:** Poor fit. It needs leverage and near-zero costs, it trades an index ETF, and the edge has compressed to about 0 since 2025.

---

## 2. Opening range breakout / "stocks in play"

### 2.1 A Profitable Day Trading Strategy for the U.S. Equity Market
- **Authors, year:** Zarattini, Barbon, Aziz (Feb 2024; revised 2025). SSRN 4729284; SFI RP 24-98.
- **URL:** full text PDF https://alexandria.unisg.ch/bitstreams/3c2989c4-688d-4d78-8a71-f02690990d51/download (loads; read in full)
- **Rules and sample:**
  - 7,000+ US stocks, 2016–2023, survivorship-free.
  - Filters: price above $5, 14-day average volume of at least 1M shares, 14-day ATR above $0.50.
  - Entry: 5-minute ORB stop order in the direction of the first 5-minute candle, **long and short**.
  - Stop at **10% of ATR**, exit at 16:00.
  - Risk 1% of equity per trade, **leverage up to 4x**, $25k starting equity.
- **Key finding:** Plain ORB on all stocks was weak: Sharpe 0.48, about 3% per year. Restricting to relative volume (RVOL) of at least 100% and the top 20 RVOL names produced 1,600%+ net, Sharpe 2.81.
  - Average PnL per trade was −0.02R when RVOL < 1, **+0.08R** when RVOL > 1, and +0.38R when RVOL > 30x.
- **Net of cost:** **Commission only ($0.0035/share). No slippage or spread modelled.** Stops were assumed to fill at the stop price.
  - With a 10%-ATR stop, R is typically about 0.3–0.6% of price.
  - The bot's 0.2% round-trip slippage is therefore about 0.3–0.7R per trade. That is larger than the +0.08R average edge.
- **Replication or decay:**
  - QuantConnect community replication: Sharpe about 2.4 on the 2016 window. Users report poor results in other years and parameter instability. https://www.quantconnect.com/research/18444/opening-range-breakout-for-stocks-in-play/ (loads; community, not peer-reviewed).
  - Mesfin (arXiv 2605.04004, 2026) finds ORB-long on MNQ futures failed out of sample: T = 0.88, unstable across years.
  - The project's own OOS test also failed.
- **Verdict:** ORB itself: poor fit, and this is consistent with the project's result. **The part with evidence is the RVOL "stocks in play" selection.** Monotone PnL in RVOL is the one robust-looking feature, and it is worth reusing as a universe filter rather than the ORB entry rule.

### 2.2 Can Day Trading Really Be Profitable? (ORB on QQQ/TQQQ)
- **Authors, year:** Zarattini and Aziz (2023). SSRN 4416622. Listed at https://concretumgroup.com/papers/ (loads).
- **Effect:** Similar ORB rules on QQQ/TQQQ with leverage. Commission-only costs.
- **Verdict:** Poor fit, for the same cost and leverage caveats. It is an ETF, not a stock-selection rule.

---

## 3. Overnight vs intraday return decomposition

### 3.1 Return Differences between Trading and Non-Trading Hours: Like Night and Day
- **Authors, year:** Cliff, Cooper, Gulen (2008). SSRN 1004081 (403 to bots; confirmed via index).
- **Effect:** For 1993–2006, essentially all of the US equity premium was earned overnight. Intraday returns were about zero or negative. This holds for stocks, indexes and futures. It is partly driven by high opening prices that fall in the first hour.
- **Verdict:** Important context. A flat-by-close long-only bot sits in the zero-premium window, so random long entries have roughly zero expected gross return and negative net. That is exactly the "random baseline" the project observed.

### 3.2 A Tug of War: Overnight versus Intraday Expected Returns
- **Authors, year:** Lou, Polk, Skouras (2019). *Journal of Financial Economics* 134(1): 192–213.
- **URL:** https://personal.lse.ac.uk/polk/research/TugOfWar.pdf (loads)
- **Effect:** Across 14 anomalies, profits are earned either entirely overnight (for example momentum and reversal) or entirely intraday. Overnight and intraday components each persist and offset each other across periods. Intraday-earned premia exist but are small and slow-moving (monthly-rebalanced portfolios).
- **Verdict:** Informative but not tradeable at 5-minute or daily frequency with $50.

### 3.3 Paying Attention: Overnight Returns and the Hidden Cost of Buying at the Open
- **Authors, year:** Berkman, Koch, Tuttle, Zhang (2012). *Journal of Financial and Quantitative Analysis* 47: 715–741.
- **URL:** Semantic Scholar record https://www.semanticscholar.org/paper/ff64bccbd678828e4a83fb0304e8e15148ef67a6 (journal version paywalled)
- **Effect:** High-attention stocks gap up overnight on retail buying at the open, then **reverse during the day**.
- **Verdict:** A useful negative rule. **Avoid buying high-attention names at or near the open.** This supports not buying morning strength in "most volatile" names.

### 3.4 Overnight Returns, Daytime Reversals, and Future Stock Returns
- **Authors, year:** Akbas, Boehmer, Jiang, Koch (2022). *Journal of Financial Economics* 145(3): 850–875. DOI 10.1016/j.jfineco.2021.09.019 (paywalled).
- **Effect:** Frequent "positive overnight, negative daytime" tug-of-war patterns predict higher future returns (monthly horizon). This is interpreted as arbitrageurs correcting retail overnight pressure.
- **Verdict:** Monthly horizon, so not a 5-minute signal. It confirms that intraday sessions often reverse overnight moves.

### 3.5 Overnight Returns and Firm-Specific Investor Sentiment
- **Authors, year:** Aboody, Even-Tov, Lehavy, Trueman (2018). *Journal of Financial and Quantitative Analysis* 53(2): 485–505.
- **URL:** https://anderson-review.ucla.edu/wp-content/uploads/2021/03/Aboody-et-al_overnight_returns_and_firmspecific_investor_sentiment_JFQA2018.pdf (loads)
- **Effect:** Overnight returns persist in the short term, especially for hard-to-value firms, and reverse over the longer term.
- **Verdict:** Background only.

### 3.6 The Cross-Section of Intraday and Overnight Returns
- **Authors, year:** Bogousslavsky (2021). *Journal of Financial Economics* 141: 172–194.
- **URL:** https://econpapers.repec.org/article/eeejfinec/v_3a141_3ay_3a2021_3ai_3a1_3ap_3a172-194.htm (loads; journal paywalled)
- **Effect:** Size and illiquidity premia are realised in the last 30 minutes of trading. Mispricing anomalies accrue during the day and lose overnight.
- **Verdict:** Background. The end-of-day effects it documents are basis-point scale.

### 3.7 The Overnight Drift
- **Authors, year:** Boyarchenko, Larsen, Whelan. NY Fed Staff Report 917 (2020, rev. 2022; later published in RFS).
- **URL:** https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr917.pdf (loads)
- **Effect:** US equity futures returns concentrate around the European open (about 2–3am ET), linked to the prior US close's order imbalance. Sell-offs are followed by strong overnight reversals.
- **Verdict:** Not accessible to a day-only stock bot.

### 3.8 Practitioner summary and Knuteson
- **Elm Wealth, "Night Moves" (2023):** covers 1995–2022. It suggests the drift has **waned** since publication, and costs of about 1 bp per round trip already cut about 5% per year from the long-short version. https://elmwealth.com/night-moves-overnight-drift/ (loads; practitioner).
- **Knuteson, arXiv 2201.00223:** a contrarian, controversial explanation of the overnight/intraday split. (loads)

---

## 4. End-of-day (intraday) reversal. The single most relevant cross-sectional finding

### 4.1 End-of-Day Reversal
- **Authors, year:** Baltussen, Da, Soebhag (working paper, April 2025 version; EFMA 2024).
- **URL:** https://academicweb.nd.edu/~zda/EOD.pdf (loads; read in full). The EFMA copy returned 503.
- **Effect:**
  - Sample: all NYSE/AMEX/Nasdaq stocks, TAQ, **1993–2019**.
  - A stock's return from the prior close to 15:00 (ROD3) **negatively** predicts its return over 15:30–16:00 in the cross-section. The authors skip 15:00–15:30 to avoid bid-ask bounce.
  - t-statistics are above 10. The effect is present in almost every 3-year rolling window. It holds for large, liquid and volatile subsets, and in midquote returns.
  - **It is robust when the window ends at 15:55 instead of 16:00.** Regression coefficient −0.92, t = −8.76. That matches this bot's flat-by-15:55 rule.
  - **The effect is mostly in the long leg.** Intraday losers rise into the close, while winners are about flat. The paper attributes this to retail "buy-the-dip" purchases and short-sellers covering before the close.
- **Size:**
  - Value-weighted quintile spread: 3.78 bps per day. The low-return (loser) quintile earns about 3.55 bps.
  - Equal-weighted spread: 6.4–6.9 bps per day.
  - Smallest-size quintile: 14.7 bps six-factor alpha long-short. Largest 20% of firms: 3.4 bps.
  - The extreme loser decile compounded to about +400% over 27 years using only the last half-hour. That is a small daily edge applied every day.
  - The price pressure **reverses the next day**. It is transitory and does not persist.
- **Net of cost:** The authors say explicitly that it "might not be exploitable by many investors after accounting for transaction costs". No net test is reported.
- **Replication or decay:** No independent post-2019 replication found. Heston et al. (2010) and Bogousslavsky (2021) are consistent in-sample precursors.
- **Verdict:** **Best directional fit of anything found.** It is long-only compatible (the loser leg carries the effect), sits inside the 15:30–15:55 window and is a single trade per day. But the documented gross edge (about 3–15 bps; perhaps more in the extreme decile of small, volatile names) is **below the 20 bps round-trip hurdle**. It is worth a pre-registered test, not a deployment.

### 4.2 Intraday Residual Reversal in the U.S. Stock Market
- **Authors, year:** Brogaard, Han, Kim (2024 working paper; CICF 2026).
- **URLs:** SSRN 4731947 (403 to bots); author page https://sites.google.com/view/hanjunkim/research
- **Effect:** Residual returns from a 15-anomaly cross-sectional model reverse over the next interval. Long-short at about 30-minute frequency, 162% per year gross.
- **Net of cost:** No cost details found on the public page. The very high turnover implies gross-only results.
- **Verdict:** Poor fit. It needs a factor model across the whole cross-section and long-short trading, and turnover would be far above one trade per day.

### 4.3 Intraday Patterns in the Cross-Section of Stock Returns
- **Authors, year:** Heston, Korajczyk, Sadka (2010). *Journal of Finance*.
- **URL:** https://arxiv.org/abs/1005.3535 (loads)
- **Effect:**
  - Sample: NYSE stocks, 2001–2005.
  - Continuation at the same half-hour on subsequent days, lasting 40 days or more.
  - Extreme-decile spread about 1.7–3 bps per half-hour.
  - Short-term reversal of about 1–1.5 bps within the hour.
  - The authors present it as an execution-timing effect worth about one effective spread.
- **Verdict:** Poor fit as alpha, because it is about 3 bps. It could be used only to time an entry you were going to make anyway.

---

## 5. Short-term reversal / short-term momentum (daily to monthly)

### 5.1 Evaporating Liquidity
- **Authors, year:** Nagel (2012). *Review of Financial Studies* 25(7): 2005–2039.
- **URL:** https://gsbpreserve.stanford.edu/view/41388/evaporating-liquidity (loads)
- **Effect:** Short-term reversal returns are compensation for providing liquidity. Expected returns rise sharply with the VIX.
- **Verdict:** Conceptual support for "buy losers when volatility is high". The evidence is at a daily-to-weekly horizon on large portfolios.

### 5.2 Short-term Momentum
- **Authors, year:** Medhat and Schmeling (2022). *Review of Financial Studies* 35(3): 1480–1526.
- **URL:** https://openaccess.city.ac.uk/id/eprint/31278/1/MS_short_term_mom_v27.pdf (loads)
- **Effect:**
  - Sorting on last month's return and turnover: **low-turnover losers reverse** (+17% per year), **high-turnover winners continue** (+16% per year).
  - It survives costs and is strongest in large, liquid stocks.
  - Monthly rebalancing, 1963–2018, US plus 22 countries.
- **Verdict:** Not intraday. It conflicts with flat-by-close. At most it could bias which names to trade (high-turnover recent winners).

### 5.3 Liquidity and Return Reversals
- **Authors:** Collin-Dufresne and Daniel. https://www.kentdaniel.net/papers/unpublished/str2.pdf (loads)
- **Related:** Miwa, "Short-term Return Reversals and Intraday Transactions".
- **Effect:** Reversal is concentrated in past *intraday* price moves, not overnight moves.
- **Verdict:** Background.

### 5.4 Overnight-Intraday Reversal Everywhere
- **Authors:** Liu, Liu, Wang, Zhou, Zhu. SSRN 2730304, revised about 2025. (403 to bots)
- **Effect:** Buying the lowest overnight-return assets and shorting the highest, held intraday, gives Sharpe ratios 2–5x classic reversal across asset classes. The paper claims out-of-sample validity.
- **Replication:** A third-party auto-backtest on paperswithbacktest.com on index, bond, commodity and FX data showed a large loss (Sharpe −0.23). That is low-quality evidence either way.
- **Verdict:** A gap-fade-like idea (buy the worst gap-downs and hold intraday). It is long-short, gross, and the evidence is at asset-class level.

---

## 6. Gaps: gap-fade vs gap-and-go

### 6.1 Price Gap Anomaly in the US Stock Market: The Whole Story
- **Authors, year:** Plastun, Sibande, Gupta, Wohar (2020). *North American Journal of Economics and Finance* 52.
- **URL:** https://repository.up.ac.za/bitstream/handle/2263/78336/Plastun_Price_2020.pdf (loads)
- **Effect:**
  - DJI, S&P 500 and Nasdaq **index** daily data, 1928–2018.
  - On gap days prices tend to move **in the gap direction** (continuation). Gaps do **not** reliably fill, contrary to trader folklore. The momentum is temporary.
  - Costs are essentially ignored (spread about 0.02%).
- **Verdict:** Weak evidence (index-level, daily bars, no realistic costs). If anything it argues against gap-fade.

### 6.2 Statistical Arbitrage with Mean-Reverting Overnight Price Gaps on High-Frequency Data of the S&P 500
- **Authors, year:** Stübinger and Schneider (2019). *Journal of Risk and Financial Management* 12(2): 51.
- **URL:** https://www.mdpi.com/1911-8074/12/2/51 (MDPI returns 403 to bots; confirmed via econpapers and search)
- **Effect:** S&P 500 constituents at minute frequency, 1998–2015. A jump test identifies overnight gaps, and the strategy trades mean reversion in the first minutes to 2 hours. Reported 51% per year, Sharpe 2.38 "after transaction costs".
- **Caveat:** I could not verify the cost assumption; the full text was blocked. It is long-short, the sample ends in 2015, and there is no post-publication replication.
- **Verdict:** Weak to moderate, unverified. Large-cap gap fade in the first 2 hours is the most concrete published gap result, but it is stale.

### 6.3 Falsification study on MNQ futures
- **Source:** Mesfin (2026), arXiv 2605.04004 (loads).
- **Finding:** Gap-fill fade failed at 09:30, 09:45 and 10:00 entries. Gap-continuation short made +16.5 points gross but failed year stability.
- **Verdict:** Recent negative evidence for gap rules at 5-minute resolution.

---

## 7. VWAP and relative volume

### 7.1 Volume Weighted Average Price (VWAP): The Holy Grail for Day Trading Systems
- **Authors, year:** Zarattini and Aziz (2023). SSRN 4631351.
- **URL:** https://concretumgroup.com/volume-weighted-average-price-vwap-the-holy-grail-for-day-trading-systems/
- **Effect:** Long QQQ/TQQQ above VWAP and short below, 2018–2023, commission-only. 671% on QQQ, Sharpe 2.1.
- **Verdict:** Poor fit. It is ETF trend-following (not VWAP *reversion*), long-short, 2018–2023 in-sample only, with no slippage. The project's VWAP-reversion test failing is consistent with the absence of any academic VWAP-reversion alpha result. VWAP's academic literature is almost entirely about execution benchmarks, not alpha.

### 7.2 The High-Volume Return Premium
- **Authors, year:** Gervais, Kaniel, Mingelgrin (2001). *Journal of Finance* 56: 877–919.
- **URL:** https://sites.duke.edu/sgervais/research/gervais-kaniel-mingelgrin-2001/ (loads)
- **Effect:** Stocks with unusually high daily or weekly volume outperform over the next month, attributed to a visibility effect.
- **Verdict:** Monthly horizon. It supports RVOL as a *selection* variable, not an intraday trigger.

### 7.3 Stocks-in-play RVOL
- See §2.1: monotone per-trade PnL rising with opening RVOL.
- **Verdict:** The best-supported intraday selection filter, though evidence comes from one author group.

---

## 8. Closing auction / MOC imbalance, LETF and gamma flows

### 8.1 Who Trades at the Close? Implications for Price Discovery and Liquidity
- **Authors, year:** Bogousslavsky and Muravyev (2023). *Journal of Financial Markets* 66.
- **URL:** https://static1.squarespace.com/static/6310c0b9bb63a25599f4418c/t/634ffc92f81e226b2c30654f/1666186387645/who-trades-at-the-close_June2021.pdf (loads)
- **Effect:** Closing auctions made up 7.5% of volume in 2018. About 85% of auction price deviations reverse by the next morning.
- **Verdict:** No fit. It needs auction participation and an overnight hold. The bot is flat by 15:55.

### 8.2 The Role of Leveraged ETFs and Option Market Imbalances on End-of-Day Price Dynamics
- **Authors, year:** Barbon, Beckmeyer, Buraschi, Moerke (2021). SSRN 3925725; HSG WP 2021/14.
- **URL:** https://fmai.memberclicks.net/assets/docs/Derivatives2021/beckmeyer_etf_options.pdf (loads)
- **Effect:**
  - 2012–2019.
  - Negative gamma imbalance gives end-of-day momentum; positive gives reversal. LETF rebalancing also pushes end-of-day prices.
  - Effects are **about 0.3–4 bps** and revert at the next open.
  - The LETF impact was constant over the sample; the delta-hedging impact rose over time.
- **Related:** Shum, Hejazi, Haryanto, Rodier (2016) find LETF flows amplify end-of-day volatility, 2006–2011.
- **Related (2026):** Zhao, "Preying on Leveraged ETFs", arXiv 2608.03703 (loads). Speculators front-run predictable LETF closing rebalances. The evidence is on Korean single-stock LETFs in 2026.
- **Verdict:** No fit. It is basis-point scale, concentrated in the final minutes and the auction (after 15:55), and needs options and LETF AUM data.

### 8.3 Closing-auction imbalance thesis
- **Source:** Imperial College MSc thesis (Morand) on predicting the 15:50–16:00 return from published imbalance.
- **Finding:** The model captures about 30% of the spread.
- **Status:** URL timed out during verification; student work.
- **Verdict:** No fit, because it is after 15:55.

---

## 9. Calendar effects (day-of-week, turn-of-month)

### 9.1 Day of the Week and the Cross-Section of Returns
- **Authors, year:** Birru (2018). *Journal of Financial Economics* 130: 182–214.
- **URL:** https://ideas.repec.org/a/eee/jfinec/v130y2018i1p182-214.html (loads)
- **Effect:** Speculative stocks do relatively worse on Mondays and better on Fridays (mood-driven). This shows up in anomaly long-short returns.
- **Verdict:** A weak tilt at most. For example, avoid long entries in speculative names on Monday. It is not a standalone strategy.

### 9.2 Monday reversal
- **Source:** "Reversal of Monday returns: it is the afternoon that matters", *Finance Research Letters* (2024). https://www.sciencedirect.com/science/article/pii/S1544612324005555 (403 to bots; paywalled)
- **Effect:** The Monday reversal comes from Monday afternoons.
- **Verdict:** Unverified detail. Low priority.

### 9.3 Turn of the month
- **Sources:**
  - McConnell and Xu (2008), "Equity Returns at the Turn of the Month". https://business.purdue.edu/faculty/mcconnell/publications/Equity-Returns-at-the-Turn-of-the-Month.pdf (loads)
  - Etula, Rinne, Suominen, Vaittinen (2020), "Dash for Cash", *Review of Financial Studies* 33(1): 75–111. https://econpapers.repec.org/article/ouprfinst/v_3a33_3ay_3a2020_3ai_3a1_3ap_3a75-111..htm (loads). Institutional month-end liquidity needs depress prices before the turn and lift them after.
- **Decay:** QuantSeeker (Feb 2025, practitioner) finds the classic [0:+3] window **no longer significant** in US equities post-2010. The wider [−3:+3] window is weaker but persists, mostly internationally. https://www.quantseeker.com/p/turn-of-the-month-strategies-do-they (loads)
- **Verdict:** A daily or overnight effect, and decayed in the US. It does not fit an intraday bot.

---

## 10. Other 2024–2026 replications and failures

- **Mesfin (2026), "Structural Limits of OHLCV-Based Intraday Momentum Signals in MNQ Futures: A Systematic Falsification Study".** arXiv 2605.04004 (loads).
  - 14 signal families on 5-minute bars, 947 days (2021–2025), walk-forward.
  - **None passed.** 11 of 14 had gross edges of 0.07–1.5 points, below a 2-point friction floor.
  - ORB-long failed (T = 0.88).
  - Closest analogue to the project's own experience.
- **Darmanin (July 2026), "Retail Trader's Ruin: An Anatomy of Popular Signal Failure".** arXiv 2607.20093 (loads).
  - Tests trend, oscillator, candlestick, volume and calendar retail signals with multiple-testing correction, cost gates and exposure-matched benchmarks.
  - Four families refuted, two inconclusive, **none supported**.
- **Aleti, Bollerslev, Siggaard, "Intraday Market Return Predictability Culled from the Factor Zoo".** *Management Science* (R&R/forthcoming). https://public.econ.duke.edu/~boller/Papers/HFML.pdf (loads).
  - Machine learning on 200+ high-frequency factor returns predicts intraday SPY.
  - Out-of-sample net-of-cost Sharpe 1.37, mostly in high-uncertainty periods.
  - Needs a large high-frequency factor dataset. Not feasible here.
- **Zarattini/Aziz SPY replication showing Sharpe about 0 in 2025–26:** see §1.3.
- **The 0DTE-era intraday momentum retest:** see §1.1.

---

## 11. Retail day-trader outcomes (calibrating expectations)

### 11.1 The Cross-Section of Speculator Skill: Evidence from Day Trading
- **Authors, year:** Barber, Lee, Liu, Odean (2014). *Journal of Financial Markets* 18: 1–24.
- **URL:** https://faculty.haas.berkeley.edu/odean/papers/day%20traders/The%20Cross-Section%20of%20Speculator%20Skill.pdf (loads; read)
- **Findings:**
  - Taiwan, 1992–2006, about 450,000 day traders a year.
  - **Less than 1% are predictably profitable.** The top 500 earn 37.9 bps per day after fees, while the population loses.
  - All partitions of the less-active traders lose after costs.

### 11.2 Do Day Traders Rationally Learn About Their Ability?
- **Authors:** Barber, Lee, Liu, Odean (working paper; later retitled "Learning, Fast or Slow").
- **URL:** https://faculty.haas.berkeley.edu/odean/papers/Day%20Traders/Day%20Trading%20and%20Learning%20110217.pdf (loads)
- **Findings:** Most day traders keep trading despite persistent losses.

### 11.3 Just How Much Do Individual Investors Lose by Trading?
- **Authors, year:** Barber, Lee, Liu, Odean (2009). *Review of Financial Studies* 22(2): 609–632.
- **URL:** https://econpapers.repec.org/RePEc:oup:rfinst:v:22:y:2009:i:2:p:609-632 (loads)
- **Findings:** Individual investors' trading costs them 3.8 percentage points per year in aggregate. Losses come mostly from **aggressive (liquidity-taking) orders**, which is what a market-order bot uses.

### 11.4 Day Trading for a Living?
- **Authors, year:** Chague, De-Losso, Giovannetti (2019/2020). SSRN 3423101. SSRN and ResearchGate return 403 to bots; confirmed via search index. Also covered in press and academic citations.
- **Findings:**
  - Brazilian mini-index futures, all individuals who started 2013–2015.
  - **97% of those who persisted for more than 300 days lost money.** Only 1.1% earned more than the minimum wage and 0.5% more than a bank teller's starting salary.
  - No evidence of learning.

### 11.5 Attention-Induced Trading and Returns: Evidence from Robinhood Users
- **Authors, year:** Barber, Huang, Odean, Schwarz (2022). *Journal of Finance* 77(6): 3141–3190.
- **URLs:** SSRN 3715077; Wiley version paywalled (403 to bots).
- **Findings:** Herding into "Top Movers" predicts negative returns: −4.7% over 20 days for top-bought stocks. This matters because a "most volatile names today" universe is the Top-Movers list.

### 11.6 Resolving a Paradox: Retail Trades Positively Predict Returns but Are Not Profitable
- **Authors, year:** Barber, Lin, Odean (2024). *Journal of Financial and Quantitative Analysis*.
- **URL:** https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/resolving-a-paradox-retail-trades-positively-predict-returns-but-are-not-profitable/6AAA9078F50C2597F44D73FA6A8E3F0D (loads)
- **Related:** Barber, Huang, Jorion, Odean, Schwarz, "A (Sub)penny for Your Thoughts" (JF 2024). Retail order-imbalance strategies earn **−14.8% per year among heavily retail-traded stocks**.

### 11.7 SEBI (India) intraday cash-segment study
- **Source:** SEBI, July 2024. https://www.sebi.gov.in/reports-and-statistics/research/jul-2024/study-analysis-of-intraday-trading-by-individuals-in-equity-cash-segment_84946.html (loads)
- **Findings:**
  - **71% of individual intraday traders lost money** in FY23.
  - 80% of those with more than 500 trades a year lost money.
  - Among loss-makers, trading costs added 57% on top of their losses.

**Takeaway:** The null hypothesis for a retail intraday rule is "negative after costs". Random-entry parity is not a failure of the project. It is the documented base rate.

---

## 12. Summary table

"Gross size" means the published per-trade or per-day edge before retail costs. The bot's hurdle is about 20 bps per round trip.

| Effect | Key source | Gross size | Survives about 20 bps? | Recent status | Fit |
|---|---|---|---|---|---|
| End-of-day reversal (buy intraday losers 15:30→15:55) | Baltussen/Da/Soebhag 2025 | 3–15 bps/day | No (on averages) | Robust 1993–2019; no post-2019 replication | Best directional fit; test only |
| RVOL "stocks in play" selection | Zarattini/Barbon/Aziz 2024 | +0.08R/trade (RVOL>1) to 0.38R (>30x) | No with tight stops | One group; community replications unstable | Use as filter, not as a system |
| Market intraday momentum | Gao et al. 2018; Baltussen et al. 2021 | few bps (index) | No | Unconditional effect about 0 since 2022 | Poor |
| Noise-area SPY momentum | Zarattini/Aziz/Barbon 2024 | Sharpe 1.33 levered | Only at futures costs | Sharpe about 0 in 2025–26 | Poor |
| ORB | same | ~0 unfiltered | No | Failed OOS (project, MNQ study) | Poor |
| Gap fade (large caps, first 2h) | Stübinger & Schneider 2019 | claims Sharpe 2.4 net | Unverified | Sample ends 2015; futures gap-fill failed 2021–25 | Weak |
| VWAP trend/reversion | Zarattini & Aziz 2023 | ETF trend, in-sample | No evidence | No academic reversion alpha | Poor |
| Overnight vs intraday split | Cliff/Cooper/Gulen; Lou/Polk/Skouras | intraday about 0 | n/a | Waning | Context: explains random-baseline result |
| Avoid buying attention names at open | Berkman et al. 2012; Barber et al. 2022 | negative drift for buyers | n/a (a "don't" rule) | Consistent through Robinhood era | Useful filter |
| LETF/gamma end-of-day, MOC imbalance | Barbon et al. 2021; Bogousslavsky & Muravyev 2023 | 0.3–4 bps, after 15:55 | No | Delta-hedging impact rising | None |
| Day-of-week, turn-of-month | Birru 2018; Etula et al. 2020 | daily/overnight | No | TOM decayed in US | None |
| Short-term momentum/reversal | Medhat & Schmeling 2022; Nagel 2012 | monthly | n/a | Robust at monthly horizon | Not intraday |

## 13. Practical implications for this project (evidence-based, not a guarantee)

1. **Accept the base rate.** Several 2025–2026 falsification studies (Mesfin; Darmanin; the Zarattini SPY replication) and the retail-outcome literature all say realistic-cost intraday rules on OHLCV bars usually fail. The project's "nothing beats random OOS" result is in line with the literature.
2. **If anything is tested next, pre-register one test: an end-of-day loser reversal.**
   - At about 15:25–15:30, among liquid names that pass an RVOL/price filter, buy the stock with the most negative return from the prior close to 15:00 (or 15:25).
   - Exit at 15:55.
   - Compare against a random-stock 15:30→15:55 baseline, net of 0.2% round-trip cost.
   - The published average edge is below the hurdle, so expect failure unless the extreme tail is much larger. It is still the one effect that matches all bot constraints (long leg, single daily trade, window ends 15:55).
3. **Use evidence-based "don'ts" as filters.**
   - Don't buy attention/Top-Mover names in the first hour (Berkman et al.; Barber et al.).
   - Keep trades to one per day because of T+1.
   - Prefer liquid, tight-spread names, where effective costs are closest to the assumed 0.1%.
4. **Lower the cost, or accept that no edge is available.** Every surviving result in this review relies on costs about an order of magnitude below 20 bps round trip.
