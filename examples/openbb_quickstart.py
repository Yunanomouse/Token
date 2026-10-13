"""Fetch a year of daily prices for a list of tickers and save them as CSVs.

Setup (one time):  pip install "openbb-core>=2,<3" "openbb-equity>=2,<3" "openbb-yfinance>=2,<3"
Run:               python examples/openbb_quickstart.py

Edit TICKERS below to track your own symbols. Uses the free Yahoo Finance
provider, so no API key is needed. See docs/openbb_setup.md for a full
walkthrough.

Note: since openbb 5.0, `pip install openbb` no longer includes the equity
commands or the yfinance provider, so install the three packages above.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

from openbb import obb

# Tickers to fetch. Yahoo symbols: US listings are plain ("AAPL"),
# TSX listings end in .TO ("SHOP.TO"), crypto pairs like "BTC-USD".
TICKERS = ["AAPL", "SHOP.TO", "BTC-USD"]

OUT_DIR = Path(__file__).resolve().parent / "market_data"


def main() -> None:
    if not hasattr(obb, "equity"):
        sys.exit(
            "OpenBB's equity commands are not installed. Run:\n"
            '  pip install "openbb-core>=2,<3" "openbb-equity>=2,<3" '
            '"openbb-yfinance>=2,<3"'
        )

    OUT_DIR.mkdir(exist_ok=True)
    start = date.today() - timedelta(days=365)
    saved = 0

    for symbol in TICKERS:
        print(f"Fetching {symbol} ...")
        try:
            result = obb.equity.price.historical(
                symbol, start_date=str(start), provider="yfinance"
            )
        except Exception as exc:  # noqa: BLE001 - report and keep going
            print(f"  skipped {symbol}: {exc}")
            continue

        df = result.to_df()
        out_file = OUT_DIR / f"{symbol.replace('-', '_').replace('.', '_')}.csv"
        df.to_csv(out_file)
        last_close = df["close"].iloc[-1]
        print(f"  {len(df)} rows -> {out_file.name} (last close: {last_close:,.2f})")
        saved += 1

    if saved == 0:
        sys.exit("\nNo data saved: every ticker failed. See the errors above.")
    print(f"\nDone. {saved} of {len(TICKERS)} CSVs are in {OUT_DIR} — they open directly in Excel.")


if __name__ == "__main__":
    main()
