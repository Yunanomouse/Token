#!/usr/bin/env python3
"""Fetch daily adjusted closes for the live bot and write them as one wide CSV.

    python3 scripts/fetch_prices.py --config live/config.json --out live/prices.csv

Sources, tried in order per ticker, skipping any whose key is not set:

1. Financial Modeling Prep (``FMP_API_KEY``), dividend-adjusted closes.
2. Twelve Data (``TWELVEDATA_API_KEY``), ``adjust=all``.
3. Stooq (``STOOQ_API_KEY`` if set; since about April 2026 Stooq wants a
   key obtained through a captcha, and answers without one with an HTML
   page instead of a CSV).
4. Yahoo Finance's chart endpoint (no key; rate-limits cloud servers).

Free official keys (1 and 2) are the reliable route from GitHub Actions;
the keyless sources are kept as fallbacks.  Each ticker's whole series comes
from one source, never spliced, because vendors adjust dividends
differently.  Standard library only, so it runs anywhere Python does.  Every run rewrites the whole file
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
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

UA = {"User-Agent": "Mozilla/5.0 (quantum-trading paper bot)"}
# Yahoo rate-limits (HTTP 429) by User-Agent string, and which strings it
# refuses changes over time; on a 429 the same request is retried as these.
ALT_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "Mozilla/5.0",
]


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


# Sources that could not be reached at all this run.  A host that resets or
# times out on every attempt for one ticker will do the same for the next, so
# the rest of the run skips it instead of paying the retries per ticker.
UNREACHABLE: set[str] = set()


def _unreachable(exc: Exception) -> bool:
    """True for connection-level failures; an HTTP status or bad data is per-ticker."""
    return isinstance(exc, OSError) and not isinstance(exc, urllib.error.HTTPError)


def sources(ticker: str, days: int) -> list[tuple[str, object]]:
    """The sources to try for one ticker, in order; keyed ones only if their key is set."""
    out = []
    if _env("FMP_API_KEY"):
        out.append(("fmp", lambda: fmp(ticker, days)))
    if _env("TWELVEDATA_API_KEY"):
        out.append(("twelvedata", lambda: twelvedata(ticker, days)))
    out.append(("stooq", lambda: stooq(ticker)))
    out.append(("yahoo", lambda: yahoo(ticker, days)))
    return out


def sanity(ticker: str, series: dict[str, float], max_move: float = 0.5) -> None:
    """Refuse a series with an implausible one-day move (an unadjusted split, bad data)."""
    dates = sorted(series)
    for a, b in zip(dates, dates[1:]):
        move = series[b] / series[a] - 1.0
        if abs(move) > max_move:
            raise ValueError(f"{ticker}: {move:+.0%} from {a} to {b}; unadjusted split or bad data")


def fetch(ticker: str, days: int) -> tuple[dict[str, float], str]:
    errors = []
    for name, fn in sources(ticker, days):
        if name in UNREACHABLE:
            errors.append(f"{name}: skipped, unreachable earlier this run")
            continue
        down = True
        for attempt in range(3):
            try:
                series = fn()
                sanity(ticker, series)
                return series, name
            except Exception as exc:  # network, parse, or empty: try again, then fall back
                errors.append(f"{name}#{attempt + 1}: {exc}")
                down = down and _unreachable(exc)
                time.sleep(2 * (attempt + 1))
        if down:
            UNREACHABLE.add(name)
            print(f"{name} unreachable; skipping it for the rest of this run", file=sys.stderr)
    raise RuntimeError(f"could not fetch {ticker}: " + " | ".join(errors))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="live/config.json")
    ap.add_argument("--out", default="live/prices.csv")
    ap.add_argument("--days", type=int, default=730, help="calendar days of history to keep")
    ap.add_argument("--max-age-days", type=int, default=6, dest="max_age_days",
                    help="fail if the newest close is older than this (holiday weekends are 4)")
    args = ap.parse_args()

    tickers = json.load(open(args.config, encoding="utf-8"))["tickers"]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%d")
    series, used = {}, {}
    for t in tickers:
        series[t], used[t] = fetch(t, args.days + 10)
        print(f"{t:6} {used[t]:10} {len(series[t]):5} closes, last {max(series[t])}")

    lasts = {t: max(s) for t, s in series.items()}
    newest = max(lasts.values())
    stale = {t: d for t, d in lasts.items() if d != newest}
    if stale:
        print(f"ERROR: tickers disagree on the latest date {newest}: {stale}", file=sys.stderr)
        return 2
    age = (datetime.now(timezone.utc).date() - datetime.strptime(newest, "%Y-%m-%d").date()).days
    if age > args.max_age_days:
        print(f"ERROR: newest close is {newest}, {age} days old; the sources are serving "
              "stale data", file=sys.stderr)
        return 3
    dates = sorted(d for d in set.intersection(*(set(s) for s in series.values())) if d >= cutoff)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["date"] + tickers)
        for d in dates:
            w.writerow([d] + [f"{series[t][d]:.6f}" for t in tickers])
    print(f"wrote {args.out}: {len(dates)} days, {dates[0]} to {dates[-1]}")
    with open(args.out.rsplit(".", 1)[0] + "_sources.json", "w", encoding="utf-8") as fh:
        json.dump({"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "sources": used}, fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
