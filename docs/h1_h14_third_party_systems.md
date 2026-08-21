# H1–H14 Verdicts and Third-Party System Support Audit

Cross-reference of the Trading Bot Evidence Ledger (hypotheses H1–H14) against the
third-party systems the trading stack actually depends on, with each system's real
support status verified from source: the `openbb-trader` codebase and the upstream
`lightpanda-io/browser` repository on GitHub.

## 1. H1–H14 — every hypothesis and its verdict

H1–H5 cover the swing rotation strategy; H6–H14 cover the scalp/intraday family.
Each protocol was pre-registered before its run and unedited after.

| ID | What was tested | Verdict | Key evidence |
|------|----------------|---------|--------------|
| H1 | Efficiency-ratio market selection | Not supported | ρ=+0.34, p=0.096, n=25; classified 24 of 25 markets as tradeable |
| H2 | Momentum rotation beats SPY | **Supported** | Beat benchmark within the risk bound, in both eras |
| H3 | Momentum survives robustness | **Supported** | 91.7% of 24 parameter cells beat SPY; tolerates 20 bps costs |
| H4 | Dual-momentum absolute filter | Not supported | Drawdown improved +0.00pp |
| H5 | Momentum at $131 per holding | Not supported | Plateau 50%; wins 1 of 3 regimes; breakeven 10 bps |
| H6 | TJL top-25 ticker selection | Not supported | 39.8th percentile of 2,000 random draws; 13,007 trades |
| H7 | TJL intraday breakout gate | Not supported | −0.62pp expectancy; target hit 0.73% vs 2.91%; 5,791 trades |
| H8 | Crabel prior-day conditioning | Not supported | All 4 conditions negative |
| H9 | Live scanner composite score | Not supported | ρ = −0.01644 (inverse), p=7.8e−206, 3,468,938 bars |
| H10 | Relative-volume scalp signal | Not supported | 0 of 90 cells positive net of cost; grid mean −0.102% |
| H11 | Cross-sectional market-neutral fade | **Supported** | +1.081%/day gross; 17 of 18 cells positive — but only 59 dates |
| H12 | The fade, out of sample | Not supported | Point estimate replicated (+1.119%) but CI [−0.089, +0.711] on 30 dates |
| H13 | The fade on 729 trading days | Not supported | Breakeven collapses 27.0 → 7.45 bps/leg; 0 of 15 cells positive |
| H13b | Timing, or a recent regime? | Neither | 10:30 keeps 80% of 10:00; only 1 of 12 windows reaches H11 — the oldest |
| H14 | The fade at $655 of capital | Not supported | Negative gross at 5 names; max drawdown −91.7%; P(DD>20%) = 100% |

Score: **2 of 15 passed** (H2, H3 — the swing momentum rotation), and that strategy
is blocked by capital (~$770 per holding), not by evidence. Every scalp and intraday
hypothesis failed on the merits.

## 2. Third-party systems inventory

The live estate spans three trees; only two modules can reach a broker
(`tradingview.py → execute_trade` on the desktop stack, `questrade.py → place_order`
in `openbb-trader`). The third-party systems those trees depend on:

| System | Role | Support status |
|--------|------|----------------|
| Kraken | Crypto quotes + WebSocket v2 live ticks | **Working** — keyless public API, 24/7 |
| Lightpanda | Headless browser used to scrape TradingView | **Not fully supported** — beta upstream (see §3) |
| TradingView | News flow + technical ratings + order UI | **No official support** — scraped, no API, no key; MOC orders unavailable |
| Questrade | Broker (REST + browser session) | **Not operational** — unauthenticated, `LIVE_TRADING_ENABLED` defaults false; no broker-native stop (open defect) |
| Telegram | Primary alert channel | Degrades to disabled — token unset in `.env.example` |
| Slack | Alert mirror | Degrades to disabled — webhook unset |
| LSE data | Candles, insiders, options flow, COT | Degrades to disabled — key unset |
| Reuters | News wire | **No public RSS since 2020** — proxied via Google News RSS |
| Bloomberg | News wire | Working — official public RSS |
| Reddit | Social buzz | **Blocks direct JSON** — proxied via ApeWisdom |
| FINRA | Short interest | Partial — short % of float unavailable (`collector.py`) |
| Yahoo / yfinance / OpenBB | Quotes, movers, fundamentals | Working but throttled/lagging free feeds; per-symbol fallback |
| FRED / Nasdaq / CFTC | Macro, earnings, COT | Working — public feeds |
| Flipboard | Discovery topic feeds | Working — public topic pages |
| Ollama (local LLM) | Nightly AI analysis | Working with `qwen2.5:7b-instruct` only — `qwen3:8b` returns empty content; OmniRoute gateway configured but inactive |
| exchange_calendars | NYSE holiday-aware scheduling | Optional — falls back to weekday hours if missing |
| Obsidian | Research-note mirror | Working — local file writes |
| Windows tray app | Serves the dashboard | **Not in the repo**; `autostart.ps1` points at the wrong directory (blocked), watchdog restarted the tray instead of the engine — 307 of 332 restarts failed |

## 3. Lightpanda ("lightbear") — what upstream GitHub says

From `lightpanda-io/browser`'s own README:

- **Beta**: "Lightpanda is in Beta and currently a work in progress… You may still
  encounter errors or crashes."
- **CORS is not supported** — the one unchecked feature, open issue
  [#2015](https://github.com/lightpanda-io/browser/issues/2015).
- **Incomplete Web API coverage**: "There are hundreds of Web APIs… Coverage will
  increase over time."

And what the trading code itself records about running on it:

- `newsflow.py` — current Lightpanda nightlies **silently ignore sessionless CDP
  commands** ("every evaluate came back None until this was added"); the TradingView
  news page is a JS SPA that hydrates slowly, so extraction retries up to 4 times and
  can still come back empty.
- `tv_ratings.py` — "Lightpanda unavailable — skipping TradingView ratings": the
  whole ratings feed disappears when the browser fails.
- Codebase audit — the Lightpanda subprocess can orphan on the `start_server()`
  timeout branch.

## 4. Conclusion

The unsupported systems and the unsupported hypotheses line up. Everything the
"Not supported" verdicts depend on — TradingView signals (H9), the TJL system
(H6–H7), Crabel conditioning (H8), the fade at the broker (H13–H14) — runs on
third-party paths that were never on solid support: scraping through a beta browser
with incomplete Web API coverage, an unauthenticated broker with no native stop
orders, and proxied news feeds. The only fully supported keyless integration is
Kraken, and the only strategy with a supported verdict (H2/H3 momentum rotation) is
blocked by account size, not by its evidence or its integrations.
