# Intraday strategies: research and test (2026-09-24)

The KAMA day-trading bot (`quantum/intraday.py`) was tested against the
best-supported intraday ideas found in published research. Every candidate
used its source's own settings. The pass bar was written down before any
result was seen.

## Setup

- **Data:** 5-minute bars for the 58 stocks in `live/intraday/universe.txt`, 46 sessions (Jul 21 to Sep 23, 2026). The first 14 sessions of the 60-session download are reserved to compute each stock's usual volume and ATR.
- **Account:** $50, long only, whole shares, one position at a time.
- **Settlement:** sale money is not reusable until the next session (T+1).
- **Costs and fills:** 0.1% per side. Fills happen at the next bar's open, and everything is closed by 15:55.

## Pass bar

A candidate had to meet all four rules:
1. Made money over all 46 sessions and, separately, over the last month (Aug 24 to Sep 23).
2. Did better than at least 90% of 40 random-entry runs. Each random run had the same number of trades, trade timing, holding times and costs.
3. Made money in both halves of the 46 sessions.
4. Still made money over all 46 sessions at a 0.25% per-side cost.

## Results

| Candidate | Source | 46 sessions | Trades | Won | 1st half / 2nd half | Last month | At 0.25% cost | Beats random | Pass |
|---|---|---|---|---|---|---|---|---|---|
| KAMA 10/2/30, prior-day range picks (current) | Kaufman | +9.7% | 99 | 37% | +12.9% / −1.0% | −1.4% | −0.0% | 95% | no |
| Opening-range breakout, stocks in play | Zarattini, Barbon & Aziz 2024, SSRN 4729284 | −4.9% | 65 | 18% | −2.6% / −2.3% | −1.9% | −10.1% | 60% | no |
| KAMA, stocks-in-play picks | same | −7.5% | 86 | 37% | +1.8% / −12.0% | −6.4% | −22.4% | 55% | no |
| KAMA with a VWAP filter and exit | Zarattini, Aziz & Barbon 2024, SSRN 4824172 | −6.0% | 99 | 31% | −1.5% / −4.4% | −3.4% | −18.0% | 62% | no |
| KAMA with ER > 0.3 and filter k = 1.0 | Kaufman, as practitioners cite him | −5.1% | 88 | 33% | +11.1% / −13.2% | −12.5% | −16.1% | 62% | no |
| KAMA on 15-minute bars | Kaufman's suggested minimum timeframe | +8.1% | 58 | 50% | +11.2% / −0.5% | −1.0% | +2.0% | 95% | no |

No candidate passed, and the live configuration is unchanged.

- **KAMA on 15-minute bars** came closest. It won half its trades and was the only candidate to survive a 0.25% cost. It lost only because the last month was down 1.0%.
- **The opening-range breakout did not reproduce here.** Our setup differs from the paper's in four ways:
  - It picks from 58 pre-chosen names, not the top 20 of about 7,000 stocks.
  - It trades long only.
  - It has one $50 position.
  - The paper's stop at 10% of ATR is close to one spread on these stocks.

## Not tested

- **Noise-area momentum:** tested in the literature on SPY only.
- **End-of-day reversal:** its gross edge of 4–15 bps per day is below our costs.
- **SPY first-half-hour filter:** there is no SPY data in the universe.
- **Gap-and-go:** no peer-reviewed support, and it needs premarket, float and news data.

## Sources

- Zarattini, Barbon & Aziz (2024), *A Profitable Day Trading Strategy for the U.S. Equity Market*, https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4729284
- Zarattini, Aziz & Barbon (2024), *Beat the Market: An Effective Intraday Momentum Strategy for SPY*, https://ssrn.com/abstract=4824172
- Gao, Han, Li & Zhou (2018), *Market Intraday Momentum*, JFE, https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2440866
- Baltussen, Da & Soebhag (2025), end-of-day reversal, https://academicweb.nd.edu/~zda/EOD.pdf
- Kaminski & Lo (2014), *When Do Stop-Loss Rules Stop Losses?*, https://papers.ssrn.com/sol3/papers.cfm?abstract_id=968338
- Kaufman's AMA filter rule, as tested by Oxford Capital, https://oxfordstrat.com/trading-strategies/adaptive-moving-average-1/
- arXiv 2605.04004: 14 families of 5-minute momentum signals on MNQ futures; none survived costs out of sample.
- TradingView's `ta` library has had `er()` and `kama()` since v11, https://www.tradingview.com/script/BICzyhq0-ta/

**Caveat on sample size:** 46 sessions and 60–100 trades are too few to separate a real edge from luck. The researchers suggest 150–200 trades or more, which means months of forward paper trading.
