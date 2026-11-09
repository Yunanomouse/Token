"""Fetch recent daily prices for a list of symbols and save them as CSVs.

Setup (one time):  pip install "openbb[routers]"
Run:               python examples/openbb_quickstart.py

Edit SYMBOLS below to track your own tickers. Every provider used here is free
and needs no API key. See docs/openbb_setup.md for a full walkthrough.

Each symbol names the provider to fetch it from, because no single free
provider covers everything:

  tmx     Canadian listings (TSX, TSX-V). Canada only.
  cboe    US listings.
  nasdaq  crypto, using the bare coin symbol ("BTC", not "BTC-USD").

Careful with cross-listed names: on TMX the symbol "AAPL" is the Apple CDR
(CAD hedged) that trades on the TSX, not Apple on the Nasdaq. They are
different securities at different prices. Fetch US names from cboe.
"""

from datetime import date, timedelta
from pathlib import Path

from openbb import obb

# (symbol, provider, what it is). Add your own rows here.
SYMBOLS = [
    ("SHOP", "tmx", "Shopify on the TSX"),
    ("AAPL", "cboe", "Apple on the Nasdaq"),
    ("BTC", "nasdaq", "Bitcoin"),
]

OUT_DIR = Path(__file__).resolve().parent / "market_data"


def fetch(symbol: str, provider: str, start: date):
    """Return a DataFrame of daily prices, or None if the fetch failed."""
    route = obb.crypto if provider == "nasdaq" else obb.equity
    result = route.price.historical(
        symbol, start_date=str(start), provider=provider
    )
    return result.to_df()


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    start = date.today() - timedelta(days=365)

    for symbol, provider, description in SYMBOLS:
        print(f"Fetching {symbol} ({description}) from {provider} ...")
        try:
            df = fetch(symbol, provider, start)
        except Exception as exc:  # noqa: BLE001 - report and keep going
            print(f"  skipped {symbol}: {exc}")
            continue

        out_file = OUT_DIR / f"{symbol}_{provider}.csv"
        df.to_csv(out_file)
        last_close = df["close"].iloc[-1]
        print(f"  {len(df)} rows -> {out_file.name} (last close: {last_close:,.2f})")

    print(f"\nDone. CSVs are in {OUT_DIR} — they open directly in Excel.")


if __name__ == "__main__":
    main()
