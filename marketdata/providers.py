"""Daily OHLCV providers. None of these is Yahoo Finance.

Each provider is the primary publisher of the prints it serves, or as close to
it as a keyless endpoint gets:

==============  ===================================================
``nasdaq``      Nasdaq's own quote API -- US listed equities and ETFs
``tmx``         TMX Group, the operator of the TSX and TSX Venture
``kraken``      Kraken exchange, including native CAD crypto pairs
``coinbase``    Coinbase Exchange
``stooq``       Stooq -- broad global coverage, including indices
==============  ===================================================
"""

from __future__ import annotations

import csv
import io
from datetime import date, timedelta

from .core import (
    Bar,
    ProviderError,
    clean_number,
    from_epoch,
    to_epoch,
    http_json,
    http_text,
    register,
)


# --- Nasdaq ------------------------------------------------------------

NASDAQ_URL = "https://api.nasdaq.com/api/quote/{symbol}/historical"


@register(
    "nasdaq",
    "Nasdaq official quote API - US equities and ETFs, no key",
    ["equity", "etf"],
)
def nasdaq_history(symbol: str, start: date, end: date) -> list[Bar]:
    """US equities straight from Nasdaq.

    ``assetclass`` must match the instrument or the API returns an empty
    table rather than an error, so ETFs are retried under ``etf`` when the
    ``stocks`` class comes back empty.
    """
    symbol = symbol.upper()
    span = (end - start).days + 1

    for asset_class in ("stocks", "etf"):
        payload = http_json(
            NASDAQ_URL.format(symbol=symbol),
            params={
                "assetclass": asset_class,
                "fromdate": start.isoformat(),
                "todate": end.isoformat(),
                # The API caps rows server-side; ask for one per calendar day
                # and let it trim to trading days.
                "limit": max(span, 10),
            },
            headers={"Accept": "application/json"},
            # Nasdaq is slow to assemble long ranges and will sit on the
            # connection rather than stream partial JSON.
            timeout=60.0,
        )
        table = (payload.get("data") or {}).get("tradesTable") or {}
        rows = table.get("rows") or []
        if rows:
            return [_nasdaq_bar(row, symbol) for row in rows]

    status = (payload.get("status") or {}).get("bCodeMessage")
    raise ProviderError(f"nasdaq returned no rows for {symbol!r} ({status})")


def _nasdaq_bar(row: dict, symbol: str) -> Bar:
    month, day, year = row["date"].split("/")
    return Bar(
        date=date(int(year), int(month), int(day)),
        open=clean_number(row.get("open")),
        high=clean_number(row.get("high")),
        low=clean_number(row.get("low")),
        close=clean_number(row.get("close")),
        volume=clean_number(row.get("volume")),
        currency="USD",
        provider="nasdaq",
        symbol=symbol,
    )


# --- TMX (Toronto Stock Exchange) --------------------------------------

TMX_URL = "https://app-money.tmx.com/graphql"

TMX_QUERY = """
query getTimeSeriesData($symbol: String!, $freq: String, $interval: Int,
                        $start: String, $end: String) {
  getTimeSeriesData(symbol: $symbol, freq: $freq, interval: $interval,
                    start: $start, end: $end) {
    dateTime open high low close volume
  }
}
"""


@register(
    "tmx",
    "TMX Group - TSX / TSX Venture listings priced in CAD, no key",
    ["equity", "etf"],
)
def tmx_history(symbol: str, start: date, end: date) -> list[Bar]:
    """Canadian listings from the exchange operator itself.

    Pass the plain TSX root (``SHOP``, ``RY``, ``ENB``) -- no ``.TO`` suffix.
    Prices are the CAD prints from the Toronto book, not a converted copy of
    the US line.
    """
    symbol = symbol.upper().removesuffix(".TO").removesuffix(".TSX")
    payload = http_json(
        TMX_URL,
        json={
            "operationName": "getTimeSeriesData",
            "variables": {
                "symbol": symbol,
                "freq": "day",
                "interval": 1,
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
            "query": TMX_QUERY,
        },
        headers={"locale": "en", "Accept": "application/json"},
    )

    if payload.get("errors"):
        raise ProviderError(f"tmx error for {symbol!r}: {payload['errors']}")

    rows = (payload.get("data") or {}).get("getTimeSeriesData")
    if not rows:
        raise ProviderError(f"tmx returned no rows for {symbol!r}")

    return [
        Bar(
            date=date.fromisoformat(row["dateTime"][:10]),
            open=clean_number(row.get("open")),
            high=clean_number(row.get("high")),
            low=clean_number(row.get("low")),
            close=clean_number(row.get("close")),
            volume=clean_number(row.get("volume")),
            currency="CAD",
            provider="tmx",
            symbol=symbol,
        )
        for row in rows
    ]


# --- Kraken ------------------------------------------------------------

KRAKEN_URL = "https://api.kraken.com/0/public/OHLC"


@register(
    "kraken",
    "Kraken exchange - crypto OHLCV including native BTC/CAD, no key",
    ["crypto"],
)
def kraken_history(symbol: str, start: date, end: date) -> list[Bar]:
    """Exchange-native crypto candles.

    Use ``BTC/CAD`` or ``BTC-CAD``. A CAD pair here is a real order book, not
    a USD price run through an FX rate, which is what makes it usable for
    Canadian cost-base reporting.
    """
    pair = symbol.upper().replace("-", "/").replace("_", "/")
    if "/" not in pair:
        raise ProviderError(f"kraken needs a pair like BTC/CAD, got {symbol!r}")
    base, quote = pair.split("/", 1)

    payload = http_json(
        KRAKEN_URL,
        params={
            "pair": f"{base}{quote}",
            "interval": 1440,  # minutes; 1440 = daily
            "since": to_epoch(start - timedelta(days=1)),
        },
    )
    if payload.get("error"):
        raise ProviderError(f"kraken error for {pair}: {payload['error']}")

    result = {k: v for k, v in payload.get("result", {}).items() if k != "last"}
    if not result:
        raise ProviderError(f"kraken returned no series for {pair}")

    _, candles = next(iter(result.items()))
    bars = []
    for row in candles:
        bar_date = from_epoch(row[0])
        if not (start <= bar_date <= end):
            continue
        bars.append(
            Bar(
                date=bar_date,
                open=clean_number(row[1]),
                high=clean_number(row[2]),
                low=clean_number(row[3]),
                close=clean_number(row[4]),
                volume=clean_number(row[6]),
                currency=quote,
                provider="kraken",
                symbol=pair,
            )
        )
    if not bars:
        raise ProviderError(
            f"kraken has no {pair} candles between {start} and {end} "
            "(its OHLC endpoint only serves a recent window)"
        )
    return bars


# --- Coinbase ----------------------------------------------------------

COINBASE_URL = "https://api.exchange.coinbase.com/products/{product}/candles"


@register(
    "coinbase",
    "Coinbase Exchange - crypto OHLCV, no key",
    ["crypto"],
)
def coinbase_history(symbol: str, start: date, end: date) -> list[Bar]:
    """Coinbase candles, paged backwards 300 at a time.

    Coinbase caps a single response at 300 candles and returns 400 rather
    than truncating, so longer ranges are walked in windows.
    """
    product = symbol.upper().replace("/", "-").replace("_", "-")
    if "-" not in product:
        raise ProviderError(f"coinbase needs a product like BTC-USD, got {symbol!r}")
    quote = product.split("-", 1)[1]

    bars: list[Bar] = []
    window_end = end
    while window_end >= start:
        window_start = max(start, window_end - timedelta(days=299))
        rows = http_json(
            COINBASE_URL.format(product=product),
            params={
                "granularity": 86400,
                "start": window_start.isoformat(),
                "end": window_end.isoformat(),
            },
        )
        if not rows:
            break
        for row in rows:
            # [ time, low, high, open, close, volume ]
            bars.append(
                Bar(
                    date=from_epoch(row[0]),
                    open=clean_number(row[3]),
                    high=clean_number(row[2]),
                    low=clean_number(row[1]),
                    close=clean_number(row[4]),
                    volume=clean_number(row[5]),
                    currency=quote,
                    provider="coinbase",
                    symbol=product,
                )
            )
        window_end = window_start - timedelta(days=1)

    if not bars:
        raise ProviderError(f"coinbase returned no candles for {product}")
    return bars


# --- Stooq -------------------------------------------------------------

STOOQ_URL = "https://stooq.com/q/d/l/"


@register(
    "stooq",
    "Stooq - global equities, indices and FX as CSV, no key",
    ["equity", "etf", "index", "fx"],
)
def stooq_history(symbol: str, start: date, end: date) -> list[Bar]:
    """Broad global coverage, including index levels other free feeds omit.

    Stooq wants its own suffixes: ``aapl.us``, ``shop.ca``, ``^spx`` for the
    S&P 500. A bare symbol is assumed to be US listed.

    Stooq blocks many datacentre IP ranges, so this provider can fail from a
    cloud host while working from a home connection.
    """
    ticker = symbol.lower()
    if "." not in ticker and not ticker.startswith("^"):
        ticker = f"{ticker}.us"

    text = http_text(
        STOOQ_URL,
        params={
            "s": ticker,
            "i": "d",
            "d1": start.strftime("%Y%m%d"),
            "d2": end.strftime("%Y%m%d"),
        },
    )
    if not text.lstrip().lower().startswith("date"):
        raise ProviderError(
            f"stooq did not return CSV for {ticker!r} (got {text[:120]!r}). "
            "Stooq blocks many datacentre IPs; try from a home connection."
        )

    currency = {"us": "USD", "ca": "CAD", "uk": "GBP", "de": "EUR"}.get(
        ticker.rsplit(".", 1)[-1], ""
    )
    bars = []
    for row in csv.DictReader(io.StringIO(text)):
        if not row.get("Date"):
            continue
        bars.append(
            Bar(
                date=date.fromisoformat(row["Date"]),
                open=clean_number(row.get("Open")),
                high=clean_number(row.get("High")),
                low=clean_number(row.get("Low")),
                close=clean_number(row.get("Close")),
                volume=clean_number(row.get("Volume")),
                currency=currency,
                provider="stooq",
                symbol=ticker,
            )
        )
    if not bars:
        raise ProviderError(f"stooq returned an empty series for {ticker!r}")
    return bars


# --- Alpha Vantage -----------------------------------------------------

ALPHAVANTAGE_URL = "https://www.alphavantage.co/query"


@register(
    "alphavantage",
    "Alpha Vantage - US equities with split/dividend adjusted close, free key",
    ["equity", "etf"],
    needs_key=True,
)
def alphavantage_history(symbol: str, start: date, end: date) -> list[Bar]:
    """US equities with a genuinely adjusted close.

    Set ``ALPHAVANTAGE_API_KEY``; a free key is issued instantly at
    https://www.alphavantage.co/support/#api-key. Unlike the keyless
    endpoints this one has a published, permissive terms of service, which
    is the point of preferring it over a scraper.
    """
    import os

    key = os.environ.get("ALPHAVANTAGE_API_KEY", "").strip()
    if not key:
        raise ProviderError(
            "set ALPHAVANTAGE_API_KEY (free key: "
            "https://www.alphavantage.co/support/#api-key)"
        )

    # "full" reaches back 20+ years but is gated on some plans; "compact"
    # stops at the last 100 rows and is always available. Ask for the range
    # actually needed, then fall back rather than failing the call.
    sizes = ["full", "compact"] if (end - start).days > 100 else ["compact"]

    payload: dict = {}
    for size in sizes:
        payload = http_json(
            ALPHAVANTAGE_URL,
            params={
                "function": "TIME_SERIES_DAILY_ADJUSTED",
                "symbol": symbol.upper(),
                "outputsize": size,
                "apikey": key,
            },
            timeout=60.0,
        )
        if "Time Series (Daily)" in payload:
            break

    for field_name in ("Note", "Information", "Error Message"):
        if field_name in payload:
            raise ProviderError(f"alphavantage: {payload[field_name]}")

    series = payload.get("Time Series (Daily)")
    if not series:
        raise ProviderError(f"alphavantage returned no series for {symbol!r}")

    bars = []
    for day, row in series.items():
        bar_date = date.fromisoformat(day)
        if not (start <= bar_date <= end):
            continue
        bars.append(
            Bar(
                date=bar_date,
                open=clean_number(row.get("1. open")),
                high=clean_number(row.get("2. high")),
                low=clean_number(row.get("3. low")),
                close=clean_number(row.get("4. close")),
                adj_close=clean_number(row.get("5. adjusted close")),
                volume=clean_number(row.get("6. volume")),
                currency="USD",
                provider="alphavantage",
                symbol=symbol.upper(),
            )
        )
    if not bars:
        raise ProviderError(
            f"alphavantage has no {symbol!r} rows between {start} and {end}"
        )
    return bars


# --- Tiingo ------------------------------------------------------------

TIINGO_URL = "https://api.tiingo.com/tiingo/daily/{symbol}/prices"


@register(
    "tiingo",
    "Tiingo - curated, survivorship-bias-aware US EOD history, free key",
    ["equity", "etf"],
    needs_key=True,
)
def tiingo_history(symbol: str, start: date, end: date) -> list[Bar]:
    """Tiingo's curated end-of-day series.

    Set ``TIINGO_API_KEY``; the free tier is issued at
    https://www.tiingo.com/ . Tiingo reconciles multiple upstream feeds and
    keeps delisted tickers, so a backtest run against it is not quietly
    survivorship-biased the way a scraped feed is.
    """
    import os

    key = os.environ.get("TIINGO_API_KEY", "").strip()
    if not key:
        raise ProviderError("set TIINGO_API_KEY (free key: https://www.tiingo.com/)")

    rows = http_json(
        TIINGO_URL.format(symbol=symbol.lower()),
        params={
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "format": "json",
        },
        headers={"Authorization": f"Token {key}", "Accept": "application/json"},
        timeout=60.0,
    )
    if not rows:
        raise ProviderError(f"tiingo returned no rows for {symbol!r}")

    return [
        Bar(
            date=date.fromisoformat(row["date"][:10]),
            open=clean_number(row.get("open")),
            high=clean_number(row.get("high")),
            low=clean_number(row.get("low")),
            close=clean_number(row.get("close")),
            adj_close=clean_number(row.get("adjClose")),
            volume=clean_number(row.get("volume")),
            currency="USD",
            provider="tiingo",
            symbol=symbol.upper(),
        )
        for row in rows
    ]
