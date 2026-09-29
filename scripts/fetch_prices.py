#!/usr/bin/env python3
"""Fetch daily adjusted closes for the live bot and write them as one wide CSV.

    python3 scripts/fetch_prices.py --config live/config.json --out live/prices.csv

Sources, tried in order for the whole ticker list: Yahoo Finance's chart
endpoint (no key; closes adjusted for splits and dividends, the basis the
bot's stored history is on), then Stooq's CSV download (no key).  One
source per run, never a mix: the two do not adjust history the same way,
and a ticker whose basis changed between runs would look to the engine
like a split or a dividend.  Standard library only, so it runs anywhere
Python does.  Every run rewrites the whole file from the source; the engine
re-bases its stored history from it and only acts on dates newer than its
state, so a rewrite is safe and self-healing.

A bot must never trade on a partial market.  A source that fails for any
ticker, or whose tickers disagree on the latest date (today's close not yet
published for every name), hands over to the next source.  If every source
disagrees, the file stops at the latest date all tickers share, with a
warning, unless that is more than ``--max-lag-days`` behind the newest date
seen, which fails the run.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

UA = {"User-Agent": "Mozilla/5.0 (quantum-trading paper bot)"}
# Yahoo rate-limits (HTTP 429) by User-Agent string, and which strings it
# refuses changes over time; on a 429 the same request is retried as these.
ALT_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "Mozilla/5.0",
]
SOURCES = ("yahoo", "stooq")


def _get(url: str, timeout: float = 30.0, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(url, headers=headers or UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def stooq(ticker: str) -> dict[str, float]:
    raw = _get(f"https://stooq.com/q/d/l/?s={ticker.lower()}.us&i=d").decode("utf-8", "replace")
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


# Sources that could not be reached at all this run.  A host that resets or
# times out on every attempt for one ticker will do the same for the next, so
# the rest of the run skips it instead of paying the retries per ticker.
UNREACHABLE: set[str] = set()


def _unreachable(exc: Exception) -> bool:
    """True for connection-level failures; an HTTP status or bad data is per-ticker."""
    return isinstance(exc, OSError) and not isinstance(exc, urllib.error.HTTPError)


def fetch(ticker: str, days: int, sources: tuple[str, ...] = SOURCES) -> tuple[dict[str, float], str]:
    """One ticker's closes from the first of ``sources`` that delivers, with
    three attempts per source; ``RuntimeError`` lists every failure."""
    errors = []
    for name in sources:
        if name in UNREACHABLE:
            errors.append(f"{name}: skipped, unreachable earlier this run")
            continue
        fn = (lambda: yahoo(ticker, days)) if name == "yahoo" else (lambda: stooq(ticker))
        down = True
        for attempt in range(3):
            try:
                return fn(), name
            except Exception as exc:  # network, parse, or empty: try again, then fall back
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
    return {t: fetch(t, days, sources=(source,))[0] for t in tickers}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", default="live/config.json")
    ap.add_argument("--out", default="live/prices.csv")
    ap.add_argument("--days", type=int, default=730, help="calendar days of history to keep")
    ap.add_argument("--max-lag-days", type=int, default=5, dest="max_lag_days",
                    help="fail rather than write a file whose latest complete date is more than "
                         "this many days behind the newest date any ticker has")
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as fh:
        tickers = json.load(fh)["tickers"]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%d")

    candidates = []  # (latest date every ticker has, newest date seen, source, series, common dates)
    for source in SOURCES:
        try:
            series = fetch_all(tickers, args.days + 10, source)
        except RuntimeError as exc:
            print(f"{source}: {exc}", file=sys.stderr)
            continue
        lasts = {t: max(s) for t, s in series.items()}
        for t in tickers:
            print(f"{t:6} {source:6} {len(series[t]):5} closes, last {lasts[t]}")
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
