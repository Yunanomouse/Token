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

## 5. Display modes: window, borderless, fullscreen

OpenBB itself is a Python library plus a terminal CLI, so it has no window of
its own. Display modes therefore belong to whatever *hosts* OpenBB. This repo
gives you three hosts, each supporting **window**, **borderless window**, and
**fullscreen**.

### The web UI, in a browser window you control

`examples/openbb_launcher.py` opens OpenBB Workspace in a Chromium-family
browser (Chrome, Chromium, Edge, or Brave — it finds them automatically):

```
python examples/openbb_launcher.py --mode window
python examples/openbb_launcher.py --mode borderless --width 1400 --height 900
python examples/openbb_launcher.py --mode fullscreen
python examples/openbb_launcher.py --mode fullscreen --kiosk
```

| Mode | What you get |
|---|---|
| `window` | A normal browser window, with tabs and address bar. |
| `borderless` | Chromium's app mode: no tab strip, no omnibox, still movable and resizable. Good for a dedicated monitor. |
| `fullscreen` | Fills the screen. Add `--kiosk` to lock it down so F11 and Ctrl+W will not leave it. |

Useful extras: `--url` to point at a local OpenBB server instead of
`https://pro.openbb.co`, `--profile` to give the launched browser its own
profile directory, `--position X,Y` to place the window, and `--dry-run` to
print the exact browser command without launching anything.

If no Chromium-family browser is installed, `window` mode falls back to your
default browser and says so; `borderless` and `fullscreen` stop with an error,
because both depend on Chromium command-line flags that other browsers do not
have.

### A native desktop chart

`examples/openbb_desktop.py` is a small Tkinter window that fetches prices
through OpenBB and draws them itself, with no plotting dependencies:

```
python examples/openbb_desktop.py AAPL
python examples/openbb_desktop.py SHOP.TO --days 90 --mode fullscreen
python examples/openbb_desktop.py --demo          # synthetic data, no network
python examples/openbb_desktop.py AAPL --csv examples/market_data/AAPL.csv
```

Switch modes with the buttons in the header, or with the keyboard:

| Key | Action |
|---|---|
| `W` | Windowed — ordinary title bar and borders |
| `B` | Borderless — no window decorations; drag the header strip to move it |
| `F` / `F11` | Fullscreen |
| `Escape` | Back to windowed from either mode |
| `Ctrl+Q` | Quit |

Borderless mode removes the OS title bar, so the app supplies its own drag
strip and close button. If the fetch fails — no network, no `openbb`
installed, a bad ticker — the window still opens and shows the reason, and
the display modes keep working; `--demo` gives you deterministic synthetic
prices to try it with.

Tkinter ships with the python.org installers. On Debian/Ubuntu you may need
`sudo apt install python3-tk`; the script tells you so rather than crashing.

### The trailer page

`src/openbb.html` has the same three modes, offered as a small control in the
bottom-right corner (keys `W`, `B`, `F`, and `Escape`). The page is also the
source for a frame-by-frame video render locked to 1280x720, so the control
deliberately does not appear at exactly that size — the rendered video is
unaffected by it.

## 6. Optional: the interactive OpenBB terminal

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
