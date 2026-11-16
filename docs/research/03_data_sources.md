# 03 — Free / cheap US market-data sources (checked 2026-09-30)

Context: Python (stdlib + numpy) paper-trading bots running daily on GitHub Actions. Today they use
Yahoo's unofficial `v8/finance/chart` endpoint: daily adjusted closes for bots of about 8 tickers, and 5-minute bars for 58 US tickers.
Yahoo has limits: 5m history goes back only about 60 days and 1m about 7 days, it returns an unfinished bar for today, it rewrites adjusted history, and it returns HTTP 429.
The user is in Canada. Stooq cannot be reached from the runner.

All pages were fetched or searched on **2026-09-30** unless another date is given. "Verified" means I read the vendor's own page or
docs, or probed the endpoint. "Secondary" means the claim comes from a third-party page or forum and should be re-checked before
anyone depends on it.

---

## 0. Short version

| Need | Best free option | Why | Cheap paid step-up |
|---|---|---|---|
| (a) Daily OHLCV, adjusted, plus corporate actions | **Tiingo free (EOD)**, with **Alpaca free** as the second source | Tiingo: 30+ years; each row has raw and adjusted OHLCV plus `divCash` and `splitFactor`; 1,000 requests/day. Alpaca: `adjustment=raw/split/dividend/spin-off/all` plus a `/v1/corporate-actions` endpoint | Tiingo Power $30/mo; EODHD Historian $19.99/mo |
| (b) Intraday 1m/5m with years of history | **Alpaca free (Basic) with `feed=sip`**, where the query ends more than 15 minutes before now | Consolidated SIP bars from 2016, all timeframes (1Min, 5Min, …), up to 10,000 bars per page, 200 requests/min, adjustment options | FirstRate Data or Kibot one-off purchase; Databento ($125 free credits); Massive Starter $29/mo (5 years) |
| (c) Real-time or 15-min-delayed quotes for paper trading | **Alpaca free**: real-time IEX feed, or SIP delayed 15 minutes | The same key and account as (b). Paper-only accounts are open to Canadians | Alpaca Algo Trader Plus $99/mo (real-time SIP) |

**Licensing**: **none** of the commercial APIs below allow you to commit their raw data to a *public* GitHub repo. This covers
Alpaca, Massive/Polygon, Tiingo, Twelve Data, FMP, EODHD, Finnhub, Marketstack, Alpha Vantage and Yahoo. The only verified
exception is **IEX HIST**: free exchange data that you may redistribute if you credit IEX with the required text (§2.14).
Databento's *US Equities Mini* is sold with "free redistribution rights", but I did not read the licence document itself. The
practical pattern is to keep raw vendor data in a **private** repo, a private storage bucket or the Actions cache, and commit
only derived outputs such as signals, trades and P&L.

---

## 1. Comparison table

Legend: **Key** = needs an API key. **Hist** = history depth. **Public-repo OK?** = may raw data be committed to a public repo.

| Source | Key | Free-tier rate limit | Free daily hist | Free intraday | Adjustment / corp actions | Real-time on free | Public-repo OK? | First paid tier |
|---|---|---|---|---|---|---|---|---|
| **Alpaca Market Data** (Basic) | Yes (paper account; email only) | 200 req/min; 10,000 bars/page | Since 2016 | 1m…1D since 2016; **SIP allowed if query ends more than 15 min before now**, IEX real-time | `adjustment=raw/split/dividend/spin-off/all`; `/v1/corporate-actions` | IEX real-time (REST + WS, 30 symbols); SIP 15-min delayed | **No** | Algo Trader Plus $99/mo (real-time SIP, 10k req/min) |
| **Massive (ex-Polygon.io)** Basic | Yes | **5 calls/min** | 2 years | Minute aggs, 2 years, EOD only; up to 50,000 rows/request | `adjusted=true` (default) is split-only; splits and dividends endpoints | No (EOD) | **No** ("individual use only") | Starter $29/mo (5 yrs, 15-min delayed, unlimited calls) |
| **Tiingo** Starter | Yes | 50 req/hr, 1,000 req/day, 500 unique symbols/mo, 1 GB/mo | 30+ years | IEX-sourced intraday since Aug 2017 (per-request row cap reported, see §2.3) | EOD rows have adj OHLCV + `divCash` + `splitFactor` | IEX real-time REST/WS | **No** ("internal use only") | Power $30/mo ($300/yr) |
| **Alpha Vantage** | Yes | **25 req/day** | `TIME_SERIES_DAILY` compact (100 pts) only | **None**: intraday is now premium | `DAILY_ADJUSTED` is premium | No | No | $49.99/mo (75 req/min) |
| **Twelve Data** Basic | Yes | 8 credits/min, 800/day | Yes | 1m, starts 2020-02-10 in support-article example; 5,000 pts/request | See their "Are prices adjusted?" article | "Real-time US equities" advertised | **No** (personal/internal) | Grow $29/mo (55/min) |
| **Financial Modeling Prep** Basic | Yes | 250 calls/day | ~5 yrs EOD (secondary) | None (paid) | Adjusted EOD + dividends/splits endpoints | No | No | Starter ~$22/mo annual (secondary; site returned 403 to me) |
| **EODHD** Sandbox | Yes | 20 calls/day | 1 year | None (intraday needs Active Trader) | EOD `adjusted_close`; intraday is **raw only** | No | No (personal use) | Historian $19.99/mo; Active Trader $29.99/mo (intraday; US 1m since 2004) |
| **Finnhub** Free | Yes | ~60 calls/min | Candles moved to premium (secondary) | No | — | Real-time US quotes, WS 50 symbols (secondary) | No | ~$50/mo (secondary) |
| **Marketstack** Free | Yes | 100 req/**month** | 1 year | No | — | No | No | Basic $9.99/mo (10k/mo); sub-15-min intraday only on Professional $49.99/mo. US data comes from Tiingo |
| **Nasdaq Data Link** | Yes | — | WIKI is frozen (2018); EOD/Sharadar are paid | No | Sharadar SEP is split-adjusted plus dividends | No | No | Sharadar/QuoteMedia subscriptions (low hundreds USD/mo range, secondary) |
| **IEX Cloud** | — | **Shut down 2024-08-31** | — | — | — | — | — | — |
| **Databento** | Yes | Pay-as-you-go | EQUS.SUMMARY daily | XNAS.ITCH from 2018-05-01; EQUS.MINI from 2023-03-28 | Raw; adjustment factors sold separately | Only with a plan | EQUS.MINI: "free redistribution rights" (vendor claim); others need a licence | **$125 free credits** (6-month expiry); Standard $199/mo includes all US-equity OHLCV-1s/1m history |
| **FirstRate Data** | No (download) | — | Since 2000 | 1m/5m/30m/1h since 2000, split+div adjusted | Adjusted (unadjusted available) | No | Not stated → assume no | Tick $49.95/ticker; S&P 500 bundle from $299.95; Russell 3000 from $399.95; updates $79.95/mo |
| **Kibot** | No (download) | — | Since 1998 | 1m (plus 5/15/30m) since 1998 | Unadjusted, split-only and split+div sets | No | Not stated → assume no | All-stocks 1m $3,000 one-off; all stocks+ETFs $4,200 |
| **Stooq** | **Captcha API key since ~2026-04-01** | Daily-hits cap | Decades | Bulk 5-min holds ~last 2,000 points (~1 month) | — | No | No terms granting it | Free (but unreachable from the runner) |
| **Yahoo / yfinance** | No | Undocumented; 429s | Decades | 5m ≈ 60 days, 1m ≈ 7 days | `adjclose` + events; history gets rewritten | ~Real-time | **No** (ToS bans automated access and redistribution) | n/a |
| **IEX HIST (exchange)** | No | — | — | Tick pcap (TOPS/DEEP) since 2016-12, T+1 | Raw | No | **Yes, with the required attribution** | Free; ~12 GB/day (TOPS, 2026) |
| **FINRA / SEC** | No | — | No prices | No | — | — | FINRA/SEC public data: generally yes | Free |

---

## 2. Per-source notes

### 2.1 Alpaca Market Data — https://alpaca.markets/data , https://docs.alpaca.markets/docs/about-market-data-api (verified)
- **Plans** (docs table): *Basic (free)*: equities feed "IEX" for real-time; historical "Since 2016" with the restriction "latest
  15 minutes"; **200 requests/min**; WebSocket **30 symbols**. *Algo Trader Plus ($99/mo)*: all US exchanges (SIP),
  historical "no restriction", 10,000/min, unlimited WS symbols. The marketing page says: free = "15 minute delay via API",
  "7+ years".
- **Free plan and SIP history**: data **older than 15 minutes is available on every feed**, including `feed=sip`. A free
  account that asks for the most recent 15 minutes of SIP data gets "subscription does not permit querying recent SIP data".
  Source: Alpaca community forum ("IEX or SIP with a free account", "Historical Data API"). The bars reference says the default
  `end` is "15 minutes before the current time" when you lack real-time access, which matches.
- **Bars endpoint** `GET https://data.alpaca.markets/v2/stocks/bars`: `symbols` (comma-separated, multi-symbol),
  `timeframe` (1Min, 5Min, …, 1Day, 1Week, 1Month), `start`/`end` (RFC-3339 or date), `limit` (default 1,000, **max 10,000**),
  `adjustment` = `raw | split | dividend | spin-off | all`, `feed` = `iex | sip | boats | otc`, `asof`, `page_token`, `sort`.
- **Corporate actions**: `GET https://data.alpaca.markets/v1/corporate-actions`. Types include forward/reverse splits,
  cash/stock dividends, spin-offs, mergers, name changes and more. A 2026-06-03 changelog added global corporate actions and ISIN fields.
- **Account**: anyone, anywhere, can open a **paper-only account with just an email**. Canadians cannot open *live*
  brokerage accounts, but paper plus market data works (Alpaca forum "Market data for Canadians?"; Alpaca learn "start paper
  trading"). The key and secret come from the paper dashboard. Reachability: `data.alpaca.markets` answered 401 without a key
  from this sandbox, so it is reachable.
- **Licence**: the customer agreement says you may not "reproduce, distribute, sell or commercially exploit the market data …
  without written consent", and includes the Nasdaq/NYSE subscriber agreements. **Not OK for a public repo.**
- **Sizing for this project**: 58 tickers × 10 years × ~78 regular-session 5m bars/day ≈ 11.4M bars, or about 1,150 pages of
  10k bars. At 200 requests/min that is about 6 minutes for a one-time backfill, and the daily increment is trivial.
- **Unfinished bar**: set `end = now − 16 min` (needed for SIP anyway). For daily bars, only ask for `end` ≤ the last completed
  session date, or drop a bar whose date is today while the market is open.
- Reliability: a first-party documented API with an SLA-style status page. Free IEX-only bars have **thin volume and gaps** on
  illiquid names, so use `feed=sip` for backtests.

### 2.2 Massive (formerly Polygon.io; renamed 2025-10-30) — https://massive.com/pricing (verified)
- Stocks plans: **Basic free**: 5 calls/min, **2 years** history, **EOD** data, minute aggregates ✓, no WebSockets, corporate
  actions ✓. **Starter $29/mo**: unlimited calls, 5 yrs, 15-min delayed, WS, flat files. **Developer $79**: 10 yrs, plus trades.
  **Advanced $199**: 20+ yrs (since 2003-09-10), real-time. 20% off with annual billing. "Individual use only".
- Aggregates: `GET https://api.massive.com/v2/aggs/ticker/{T}/range/{mult}/{timespan}/{from}/{to}`. `adjusted` defaults to
  true and covers **splits only** (dividends are not applied). Max `limit` is 50,000. Reachable from this sandbox (401 without a key).
- Terms: the market-data ToS forbids copying, republishing or redistributing "to any other computer, server, website … for
  publication", and derived works. **Not OK for a public repo.**
- Useful free fallback: 2 years of 5m history for 58 tickers is roughly 150 requests. At 5/min that is about 30 minutes, once.

### 2.3 Tiingo — https://www.tiingo.com/about/pricing , https://www.tiingo.com/products/iex-api (verified)
- **Starter (free)**: 50 req/hour, 1,000 req/day, **500 unique symbols/month**, **1 GB/month**, EOD 30+ years, IEX feed ✓, news ✓.
  **Power**: $30/mo or $300/yr; 10k req/hr, 100k/day, 40 GB/mo. **Business**: $50/mo. The licence on every tier is
  "**Internal use only** … you may not display or share the data with another person or organization". **Not OK for a public repo.**
- EOD endpoint rows carry raw `open/high/low/close/volume`, `adjOpen…adjVolume`, `divCash` and `splitFactor`. That gives you
  corporate-action events at no extra cost. Tiingo's own advice: when `splitFactor != 1` or `divCash > 0`, re-download the full
  history. EOD data only covers finished sessions, so you never get an unfinished bar.
- IEX intraday: the product page says "Intraday data from **August 2017**", with resampling (`resampleFreq=5min`), REST and
  WS. Tiingo adds its own fill-in for illiquid names. Volume is IEX-only. Caveat: older library docs (riingo, tiingo-python
  issue #117) describe a **per-request cap of the latest ~2,000 rows**. I could not confirm the current cap because the docs are
  a JS app. Treat long-history pulls as "chunk by date and test".
- Changelog: 2025-01-10 changes for the IEX market-data policy effective 2025-02-01. 2026-07-21 BOATS overnight API
  (+$9/mo, not on Free). 2026-09-08 "API limits" UX work.

### 2.4 Alpha Vantage — https://www.alphavantage.co/premium/ , /documentation/ (verified)
- Free: **25 requests/day**. `TIME_SERIES_INTRADAY` is now marked "**premium endpoint**". `TIME_SERIES_DAILY_ADJUSTED` is premium.
  Only `TIME_SERIES_DAILY` compact (last 100 points) works on free.
- Premium: $49.99/mo (75 req/min) up to $249.99 (1,200/min), no daily cap. Intraday supports `month=YYYY-MM` back to 2000-01,
  plus `adjusted` and `extended_hours`. Real-time or 15-min-delayed US data needs a separate entitlement step.
- Verdict: no longer useful for free.

### 2.5 Twelve Data — https://twelvedata.com/pricing (verified)
- Basic free: **8 API credits/min, 800/day**, 3 markets, "real-time US equities and ETFs" advertised. Grow $29/mo (55/min,
  no daily cap). Pro $99 (610/min). Ultra $329. Licence: "personal, internal, and non-commercial purposes". Redistribution needs
  a custom deal.
- Support article: `outputsize` max 5,000. In their example, 1-minute OHLC is "available only from **February 10, 2020**".
- Verdict: fine for quotes; 800/day is too few for a 58-ticker intraday backfill.

### 2.6 Financial Modeling Prep — https://site.financialmodelingprep.com/pricing-plans (HTTP 403 to both fetcher and curl; secondary)
- Basic free: **250 calls/day**, EOD only, ~5 years. Starter ≈ $22/mo (annual): 300/min, 5 yrs, US. Premium ≈ $59/mo: 750/min,
  30 yrs, intraday. Ultimate ≈ $149/mo: 1-minute intraday, bulk. Source: FMP's search snippet plus third-party reviews. Re-check
  on the site.

### 2.7 EODHD — https://eodhd.com/pricing , https://eodhd.com/financial-apis/intraday-historical-data-api (verified)
- Sandbox free: **20 calls/day**, 1 year of EOD. Historian $19.99/mo (100k/day, 1,000/min, 30+ yrs EOD). Active Trader
  $29.99/mo adds intraday. All-In-One $99.99.
- Intraday: intervals 1m/5m/1h. Max window per request: 120 days (1m), 600 days (5m), 7,200 days (1h). **US 1m back to 2004**;
  5m/1h only from Oct 2020. **Intraday is raw and not back-adjusted** ("does not retroactively adjust"). It is finalized about
  2–3 hours after the close. They say it is aggregated from "100+ sources".
- Licence: personal use; commercial plans are separate.

### 2.8 Finnhub — https://finnhub.io/pricing (JS page, not readable; secondary: apicostcalc.com, verified 2026-08-15)
- Free: ~60 calls/min, real-time US quotes, WS up to 50 symbols. Historical **stock candles return 403 on free** (moved to
  premium). Personal, non-commercial use. Paid ~$50/mo and up.
- Verdict: usable for a live quote (`/quote`), not for history.

### 2.9 Marketstack — https://marketstack.com/pricing (verified)
- Free: **100 requests/month**, 1 year. Basic $9.99/mo (10k/mo, 10 yrs). Intraday below 15 minutes only on Professional
  ($49.99) and above. US data is "licensed and sourced from Tiingo". Not competitive.

### 2.10 Nasdaq Data Link — https://data.nasdaq.com (JS pages; secondary)
- The free WIKI prices dataset is frozen (last updated 2018). Current US prices are premium: QuoteMedia EOD, and Sharadar SEP
  (split-adjusted OHLCV plus dividends, active and delisted names since 1998–2000). There is no free intraday data. Only worth it
  if you need survivorship-free fundamentals.

### 2.11 IEX Cloud — **shut down 2024-08-31** (announced 2024-05-31)
- Sources: Alpha Vantage and Massive migration guides, and the api-evangelist archive. Former executives relaunched the assets as
  "Blue Sky Data" (Sept 2024), which I did not evaluate. Remove from consideration.

### 2.12 Databento — https://databento.com/pricing , /equities , blog posts (verified)
- **$125 free credits** for historical data, expiring after 6 months. Pay-as-you-go historical data "from $0.40/GB". Actual
  OHLCV examples cost more: EQUS.SUMMARY ohlcv-1d for 1 year of all US stocks costs $4.38 (157 MB), and XNAS.ITCH costs $3.78
  (135 MB). That works out to about $28/GB for OHLCV.
- Rough estimate: 58 tickers × 5 yrs of regular-session 1m bars ≈ 28M records × 56 B ≈ 1.6 GB, or roughly $45. That fits inside
  the free credits (use `metadata.get_cost` first to confirm).
- Plans: **Standard $199/mo** includes "unlimited access to the entire history of OHLCV-1s/-1m … for US equities" (since the
  Jan-2025 plan change). Plus $1,750/mo and Unlimited $4,500/mo require annual contracts.
- Datasets: XNAS.ITCH (Nasdaq TotalView) since 2018-05-01. **EQUS.MINI** since 2023-03-28 is sold with "zero license fees,
  free redistribution rights". Databento US Equities (consolidated) "since 2018". Bars are **raw**; adjustment factors are a
  separate product.
- Licence: "Redistribution rights depend on the dataset". EQUS.MINI is the one they market as redistributable. Read the
  dataset licence before committing anything. Needs a Python client or HTTP API plus a key. Good data quality.

### 2.13 FirstRate Data — https://firstratedata.com (verified in part)
- 1m/5m/30m/1h/1D bars for about 16k US stocks, **from Jan 2000 to present**, "adjusted for splits/dividends", extended hours
  included, updated daily by 23:45 ET. Free 2-week samples for every ticker.
- Prices (secondary, via Datarade and search snippets): S&P 500 components 1m from $299.95; Russell 3000 (15 yrs) from $399.95;
  tick data $49.95/ticker. Bundle updates cost **$79.95/mo** after one free month. The bundle page shows no licence text, so
  assume no redistribution.
- Reliability: an EliteTrader user benchmarked it against a firm's reference data and found a good match back to about 2010.

### 2.14 Kibot — https://www.kibot.com (buy page returned 503 on fetch; product pages via search)
- All stocks 1m (18k+ symbols, including delisted, **since 1998**): **$3,000 one-off**. Stocks + ETFs: $4,200. Includes the 5/15/30m
  resolutions, and unadjusted, split-adjusted and split+dividend-adjusted sets. There are smaller packages (S&P 500 set) and
  per-symbol purchases, but I could not load their prices. It has a free sample and an HTTP API for updates.

### 2.15 Stooq — https://stooq.com/db/h/ (503 on fetch; secondary)
- **An API key obtained via captcha has been required since about 2026-04-01** (qf-localc README), with daily-hit limits. Bulk
  `db/h` ZIPs hold daily data (long history), hourly (about the last 1,400 points) and 5-min (about the last 2,000 points, roughly
  1 month). There are no clear redistribution terms. It is unreachable from the runner anyway, so drop it.

### 2.16 Yahoo Finance / yfinance — https://github.com/ranaroussi/yfinance , PyPI
- yfinance is active: 1.0 (2025-12-22) → 1.7.0 (2026-08-26). Releases in 2026 handled curl_cffi breakage (1.5.2), price-repair
  fixes for splits, and Yahoo login (1.4.0).
- 2025–2026 reports: persistent `YFRateLimitError` from data-centre and non-US IPs (TradingAgents #1425, 2026-09-27, Singapore,
  more than 48 hours with no recovery). A GitHub Actions project (ayushganatra3-del/trader PR #2, 2026-09-24) got 429 "for every
  symbol" with a plain HTTP client and fixed it by switching to yfinance, which impersonates a browser TLS fingerprint via curl_cffi.
- **My own probe from this cloud sandbox (2026-09-30)**: Python `urllib` with the **default User-Agent → HTTP 429**. The same
  request with a **browser User-Agent → HTTP 200**. The same held for curl. So a large share of the project's 429s is probably
  the `Python-urllib/3.x` UA. Set a realistic UA header. This is a stdlib-only fix, and it may not survive Yahoo's future changes.
- Terms: Yahoo's ToS forbid automated collection without permission. The data is licensed from exchanges. **Not OK to
  redistribute or commit publicly.** Keep it only as a fallback.

### 2.17 IEX HIST (free exchange data) — https://iextrading.com/api/1.0/hist?date=YYYYMMDD (probed), terms https://www.iex.io/legal/hist-data-terms (verified)
- Free, T+1, pcap.gz tick files (TOPS top of book plus trades, DEEP, DEEP+) back to Dec 2016. **Size**: 2017-01-03 TOPS was
  0.7 GB; **2026-09-25 TOPS was 12.0 GB** (DEEP 12.7 GB). Too heavy to process daily in pure Python on Actions, though a one-off
  backfill on a bigger machine is possible.
- **Licence**: redistribution is allowed if you cite: "Data provided for free by IEX. By accessing or using IEX Historical Data,
  you agree to the IEX Historical Data Terms of Use." This is the only verified source whose bars (derived from IEX trades) could
  sit in a public repo.
- Caveat: IEX is only a few percent of consolidated volume, so its 5m bars are sparse and noisy on anything but liquid names.

### 2.18 SEC / FINRA free datasets
- FINRA Reg SHO daily short-sale volume: `https://cdn.finra.org/equity/regsho/daily/CNMSshvolYYYYMMDD.txt`. I probed it (HTTP
  200, fields Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market). It is a free signal source, not prices.
- SEC EDGAR (`company_tickers.json`, XBRL frames; requires a descriptive User-Agent) is useful for ticker↔CIK mapping and
  fundamentals. SEC MIDAS market-structure metrics are aggregate. **Neither provides OHLCV.**

### 2.19 Academic / other free intraday
- WRDS/TAQ requires an institutional subscription. Kaggle and Hugging Face "US 1-minute" dumps vary in provenance and licence,
  and are often scraped from vendors, so they are not safe for public redistribution or for backtest integrity. There is no free,
  licence-clean, consolidated multi-year 1m US dataset. IEX HIST is the closest.
- Canadian broker APIs such as Questrade, or IBKR Canada via TWS, give intraday history to account holders. They need a funded
  account and a gateway, and fit poorly with GitHub Actions. Not evaluated in depth.

---

## 3. Practical guidance for this project
1. **Yahoo 429 fix today**: send a browser `User-Agent` header in `urllib.request.Request`. Add jittered retry/backoff and a
   per-run circuit breaker.
2. **Intraday history**: backfill 5m (or 1m) bars with Alpaca `feed=sip`, `adjustment=raw`, `end=now-16min`, and paginate
   with `page_token`. Store raw bars, then apply splits yourself from `/v1/corporate-actions` so history never silently changes.
3. **Daily**: Tiingo EOD (raw + adj + `divCash`/`splitFactor`). The ~8-ticker bots use far less than the 500 symbols/month and
   1,000 requests/day limits. Cross-check with Alpaca daily bars (`adjustment=all`).
4. **Keys**: store them as GitHub Actions secrets (`ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY`, `TIINGO_TOKEN`).
5. **Public repo**: do not commit vendor OHLCV. Keep it in a private data repo, the Actions cache or a private bucket. Commit
   only derived signals and results. The one exception is IEX-HIST-derived bars, which you may commit with the attribution.

## Sources
- Alpaca: https://docs.alpaca.markets/docs/about-market-data-api ; https://alpaca.markets/data ; https://docs.alpaca.markets/reference/stockbars ; https://forum.alpaca.markets/t/iex-or-sip-with-a-free-account/17141 ; https://forum.alpaca.markets/t/market-data-for-canadians/11916 ; https://docs.alpaca.markets/us/reference/corporateactions-1 ; https://files.alpaca.markets/disclosures/library/AcctAppMarginAndCustAgmt.pdf
- Massive: https://massive.com/pricing ; https://massive.com/docs/rest/stocks/aggregates/custom-bars ; https://massive.com/terms/market_data_terms.pdf
- Tiingo: https://www.tiingo.com/about/pricing ; https://www.tiingo.com/products/iex-api ; https://www.tiingo.com/documentation/general/changelog ; https://github.com/hydrosquall/tiingo-python/issues/117
- Alpha Vantage: https://www.alphavantage.co/premium/ ; https://www.alphavantage.co/documentation/
- Twelve Data: https://twelvedata.com/pricing ; https://support.twelvedata.com/en/articles/5656039-how-to-get-historical-prices
- FMP: https://site.financialmodelingprep.com/pricing-plans (403) ; https://www.findmymoat.com/tools/financial-modeling-prep-fmp
- EODHD: https://eodhd.com/pricing ; https://eodhd.com/financial-apis/intraday-historical-data-api
- Finnhub: https://apicostcalc.com/finnhub.html
- Marketstack: https://marketstack.com/pricing
- IEX Cloud: https://www.alphavantage.co/iexcloud_shutdown_analysis_and_migration/ ; https://github.com/api-evangelist/iex-cloud
- Databento: https://databento.com/pricing ; https://databento.com/equities ; https://databento.com/blog/upcoming-changes-to-pricing-plans-in-january-2025 ; https://databento.com/blog/databento-us-equities-mini-now-available ; https://news.ycombinator.com/item?id=45516154
- FirstRate: https://firstratedata.com/cb/4/complete-stocks-etf ; https://datarade.ai/data-products/s-p-500-components-historical-intraday-dataset-firstrate-data ; https://www.elitetrader.com/et/threads/firstratedata-quality.357596/
- Kibot: https://www.kibot.com/historical-data/all-stocks-1-minute-intraday-data.html
- Stooq: https://github.com/qalydon/qf-localc/blob/master/README_STOOQ.md ; https://www.quantstart.com/articles/an-introduction-to-stooq-pricing-data/
- yfinance: https://pypi.org/project/yfinance/ ; https://github.com/TauricResearch/TradingAgents/issues/1425 ; https://github.com/ayushganatra3-del/trader/pull/2 ; https://legal.yahoo.com/us/en/frontier/terms/otos/index.html
- IEX HIST: https://iextrading.com/api/1.0/hist ; https://www.iex.io/legal/hist-data-terms ; https://github.com/vargaconsulting/iex-download
- FINRA: https://cdn.finra.org/equity/regsho/daily/
