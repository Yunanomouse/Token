# Running OpenBB on Your Own Computer

OpenBB is a free, open-source financial data platform. It can pull stock
prices, crypto, economic data, and more — right from Python. This guide gets
it running locally in about 10 minutes, no accounts or API keys required.

> **Updated for OpenBB 5.** OpenBB 5.0 (released 29 September 2026) changed
> both the install command and the free data providers. If you followed an
> earlier version of this guide, see [What changed in OpenBB 5](#what-changed-in-openbb-5)
> at the bottom.

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

Then paste this and press Enter (it downloads about a gigabyte, so give it a
few minutes):

```
pip install "openbb[routers]"
```

The quotes and the `[routers]` part matter. As of OpenBB 5, a plain
`pip install openbb` leaves out the modules that actually fetch prices, and
you get `'App' object has no attribute 'equity'` when you try to use one.

If `pip` isn't recognized on Windows, try `py -m pip install "openbb[routers]"`.
On Mac, try `pip3 install "openbb[routers]"`.

## 3. Try it

Start Python by typing `python` (Windows) or `python3` (Mac), then paste:

```python
from openbb import obb

data = obb.equity.price.historical("SHOP", provider="tmx")
df = data.to_df()
print(df.tail())
```

The very first `from openbb import obb` takes a minute — it builds its
interface on first run. After that it's fast. You should see a table of
Shopify's recent daily prices from the Toronto Stock Exchange.

Type `exit()` to leave Python.

## 4. Which free provider to use

No single free provider covers everything, so you pick one per symbol with
the `provider=` argument. These three need no API key:

| Provider | Use it for | Example |
|---|---|---|
| `tmx` | Canadian listings (TSX, TSX-V) | `obb.equity.price.historical("SHOP", provider="tmx")` |
| `cboe` | US listings | `obb.equity.price.historical("AAPL", provider="cboe")` |
| `nasdaq` | crypto, bare coin symbol | `obb.crypto.price.historical("BTC", provider="nasdaq")` |

**Watch out for cross-listed names.** On `tmx`, the symbol `AAPL` is the
**Apple CDR (CAD hedged)** that trades on the TSX — a different security at a
different price from Apple on the Nasdaq. On 2 October 2026 the CDR closed at
$46.90 while Nasdaq Apple closed at $333.69. If you want the US listing, ask
`cboe` for it.

`tmx` accepts Canadian symbols with or without a suffix, so `SHOP`, `SHOP.TO`
and `SHOP.TSX` all work.

## 5. Or use the ready-made script in this repo

`examples/openbb_quickstart.py` fetches a year of prices for a few symbols and
saves them to CSV files you can open in Excel. Run it from the repo folder
with:

```
python examples/openbb_quickstart.py
```

Edit the `SYMBOLS` list at the top of the script to track your own tickers.
Each row carries its own provider, so you can mix Canadian, US, and crypto in
one run.

## 6. Optional: the interactive OpenBB terminal

If you'd rather type commands than write Python:

```
pip install openbb-cli
openbb -i
```

That opens the OpenBB command line — try `/equity/price/historical --symbol SHOP --provider tmx`.
The `-i` flag matters: as of OpenBB 5 the command runs once and exits without
it.

## Other free data worth knowing about

Beyond market prices, these two Canadian government APIs are free, need no
signup, and are useful alongside the tax data in this repo:

- **Statistics Canada** — the CPI series behind the indexation factors in
  `data/json/personal_income_tax_2026.json`. Easiest from Python via
  `pip install stats-can`:

  ```python
  import stats_can
  # v41690973 = CPI, all items, Canada, monthly
  print(stats_can.vectors_to_df(["v41690973"], periods=12))
  ```

- **Bank of Canada Valet** — exchange rates and policy rates, no library
  needed: https://www.bankofcanada.ca/valet/docs

## What changed in OpenBB 5

If something that used to work has stopped:

- **`pip install openbb` is no longer enough.** Use
  `pip install "openbb[routers]"`.
- **The `yfinance` (Yahoo Finance) provider is gone from the default
  install.** It moved out of the official OpenBB project and is now a
  community-maintained package. On a standard OpenBB 5 install,
  `provider="yfinance"` is rejected with
  `Input should be 'cboe', 'nasdaq' or 'tmx'`. You can add it back with
  `pip install openbb-yfinance`, but Yahoo also rate-limits scripted requests
  heavily, so the providers in the table above are the more reliable choice.
- **Other providers were dropped too:** `fmp`, `tiingo`, `intrinio`,
  `finviz`, `seeking-alpha`, `alpha-vantage`, `benzinga`, `econdb` and
  `tradingeconomics`.
- **The CLI no longer stays open by default** — use `openbb -i`.

## Troubleshooting

- **"pip is not recognized"** — Python wasn't added to PATH. Re-run the
  installer, choose "Modify", and enable "Add to PATH" (or use `py -m pip`).
- **"No module named openbb"** — you may have multiple Pythons installed.
  Use the same command for installing and running (`python -m pip install
  "openbb[routers]"`, then `python`).
- **`'App' object has no attribute 'equity'`** — you installed plain
  `openbb`. Run `pip install "openbb[routers]"`.
- **`Input should be 'cboe', 'nasdaq' or 'tmx'`** — you asked for a provider
  that isn't installed, most often `yfinance`. Pick one from the table above.
- **Empty results** — usually a symbol the provider doesn't carry. Check it on
  https://money.tmx.com for Canadian listings, and remember `tmx` covers
  Canada only.
