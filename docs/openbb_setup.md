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

Then add two data providers that need no account:

```
pip install openbb-cboe openbb-tmx
```

- **cboe** — Cboe's own market data: US equities, ETFs and indices.
- **tmx** — TMX Group, the operator of the Toronto Stock Exchange. TSX
  listings priced in Canadian dollars, straight from the exchange.

## 3. Try it

Start Python by typing `python` (Windows) or `python3` (Mac), then paste:

```python
from openbb import obb

# US listing, from Cboe
print(obb.equity.price.historical("AAPL", provider="cboe").to_df().tail())

# Toronto listing, in CAD, from the TSX operator itself
print(obb.equity.price.historical("SHOP", provider="tmx").to_df().tail())
```

The very first `from openbb import obb` takes a minute — it builds its
interface on first run. After that it's fast.

Note the symbols: `cboe` wants the plain US ticker, and `tmx` wants the TSX
root with **no** `.TO` suffix. The `.TO` convention is a Yahoo one.

Type `exit()` to leave Python.

## 4. Or use the ready-made script in this repo

`examples/openbb_quickstart.py` fetches a year of prices for a few tickers
from Cboe and TMX and saves them to CSV files you can open in Excel. Run it
from the repo folder with:

```
python examples/openbb_quickstart.py
```

Edit the `WATCHLIST` at the top of the script to track your own symbols.
Each entry is a `(provider, symbol)` pair.

## 5. Optional: the interactive OpenBB terminal

If you'd rather type commands in a menu-driven terminal instead of Python:

```
pip install openbb-cli
openbb
```

That opens the OpenBB command line — try
`/equity/price/historical --symbol AAPL --provider cboe`.

## A note on Yahoo Finance

Most OpenBB tutorials reach for `provider="yfinance"`. This repo does not,
and neither should you if the numbers are going anywhere near a tax return.

Yahoo has no public API — `yfinance` works by calling the endpoints behind
Yahoo's own web pages. There is no terms of service permitting that, no
stability commitment, and the crypto and TSX series are re-published
aggregates rather than exchange prints. It usually works. The problem is that
when it doesn't, it fails quietly.

`cboe` and `tmx` need no key either, and both are the venues publishing their
own data. For US history with a proper split- and dividend-adjusted close,
`pip install openbb-tiingo` or `openbb-alpha-vantage` and get a free key —
both have a published terms of service that permits what you're doing. See
https://docs.openbb.co/platform/settings/user_settings/api_keys for where to
put keys.

`docs/market_data_providers.md` in this repo covers the full comparison, and
`marketdata/` gives you the same data with **no dependencies at all** if you
would rather skip the OpenBB install.

## Troubleshooting

- **"pip is not recognized"** — Python wasn't added to PATH. Re-run the
  installer, choose "Modify", and enable "Add to PATH" (or use `py -m pip`).
- **"No module named openbb"** — you may have multiple Pythons installed.
  Use the same command for installing and running (`python -m pip install
  openbb`, then `python`).
- **Empty results / download errors** — usually a network hiccup or a symbol
  in the wrong format for that provider. Check a TSX symbol at
  https://money.tmx.com and a US one at https://www.cboe.com/us/equities/.
  Remember: no `.TO` suffix for the `tmx` provider.
- **Not sure which sources your network can reach** — run
  `python3 scripts/check_providers.py`. It tests each one and prints what
  came back.
