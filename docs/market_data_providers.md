# Market data without Yahoo Finance

The original quickstart in this repo pulled prices through OpenBB's
`yfinance` provider. This document explains why that is a weak foundation,
what replaced it, and what each replacement is actually good for.

Everything below was tested live on 2026-09-24. Results that could not be
verified from the test machine are labelled as such rather than asserted.

## Why move off Yahoo

Yahoo Finance has no public API. `yfinance` works by calling the endpoints
that back Yahoo's own web pages, with a browser-shaped request. That gives it
four problems that matter for anything you file a tax return on:

1. **No agreement to rely on.** Yahoo retired its official finance API in
   2017. What remains is intended for personal use, and yfinance's own
   documentation says it is "not affiliated, endorsed, or vetted by Yahoo"
   and is "intended for research and educational purposes". Commercial use
   or redistribution is squarely in grey-area territory. There is no
   documented rate limit to design around because there is no documented
   contract at all — and so no commitment that tomorrow's response looks
   like today's.
2. **It breaks without warning.** The library's issue tracker is a running
   log of endpoint changes, cookie/crumb authentication being added, and
   sudden 401/429 storms. Those breakages land on whatever you built on top.
3. **It is an aggregate, not a print.** Yahoo's `BTC-USD` is a blended
   composite across venues. It is nobody's actual fill. For Canadian
   reporting, where you need a defensible price on a specific date, an
   unattributable blend is the wrong input.
4. **Canadian coverage is second class.** `SHOP.TO` is a re-publication of
   the TSX line, and its history has gaps around Canadian market holidays and
   corporate actions that the exchange's own feed does not have.

None of this means Yahoo returns garbage most days. It means you cannot tell
which days it does.

## What replaced it

The `marketdata` package in this repo talks to seven sources. Five need no
account at all. It depends only on the Python standard library — no pandas,
no OpenBB, no install step.

| Source | Covers | Key | Verified 2026-09-24 |
|---|---|---|---|
| **TMX Group** | TSX / TSX-V equities and ETFs, priced in CAD | no | ✅ working |
| **Kraken** | Crypto OHLCV, incl. native `BTC/CAD`, `ETH/CAD` | no | ✅ working |
| **Coinbase Exchange** | Crypto OHLCV | no | ✅ working |
| **Bank of Canada** | Daily FX, policy rate, benchmark bond yields | no | ✅ working |
| **Statistics Canada** | All-items CPI (bracket indexation input) | no | ✅ working |
| **Nasdaq** | US equities and ETFs | no | ⚠️ blocked from cloud IPs |
| **Stooq** | Global equities, indices, FX | no | ⚠️ blocked from cloud IPs |
| **Alpha Vantage** | US equities with adjusted close | free key | ✅ working |
| **Tiingo** | Curated US EOD, keeps delisted tickers | free key | not tested (no key) |

### The ones worth singling out

**TMX Group** is the company that operates the Toronto Stock Exchange. Asking
it for `SHOP` returns the CAD prints from the Toronto book — the actual
Canadian line, not a converted copy of the US listing. For a Canadian trader
this is strictly better than `SHOP.TO` from an aggregator.

**Kraken's CAD pairs** are real order books. `BTC/CAD` is a price Canadians
actually traded at, not a USD price multiplied by an exchange rate afterwards.
When you need an adjusted cost base in Canadian dollars, starting from a CAD
print removes a conversion — and a source of argument — entirely.

**Bank of Canada** is the source the CRA itself points at for converting
foreign-currency amounts. Taking the rate from the central bank rather than
from a quote vendor means the number on your return matches the number the CRA
would look up if it checked.

**Statistics Canada** publishes the CPI that drives bracket indexation. The
repo's tax dataset was assembled partly by applying indexation factors by
hand; `marketdata.canada.cpi_all_items()` lets that be checked against the
actual series.

### Network caveat, stated plainly

Nasdaq and Stooq both appear to throttle or block datacentre IP ranges.
From the cloud container these were developed in, Nasdaq served a handful of
requests and then began closing connections without a response, and Stooq reset
the connection immediately. **Both are expected to work from an ordinary home
or office connection**, which is where you would actually run this. That is
why `scripts/check_providers.py` exists — run it on your own machine and build
on whatever it says is green there, rather than trusting this table.

The keyless US-equity gap this leaves is why Alpha Vantage and Tiingo are
included. A free key takes about twenty seconds to get, and unlike Yahoo,
both have a published terms of service that permits what you are doing.

## Cross-checking: the part that beats a single feed

A single source cannot tell you when it is wrong. Two independent sources can.

```bash
python3 -m marketdata crosscheck kraken=BTC/USD coinbase=BTC-USD \
  --start 2026-06-01 --end 2026-09-20
```

```
====================================================================
Cross-check  coinbase:BTC-USD / kraken:BTC/USD
====================================================================
  coinbase        112 bars  2026-06-01 -> 2026-09-20  (USD)
  kraken          112 bars  2026-06-01 -> 2026-09-20  (USD)

  Overlapping trading days: 112
  Median spread 0.78bp   max 4.25bp

  PASS - every shared close agrees within 10 basis points.
```

Two exchanges that never spoke to each other agree on every close to under
half a basis point in the median case. That is a result you can act on. The
same command against a feed with a missed split would show a persistent ~50%
offset instead, and a stale feed would show up in the coverage-gap lines.

`--strict` makes it exit non-zero when the tolerance is breached, so it can
run in CI or a cron job as a data-quality gate.

## What this does not do

- **No intraday or tick data.** Everything here is daily bars. Sub-minute data
  from a free source that also permits redistribution does not really exist;
  if you need it, budget for Databento or Polygon.
- **No adjusted close on the keyless sources.** Nasdaq, TMX, Kraken and
  Coinbase return raw prints. `Bar.adj_close` is `None` for those rather than
  a silent copy of `close`, so you can always tell the difference. Alpha
  Vantage and Tiingo do provide a true adjusted series.
- **No fundamentals.** SEC EDGAR's XBRL API (`data.sec.gov`) is free, keyless,
  and works from a datacentre as long as you send a `User-Agent` with a
  contact address. It is a sensible next addition but is not wired up here.
- **No real-time quotes.** These are end-of-day sources.

## Worth a look, not wired up

These are reasonable and were left out only because a key could not be
obtained to verify the response format from the development machine. Adding
one is a ~30-line provider function — see the last section.

| Source | Free tier | Why you might want it |
|---|---|---|
| **Twelve Data** | 800 requests/day | Covers TSX and TSXV directly, so it can serve both sides of a Canadian portfolio from one feed |
| **Finnhub** | 60 requests/min | Fundamentals and earnings alongside prices |
| **Financial Modeling Prep** | limited | Has a documented TSX prices endpoint |
| **`yahooquery`** | n/a | Sometimes suggested as a "stabler yfinance" — it is still Yahoo, so it inherits every problem in the first section |

## Deliberately left out

| Considered | Why not |
|---|---|
| Binance | Returns HTTP 451 to Canadian and many datacentre IPs; it withdrew from Canada in 2023 |
| `ccxt` | Excellent library, and the right answer if you want more than two exchanges — but it is a dependency, and it sets `session.trust_env = False`, so it silently ignores `HTTPS_PROXY` and fails behind a corporate proxy until you set it back |
| `pandas-datareader` | Its Stooq backend raises `NotImplementedError` as of 0.11.1 |
| IEX Cloud | Retired |
| Polygon / Databento | Genuinely better data, but no meaningful free tier for history |

There is no perfect free market-data source in 2026. Yahoo is unreliable, IEX
Cloud is gone, and everything remaining trades off coverage, latency or rate
limits. The response to that is not to pick a favourite and trust it — it is
to use sources that publish their own data, and to check two of them against
each other. That is what the `crosscheck` command is for.

## Adding a provider

Providers are single functions with a decorator. The contract is: take
`(symbol, start, end)`, return a list of `Bar`, raise `ProviderError` on
anything you cannot serve.

```python
from datetime import date
from marketdata.core import Bar, http_json, register

@register("myfeed", "What it is - and whether it needs a key", ["equity"])
def myfeed_history(symbol: str, start: date, end: date) -> list[Bar]:
    payload = http_json("https://example.com/prices", params={"s": symbol})
    return [
        Bar(
            date=date.fromisoformat(row["d"]),
            open=row["o"], high=row["h"], low=row["l"], close=row["c"],
            volume=row["v"], currency="USD",
            provider="myfeed", symbol=symbol,
        )
        for row in payload["rows"]
    ]
```

`http_json` already handles retries with backoff, gzip, timeouts and the
User-Agent. Add an offline test in `tests/test_providers.py` with a captured
response — that is where format changes get caught.
