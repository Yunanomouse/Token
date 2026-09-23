# Handoff: where the quantum trading project stands

Written 2026-09-23 so a new Claude Code session can pick up without the old
chat. Read this first, then `README.md` and `docs/quantum_trading.md`.

## The owner and what they want

The owner is not a programmer. They want a trading program that uses quantum
methods, that they can click on and watch, and that runs live. They have
repeatedly been stuck installing things, so prefer anything that works from a
link or a single download. Explain in plain words and give numbered steps.

Everything is **paper trading** unless the owner switches it. The broker
code exists (`quantum/alpaca.py`, `--broker alpaca`, repository variable
`QT_BROKER`); it defaults to Alpaca's paper endpoint, and real money needs
both `ALPACA_BASE_URL` set to the live endpoint and `QT_ALLOW_REAL_MONEY=yes`.
Steps are in `live/README.md`. Never ask for API keys in chat (they go in
GitHub repository secrets), and never flip the real-money settings for the
owner.

## Where everything is

| What | Where |
|---|---|
| Code, tests, docs | this repo, branch `claude/day-trading-quantum-programs-7iy790` |
| Pull request | https://github.com/Yunanomouse/Token/pull/4 (draft; base `claude/canada-tax-system-data-e7jmyx`, the repo default) |
| Web app (live bot view + simulator) | https://claude.ai/artifact/Tb8tESAdEPUkv6sRbmfGTK |
| Windows installer and desktop zips | https://github.com/Yunanomouse/Token/releases/tag/desktop-latest |
| Live bot's state | `live/` (written by the bot, see below) |

## What exists

- `quantum/` — the package: statevector simulator, amplitude estimation,
  QUBO solvers (annealing, bifurcation, QAOA, subspace QAOA, Grover search),
  portfolio / pricing / risk / arbitrage, walk-forward backtest, noise model
  with published hardware error rates, OpenQASM 3 export, QOBLIB benchmark
  reader, the live engine (`live.py`), the local dashboard (`desktop.py`),
  and the CLI (`python -m quantum --help`).
- `web/` — the browser version: `engine.js` is a port of the engine that
  must match Python to the cent (tested); `build.py` rebuilds
  `quantum-trading.html` from `template.html` and the bundled prices.
- `packaging/` + `.github/workflows/desktop-app.yml` — standalone desktop
  app for Windows, macOS and Linux and a Windows installer, built and
  published to the `desktop-latest` release on pushes that change the app.
- `.github/workflows/live-bot.yml` + `scripts/fetch_prices.py` — the live bot.
- `.github/workflows/tests.yml` — the test suite on Python 3.10-3.12.

## How the live bot works

1. After each US close (21:30 UTC weekdays) the `live bot` workflow fetches
   real adjusted closes (Stooq, then Yahoo), runs the engine over new bars,
   and commits `live/state.json`, `live/snapshot.json` and
   `live/snapshot_prices.json`. Commits come from `quantum-trading-bot` and
   only touch `live/`; pull them before pushing.
2. A routine on the owner's account, "Sync live bot to dashboard"
   (weekdays 22:15 UTC, fresh session), copies those two snapshot files into
   the web app's database (`bot/status`, `bot/prices`) with ArtifactData.
   Only the owner can write them.
3. The web app's Live bot tab reads them and re-runs the same engine in the
   browser to confirm the numbers match.

`live/config.json` sets the stocks and rules. `trade_from` is 2026-09-23:
earlier bars are warm-up only. As of this note the bot has warmed up on two
years of prices through 2026-09-21, holds $100,000 in cash, and has made no
trades yet.

**Blocker only the owner can clear:** GitHub runs scheduled workflows only
from the default branch, so the daily bot does not run until PR #4 is merged.
Until then it runs only when `live/config.json`, the workflow, or the fetch
script is pushed.

## What the evidence says (keep saying it)

- On synthetic data the optimiser lost to equal weight. On real 2006-2018
  prices it beat equal weight (t = +2.14), but the stock list was picked in
  hindsight. On an 8-year paper replay it made 16.9%/yr against equal
  weight's 17.3%/yr.
- On the QOBLIB benchmark (710 variables, proven optimum) the heuristic
  solvers fall far short.
- The quantum speedup for pricing needs about 1e-4 error per gate; current
  commercial hardware is roughly ten times worse.
- Nothing here predicts prices. Do not claim it makes money.

## Environment notes

- The old sessions ran with **Trusted** network access: PyPI and GitHub
  work, market-data sites do not. The owner is creating an environment with
  **Full** (or Custom) access. First thing in a new session: check you can
  reach `stooq.com` and `query1.finance.yahoo.com`.
- A PR check-in routine ("Re-check Token PR #4") is bound to the old
  session. If that session is archived, create a new check-in from the new
  session.

## Offered next steps (owner has not chosen yet)

1. Run exported circuits through **Qiskit** and compile them for real IBM
   hardware to get true gate counts.
2. Solve the QOBLIB instances exactly with **HiGHS** or **OR-Tools**.
3. Try **D-Wave's open-source sampler** on the QOBLIB instance the solvers
   failed.
4. Run the **larger QOBLIB instances** (up to 400 stocks).

Checks before any push: `python -m pytest tests -q` (209 tests pass as of
this note), and `python web/build.py` after changing `web/` or the engine.
