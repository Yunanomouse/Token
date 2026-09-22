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
  https://finance.yahoo.com. The quickstart script now prints a summary of
  which tickers failed and why, and tells you whether the cause looks like a
  network problem or a bad symbol.
- **Every ticker fails with a connection, proxy, or tunnel error** — the
  requests aren't reaching Yahoo at all. Corporate networks, VPNs, school
  Wi-Fi, and locked-down cloud sandboxes often block `finance.yahoo.com`.
  Try the same script on a home connection or off the VPN; if it has to run
  on the restricted network, the network's egress rules need to allow
  `finance.yahoo.com` and `query1.finance.yahoo.com`, or you'll need a
  provider that is reachable (most alternatives require a free API key).
- **`pip install openbb` fails with "Cannot uninstall <package>, RECORD file
  not found"** — your Python is managed by the operating system (common on
  Linux and on Macs using Homebrew Python), and pip isn't allowed to replace
  a system package. Install into a virtual environment instead:

  ```
  python3 -m venv ~/openbb-env
  source ~/openbb-env/bin/activate      # Windows: %USERPROFILE%\openbb-env\Scripts\activate
  pip install openbb
  ```

  Then run the script with that environment active. Re-run the `activate`
  line each time you open a new terminal.
