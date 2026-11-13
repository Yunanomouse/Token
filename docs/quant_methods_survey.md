# Quant trading methods: survey and tests for a $50–$100 account (2026-09-24)

Six parallel literature reviews covered these families of methods:

- equity factors
- trend and tactical allocation
- calendar and event effects
- stat arb and mean reversion
- machine learning and alternative data
- options and risk premia

Each was judged against one account: a C$50–100 Questrade cash account that buys whole shares only, cannot short, settles T+1, and uses free Yahoo data. The index-timing candidates that were feasible were then backtested against a pass bar written down before any results were seen.

## What the literature says

| Family | Verdict for this account | Key evidence |
|---|---|---|
| Buy-and-hold of a broad index ETF | **Benchmark that every strategy must beat** | Equity premium; every other row is measured against it |
| Trend: 10-month SMA, 200-day SMA, GTAA | Works as **drawdown control**; since about 2010 it trails buy-and-hold on return | Faber (2007); Hurst, Ooi & Pedersen (2017); Zarattini (2025) found 6.05% CAGR out of sample for 2006–2025 |
| Dual momentum (GEM), Keller's VAA/DAA/BAA | Did much worse after publication; high data-mining risk | GEM made 5.9% CAGR over 2014–21 with a 33.7% drawdown |
| Cross-sectional momentum and quality | The factors that survived replication. Only reachable through a CAD-listed factor ETF (XMTM, ZUQ), because 1–3 stocks is too few | Hou, Xue & Zhang (2020); Jensen, Kelly & Pedersen (2023); McLean & Pontiff: premia fall 58% after publication |
| Value, PEAD, short-term reversal, seasonality | Value has been weak for a decade. PEAD has been gone in large caps since about 2006. Reversal is eaten by costs | Martineau (2022), "Rest in Peace PEAD" |
| Calendar effects | Mostly gone: January, pre-holiday, Monday, index inclusion, turn of the month. Pre-FOMC drift is unstable. Month-end rebalancing is new and not yet tested out of sample | Kurov et al.; Greenwood & Sammon; Harvey, Mazzoleni & Melone (2025) |
| Overnight vs intraday returns | Real in the data, but daily round trips cost the whole edge | Robot Wealth; Alpha Architect |
| Pairs, PCA stat arb, ETF arbitrage, market making, interlisted arbitrage | **Infeasible**: they need shorting, low latency or Level-2 data | Gatev et al. (2006); Do & Faff (2010) show the returns decaying |
| RSI(2) dip-buying on an index | The only long-only mean-reversion idea. Lower return than holding, much smaller drawdown | Practitioner tests only; no peer-reviewed out-of-sample study |
| ML, CNN chart images, LLM news sentiment, WallStreetBets, Google Trends | Edges concentrate in microcaps and in the minutes after news, and decay fast. The LLM headline Sharpe fell from 6.5 to 1.2 in 2.5 years. WallStreetBets predictability was gone after GameStop | Gu, Kelly & Xiu (2020); Jiang, Kelly & Xiu (2023); Lopez-Lira & Tang; Bradley et al. (2024) |
| Options: put writing, covered calls, the wheel, 0DTE | Direct options need $2,000+ per contract. Covered-call ETFs trail their own index: QYLD 9.8% vs QQQ 21.7% a year, JEPI 7.5% vs SPY 13.4%. Retail 0DTE traders lose money | Israelov & Nielsen (2015); Beckmeyer et al. |

Two costs matter for this account:

- **USD conversion.** Questrade's markup is about 1.5–2% per conversion. Norbert's gambit costs $9.95 per journal. So trade CAD-listed ETFs only.
- **Commissions.** Stock and ETF trades are commission-free (since February 2025).

## Backtests (pre-registered)

**Method**

- Signals are taken at the close. Trades happen at the next day's close. Each switch costs 0.1%.
- Uninvested cash earns 0.
- Markets:
  - SPY, 1994–2026
  - XIU.TO, 2000–2026
  - GEM: SPY, EFA and AGG, 2004–2026
  - Sector momentum: nine SPDR sector ETFs, 2000–2026

**Pass bar.** A strategy passes only if its Sharpe beats buy-and-hold in all four windows: the full period, each half, and the last 5 years. Its CAGR must also be no more than 2 points a year below buy-and-hold, and it must pass on both SPY and XIU.

| Strategy | Market | CAGR (buy-and-hold) | Sharpe (buy-and-hold) | Max drawdown (buy-and-hold) | Sharpe, 2nd half | Sharpe, last 5 years | Pass |
|---|---|---|---|---|---|---|---|
| 10-month SMA (Faber) | SPY | 9.4% (11.0%) | 0.76 (0.65) | −28% (−55%) | 0.71 vs 0.90 | 0.49 vs 0.82 | no |
| 10-month SMA (Faber) | XIU | 6.1% (7.2%) | 0.58 (0.49) | −29% (−52%) | 0.83 vs 0.83 | 0.79 vs 1.13 | no |
| 200-day SMA | SPY | 8.5% (11.0%) | 0.73 (0.65) | −25% (−55%) | 0.86 vs 0.90 | 0.72 vs 0.82 | no |
| 200-day SMA | XIU | 4.1% (7.2%) | 0.43 (0.49) | −34% (−52%) | — | — | no |
| RSI(2) dip-buy | SPY | 3.7% (11.0%) | 0.57 (0.65) | −16% (−55%) | 0.32 vs 0.90 | 0.74 vs 0.82 | no |
| RSI(2) dip-buy | XIU | 2.1% (7.2%) | 0.42 (0.49) | −13% (−52%) | — | — | no |
| Month-end rebalancing | SPY | 10.2% (11.3%) | 0.62 (0.67) | −56% (−55%) | — | — | no |
| Dual momentum (GEM) | SPY/EFA/AGG | 8.8% (11.2%) | 0.61 (0.66) | −34% (−55%) | — | — | no |
| Sector momentum, top 2 | 9 sectors | 7.3% (8.8% SPY) | 0.50 (0.53) | −38% (−53%) | — | — | no |

No strategy passed. The pattern matches the literature:

- **Trend rules** (the 10-month and 200-day SMA) beat buy-and-hold on Sharpe over the whole history and cut the worst drawdown roughly in half. Both advantages came from 2000–2009. Since about 2010 they trail buy-and-hold on Sharpe and on return.
- **Every other rule** lost to simply holding the index.

For a $50–100 account, the evidence points to buy-and-hold of one broad CAD-listed ETF such as XEQT ($45.78) or ZEQT ($23.60). The one defensible overlay is a monthly 10-month SMA rule. It costs about 1–2 points a year of return and roughly halves crash drawdowns.

The daily 8-stock bot trailed holding its own 8 stocks over the past year: +15.4% against +19.7%. The intraday bot lost 15.1% on 1-hour bars.

A caveat on these results: this was 7 strategies on 2–3 markets. Any single pass would have needed paper trading before it could be trusted.
