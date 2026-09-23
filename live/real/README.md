# The $40 bot

A second bot next to the main one. It runs the **same tested engine and
rules** (strategy, 252-day look-back, monthly rebalance, 25% kill switch,
re-arm after 63 days). The main 8-stock paper bot in `live/` is unchanged
and keeps its record.

What is different, and why:

| Setting | Main bot | $40 bot | Why |
|---|---|---|---|
| Money | $100,000 | $40 | the owner's real budget |
| Stocks | AAPL, XOM, JPM, WMT, PFE, AMZN, BAC, T | F, NOK, VALE, ITUB, SNAP, PCG, HBAN, KEY | whole shares must fit in $20 |
| Picks | best 4 | best 2 | $40 across 4 buys no whole shares |
| Max in one stock | 40% | 50% | follows from 2 picks |
| Shares | fractional | whole only | Questrade sells whole shares |
| Cash kept aside | 0% | 3% | limit prices sit 1% above the close |

## Two rules for small accounts

A $50 test month (Aug 24 to Sep 23, 2026) put only $9.96 to work and left
80% in cash. Two rules did that, and both are now changed for this bot:

- `"deploy_from_cash": true`: the 50% turnover cap is skipped when the
  book is almost all cash, so the first buy goes all the way to the target.
  The cap still limits every later swap between stocks.
- `"fill_leftover": true`: after rounding down to whole shares, the money
  rounding left behind buys one more share of the stock furthest below its
  target, if it fits the budget, the 3% cash reserve and the 50% cap.

Tested from 46 start dates over the past year (Sep 2025 to Aug 2026, one
every 5 trading days):

| Money | Invested in month 1, before / after | Average 1-month return, before / after | Average return to Sep 23, before / after |
|---|---|---|---|
| $40 | 16% / 76% | +1.05% / +2.28% | +5.97% / +5.88% |
| $50 | 20% / 74% | +1.57% / +2.96% | +1.51% / +2.70% |
| $100 | 37% / 89% | +1.52% / +2.98% | +0.16% / +3.11% |

Being invested means taking the market's moves both ways. On the $50 test
month itself the new rules bought 2 NOK and 1 VALE, and VALE then fell:
the account ended at $50.12 instead of $50.67, after reaching $52.53.

## The paper/live switch

In `config.json`, the first line:

    "mode": "paper",

- `paper`: the bot simulates its trades. `orders.json` is for information.
- `live`: the same simulation runs, and every trading day `orders.json`
  lists the orders to place at Questrade the next morning.

To change it: open `live/real/config.json` on GitHub, click the pencil,
change `paper` to `live` (keep the quotes), and commit. That also runs the
bot once.

## Placing the orders

Nothing places orders by itself. On your computer, run
`tools/tradingview_orders.py`. It opens TradingView on each order's stock,
shows what to do, and on request types the shares and limit price into the
order panel. You pick Buy or Sell and click it yourself.

The bot's book assumes its orders filled at the close. If you skip an
order, or it does not fill, the bot does not know, so place them all or
tell Claude to reconcile the book.

Limit prices are 1% past the close: a small overnight move still fills, a
big one does not. A missed day is never traded late.

Everything in this folder is public, because the repository is public.
