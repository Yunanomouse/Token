# Indicator duel: Claude vs Codex (started 2026-09-29)

Claude and Codex each build one trading indicator. Both are scored by the
same referee, on the same bars, under rules written down before any result
was seen. Everything is **paper**: no indicator here places an order.

- **Referee:** `quantum/signals.py` (the rules) and `scripts/indicator_duel.py` (the scorer).
- **Claude's entry:** `indicators/claude.py` (Python) and `pine/claude_supertrend.pine` (TradingView).
- **Codex's entry:** `indicators/codex.py` and `pine/codex_*.pine`, when submitted.
- **Reference:** `indicators/kama_baseline.py`, the live intraday bot's own KAMA rule.

## The rules (pre-registered 2026-09-29)

**What an indicator is.** A Python file with numpy as its only dependency.
It defines `NAME`, `TIMEFRAME` (5, 15, 30 or 60 minutes) and optional
`PARAMS`. It also defines `signals(bars, **PARAMS)`:

- **Input:** one stock's bars, several sessions in a row. These are numpy
  arrays `datetime`, `open`, `high`, `low`, `close` and `volume`.
- **Output:** two true/false arrays of the same length:
  - `entry`: go long.
  - `exit`: get out.
- **No look-ahead:** the signal on bar *t* may use only bars up to *t*. The referee checks this by cutting
  the history short and seeing whether any earlier signal changes. If one does, the indicator fails.

**How it trades.** Every entry trades on the live $50 intraday bot's engine and account (`quantum/intraday.py`):

- **Fills:**
  - A signal is filled at the next bar's open, 0.1% against you.
  - An exit signal while flat does nothing, and so does an entry signal while already long.
- **Stocks:** each day, the five most volatile stocks you can afford, ranked on the previous day's range. These come from the 58 stocks in `live/intraday/universe.txt`.
- **Account:**
  - $50, long only, whole shares.
  - 70% of the account per position, one position at a time.
  - Sale money is unusable until the next session (T+1).
- **Limits:**
  - At most 6 entries a day.
  - No new entries from 15:30.
  - Everything is closed by 15:55.

The indicator decides *when*; the engine decides everything else, the same for everyone.

**The data.** Yahoo 5-minute bars for the 58 stocks. Complete sessions from
2026-07-07 through 2026-09-28 (59 sessions) are frozen in the scorer's cache.
They are not in the repository, because the data belongs to Yahoo. They are split as follows:

| Window | Sessions | Use |
|---|---|---|
| Warm-up | first 10 (Jul 7 – Jul 20) | indicator and screen warm up, no trading |
| Training | 29 (Jul 21 – Aug 28) | tune here, and only here |
| Test | last 20 (Aug 31 – Sep 28) | scored once, after the pick is locked |
| **Forward** | **Sep 30 – Oct 27, 2026** | **decides the duel**: nobody had seen it when the rules were written |

**Pass bar.** On the test window, all of the following must hold:

1. Made money on the test window, and on the training window.
2. Made money in each half of the test window.
3. Still made money at 0.25% per side, instead of 0.1%.
4. Beat at least 90% of 40 random-entry runs. The random runs have the same entries per day, holding times drawn from the indicator's own, and the same costs.
5. Made at least 30 test trades.
6. Showed no look-ahead.

**Who wins.** Whoever has the higher return on the forward window, once it has happened.

- **Why forward:** the frozen test window was published in this file, so from now on it is no longer clean for anyone.
- **Deadline:** Yahoo keeps 5-minute bars for about 60 days, so the forward window must be scored by **2026-12-15**.
- **Command:** `python3 scripts/indicator_duel.py --fetch --forward indicators/claude.py indicators/codex.py`.

## Round 1: Claude's entry

**How it was picked.**

- **Candidates:** 20 configurations of five indicators, each with its published or standard settings and a small grid. All are in `indicators/research/claude_candidates.py`:
  - Kaufman's KAMA
  - VWAP reversion
  - Supertrend
  - a volume surge
  - an efficiency-ratio breakout
- **Scored on training only:** `indicators/research/search_train.py`, with results in `train_results.json`.
- **Pick rule, fixed before the run:**
  - Eligible if it made at least 40 training trades and made money in each half of training at 0.1%.
  - Among the eligible, take the highest training return at 0.25% per side.

**The pick: Supertrend, ATR 10 × 3.0, on 5-minute bars.**

- **The indicator:** long while the Supertrend is up, out when it turns down. It is TradingView's `ta.supertrend`, bar for bar. The tests check this against a line-by-line copy of TradingView's formula.
- **Why it won:** it was the only configuration that met the eligibility bar. Training: +27.1% on 43 trades, +8.9% and +14.9% in the two halves, +17.6% at 0.25% costs.

**Then the test window was opened, once:**

| | Training | Test | Test halves | Test at 0.25% | Beats random | Passed |
|---|---|---|---|---|---|---|
| **Claude: Supertrend 5m** | +27.1% (43 trades) | **−7.5%** (39 trades, 33% won) | −3.8% / −4.1% | −10.8% | 2% | **no** |
| KAMA baseline (live bot) | +11.0% (59 trades) | −0.7% (45 trades, 42% won) | +2.7% / −2.0% | −5.2% | 65% | no |

**It failed every money gate.** The pick stays locked as Claude's entry:
changing it after seeing the test would mean choosing on the test data.

**What the other 19 did on test** (looked at only after the pick was locked, for information):

| Candidate | Training | Test |
|---|---|---|
| KAMA 30m, k = 1.0 | −5.8% | **+6.3%** |
| KAMA 30m, k = 0.5 | −2.5% | +5.3% |
| VWAP reversion 15m, z = 1.5 | +2.7% | +2.5% |
| VWAP reversion 5m, z = 1.5 | −9.4% | +1.6% |
| Supertrend 5m ×3 (**pick**) | **+27.1%** | **−7.5%** |
| Supertrend 15m ×2 | +16.6% | −9.6% |
| ER breakout 15m, ER > 0.3 | +11.1% | −5.1% |
| ER breakout 5m, ER > 0.5 | −15.1% | −12.9% |

Seven of the 20 made money on test. Across all 20, training return had essentially **no link** to test
return (rank correlation −0.16). The best configurations in training were trend-followers; July and
August trended, and September chopped, so the trend-followers lost and the mean-reversion ones gained.
**Choosing the best of 20 on one month and a half picked the one most fitted to that stretch.** This is
the same finding as `docs/intraday_research.md` and `docs/quant_methods_survey.md`: on these stocks,
at this account size and these costs, nothing tried so far beats random entries out of sample.

## Brief for Codex (copy everything below this line)

---

You are the second contestant in an indicator duel. The repository is
https://github.com/Yunanomouse/Token, branch `claude/affectionate-cray-p71bnw`.
Read `docs/indicator_duel.md` and `quantum/signals.py` first: they are the
rules, and they are not up for change.

**Your task.** Build one intraday trading indicator for the live $50 paper bot's engine and submit two files:

1. **`indicators/codex.py`**
   - Defines `NAME`, `TIMEFRAME` (5, 15, 30 or 60) and `PARAMS`.
   - Defines `signals(bars, **PARAMS) -> {"entry": bool array, "exit": bool array}`.
   - Uses numpy only.
   - The signal on bar *t* uses bars up to *t* only; the referee checks this.
2. **`pine/codex_<name>.pine`**
   - The same indicator in Pine Script v5 for TradingView, drawing the same entries and exits.

**Rules you must keep:**

- **Tune on the training window only (Jul 21 – Aug 28, 2026).** The test window's results for Claude's candidates are published in the doc; do not use them. The duel is decided on the forward window (Sep 30 – Oct 27, 2026), which nobody has seen.
- **Do not change the engine, the referee, the account or the costs:**
  - `quantum/intraday.py`
  - `quantum/signals.py`
  - `live/intraday/config.json`
- **Paper only.** Add no broker code, and send no orders anywhere.
- **Say what you tried:** in the file's docstring, list every configuration you tried and the rule you used to pick, so multiple testing can be judged.

**How to check your work:**

```bash
pip install -e ".[test]"
python3 scripts/indicator_duel.py --fetch indicators/codex.py indicators/claude.py   # training/test report
python3 -m pytest tests/test_signals.py -q                                           # the contract tests
```

`--fetch` downloads the 5-minute bars from Yahoo into `~/duel_data/`.
Yahoo's window rolls, so your earliest sessions may differ slightly from the
frozen set. The official score is run by the referee on the frozen cache
and, for the forward window, on data fetched after Oct 27.

---

## How to score

```bash
python3 scripts/indicator_duel.py --bars ~/duel_data/bars_5m.csv indicators/claude.py indicators/codex.py
python3 scripts/indicator_duel.py --fetch --forward indicators/claude.py indicators/codex.py   # after 2026-10-27
```
