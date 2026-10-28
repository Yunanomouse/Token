# 04 — External tooling and references to validate or improve the engine

Research date: 2026-09-30. Release dates come from the PyPI JSON API (`pypi.org/pypi/<pkg>/json`). Commit dates come from GitHub commit pages fetched with WebFetch. Behaviour claims come from the project's own docs or source (fetched from raw.githubusercontent.com) unless marked *(unverified)*.

Project context: numpy-only runtime; daily rebalancing paper bots (split/dividend re-basing, kill switch, whole shares); 5-minute intraday simulator (next-bar-open fills, slippage, T+1 settled cash, flat by 15:55); indicator "duel" referee with look-ahead detection by truncation; Pine v5 Supertrend port (must equal `ta.supertrend`); browser JS port; runs on a GitHub Actions schedule.

**Principle:** keep the numpy-only runtime. Everything below is either a **test/dev-only dependency** (a cross-check oracle in CI) or a **reference to cite in code comments**.

---

## 1. Backtesting / engine frameworks to cross-check against

### Summary matrix (execution semantics)

| Project | Default market-order fill | Slippage model | Settlement / T+1 | Whole shares | Corporate actions |
|---|---|---|---|---|---|
| **vectorbt (open)** | Same bar at `price` (default close). Next-bar-open means shifting signals yourself and passing `price=open` | `slippage` = % of order price | None | `size_granularity=1` | None (use adjusted data) |
| **vectorbt PRO** (paid, closed) | `price="nextopen"` / `"nextclose"` built in | % slippage | Has cash deposits/withdrawals; no T+1 model *(unverified)* | yes | n/a |
| **backtrader** | **Next bar open** for Market orders; `cheat_on_open` optional | `slip_perc`/`slip_fixed`; applies to open fills only with `slip_open=True`; `slip_match` caps the price at the bar's high/low | None | Integer sizers by default | Not native |
| **zipline-reloaded** | Daily mode: order fills at the **next session's close** | `VolumeShareSlippage` (default 2.5 % of bar volume, `price_impact=0.1`), `FixedSlippage`, `FixedBasisPointsSlippage` | None (cash is immediate) | Integer order amounts | **Yes:** splits (with fractional cash-in-lieu), cash dividends earned on ex-date and paid on pay-date |
| **LEAN / QuantConnect** | Daily data with the market closed: Market order is converted to **MarketOnOpen**, filled at the next open auction | Pluggable `ISlippageModel` | **Default for US equity cash accounts is T+1 at 06:00 ET (trading days)** | Lot size; fractional remainder goes to cash | **Yes:** Raw mode adjusts holdings by `SplitFactor` and credits dividends to cash |
| **NautilusTrader** | Bar data: order submitted in `on_bar` fills **against bar N's close** (no latency model). Bars must be stamped at close (`ts_init`) | `FillModel(prob_slippage)` = one adverse tick, seeded RNG | Venue/account models; no retail T+1 *(unverified)* | Instrument lot size | Not a focus |
| **bt** | Trades at the data price of the rebalance bar (typically close), no next-open | Commission function only | None | **`integer_positions=True` default** | Needs adjusted data |
| **backtesting.py** | **Next bar open** (`trade_on_close=False` default) | `spread` (relative), `commission` (can be a callable) | None | `size >= 1` = whole units; `0 < size < 1` = fraction of equity, floored to units | None |
| **Freqtrade** | Entry at open; exit-signal exits at **open of the next candle** | Custom pricing only | n/a (crypto) | n/a | n/a |

### Details

**vectorbt (open source)** — https://github.com/polakowo/vectorbt · https://pypi.org/project/vectorbt/
- Latest: **1.1.1, 2026-09-26** (1.0.0 2026-04-22, 1.1.0 2026-07-05). Python >=3.11,<3.15. There is now an optional Rust engine (`vectorbt[rust]`).
- Licence: **Apache-2.0 with Commons Clause** (fair-code: no selling the software itself).
- `Portfolio.from_orders` / `from_signals` take `slippage` (% of price), `size_granularity`, `cash_sharing`, and `call_seq='auto'` (sell before buy inside a rebalance group).
- PRO: https://vectorbt.pro/ — proprietary, subscription. Adds `price="nextopen"`, limit orders, leverage, parallelisation. See https://vectorbt.dev/getting-started/upgrade/.
- **How to use it:** as a CI oracle for the daily-rebalance bots. Feed the same signals shifted by one bar with `price=open`, `size_granularity=1`, `slippage=x` and `call_seq='auto'`, then assert that the equity curves match within cents. It cannot check T+1 settlement or corporate actions, so use split-free fixtures.

**backtrader** — https://github.com/mementum/backtrader · docs https://www.backtrader.com/docu/slippage/slippage/
- Latest PyPI **1.9.78.123, 2023-04-19**. Last commits **2023-04-19** (commits page). Effectively **unmaintained / feature-frozen**; the author considers it complete. Licence **GPL-3.0**.
- Forks: `backtrader2/backtrader` is inactive. `smalinin/backtrader_next` and `cloudQuant/backtrader` show recent activity but are unvetted.
- Its fill semantics are the best documented anywhere. Market orders fill at the next bar's open. `slip_open=True` is needed for slippage to apply to those opens, and `slip_match` clamps the fill price to the bar's high/low.
- **How to use it:** borrow the **slippage clamping rule** (a slipped open never goes outside [low, high]) for the intraday simulator. Do not adopt it as a dependency: it is GPL and stale.

**zipline-reloaded** — https://github.com/stefan-jansen/zipline-reloaded · https://zipline.ml4trading.io/
- Latest **3.1.1, 2025-07-19** (Python 3.13 and NumPy 2 support). Since then the commits are mostly Dependabot/CI bumps (latest ~Nov 2025), so it is in **maintenance mode**. Licence **Apache-2.0**.
- The reference implementation for corporate actions in a ledger (see section 3). `Position.handle_split` floors shares and returns the fractional remainder as cash rounded to the cent. `Ledger.process_dividends` earns dividends on the ex-date and pays them on the pay-date. `Order.handle_split` rescales open orders (`amount = int(amount/ratio)`, limit/stop prices × ratio).
- Defaults: `VolumeShareSlippage(volume_limit=0.025, price_impact=0.1)`, `PerShare` commission $0.001/share.
- **How to use it:** port its split/dividend unit-test scenarios (forward split, reverse split with a fractional remainder, dividend with ex-date ≠ pay-date) into your test suite. Heavy install (bundles, calendars), so use it as a design reference rather than a CI oracle.

**LEAN (QuantConnect)** — https://github.com/QuantConnect/Lean · docs https://www.quantconnect.com/docs/v2/
- Very active: commits on **2026-09-30** (commits page). GitHub "Releases" is stale (v2.4.0.1, 2020); versions ship via tags, the `lean` CLI (**1.0.229, 2026-08-28**) and `quantconnect-stubs` (**2026-09-30**). Licence **Apache-2.0**.
- Settlement docs: "The default delayed settlement rule for US Equity and Option trades is T+1 at 6 AM Eastern Time (ET), where T+1 counts trading days." (https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/settlement/key-concepts)
- Corporate actions (https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/corporate-actions): in Raw mode "LEAN automatically adjusts your positions based on the SplitFactor", and "If the post-split quantity isn't a valid lot size, LEAN credits the remaining value to your cashbook". Dividends are added to the cashbook unless the Adjusted/TotalReturn normalization mode is used. The docs also recommend resetting indicators after splits.
- Fills (https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/trade-fills/key-concepts): with daily data, a market order placed while the market is closed becomes MarketOnOpen.
- **How to use it:** the closest match to your semantics (MOO fills, T+1 at 06:00 ET, lot-size remainder to cash). Mirror its settlement timing: sale proceeds become spendable at 06:00 ET on the next trading day, so they are usable at the next open. Mirror its "reset indicators on split" advice too. The LEAN CLI plus Docker is too heavy for CI, but one manual comparison run is feasible.

**NautilusTrader** — https://github.com/nautechsystems/nautilus_trader · https://nautilustrader.io/docs/latest/concepts/backtesting
- PyPI: **1.231.0 (2026-08-02)**, then **2.0.0rc5 (2026-09-15)**, so a **2.0 major release is imminent**. Python 3.12–3.14. Licence **LGPL-3.0-or-later**.
- Bar execution (https://nautilustrader.io/docs/latest/concepts/backtesting/bar-execution): each bar's `ts_init` "must represent the close of the interval"; the path is O→H→L→C, with optional adaptive ordering that visits the extreme nearest the open first. A market order from `on_bar` settles "against the book left at bar N's close".
- Fill model (https://nautilustrader.io/docs/latest/concepts/backtesting/fill-models): `prob_slippage` means "A successful slippage draw moves the fill one tick against the order direction". `random_seed` makes runs reproducible.
- **How to use it:** as a conceptual reference for **bar timestamp discipline**. The 5-minute simulator should label bars by their close time internally, or document that it labels by open time, so that "flat by 15:55" is unambiguous. Its default fill is at the same bar's close, not the next open, so it is not a drop-in oracle for your fills.

**bt** — https://github.com/pmorissette/bt · https://pmorissette.github.io/bt/
- Latest **1.2.3, 2026-09-12**. Active. Licence **MIT**. Source: `Backtest(..., initial_capital=1000000.0, commissions=None, integer_positions=True, ...)`. A recent commit rejects non-monotonic indexes because they could expose future rows.
- **How to use it:** the easiest **whole-share daily-rebalance oracle**. Target-weight rebalancing (`bt.algos.WeighSpecified` + `Rebalance`) with `integer_positions=True` and a commission lambda should reproduce the daily bots' share counts when you feed it the fill-price series.

**backtesting.py** — https://github.com/kernc/backtesting.py · https://kernc.github.io/backtesting.py/doc/backtesting/backtesting.html
- Latest **0.6.6, 2026-07-22**; commits **2026-08-05**. Active. Licence **AGPL-3.0**, which is fine as a test-only tool (not distributed).
- `Backtest(data, strategy, *, cash=10000, spread=0.0, commission=0.0, margin=1.0, trade_on_close=False, hedging=False, exclusive_orders=False, finalize_trades=False)`. Default fill is at the next bar's open.
- **How to use it:** an oracle for **single-symbol intraday** trades. Signal on bar t, fill at the open of t+1, `spread` ≈ your slippage. Compare trade lists, not just P&L. It does not model T+1 cash, so disable settlement in your simulator for the comparison.

**Freqtrade** — https://github.com/freqtrade/freqtrade · https://www.freqtrade.io/en/stable/
- Latest **2026.9, 2026-09-29**. Very active. Licence **GPL-3.0**. Crypto-only.
- Two tools map directly onto your duel referee:
  - `lookahead-analysis` (https://www.freqtrade.io/en/stable/lookahead-analysis/) runs a full baseline backtest, re-runs sliced/truncated backtests per signal, and flags any column that differs. This is **the same truncation method** as your referee. Its documented false positives (callbacks that depend on the pairlist, limit orders) are worth copying into the referee's docs.
  - `recursive-analysis` (https://www.freqtrade.io/en/stable/recursive-analysis/) compares the last-row indicator values across different **startup candle counts**. It catches warm-up sensitivity in recursive indicators such as EMA/RMA/KAMA/Supertrend, which truncation from the end does not catch.
- **How to use it:** add a "recursive/warm-up" check to the referee: compute the indicator on `data[-N:]` for several N and report the relative difference at the last bar. Use it to pick the warm-up length for RMA-based ATR and KAMA.

---

## 2. Indicator reference implementations

### TA-Lib (C library + Python wrapper) — strongly recommended as the test oracle
- Python: https://pypi.org/project/TA-Lib/ · https://github.com/TA-Lib/ta-lib-python. **0.8.1, 2026-09-21**. Licence **BSD-2-Clause**.
- C library: https://github.com/TA-Lib/ta-lib/releases. **v0.8.1, 2026-09-12**. Active again after years of dormancy.
- **Binary wheels bundle the C library** (since 0.6.5) for Linux/macOS/Windows (x86_64, arm64), Python 3.9–3.14, NumPy 2 compatible. A plain `pip install TA-Lib` works in GitHub Actions with no apt build.
- 0.8.x adds ~40 functions, including **`SUPERTREND(high, low, close, timeperiod=10, multiplier=3.0) -> (supertrend, trend:int32)`** and **`ER(real, timeperiod=10)`** (Kaufman Efficiency Ratio), plus `KAMA(real, timeperiod=30)`.
- Its SUPERTREND doc (https://ta-lib.org/functions/supertrend.html) states explicitly: *"TradingView's built-in `ta.supertrend` returns the opposite signs for the same two states, and seeds the other way."* It uses hl2, Wilder ATR, and the same band-ratchet rule as TradingView.
- KAMA (https://ta-lib.org/functions/kama.html): SC = (ER·(2/3 − 2/31) + 2/31)², so fast and slow are fixed at 2 and 30. It has an unstable period, and its seed differs from StockCharts (TA-Lib seeds from the prior price rather than an SMA; see TA-Lib issues #350/#378). Values converge after warm-up.
- Breaking changes in 0.8: BBANDS default period 5→20, PPO/APO default to EMA, and `talib.stream` is now a real streaming API with `handle.update(bar)` / `handle.peek(bar)`.
- **How to use it:** add `TA-Lib` to a `requirements-dev.txt` and write parity tests:
  - ATR vs `talib.ATR`, after warm-up.
  - Supertrend vs `talib.SUPERTREND`, with the sign flipped and warm-up bars skipped.
  - ER vs `talib.ER`.
  - KAMA vs `talib.KAMA`, only where your fast/slow = 2/30, after the unstable period.
  - Use `stream.X(...).peek(bar)` against `update(bar)` as an independent look-ahead probe for the referee.

### pandas-ta — avoid; use pandas-ta-classic only as a secondary cross-check
- `pandas_ta` on PyPI: **0.4.71b0 (2025-09-14)**, a pre-release, Python >=3.12, maintainer now "pta". The original GitHub repo `twopirllc/pandas-ta` **returns 404**. The PyPI history was wiped, the maintainer changed, and the project announced paid releases for businesses and possible archival by July 2026 (search results; https://github.com/xgboosted/pandas-ta-classic/issues/30 discusses the trust/supply-chain concerns).
- **pandas-ta-classic** — https://github.com/xgboosted/pandas-ta-classic · **0.8.32, 2026-09-14**, **MIT**. Active community fork.
- Its `supertrend` (source fetched) ratchets both bands with the TradingView "or" rule. However, its **direction rule differs from TradingView**: it compares close to the *previous* final bands and carries the prior direction. It uses the opposite sign convention (+1 = up), a 7-bar default length, and a warm-up seeded at dir=+1. **It is not an exact `ta.supertrend` oracle.**
- **How to use it:** do not depend on `pandas_ta`. Optionally use pandas-ta-classic for indicators TA-Lib lacks, but treat TradingView's own definition (below) as the authority for Supertrend.

### Other indicator libraries (status)
- `ta` (bukosabino): 0.11.0, 2023-11-02, MIT. Stale.
- `talipp` (incremental/streaming indicators): 2.7.0, 2025-09-09. Useful as a streaming cross-check.
- `stock-indicators` (Python wrapper of the .NET Skender library): 1.3.5, 2025-06-02, Apache-2.0. Needs a .NET runtime.
- `finta` (2021) and `tulipy` (2019): stale.

### TradingView definitions (authoritative for the Pine port)
- Reference manual v6: https://www.tradingview.com/pine-script-reference/v6/ (JS-rendered, so WebFetch could not extract the text; open it in a browser: `ta.supertrend`, `ta.atr`, `ta.rma`, `ta.tr`).
- Support article with the Supertrend calculation (fetched): https://www.tradingview.com/support/solutions/43000634738-supertrend/
  - `basicUpper = hl2 + mult·ATR`, `basicLower = hl2 − mult·ATR`
  - `upper = basicUpper < prev upper or prev close > prev upper ? basicUpper : prev upper`
  - `lower = basicLower > prev lower or prev close < prev lower ? basicLower : prev lower`
  - direction starts as downtrend when ATR starts; `superTrend = up ? lower : upper`
- Reference-manual example code for `ta.supertrend` (reproduced from the manual's `pine_supertrend` example as widely mirrored; the wording matches the support article above):
  ```pine
  pine_supertrend(factor, atrPeriod) =>
      src = hl2
      atr = ta.atr(atrPeriod)
      upperBand = src + factor * atr
      lowerBand = src - factor * atr
      prevLowerBand = nz(lowerBand[1])
      prevUpperBand = nz(upperBand[1])
      lowerBand := lowerBand > prevLowerBand or close[1] < prevLowerBand ? lowerBand : prevLowerBand
      upperBand := upperBand < prevUpperBand or close[1] > prevUpperBand ? upperBand : prevUpperBand
      int _direction = na
      float superTrend = na
      prevSuperTrend = superTrend[1]
      if na(atr[1])
          _direction := 1
      else if prevSuperTrend == prevUpperBand
          _direction := close > upperBand ? -1 : 1
      else
          _direction := close < lowerBand ? 1 : -1
      superTrend := _direction == -1 ? lowerBand : upperBand
      [superTrend, _direction]
  ```
  Key exactness points:
  - direction **−1 = uptrend, +1 = downtrend**
  - `nz()` makes the first prev bands 0
  - the direction test uses the **current** ratcheted bands and `prevSuperTrend == prevUpperBand` (float equality)
  - `na(atr[1])` forces +1 on the first ATR bar
- RMA (`ta.rma`) example code:
  ```pine
  pine_rma(src, length) =>
      alpha = 1/length
      sum = 0.0
      sum := na(sum[1]) ? ta.sma(src, length) : alpha * src + (1 - alpha) * nz(sum[1])
  ```
  The seed is the **SMA of the first `length` values**, not the first value.
- ATR (`ta.atr`): `trueRange = na(high[1]) ? high - low : math.max(high - low, math.abs(high - close[1]), math.abs(low - close[1]))`, then `ta.rma(trueRange, length)`. Bar 0's TR is `high − low`, so the first ATR is at index `length − 1`. **TA-Lib's ATR starts one bar later** (it skips bar 0's TR), so TV and TA-Lib differ during warm-up and converge afterwards.
- **There is no built-in `ta.kama`.** TradingView's official **`TradingView/ta` library** (https://www.tradingview.com/script/BICzyhq0-ta/, **v14, 2025-08-04, Pine v6**) exports `kama()`, `supertrend()`/`supertrend2()`, `atr2()` (series-length ATR), `rma2()`, `frama()`, `t3()` and others. It is useful as the official Pine-side KAMA definition if the project ports KAMA to Pine. (`jmosullivan/TA`, https://www.tradingview.com/script/LYPLUYbl-TA/, is a community library, not official.)

### Kaufman's KAMA — primary definition
- Perry J. Kaufman, *Trading Systems and Methods*, 6th ed., Wiley, 2019-10-22, ISBN 978-1119605355 (https://www.wiley.com/en-us/Trading+Systems+and+Methods,+6th+Edition-p-9781119605393). It was originally introduced in Kaufman's *Smarter Trading* (1995) *(unverified)*.
- Canonical formula (StockCharts ChartSchool, fetched: https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/kaufmans-adaptive-moving-average-kama):
  - `ER = |close − close[n]| / Σ|close − close[1]|` over n = 10
  - `SC = (ER·(2/(2+1) − 2/(30+1)) + 2/(30+1))²`
  - `KAMA = KAMA[1] + SC·(price − KAMA[1])`
  - the first KAMA is an SMA
- Seeds differ between implementations: StockCharts uses an SMA, TA-Lib uses the prior price. The project should **document its seed choice** and test only after convergence against any external oracle.

---

## 3. Corporate-action handling references

| Reference | Split handling | Reverse split / fractional | Dividends |
|---|---|---|---|
| zipline-reloaded `finance/position.py`, `finance/ledger.py`, `finance/order.py` (source fetched) | `new_shares = floor(amount/ratio)`, `cost_basis = round(cost_basis*ratio, 2)` | fractional remainder × new cost basis is **returned as cash, rounded to the cent** | earned on **ex-date** and paid on **pay-date** (`_unpaid_dividends` keyed by pay date); open orders rescaled with `int(amount/ratio)` |
| LEAN docs (fetched) | Raw mode: holdings × `SplitFactor` | invalid lot remainder → **credited to cashbook** | Raw: cash credited; Adjusted/TotalReturn: folded into price; reset indicators after a split |
| Alpaca docs https://docs.alpaca.markets/docs/mandatory-corporate-actions | positions updated at the beginning-of-day process | cash-in-lieu arrives later (after DTC); **GTC orders cancelled on reverse splits**, adjusted on forward splits | `DIV` minus `DIVNRA` withholding. **Alpaca paper accounts do not apply splits/dividends** (forum reports) |
| CRSP (https://leiq.bus.umich.edu/docs/crsp_factor_adjustment.pdf, WRDS https://wrds-support.wharton.upenn.edu/hc/en-us/articles/115003135651) | adjusted price = P/CFACPR; shares = S·CFACSHR | the price factor and share factor can differ (spin-offs, rights) | price factor includes distributions |
| NYSE/FINRA T+1 rule changes (2024) | — | — | since 2024-05-29, **ex-date = record date** for normal cash dividends (NYSE Rule 204.12 amendment; DTCC FAQ https://www.dtcc.com/-/media/Files/PDFs/T2/T1-Dividend-Processing-FAQ.pdf) |

**How to use it:** test the daily bots' re-basing against the zipline algorithm, which uses floor shares and cash-in-lieu rounded to the cent. Include these cases:
- a 1-for-10 reverse split on a non-multiple-of-10 holding
- a 3-for-2 split
- a dividend whose ex-date and pay-date differ, with cash arriving on the pay-date rather than the ex-date if the engine models this; if not, document the simplification
- a pending order across a split, which should be rescaled or cancelled

---

## 4. Pine Script v6 vs v5 and alerting

- Migration guide (fetched): https://www.tradingview.com/pine-script-docs/migration-guides/to-pine-version-6/
- v6 launch post (2024-12-10): https://www.tradingview.com/blog/en/pine-script-v6-has-landed-48830/ — "the upgrades included in Pine v6 do not affect personal or published scripts written in earlier Pine versions" and "All new features from this point onward will be implemented exclusively in the latest Pine version".
- **Is migration required? No.** The v5 script keeps working unchanged. Migrate only to gain new features, for example the `once` block (Aug 2026), `time()`'s `timeframe_bars_back` parameter, and multiline strings (Apr 2026). Release notes: https://www.tradingview.com/pine-script-docs/release-notes/
- v6 breaking changes that could matter for a Supertrend script:
  - `bool` can no longer be `na`; `na()`/`nz()` reject bool
  - no implicit int/float→bool
  - `and`/`or` are **lazy**: functions with history inside `or` conditions may be skipped, which changes `[]` history
  - `const int` division returns a fraction (`5/2 = 2.5`)
  - `transp` removed (use `color.new`)
  - `plot(offset=)` must not be series
  - `timeframe.period` now always has a multiplier (`"1D"`)
  - strategies: `when=` removed, default `margin_long/short` = 100, `strategy.exit` evaluates relative and absolute params together
  - `for` loop bounds are re-evaluated every iteration
  - `request.*` is dynamic by default

  **`ta.supertrend` itself is unchanged.** The in-editor "Convert code to v6" usually suffices.
- Alerts (fetched: https://www.tradingview.com/pine-script-docs/concepts/alerts/):
  - Prefer `alert()` over `alertcondition()`.
  - Use `alert(msg, alert.freq_once_per_bar_close)`, which fires only when the realtime bar closes; or gate on `barstate.isconfirmed` so that intrabar values cannot repaint.
  - Alerts store a **snapshot of the script and inputs** at creation, so after editing the script **delete and recreate the alert**.
  - For `alertcondition`, choose "Once Per Bar Close" in the dialog.
- Strategy-emulator parity (https://www.tradingview.com/pine-script-docs/concepts/strategies/): by default orders fill "on the next available tick", i.e. the **next bar's open**. That matches the Python simulator; keep `process_orders_on_close=false` and set `slippage` (in ticks) and `commission_*` to match the Python costs if you compare a Pine strategy against the simulator.

---

## 5. GitHub Actions scheduling caveats (docs fetched as markdown via the docs.github.com article API)

- Events doc: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
  - "The `schedule` event can be delayed during periods of high loads … High load times include the start of every hour. If the load is sufficiently high enough, some queued jobs may be dropped." → **Schedule off the hour (e.g. minute 17 or 43) and make the bot idempotent and able to catch up** (it must detect a missed or duplicate day from its own state, not from the clock).
  - Scheduled workflows run only from the **default branch** and use the latest commit on it.
  - "In a public repository, scheduled workflows are automatically disabled when no repository activity has occurred in 60 days." The bot's own state commits normally count as activity, but add monitoring anyway (see below). Note that the popular `gautamkrishnar/keepalive-workflow` repo is now **disabled by GitHub staff for ToS violation**; don't use dummy-commit keepalive actions.
  - Minimum interval is 5 minutes.
- **New: timezone-aware cron** (workflow syntax doc https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onschedule):
  ```yaml
  on:
    schedule:
      - cron: '30 5 * * 1-5'
        timezone: "America/New_York"
  ```
  DST spring-forward skips advance to the next valid time. This removes the need for dual UTC crons around DST for a US-market bot. The bot must still check the exchange calendar for holidays and early closes (13:00 ET), since "flat by 15:55" is wrong on half-days.
- Concurrency (https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency):
  - Only one run per group at a time.
  - By default a **new pending run cancels the older pending run**.
  - `cancel-in-progress: true` also cancels the running one, which is **dangerous for a state-committing bot**.
  - **New `queue: max`** allows up to 100 pending runs in order (cannot be combined with `cancel-in-progress: true`).
  - Recommendation: `concurrency: { group: paper-bot-state, cancel-in-progress: false }`, plus `queue: max` if manual `workflow_dispatch` runs can overlap scheduled runs.
- Market calendars for tests / CI:
  - `exchange_calendars` 4.13.2 (2026-03-10, Apache-2.0)
  - `pandas_market_calendars` 5.4.0 (2026-05-27, MIT)

  Both pull in pandas. Use them in CI to **generate a static holiday/early-close table** that is committed to the repo and consumed by the numpy-only runtime.
- Settlement regulation: SEC Rule 15c6-1 amendments; **US equities moved to T+1 on 2024-05-28** (FINRA notice https://www.finra.org/filing-reporting/technical-notice/final-reminder-t-1-settlement-052224). This confirms the simulator's T+1 settled-cash model.

---

## Top 5 concrete actions

1. **Add a `requirements-dev.txt` with `TA-Lib>=0.8.1`** (wheels bundle the C library, so it works in Actions) and parity tests:
   - ATR vs `talib.ATR`, post-warm-up
   - Supertrend vs `talib.SUPERTREND`, with `trend` sign-flipped to TradingView's −1 = up convention
   - ER vs `talib.ER`
   - KAMA vs `talib.KAMA`, post-unstable-period

   Keep numpy-only at runtime.
2. **Encode TradingView's exact `pine_supertrend` / `pine_rma` / `pine_atr` semantics as golden tests.** Cover `nz()` zero-seeded prev bands, `na(atr[1]) → +1`, `prevSuperTrend == prevUpperBand`, the RMA SMA seed, and bar-0 TR = H−L. Compare against a CSV exported from TradingView (chart → Export data) for 2–3 symbols. Do not rely on pandas-ta or its classic fork for Supertrend: their direction logic and signs differ.
3. **Add a "recursive/warm-up" mode to the duel referee** (after Freqtrade's `recursive-analysis`) next to the existing truncation look-ahead check. Compute each indicator on `data[-N:]` for N in {1×, 2×, 5×, 10×} its lookback and report the last-bar relative difference. Use the result to set warm-up lengths for RMA/KAMA/Supertrend.
4. **Harden the corporate-action ledger against zipline's and LEAN's model.** Test a reverse split with fractional cash-in-lieu (floor shares, cash rounded to the cent), a forward split with open-order rescaling or cancellation, and a dividend whose ex-date and pay-date differ, with ex-date = record date since 2024-05-29. Cross-check the whole-share daily rebalance against `bt` (`integer_positions=True`) or vectorbt (`size_granularity=1`, `call_seq='auto'`, signals shifted one bar with `price=open`) on split-free fixtures.
5. **Fix the Actions scheduling details:**
   - use `timezone: "America/New_York"` on the cron at an off-hour minute
   - `concurrency: {group: <bot>, cancel-in-progress: false}`
   - idempotent catch-up logic keyed on the last processed session
   - a committed exchange-calendar table (holidays + 13:00 early closes, generated in CI with `exchange_calendars`) so that "flat by 15:55" becomes "flat 5 min before close"
   - a staleness alarm, e.g. a workflow step or issue if the last state commit is more than 3 trading days old, to catch the 60-day auto-disable or dropped runs

   The Pine v5 script needs **no forced v6 migration**. If alerts are used, switch to `alert(..., alert.freq_once_per_bar_close)` and recreate alerts after every script edit.
