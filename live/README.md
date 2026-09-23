# The live bot

Everything in this folder is written by `.github/workflows/live-bot.yml`, which
runs the engine after each US market close on real prices:

| File | What it is |
|---|---|
| `config.json` | The bot's settings. Edit this to change what it trades. |
| `prices.csv` | Daily adjusted closes, re-fetched every run (Stooq, Yahoo fallback). |
| `state.json` | The engine's book and history; the run resumes from it. |
| `snapshot.json`, `snapshot_prices.json` | What the dashboard shows, and the prices it re-checks against. |

`snapshot.json` carries a `pnl` block: gains and losses by average cost,
rebuilt from every fill in `state.json` on each run. Each sale shows what it
locked in (`realized_pnl` on the fill), each open holding its average cost
and paper gain, and `round_trips` lists every position from entry to full
exit with its result. A buy's fee is part of its cost and a sell's fee comes
off its proceeds, so locked-in plus open always equals the account's change
since the start.

By default the bot is **paper only**: fills at the close, no broker, no real
money. It can instead send its orders to Alpaca; see "Switching from paper
trading" below. If the account falls 25% from its peak (`max_drawdown`) the bot sells
everything, waits 63 trading days in cash (`rearm_after`), then starts again
with the fall measured from where it is.

`trade_from` is the first day it may trade; the year of prices before it is
warm-up for the estimates, so the book starts in cash on that day rather
than back-filling trades it never made.

Scheduled GitHub jobs run only from the repository's default branch, so the
daily schedule starts once this code is merged there. Until then, run it by
hand from the Actions tab ("live bot" > "Run workflow") or by pushing a
change to `live/config.json`.

## Switching from paper trading

The code that does this is `quantum/alpaca.py`. Nothing in the code needs
editing: the switch is made in the repository's GitHub settings, so keys
never sit in a file or a chat.

**Step 1, Alpaca's paper account (fake money, real orders).** Do this first
and leave it running for weeks.

1. Open an account at https://alpaca.markets (check that your country is
   supported), then open its **Paper Trading** dashboard and generate API
   keys. Do not paste them anywhere except step 2.
2. On GitHub: repository **Settings > Secrets and variables > Actions**.
   Under **Secrets**, add `ALPACA_API_KEY_ID` and `ALPACA_API_SECRET_KEY`.
3. On the same page under **Variables**, add `QT_BROKER` = `alpaca`.
4. Actions tab > "live bot" > "Run workflow". The log says
   `broker: Alpaca PAPER account (fake money)`, and orders appear in
   Alpaca's paper dashboard.

**Step 2, real money.** Only when you decide to, after step 1 has run long
enough to trust:

1. Generate keys in Alpaca's **live** dashboard and replace the two secrets.
2. Add the variables `ALPACA_BASE_URL` = `https://api.alpaca.markets` and
   `QT_ALLOW_REAL_MONEY` = `yes`. Either one alone is refused.
3. Lower `initial_cash` in `config.json` to the most you are willing to
   lose: the bot never uses more than that, whatever the account holds.

To go back to paper, delete the `QT_BROKER` variable (or set it to `paper`).

What the broker code guarantees:

- It only ever trades the tickers in `config.json` and never touches
  anything else in the account.
- It only sends orders for today's bar; missed days are caught up on paper
  but never traded late.
- It will not send a second order for a stock while an earlier one is open.
- Market orders go in after the close and fill at the next open, so the
  fill price differs from the close the bot planned on. The next run reads
  the real holdings back from Alpaca.
- With a broker, the web page's re-check says "cannot match to the cent"
  instead of confirming, because real fills are not paper fills.

Switch while the bot holds only cash (as it does until its first trade on
or after `trade_from`), so the paper history and the Alpaca account agree.
