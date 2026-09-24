"""Fetch a year of daily prices without touching Yahoo Finance.

Replaces the yfinance-backed quickstart. Every symbol below is pulled from
the venue that actually printed the trades, or from a licensed vendor:

  * US equities  -> Nasdaq's own API (no key)
  * TSX equities -> TMX Group, in CAD (no key)
  * Crypto       -> Kraken, including native CAD pairs (no key)

Requires nothing but the Python standard library.

Run:
    python3 examples/market_data_quickstart.py
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marketdata import ProviderError, fetch_history  # noqa: E402
from marketdata.core import CSV_COLUMNS  # noqa: E402

# (provider, symbol) pairs. Edit this list to track your own instruments.
#   tmx    wants the plain TSX root: SHOP, RY, ENB, XIU
#   nasdaq wants the US ticker:      AAPL, MSFT, SPY
#   kraken wants a pair:             BTC/CAD, ETH/CAD, BTC/USD
WATCHLIST = [
    ("nasdaq", "AAPL"),
    ("tmx", "SHOP"),
    ("tmx", "XIU"),
    ("kraken", "BTC/CAD"),
]

OUT_DIR = Path(__file__).resolve().parent / "market_data"


def main() -> int:
    import csv

    OUT_DIR.mkdir(exist_ok=True)
    start = date.today() - timedelta(days=365)
    failures = 0

    for provider, symbol in WATCHLIST:
        print(f"Fetching {symbol} from {provider} ...")
        try:
            bars = fetch_history(symbol, provider, start=start)
        except ProviderError as exc:
            # One unreachable venue should not cost you the rest of the run.
            print(f"  skipped: {exc}")
            failures += 1
            continue

        safe = symbol.replace("/", "_").replace("-", "_").replace(".", "_")
        out_file = OUT_DIR / f"{provider}_{safe}.csv"
        with out_file.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(bar.as_row() for bar in bars)

        last = bars[-1]
        print(
            f"  {len(bars)} rows -> {out_file.name} "
            f"(last close {last.close:,.2f} {last.currency} on {last.date})"
        )

    print(f"\nDone. CSVs are in {OUT_DIR} - they open directly in Excel.")
    if failures:
        print(
            f"{failures} source(s) were unreachable. Run "
            "`python3 -m marketdata providers` to see the alternatives."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
