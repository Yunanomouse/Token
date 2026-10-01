---
name: token-trading-house-rules
description: House rules and working checklist for the Token / Quantum Trading repository (paper trading bots, the $100k / $40 / $50 bots, Quantum Station, the indicator duel, backtests, price fetching, the desktop and web dashboards). Use this skill for ANY task in this repo, and whenever the user asks about trading bots, brokers, going live, real money, API keys, backtest or strategy results, indicators, Quantum Station, or pushing changes here, even if they don't name the skill. It sets the safety limits (paper only, no broker automation), the honesty rules for reporting results, and the verify-before-push routine.
---

# Token / Quantum Trading: house rules

This repository is the user's paper-trading project: three bots (a $100k daily
bot, a $40 whole-share daily bot, a $50 5-minute intraday bot), an indicator
"duel" referee, backtest tools, a desktop dashboard, a browser page, and
Quantum Station (`quantum/local.py`), which runs everything on the user's own
Windows PC. The user is not a programmer by trade: explain in plain words,
lead with the answer, and show evidence (numbers, test counts, commit ids).

## 1. Safety limits (settled; do not reopen them)

These were decided by the user after long discussion. Respect them without
re-arguing, and don't keep suggesting alternatives they already declined.

- **Paper trading only.** Never change a bot to real money: the `"mode"`
  line in `live/real/config.json` stays `"paper"`, never set
  `QT_BROKER=alpaca` with real-money variables, never add `--live`.
  Quantum Station strips every broker variable and passes `--broker paper`
  to each job; keep it that way in any change (`paper_env()` in
  `quantum/local.py`).
- **No broker automation.** Do not build or help build anything that places
  orders at a real broker by scripting a website or app: no browser
  automation of Questrade (or any broker), no clicking through a trading
  UI, nothing designed to avoid a broker's detection or terms. The $40 bot
  writes `orders.json` for a *person* to place by hand; that is the line.
  If asked, decline briefly, say why (it breaks the broker's terms and
  risks the account and real money), and offer what is in bounds: paper
  results, the hand-placed order list, analysis.
- **Don't push other brokers.** The user said no to switching brokers
  (moomoo, IBKR and similar). Don't recommend one; if a question is about
  costs or rules, give facts without steering to a broker.
- **API keys never go in chat or in the repo.** Never ask the user to paste
  a key. Keys go in GitHub repository secrets (for the workflow) or in
  Windows user environment variables (for Quantum Station): `FMP_API_KEY`,
  `TWELVEDATA_API_KEY`, `STOOQ_API_KEY`, `ALPACA_*`. If a key appears in a
  file the user shares, tell them to remove and rotate it.
- **Personal details stay private.** Don't send the user's email or other
  details to outside services (for example in a request header).

## 2. Honesty rules for results

The project's research found that, after costs, nothing tried so far beats
random entries out of sample. Reports must not flatter.

- **Name the period and whether it is in-sample.** A result on the data the
  settings were tuned on is a check of the machinery and costs, not
  evidence of an edge; say so in the same sentence as the number.
- **Compare with the baselines**: random entries with the same trade count
  and holding times (`random_baseline`), and equal weight of the same
  stocks for the daily bots (`quantum/evaluation.py`).
- **The duel's rules are pre-registered.** `quantum/signals.py` fixes
  TRAIN, TEST and FORWARD dates and a flat 10 bps cost; don't change them
  for the current round, and never re-pick an entry after seeing the test.
  Unofficial tests (Quantum Station's "Test the indicators") must be
  labelled unofficial.
- **Costs are part of the result.** The intraday config charges price-based
  slippage (`tick_slippage`, `open_slippage_mult`, `min_price`); quote
  results with the costs that were used.
- **Small samples are inconclusive.** Tens of trades or 20 sessions cannot
  show an edge (docs/research/02_overfitting_methods.md); say "too early"
  rather than implying skill.
- Report failures plainly: a failed test, a skipped step, a bug found in
  your own earlier work.

## 3. Data rules

- Daily prices come from `scripts/fetch_prices.py`: one source per run for
  every ticker (vendors adjust history differently, and a basis change
  reads as a split or dividend to the engine's re-basing), and today's bar
  is dropped until 16:30 New York so an intraday price is never stored as a
  close. Keep both properties in any change.
- The GitHub repository is public, and vendors' terms forbid
  republishing their data. Never commit downloaded bar files (intraday
  bars, research caches); keep them in `local_data/` or a scratch folder.
  The workflow commits `live/*/prices.csv`; whether to keep that public is
  an open decision for the owner (`live/README.md`). When it comes up, for
  example when a keyed source such as FMP starts serving those files, say
  that the vendors' free-plan terms forbid republishing and that a private
  repository or an Actions cache avoids it, and let the owner decide. Bot state, snapshots and
  results are fine to commit.
- A run during market hours must not change the bots' state with partial
  data; if it ever does, roll the state back before the next run.

## 4. Running things

- Tests: `python3 -m pytest tests -q` (TA-Lib parity tests need the test
  extra: `pip install -e ".[test]"`). Lint: `python3 -m pyflakes quantum
  scripts tests indicators station.py`.
- Quantum Station: `python -m quantum.local` (port 8777), or
  `Quantum Station.bat` on Windows; `python -m quantum.local --home <dir>
  run daily` runs one job. Use a scratch `--home` when testing, never the
  user's `local_data/`.
- GitHub bot: `.github/workflows/live-bot.yml`. A push touching
  `scripts/fetch_prices.py`, `live/config.json`, `live/real/config.json` or
  the workflow file starts a real paper run on that branch: push those only
  after the market's 16:30 New York cutoff or when the cutoff logic is in
  place, and expect a bot commit you must pull before pushing again.
- The web page is generated: after editing `web/template.html` or
  `web/engine.js`, run `python3 web/build.py` and commit the output.

## 5. Before every push

1. Run the full test suite and pyflakes; both clean.
2. For a bug fix, show the failure on the old code first (a test that fails
   before and passes after).
3. Re-read your diff for anything that would loosen section 1.
4. Commit with a clear message ending in the attribution lines this session
   specifies (don't put model names in commits), push to the session's
   branch, and keep the pull request open as a draft unless told
   otherwise.
5. Tell the user what changed, the evidence (tests, numbers), what you did
   not verify (for example, Windows-only behaviour you couldn't run), and
   the commit id.

## Where things are

- Bots and engine: `quantum/live.py`, `quantum/intraday.py`, configs in
  `live/` and `live/intraday/`.
- Quantum Station: `quantum/local.py`, `quantum/local_page.html`,
  `station.py`, `docs/station.md`.
- Duel: `quantum/signals.py`, `scripts/indicator_duel.py`, `indicators/`,
  `docs/indicator_duel.md`.
- Research and its recommendations: `docs/web_research.md` and
  `docs/research/`.
