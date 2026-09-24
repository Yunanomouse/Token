"""Fetch a year of daily prices through OpenBB, without using Yahoo Finance.

OpenBB defaults many examples to its `yfinance` provider. This script uses
keyless alternatives instead:

    cboe  - Cboe's own market data: US equities, ETFs and indices
    tmx   - TMX Group: TSX / TSX Venture listings, priced in CAD

Setup (one time):
    pip install openbb openbb-cboe openbb-tmx

Run:
    python3 examples/openbb_quickstart.py

If you would rather not install OpenBB at all, this repo's own `marketdata`
package does the same job with no dependencies whatsoever -- see
examples/market_data_quickstart.py and docs/market_data_providers.md.
"""

from datetime import date, timedelta
from pathlib import Path

from openbb import obb

# (provider, symbol). Cboe wants plain US tickers; TMX wants the TSX root
# with no ".TO" suffix.
WATCHLIST = [
    ("cboe", "AAPL"),
    ("cboe", "SPY"),
    ("tmx", "SHOP"),
    ("tmx", "XIU"),
]

OUT_DIR = Path(__file__).resolve().parent / "market_data"


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    start = date.today() - timedelta(days=365)

    for provider, symbol in WATCHLIST:
        print(f"Fetching {symbol} from {provider} ...")
        try:
            result = obb.equity.price.historical(
                symbol, start_date=str(start), provider=provider
            )
        except Exception as exc:  # noqa: BLE001 - report and keep going
            print(f"  skipped {symbol}: {exc}")
            continue

        df = result.to_df()
        if df.empty:
            print(f"  skipped {symbol}: provider returned no rows")
            continue

        out_file = OUT_DIR / f"{provider}_{symbol.replace('.', '_')}.csv"
        df.to_csv(out_file)
        print(f"  {len(df)} rows -> {out_file.name} (last close: {df['close'].iloc[-1]:,.2f})")

    print(f"\nDone. CSVs are in {OUT_DIR} - they open directly in Excel.")


if __name__ == "__main__":
    main()
