# The live paper bot

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

The bot is **paper only**: fills at the close, no broker, no real money.
If the account falls 25% from its peak (`max_drawdown`) the bot sells
everything, waits 63 trading days in cash (`rearm_after`), then starts again
with the fall measured from where it is.

`trade_from` is the first day it may trade; the year of prices before it is
warm-up for the estimates, so the book starts in cash on that day rather
than back-filling trades it never made.

Scheduled GitHub jobs run only from the repository's default branch, so the
daily schedule starts once this code is merged there. Until then, run it by
hand from the Actions tab ("live bot" > "Run workflow") or by pushing a
change to `live/config.json`.
