"""Fetch a year of daily prices for a list of tickers and save them as CSVs.

Setup (one time):  pip install openbb
Run:               python examples/openbb_quickstart.py

Edit TICKERS below to track your own symbols. Uses the free Yahoo Finance
provider, so no API key is needed. See docs/openbb_setup.md for a full
walkthrough.
"""

from datetime import date, timedelta
from pathlib import Path

from openbb import obb

# Tickers to fetch. Yahoo symbols: US listings are plain ("AAPL"),
# TSX listings end in .TO ("SHOP.TO"), crypto pairs like "BTC-USD".
TICKERS = ["AAPL", "SHOP.TO", "BTC-USD"]

OUT_DIR = Path(__file__).resolve().parent / "market_data"


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    start = date.today() - timedelta(days=365)

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

    print(f"\nDone. CSVs are in {OUT_DIR} — they open directly in Excel.")


if __name__ == "__main__":
    main()
