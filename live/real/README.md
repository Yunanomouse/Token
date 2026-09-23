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
