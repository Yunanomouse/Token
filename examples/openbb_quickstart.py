"""Fetch a year of daily prices for a list of tickers and save them as CSVs.

Setup (one time):  pip install "openbb-core>=2,<3" "openbb-equity>=2,<3" "openbb-yfinance>=2,<3"
Run:               python examples/openbb_quickstart.py

Edit TICKERS below to track your own symbols. Uses the free Yahoo Finance
provider, so no API key is needed. See docs/openbb_setup.md for a full
walkthrough.

Note: since openbb 5.0, `pip install openbb` no longer includes the equity
commands or the yfinance provider, so install the three packages above.

Legal: the data comes from Yahoo Finance through the unofficial yfinance
library and is for personal, non-commercial use only under Yahoo's terms.
Don't share, publish, sell or host it. Not financial, investment or tax
advice. This script only imports openbb-yfinance (AGPL-3.0); it does not
bundle it. See "Legal and data terms" in docs/openbb_setup.md.
"""

import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from openbb import obb

# Tickers to fetch. Yahoo symbols: US listings are plain ("AAPL"),
# TSX listings end in .TO ("SHOP.TO"), crypto pairs like "BTC-USD".
# Keep the list short: Yahoo rate-limits automated requests.
TICKERS = ["AAPL", "SHOP.TO", "BTC-USD"]

# Seconds to wait between tickers, to stay well under Yahoo's rate limits.
PAUSE_SECONDS = 1.5

# Saved data stays on your computer. This folder is gitignored because
# Yahoo's terms forbid redistributing the data.
OUT_DIR = Path(__file__).resolve().parent / "market_data"

YAHOO_TERMS = "https://legal.yahoo.com/ca/en/yahoo/terms/otos/index.html"

NOTICE = (
    "Data: Yahoo Finance via yfinance (unofficial, not affiliated with or\n"
    "endorsed by Yahoo or OpenBB). Personal, non-commercial use only. Don't\n"
    "share, publish or sell it. Prices may be delayed or wrong. Not financial,\n"
    "investment or tax advice."
)


def write_source_note(fetched: list[str]) -> None:
    """Record where the CSVs came from and how they may be used."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    (OUT_DIR / "SOURCE.txt").write_text(
        "Source of the CSV files in this folder\n"
        "======================================\n\n"
        f"Retrieved:  {stamp}\n"
        f"Tickers:    {', '.join(fetched)}\n"
        "Provider:   Yahoo Finance, via the yfinance library and the\n"
        "            openbb-yfinance provider (unofficial; not affiliated with\n"
        "            or endorsed by Yahoo or OpenBB)\n"
        f"Terms:      {YAHOO_TERMS}\n\n"
        "Personal, non-commercial use only. Do not redistribute, publish,\n"
        "sell or host this data, or commit it to a public repository.\n"
        "Prices may be delayed, adjusted or inaccurate. Not financial,\n"
        "investment or tax advice.\n",
        encoding="utf-8",
    )


def main() -> None:
    if not hasattr(obb, "equity"):
        sys.exit(
            "OpenBB's equity commands are not installed. Run:\n"
            '  pip install "openbb-core>=2,<3" "openbb-equity>=2,<3" '
            '"openbb-yfinance>=2,<3"'
        )

    print(NOTICE + "\n")
    OUT_DIR.mkdir(exist_ok=True)
    start = date.today() - timedelta(days=365)
    fetched = []

    for i, symbol in enumerate(TICKERS):
        if i:
            time.sleep(PAUSE_SECONDS)
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
        fetched.append(symbol)

    if not fetched:
        sys.exit("\nNo data saved: every ticker failed. See the errors above.")
    write_source_note(fetched)
    print(f"\nDone. {len(fetched)} of {len(TICKERS)} CSVs are in {OUT_DIR} — they open directly in Excel.")
    print("SOURCE.txt in that folder records where the data came from and its use terms.")


if __name__ == "__main__":
    main()
