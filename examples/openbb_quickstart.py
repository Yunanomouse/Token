"""Fetch a year of daily prices for a list of tickers and save them as CSVs.

Setup (one time):  pip install openbb
Run:               python examples/openbb_quickstart.py

Edit TICKERS below to track your own symbols. Uses the free Yahoo Finance
provider, so no API key is needed. See docs/openbb_setup.md for a full
walkthrough.

Exits with status 1 if no ticker could be fetched, so the failure is visible
to whatever ran the script.
"""

import socket
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from openbb import obb

# Tickers to fetch. Yahoo symbols: US listings are plain ("AAPL"),
# TSX listings end in .TO ("SHOP.TO"), crypto pairs like "BTC-USD".
TICKERS = ["AAPL", "SHOP.TO", "BTC-USD"]

OUT_DIR = Path(__file__).resolve().parent / "market_data"

# Yahoo's price endpoint. Used only to tell "the network blocked us" apart
# from "that ticker is wrong" when everything fails.
PROBE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/AAPL?range=1d"


def _one_line(exc: Exception) -> str:
    """OpenBB errors are multi-line and often start with a newline."""
    text = " ".join(str(exc).split())
    return text or type(exc).__name__


def _yahoo_reachable(timeout: float = 10.0) -> bool:
    """Can this machine reach Yahoo at all?

    OpenBB reports a blocked network and a nonexistent ticker with the same
    "no results found" error, so guessing from the message text sends people
    to check their symbols when the real problem is a proxy or firewall.
    An HTTP status of any kind means we got through; only a transport-level
    failure means we did not.
    """
    request = urllib.request.Request(PROBE_URL, headers={"User-Agent": "Mozilla/5.0"})
    try:
        urllib.request.urlopen(request, timeout=timeout).close()
        return True
    except urllib.error.HTTPError:
        return True  # reached Yahoo; it just declined this request
    except (urllib.error.URLError, socket.timeout, OSError):
        return False


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)
    start = date.today() - timedelta(days=365)

    saved: list[str] = []
    failed: list[tuple[str, str]] = []

    for symbol in TICKERS:
        print(f"Fetching {symbol} ...")
        try:
            result = obb.equity.price.historical(
                symbol, start_date=str(start), provider="yfinance"
            )
            df = result.to_df()
        except Exception as exc:  # noqa: BLE001 - report and keep going
            reason = _one_line(exc)
            print(f"  skipped {symbol}: {reason}")
            failed.append((symbol, reason))
            continue

        if df.empty:
            reason = "no rows returned"
            print(f"  skipped {symbol}: {reason}")
            failed.append((symbol, reason))
            continue

        out_file = OUT_DIR / f"{symbol.replace('-', '_').replace('.', '_')}.csv"
        df.to_csv(out_file)
        saved.append(symbol)
        last_close = df["close"].iloc[-1]
        print(f"  {len(df)} rows -> {out_file.name} (last close: {last_close:,.2f})")

    print()
    if saved:
        print(f"Saved {len(saved)} of {len(TICKERS)} tickers to {OUT_DIR}")
        print("The CSVs open directly in Excel.")
    else:
        print(f"No data was saved — all {len(TICKERS)} tickers failed.")

    if failed:
        print("\nFailed:")
        for symbol, reason in failed:
            print(f"  {symbol}: {reason}")

        if not saved:
            print("\nChecking whether Yahoo Finance is reachable ...")
            if _yahoo_reachable():
                print(
                    "  Yahoo is reachable, so this is not a network problem. "
                    "Double-check the symbols on https://finance.yahoo.com — "
                    "Toronto listings need a .TO suffix (SHOP.TO)."
                )
            else:
                print(
                    "  Could not reach Yahoo Finance from this machine. The "
                    "symbols are probably fine; something between you and "
                    "Yahoo is blocking the request — a corporate proxy, VPN, "
                    "firewall, or a restricted cloud sandbox. Try a different "
                    "network, or allow finance.yahoo.com and "
                    "query1.finance.yahoo.com through it."
                )

    return 0 if saved else 1


if __name__ == "__main__":
    sys.exit(main())
