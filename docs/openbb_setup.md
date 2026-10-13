# Running OpenBB on Your Own Computer

> **Optional extra.** Nothing else in this repo needs OpenBB; the tax data and
> calculators run on plain Python. Use this if you want free price history
> alongside them.
>
> **Status (checked 2026-10-13):** OpenBB the company announced on 2026-08-25
> that it is open-sourcing its whole suite and stepping back; a non-profit,
> OpenBQ, now stewards the code
> ([announcement](https://openbb.co/blog/openbb-belongs-to-everyone)). The
> packages below still install and work, but future maintenance is unclear,
> so the versions are pinned.

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

Then paste this and press Enter (it downloads several hundred MB, so give it a
few minutes):

```
pip install "openbb-core>=2,<3" "openbb-equity>=2,<3" "openbb-yfinance>=2,<3"
```

If `pip` isn't recognized on Windows, start the line with `py -m pip install`
instead. On Mac, use `pip3 install`.

> **Don't use plain `pip install openbb`.** Since version 5.0 (2026) that
> bundle no longer includes stock prices or the free Yahoo Finance provider,
> and the example below fails with `'App' object has no attribute 'equity'`.

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

If you'd rather type commands than write Python:

```
pip install "openbb-cli>=2,<3"
openbb equity.price.historical --symbol AAPL --provider yfinance
```

That prints the prices as JSON. Run `openbb -i` for an interactive prompt
with tab completion.

## Free data, no keys needed

The `yfinance` provider (Yahoo Finance) works with no signup and covers
stocks, ETFs, indices, currencies, and crypto. Other providers (FMP, FRED,
Intrinio, ...) unlock more data but need free-or-paid API keys — see
https://docs.openbb.co/platform/settings/user_settings/api_keys if you ever
want those.

## Troubleshooting

- **"pip is not recognized"** — Python wasn't added to PATH. Re-run the
  installer, choose "Modify", and enable "Add to PATH" (or use `py -m pip`).
- **`'App' object has no attribute 'equity'`** — you installed the plain
  `openbb` bundle. Run the install line from step 2.
- **"No module named openbb"** — you may have multiple Pythons installed.
  Use the same command for installing and running (`python -m pip install
  openbb`, then `python`).
- **Empty results / download errors** — usually a network hiccup or an
  invalid ticker; try again or double-check the symbol on
  https://finance.yahoo.com. The Yahoo provider is unofficial and can be
  rate-limited or break without notice.

## License note

`openbb-core` and `openbb-equity` are Apache-2.0. The `openbb-yfinance`
provider is AGPL-3.0, which is fine for personal use but matters if you ever
host or sell a modified version of a tool that bundles it.
