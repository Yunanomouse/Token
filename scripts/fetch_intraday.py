#!/usr/bin/env python3
"""Fetch intraday OHLCV bars from Yahoo Finance and write one long-format CSV.

    python3 scripts/fetch_intraday.py --tickers SOFI,RIVN --interval 1m --range 7d --out bars_1m.csv
    python3 scripts/fetch_intraday.py --tickers-file universe.txt --interval 5m --range 60d --out bars_5m.csv

Source: Yahoo Finance's chart endpoint (no key).  Standard library only.
Yahoo caps how far back intraday bars go: 1m about 7-8 days, 2m/5m/15m about
60 days.  Output columns: datetime,ticker,open,high,low,close,volume, with
datetime in the exchange's local time (no offset), regular session only
(bar start 09:30 <= t < 16:00), finished bars on the interval's grid from
09:30 only (the bar still forming and Yahoo's off-grid last-price point are
dropped).  Bars with any null OHLC are dropped.

A ticker that fails or returns no bars is reported and skipped; the script
exits non-zero only if no ticker at all succeeded.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

UA = {"User-Agent": "Mozilla/5.0 (quantum-trading paper bot)"}
# Yahoo rate-limits (HTTP 429) by User-Agent string, and which strings it
# refuses changes over time; on a 429 the same request is retried as these.
ALT_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "Mozilla/5.0",
]
INTERVALS = ("1m", "2m", "5m", "15m", "30m", "60m")
SESSION_OPEN, SESSION_CLOSE = dtime(9, 30), dtime(16, 0)
DEFAULT_TZ = "America/New_York"


def _get(url: str, timeout: float = 30.0, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(url, headers=headers or UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _http_detail(exc: urllib.error.HTTPError) -> str:
    """Yahoo's error description from an HTTP error body, if it has one."""
    try:
        body = json.loads(exc.read())
        return (body.get("chart", {}).get("error") or {}).get("description", "")
    except Exception:
        return ""


def yahoo_intraday(ticker: str, interval: str, rng: str) -> list[tuple]:
    """Return [(local datetime, open, high, low, close, volume)]: the regular
    session's finished bars (see :func:`parse_chart`)."""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
           f"?range={rng}&interval={interval}")
    data = None
    for ua in [None] + ALT_UAS:
        try:
            data = json.loads(_get(url, headers={"User-Agent": ua} if ua else None))
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and ua != ALT_UAS[-1]:
                continue
            detail = _http_detail(exc)
            msg = f"HTTP {exc.code}" + (f": {detail}" if detail else "")
            if "range" in detail.lower() or "data not available" in detail.lower():
                msg += (f" (Yahoo limits how far back {interval} bars go: "
                        "1m ~7d, 2m/5m/15m ~60d; try a shorter --range)")
            raise RuntimeError(msg) from None

    return parse_chart(data, interval)


def parse_chart(data: dict, interval: str, now: datetime | None = None) -> list[tuple]:
    """Regular-session bars from a Yahoo chart response.

    Only whole bars on the interval's grid from 09:30 are kept.  Yahoo also
    returns the bar still forming and, during the session, a last-price
    point stamped with the time of the last trade (e.g. 14:07:25, volume
    0); a row off the grid (seconds != 0, or minutes since 09:30 not a
    multiple of the interval) is dropped, and so is a bar that has not
    finished by ``now`` (default: the current time)."""
    chart = data.get("chart", {})
    if chart.get("error"):
        desc = chart["error"].get("description", chart["error"])
        raise RuntimeError(f"yahoo error: {desc}")
    results = chart.get("result") or []
    if not results:
        raise ValueError("yahoo returned no result")
    res = results[0]
    ts = res.get("timestamp") or []
    quote = (res.get("indicators", {}).get("quote") or [{}])[0]
    tz = ZoneInfo(res.get("meta", {}).get("exchangeTimezoneName") or DEFAULT_TZ)
    step = int(interval[:-1])  # minutes: every interval is "<n>m"
    now = now if now is not None else datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)

    cols = [quote.get(k) or [] for k in ("open", "high", "low", "close", "volume")]
    bars = []
    for i, t in enumerate(ts):
        o, h, l, c, v = (col[i] if i < len(col) else None for col in cols)
        if o is None or h is None or l is None or c is None:
            continue
        local = datetime.fromtimestamp(t, tz=tz)
        if not (SESSION_OPEN <= local.time() < SESSION_CLOSE):
            continue
        if local.second or local.microsecond or (local.hour * 60 + local.minute - 570) % step:
            continue  # the last-price point, off the bar grid
        if local + timedelta(minutes=step) > now:
            continue  # the bar still forming
        bars.append((local.replace(tzinfo=None), o, h, l, c, int(v or 0)))
    if not bars:
        raise ValueError("no regular-session bars in response")
    return bars


def _read_tickers(args) -> list[str]:
    tickers: list[str] = []
    if args.tickers:
        tickers += [t.strip() for t in args.tickers.split(",")]
    if args.tickers_file:
        with open(args.tickers_file, encoding="utf-8") as fh:
            for line in fh:
                line = line.split("#", 1)[0].strip()
                if line:
                    tickers.append(line)
    seen, out = set(), []
    for t in tickers:
        t = t.upper()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tickers", help="comma-separated tickers")
    ap.add_argument("--tickers-file", help="file with one ticker per line (# comments allowed)")
    ap.add_argument("--interval", default="1m", choices=INTERVALS)
    ap.add_argument("--range", dest="rng", default="7d", help="lookback, e.g. 7d, 60d")
    ap.add_argument("--out", required=True, help="output CSV path")
    ap.add_argument("--pause", type=float, default=0.3, help="seconds between tickers")
    args = ap.parse_args()

    tickers = _read_tickers(args)
    if not tickers:
        ap.error("no tickers given (use --tickers and/or --tickers-file)")

    rows, failed, ok = [], {}, 0
    for n, t in enumerate(tickers):
        if n:
            time.sleep(args.pause)
        try:
            bars = yahoo_intraday(t, args.interval, args.rng)
        except Exception as exc:  # network, HTTP, parse, or empty: skip this ticker
            failed[t] = str(exc)
            print(f"{t:6} FAILED: {exc}", file=sys.stderr)
            continue
        ok += 1
        for dt, o, h, l, c, v in bars:
            rows.append((dt, t, o, h, l, c, v))
        print(f"{t:6} {len(bars):6} bars  {bars[0][0]:%Y-%m-%d %H:%M} .. "
              f"{bars[-1][0]:%Y-%m-%d %H:%M}  last close {bars[-1][4]:.4f}")

    if not ok:
        print(f"ERROR: no ticker succeeded ({len(failed)} failed)", file=sys.stderr)
        return 1

    rows.sort(key=lambda r: (r[0], r[1]))
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["datetime", "ticker", "open", "high", "low", "close", "volume"])
        for dt, t, o, h, l, c, v in rows:
            w.writerow([dt.strftime("%Y-%m-%d %H:%M:%S"), t,
                        f"{o:.4f}", f"{h:.4f}", f"{l:.4f}", f"{c:.4f}", v])
    print(f"wrote {args.out}: {len(rows)} bars, {ok}/{len(tickers)} tickers, "
          f"{rows[0][0]:%Y-%m-%d %H:%M} to {rows[-1][0]:%Y-%m-%d %H:%M}"
          + (f"; failed: {', '.join(failed)}" if failed else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
