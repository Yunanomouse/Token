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
> so the versions are limited to the 2.x series.
>
> **Personal use only. Not advice.** The free price data comes from Yahoo
> Finance and may only be used for your own personal, non-commercial purposes.
> Don't share, publish or sell it. Nothing here is financial, investment or tax
> advice. Read [Legal and data terms](#legal-and-data-terms) before you start.

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
  Use the same Python for installing and running: put `python -m` in front
  of the install line from step 2, then run with `python`.
- **Empty results / download errors** — usually a network hiccup or an
  invalid ticker; try again or double-check the symbol on
  https://finance.yahoo.com. The Yahoo provider is unofficial and can be
  rate-limited or break without notice.

## Legal and data terms

Checked 2026-10-13. This is general information, not legal advice.

### What you may do with the data

The prices come from Yahoo Finance through `yfinance`, an unofficial library
that is not affiliated with, endorsed by or vetted by Yahoo. Yahoo's
[Terms of Service](https://legal.yahoo.com/ca/en/yahoo/terms/otos/index.html)
(provided in Canada by Yahoo Finance ULC) forbid commercial use, automated
collection without permission, and redistribution. In practice:

- **OK:** fetching a few tickers for your own personal, non-commercial
  research on your own computer.
- **Not OK without Yahoo's written permission:** sharing, publishing or
  selling the CSVs; committing them to a public repository; using them in a
  paid product; or running a website or service that fetches Yahoo data for
  other people.
- Yahoo rate-limits automated requests and can block your IP. The script
  fetches only a few tickers, pauses between them, and saves a `SOURCE.txt`
  next to the CSVs recording the source, retrieval time and these terms.
- For anything beyond personal use, use a licensed data provider (OpenBB
  supports several keyed providers).

`examples/market_data/` is gitignored so the downloaded data is never
committed to this repository.

### Not advice

Prices may be delayed, adjusted, incomplete or wrong. Nothing in this guide,
the script, or its output is financial, investment, tax or legal advice, or a
recommendation to buy or sell anything. The tickers in the examples (AAPL,
SHOP.TO, BTC-USD) only show Yahoo's symbol formats; they are not picks.
Token's author is not a registered adviser, CPA or lawyer, and this guide
does not provide signals, watchlists, model portfolios or performance claims.
Token's [Terms](../TERMS.md) apply.

### No affiliation or payment

Token and its author have no affiliate, referral or paid relationship with
OpenBB, OpenBQ, Yahoo, any exchange, or any broker, and receive nothing if you
use them. If that ever changes, it will be disclosed here, next to the link.

### Package licenses

| Package | License |
|---|---|
| `openbb-core`, `openbb-equity`, `openbb-cli` | Apache-2.0 |
| `openbb-yfinance` | AGPL-3.0-only |
| `yfinance` (pulled in by `openbb-yfinance`) | Apache-2.0 |

This repository is MIT licensed. Telling you to `pip install` the packages
above is fine under their licenses, because this repository doesn't include
or modify them. If you ever **bundle** `openbb-yfinance` (a Docker image, an
executable, a vendored copy) or **host a modified version** as a network
service, the AGPL requires you to offer its source code, and Yahoo's terms
would forbid the hosting anyway.

### Trademarks

OpenBB, Yahoo and the names of exchanges and brokers are trademarks of their
owners. Token and its author are not affiliated with or endorsed by OpenBB,
OpenBQ, Yahoo or any exchange.
