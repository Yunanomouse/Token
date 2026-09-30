#!/usr/bin/env python3
"""Fetch daily adjusted closes for the live bot and write them as one wide CSV.

    python3 scripts/fetch_prices.py --config live/config.json --out live/prices.csv

Sources, in order, each tried for the whole ticker list; keyed ones only when
their key is set (free sign-ups, kept in repository secrets):

1. Financial Modeling Prep (``FMP_API_KEY``), dividend-adjusted closes.
2. Twelve Data (``TWELVEDATA_API_KEY``), ``adjust=all``.
3. Yahoo Finance's chart endpoint (no key; closes adjusted for splits and
   dividends; rate-limits cloud servers at times).
4. Stooq (no key needed before about April 2026; now it wants a key obtained
   through a captcha and answers without one with an HTML page).  With
   ``STOOQ_API_KEY`` set it is tried before Yahoo.

One source per run, never a mix: vendors do not adjust history the same way,
and a ticker whose basis changed between runs would look to the engine like a
split or a dividend.  A source that fails for any ticker, serves an
implausible one-day move (over 50%: an unadjusted split or bad data), or whose
tickers disagree on the latest date hands over to the next source.  If every
source disagrees, the file stops at the latest date all tickers share, with a
warning, unless that is more than ``--max-lag-days`` behind the newest date
seen, which fails the run; so does a newest close older than
``--max-age-days`` (stale data).  The source used is written next to the CSV
as ``<name>_sources.json``.  Standard library only, so it runs anywhere Python
does.  Every run rewrites the whole file from the source; the engine re-bases
its stored history from it and only acts on dates newer than its state, so a
rewrite is safe and self-healing.

Today's bar is dropped until 16:30 New York time, whatever the source, so a
run during market hours never stores an intraday price as a close.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
SESSION_FINAL = dtime(16, 30)
UA ={"User-Agent": "Mozilla/5.0 (quantum-trading paper bot)"}
# Yahoo rate-limits (HTTP 429) by User-Agent string, and which strings it
# refuses changes over time; on a 429 the same request is retried as these.
ALT_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "Mozilla/5.0",
]
SOURCES = ("fmp", "twelvedata", "yahoo", "stooq")  # every source; see source_names()


def _get(url: str, timeout: float = 30.0, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(url, headers=headers or UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def fmp(ticker: str, days: int) -> dict[str, float]:
    """Financial Modeling Prep, dividend- and split-adjusted end-of-day closes."""
    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    url = ("https://financialmodelingprep.com/stable/historical-price-eod/dividend-adjusted"
           f"?symbol={ticker}&from={start}&apikey={_env('FMP_API_KEY')}")
    data = json.loads(_get(url))
    if isinstance(data, dict):  # {"Error Message": ...} or a wrapper
        rows = data.get("historical")
        if rows is None:
            raise ValueError(f"fmp error for {ticker}: {str(data)[:120]}")
    else:
        rows = data
    out = {}
    for row in rows or []:
        v = row.get("adjClose", row.get("close"))
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if v > 0 and row.get("date"):
            out[str(row["date"])[:10]] = v
    if not out:
        raise ValueError(f"fmp had no closes for {ticker}")
    return out


_TWELVE_LAST = [0.0]


def twelvedata(ticker: str, days: int) -> dict[str, float]:
    """Twelve Data daily series, fully adjusted (the default adjusts splits only)."""
    wait = 8.0 - (time.time() - _TWELVE_LAST[0])  # free tier: 8 requests a minute
    if wait > 0:
        time.sleep(wait)
    _TWELVE_LAST[0] = time.time()
    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    url = ("https://api.twelvedata.com/time_series"
           f"?symbol={ticker}&interval=1day&start_date={start}&outputsize=5000&adjust=all"
           f"&apikey={_env('TWELVEDATA_API_KEY')}")
    data = json.loads(_get(url))
    if data.get("status") != "ok":
        raise ValueError(f"twelvedata error for {ticker}: {str(data.get('message', data))[:120]}")
    out = {}
    for row in data.get("values", []):
        try:
            v = float(row["close"])
        except (KeyError, TypeError, ValueError):
            continue
        if v > 0:
            out[str(row["datetime"])[:10]] = v
    if not out:
        raise ValueError(f"twelvedata had no closes for {ticker}")
    return out


def stooq(ticker: str) -> dict[str, float]:
    url = f"https://stooq.com/q/d/l/?s={ticker.lower()}.us&i=d"
    if _env("STOOQ_API_KEY"):
        url += f"&apikey={_env('STOOQ_API_KEY')}"
    raw = _get(url).decode("utf-8", "replace")
    # Stooq answers refusals (no key, quota exceeded, captcha) with HTTP 200
    # and a text or HTML body, so the body is what must be checked.
    if not raw.lower().startswith("date"):
        raise ValueError(f"stooq returned no CSV for {ticker}: {raw[:80]!r}")
    out = {}
    for row in csv.DictReader(io.StringIO(raw)):
        try:
            v = float(row["Close"])
        except (KeyError, ValueError):
            continue
        if v > 0:
            out[row["Date"][:10]] = v
    if not out:
        raise ValueError(f"stooq had no closes for {ticker}")
    return out


def yahoo(ticker: str, days: int) -> dict[str, float]:
    end = int(time.time())
    start = end - days * 86400
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
           f"?period1={start}&period2={end}&interval=1d&events=div,split")
    for ua in [None] + ALT_UAS:
        try:
            data = json.loads(_get(url, headers={"User-Agent": ua} if ua else None))
            break
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or ua == ALT_UAS[-1]:
                raise
    chart = data.get("chart") or {}
    if chart.get("error"):
        err = chart["error"]
        raise ValueError(f"yahoo error for {ticker}: {err.get('description', err) if isinstance(err, dict) else err}")
    results = chart.get("result") or []
    if not results:
        raise ValueError(f"yahoo returned no result for {ticker}")
    res = results[0]
    ts = res.get("timestamp") or []
    indicators = res.get("indicators") or {}
    adj = ((indicators.get("adjclose") or [{}])[0].get("adjclose")
           or (indicators.get("quote") or [{}])[0].get("close") or [])
    out = {}
    for t, v in zip(ts, adj):
        if v and v > 0:
            out[datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")] = float(v)
    if not out:
        raise ValueError(f"yahoo had no closes for {ticker}")
    return out


def unfinished_session(now: datetime | None = None) -> str | None:
    """Today's New York date while its session may still be trading, else None.

    Yahoo's daily series includes today's bar from the open, priced at the
    latest trade.  A bot that stored it would take an intraday price for the
    close.  The regular session ends at 16:00 (13:00 on half days); closes
    are final well within the next half hour, so today's bar is kept only
    from 16:30 New York time.
    """
    ny = (now or datetime.now(timezone.utc)).astimezone(NY)
    return ny.strftime("%Y-%m-%d") if ny.time() < SESSION_FINAL else None


# Sources that could not be reached at all this run.  A host that resets or
# times out on every attempt for one ticker will do the same for the next, so
# the rest of the run skips it instead of paying the retries per ticker.
UNREACHABLE: set[str] = set()


def _unreachable(exc: Exception) -> bool:
    """True for connection-level failures; an HTTP status or bad data is per-ticker."""
    return isinstance(exc, OSError) and not isinstance(exc, urllib.error.HTTPError)


def source_names() -> list[str]:
    """The sources to try this run, in order; keyed ones only when their key is set."""
    names = [n for n, key in (("fmp", "FMP_API_KEY"), ("twelvedata", "TWELVEDATA_API_KEY")) if _env(key)]
    # Stooq refuses keyless requests now; with a key it is the better fallback.
    return names + (["stooq", "yahoo"] if _env("STOOQ_API_KEY") else ["yahoo", "stooq"])


def sources(ticker: str, days: int) -> list[tuple[str, object]]:
    """(name, fetcher) for one ticker, in :func:`source_names` order."""
    calls = {"fmp": lambda: fmp(ticker, days), "twelvedata": lambda: twelvedata(ticker, days),
             "stooq": lambda: stooq(ticker), "yahoo": lambda: yahoo(ticker, days)}
    return [(n, calls[n]) for n in source_names()]


def sanity(ticker: str, series: dict[str, float], max_move: float = 0.5) -> None:
    """Refuse a series with an implausible one-day move (an unadjusted split, bad data)."""
    dates = sorted(series)
    for a, b in zip(dates, dates[1:]):
        move = series[b] / series[a] - 1.0
        if abs(move) > max_move:
            raise ValueError(f"{ticker}: {move:+.0%} from {a} to {b}; unadjusted split or bad data")


def fetch(ticker: str, days: int, only: tuple[str, ...] | None = None) -> tuple[dict[str, float], str]:
    """One ticker's closes from the first source that delivers (of ``only``,
    default all), with three attempts per source; today's unfinished bar is
    dropped and the series must pass :func:`sanity`.  ``RuntimeError`` lists
    every failure."""
    errors = []
    for name, fn in sources(ticker, days):
        if only is not None and name not in only:
            continue
        if name in UNREACHABLE:
            errors.append(f"{name}: skipped, unreachable earlier this run")
            continue
        down = True
        for attempt in range(3):
            try:
                series = dict(fn())
                series.pop(unfinished_session(), None)
                if not series:
                    raise ValueError(f"{name} had no finished closes for {ticker}")
                sanity(ticker, series)
                return series, name
            except Exception as exc:  # network, parse, empty or implausible: try again, then fall back
                errors.append(f"{name}#{attempt + 1}: {exc}")
                down = down and _unreachable(exc)
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
        if down:
            UNREACHABLE.add(name)
            print(f"{name} unreachable; skipping it for the rest of this run", file=sys.stderr)
    raise RuntimeError(f"could not fetch {ticker}: " + " | ".join(errors))


def fetch_all(tickers: list[str], days: int, source: str) -> dict[str, dict[str, float]]:
    """Every ticker from one source; ``RuntimeError`` names the first that failed."""
    return {t: fetch(t, days, only=(source,))[0] for t in tickers}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", default="live/config.json")
    ap.add_argument("--out", default="live/prices.csv")
    ap.add_argument("--days", type=int, default=730, help="calendar days of history to keep")
    ap.add_argument("--max-lag-days", type=int, default=5, dest="max_lag_days",
                    help="fail rather than write a file whose latest complete date is more than "
                         "this many days behind the newest date any ticker has")
    ap.add_argument("--max-age-days", type=int, default=6, dest="max_age_days",
                    help="fail if the newest close is older than this (holiday weekends are 4)")
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as fh:
        tickers = json.load(fh)["tickers"]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%d")

    candidates = []  # (latest date every ticker has, newest date seen, source, series, common dates)
    for source in source_names():
        try:
            series = fetch_all(tickers, args.days + 10, source)
        except RuntimeError as exc:
            print(f"{source}: {exc}", file=sys.stderr)
            continue
        lasts = {t: max(s) for t, s in series.items()}
        for t in tickers:
            print(f"{t:6} {source:10} {len(series[t]):5} closes, last {lasts[t]}")
        common = set.intersection(*(set(s) for s in series.values()))
        if not common:
            print(f"WARNING: {source}: the tickers have no dates in common", file=sys.stderr)
            continue
        newest, latest_common = max(lasts.values()), max(common)
        candidates.append((latest_common, newest, source, series, common))
        if latest_common == newest:
            break
        stale = {t: d for t, d in lasts.items() if d != newest}
        print(f"WARNING: {source}: tickers disagree on the latest date {newest}: {stale}", file=sys.stderr)
    if not candidates:
        print(f"ERROR: no source could supply every ticker in {args.config}", file=sys.stderr)
        return 2

    latest_common, newest, source, series, common = max(candidates, key=lambda c: c[0])
    age = (datetime.now(timezone.utc).date() - date.fromisoformat(newest)).days
    if age > args.max_age_days:
        print(f"ERROR: newest close is {newest}, {age} days old; the sources are serving stale data",
              file=sys.stderr)
        return 3
    lag = (date.fromisoformat(newest) - date.fromisoformat(latest_common)).days
    if lag > args.max_lag_days:
        print(f"ERROR: the latest date every ticker has is {latest_common}, {lag} days behind {newest}; "
              "not writing a stale file", file=sys.stderr)
        return 2
    if lag:
        print(f"WARNING: writing through {latest_common}, the latest date every ticker has; "
              f"{newest} is not complete yet", file=sys.stderr)
    dates = sorted(d for d in common if d >= cutoff)
    if not dates:
        print(f"ERROR: no dates on or after {cutoff} that every ticker has", file=sys.stderr)
        return 2
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["date"] + tickers)
        for d in dates:
            w.writerow([d] + [f"{series[t][d]:.6f}" for t in tickers])
    print(f"wrote {args.out}: {len(dates)} days from {source}, {dates[0]} to {dates[-1]}")
    with open(args.out.rsplit(".", 1)[0] + "_sources.json", "w", encoding="utf-8") as fh:
        json.dump({"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "sources": {t: source for t in tickers}}, fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
