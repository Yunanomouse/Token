"""Live check: which data sources can this machine actually reach?

Reachability is network-dependent. Stooq and Nasdaq both throttle or block
datacentre IP ranges, so a source that fails on a cloud host often works fine
from a home connection -- and occasionally the reverse. Run this first; it
tells you which providers to build on rather than leaving you to guess from a
stack trace later.

Run:
    python3 scripts/check_providers.py
    python3 scripts/check_providers.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marketdata import ProviderError, fetch_history  # noqa: E402
from marketdata import canada  # noqa: E402
from marketdata.core import PROVIDERS  # noqa: E402

# A representative symbol per provider, chosen to be liquid and long-listed
# so a failure means the source is unreachable, not that the ticker is odd.
SAMPLES = {
    "nasdaq": "AAPL",
    "tmx": "SHOP",
    "kraken": "BTC/USD",
    "coinbase": "BTC-USD",
    "stooq": "aapl.us",
    "alphavantage": "IBM",
    "tiingo": "AAPL",
}


def check_price_providers() -> list[dict]:
    end = date.today()
    start = end - timedelta(days=30)
    results = []

    for name in sorted(PROVIDERS):
        symbol = SAMPLES.get(name)
        if symbol is None:
            continue
        entry = PROVIDERS[name]
        started = time.monotonic()
        try:
            bars = fetch_history(symbol, name, start=start, end=end)
        except ProviderError as exc:
            results.append(
                {
                    "source": name,
                    "kind": "prices",
                    "ok": False,
                    "needs_key": entry.needs_key,
                    "detail": str(exc)[:160],
                    "seconds": round(time.monotonic() - started, 2),
                }
            )
            continue
        results.append(
            {
                "source": name,
                "kind": "prices",
                "ok": True,
                "needs_key": entry.needs_key,
                "detail": (
                    f"{len(bars)} bars, last {bars[-1].date} "
                    f"@ {bars[-1].close:,.2f} {bars[-1].currency}"
                ),
                "seconds": round(time.monotonic() - started, 2),
            }
        )
    return results


def check_official_sources() -> list[dict]:
    checks = [
        (
            "bankofcanada",
            "fx",
            lambda: (lambda r: f"USD/CAD {r.rate} on {r.date}")(
                canada.fx_rate_on(date.today())
            ),
        ),
        (
            "bankofcanada",
            "rates",
            lambda: (lambda p: f"policy rate {p['policy_rate'][-1][1]}%")(
                canada.policy_rates(["policy_rate"], start=date.today() - timedelta(days=60))
            ),
        ),
        (
            "statcan",
            "cpi",
            lambda: (lambda s: f"CPI {s[-1][1]} for {s[-1][0]}")(canada.cpi_all_items(3)),
        ),
    ]

    results = []
    for source, kind, run in checks:
        started = time.monotonic()
        try:
            detail = run()
            ok = True
        except Exception as exc:  # noqa: BLE001 - report every failure mode
            detail = f"{type(exc).__name__}: {exc}"[:160]
            ok = False
        results.append(
            {
                "source": source,
                "kind": kind,
                "ok": ok,
                "needs_key": False,
                "detail": detail,
                "seconds": round(time.monotonic() - started, 2),
            }
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    results = check_price_providers() + check_official_sources()

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"{'SOURCE':<15}{'KIND':<9}{'':<4}{'TIME':>7}   DETAIL")
        print("-" * 92)
        for row in results:
            mark = "ok " if row["ok"] else "FAIL"
            note = " (key)" if row["needs_key"] and not row["ok"] else ""
            print(
                f"{row['source']:<15}{row['kind']:<9}{mark:<4}"
                f"{row['seconds']:>6.2f}s   {row['detail']}{note}"
            )

        working = sum(1 for r in results if r["ok"])
        print("-" * 92)
        print(f"{working} of {len(results)} sources reachable from this machine.")
        if working < len(results):
            print(
                "\nA FAIL marked (key) just needs its API key set. Others are usually "
                "network:\nStooq and Nasdaq block many datacentre IPs but work from a "
                "home connection."
            )

    return 0 if any(r["ok"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
