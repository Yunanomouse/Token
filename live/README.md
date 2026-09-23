# The live paper bot

Everything in this folder is written by `.github/workflows/live-bot.yml`, which
runs the engine after each US market close on real prices:

| File | What it is |
|---|---|
| `config.json` | The bot's settings. Edit this to change what it trades. |
| `prices.csv` | Daily adjusted closes, re-fetched every run (Stooq, Yahoo fallback). |
| `state.json` | The engine's book and history; the run resumes from it. |
| `snapshot.json`, `snapshot_prices.json` | What the dashboard shows, and the prices it re-checks against. |

The bot is **paper only**: fills at the close, no broker, no real money.
`trade_from` is the first day it may trade; the year of prices before it is
warm-up for the estimates, so the book starts in cash on that day rather
than back-filling trades it never made.

Scheduled GitHub jobs run only from the repository's default branch, so the
daily schedule starts once this code is merged there. Until then, run it by
hand from the Actions tab ("live bot" > "Run workflow") or by pushing a
change to `live/config.json`.
