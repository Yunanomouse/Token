#!/usr/bin/env python3
"""Fetch daily adjusted closes for the live bot and write them as one wide CSV.

    python3 scripts/fetch_prices.py --config live/config.json --out live/prices.csv

Sources, tried in order per ticker: Stooq's CSV download (no key), then
Yahoo Finance's chart endpoint (no key, adjusted closes).  Standard library
only, so it runs anywhere Python does.  Every run rewrites the whole file
from the source; the engine only ever acts on dates newer than its state,
so a rewrite is safe and self-healing.

Exits non-zero, loudly, if any ticker cannot be fetched or the tickers
disagree on the latest date: a bot must never trade on a partial market.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

UA = {"User-Agent": "Mozilla/5.0 (quantum-trading paper bot)"}


def _get(url: str, timeout: float = 30.0) -> bytes:
    req = urllib.request.Request(url, headers=UA)
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
    data = json.loads(_get(url))
    res = data["chart"]["result"][0]
    ts = res["timestamp"]
    adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose") or res["indicators"]["quote"][0]["close"]
    out = {}
    for t, v in zip(ts, adj):
        if v and v > 0:
            out[datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")] = float(v)
    if not out:
        raise ValueError(f"yahoo had no closes for {ticker}")
    return out


def fetch(ticker: str, days: int) -> tuple[dict[str, float], str]:
    errors = []
    for name, fn in (("stooq", lambda: stooq(ticker)), ("yahoo", lambda: yahoo(ticker, days))):
        for attempt in range(3):
            try:
                return fn(), name
            except Exception as exc:  # network, parse, or empty: try again, then fall back
                errors.append(f"{name}#{attempt + 1}: {exc}")
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"could not fetch {ticker}: " + " | ".join(errors))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="live/config.json")
    ap.add_argument("--out", default="live/prices.csv")
    ap.add_argument("--days", type=int, default=730, help="calendar days of history to keep")
    args = ap.parse_args()

    tickers = json.load(open(args.config, encoding="utf-8"))["tickers"]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%d")
    series, sources = {}, {}
    for t in tickers:
        series[t], sources[t] = fetch(t, args.days + 10)
        print(f"{t:6} {sources[t]:6} {len(series[t]):5} closes, last {max(series[t])}")

    lasts = {t: max(s) for t, s in series.items()}
    newest = max(lasts.values())
    stale = {t: d for t, d in lasts.items() if d != newest}
    if stale:
        print(f"ERROR: tickers disagree on the latest date {newest}: {stale}", file=sys.stderr)
        return 2
    dates = sorted(d for d in set.intersection(*(set(s) for s in series.values())) if d >= cutoff)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["date"] + tickers)
        for d in dates:
            w.writerow([d] + [f"{series[t][d]:.6f}" for t in tickers])
    print(f"wrote {args.out}: {len(dates)} days, {dates[0]} to {dates[-1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
