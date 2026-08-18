# Running OpenBB on Your Own Computer

OpenBB is a free, open-source financial data platform. It can pull stock
prices, options, economic data, and more — right from Python. This guide gets
it running locally in about 10 minutes, no accounts or API keys required for
the basics.

## 1. Install Python (if you don't have it)

- **Windows:** Download Python from https://www.python.org/downloads/ and run
  the installer. **Important:** on the first installer screen, tick the
  checkbox "Add python.exe to PATH" before clicking Install.
- **Mac:** Python 3 is usually already installed. Open the **Terminal** app
  (find it with Spotlight: press Cmd+Space, type "terminal") and run
  `python3 --version`. If that prints a version like `3.11`, you're set.
  Otherwise install it from https://www.python.org/downloads/.

OpenBB needs Python 3.10 or newer.

## 2. Install OpenBB

Open a terminal:

- **Windows:** press the Windows key, type `cmd`, press Enter.
- **Mac:** open the Terminal app.

Then paste this and press Enter (it downloads a few hundred MB, so give it a
few minutes):

```
pip install openbb
```

If `pip` isn't recognized on Windows, try `py -m pip install openbb`.
On Mac, try `pip3 install openbb`.

## 3. Try it

Start Python by typing `python` (Windows) or `python3` (Mac), then paste:

```python
from openbb import obb

data = obb.equity.price.historical("AAPL", provider="yfinance")
df = data.to_df()
print(df.tail())
```

The very first `from openbb import obb` takes a minute — it builds its
interface on first run. After that it's fast. You should see a table of
Apple's recent daily prices. Swap `"AAPL"` for any ticker
(`"SHOP.TO"` for Toronto-listed Shopify, `"BTC-USD"` for Bitcoin, etc.).

Type `exit()` to leave Python.

## 4. Or use the ready-made script in this repo

`examples/openbb_quickstart.py` fetches a year of prices for a few tickers
and saves them to CSV files you can open in Excel. Run it from the repo
folder with:

```
python examples/openbb_quickstart.py
```

Edit the `TICKERS` list at the top of the script to track your own symbols.

## 5. Optional: the interactive OpenBB terminal

If you'd rather type commands in a menu-driven terminal instead of Python:

```
pip install openbb-cli
openbb
```

That opens the OpenBB command line — try `/equity/price/historical --symbol AAPL`.

## Free data, no keys needed

The `yfinance` provider (Yahoo Finance) works with no signup and covers
stocks, ETFs, indices, currencies, and crypto. Other providers (FMP, FRED,
Intrinio, ...) unlock more data but need free-or-paid API keys — see
https://docs.openbb.co/platform/settings/user_settings/api_keys if you ever
want those.

## Troubleshooting

- **"pip is not recognized"** — Python wasn't added to PATH. Re-run the
  installer, choose "Modify", and enable "Add to PATH" (or use `py -m pip`).
- **"No module named openbb"** — you may have multiple Pythons installed.
  Use the same command for installing and running (`python -m pip install
  openbb`, then `python`).
- **Empty results / download errors** — usually a network hiccup or an
  invalid ticker; try again or double-check the symbol on
  https://finance.yahoo.com.
