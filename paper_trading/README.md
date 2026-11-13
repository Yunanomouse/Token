# Paper Trading: buy and sell by hand with pretend money

Paper Trading is a small program for practising trades yourself. You start an account with a
balance you choose, look up a stock, and buy or sell it. Nothing is real: **there is no broker,
no real money, and no keys**. It is a normal Windows program with its own window, and it
runs only on your own computer.

> **Not financial advice.** This is a practice tool. Its results are not a prediction of what
> real trading would make, and nothing in it is a recommendation to buy or sell anything.

## Installing it (Windows)

1. Download **`Paper Trading Setup.exe`** from the
   [paper-trading-latest release](https://github.com/Yunanomouse/Token/releases/tag/paper-trading-latest).
2. Double-click it. If Windows says "Windows protected your PC", click **More info**, then
   **Run anyway** (the installer isn't signed with a paid certificate).
3. Click through the installer. It needs no administrator rights, adds Paper Trading to the
   Start menu and, if you leave the box ticked, puts an icon on the desktop.
4. Open **Paper Trading** from the Start menu or the desktop icon. It opens in its own
   window. Python is included; there is nothing else to install.

Close the window to stop it. Your account is saved after every change, and open orders are
checked again the next time you open it. If you open it while it is already running, a second
window shows the same account.

To remove it: Settings > Apps > Installed apps > Paper Trading > Uninstall. Your account is
**not** deleted (see "Where the files are"), so reinstalling or updating keeps it.

The window is drawn by Microsoft Edge WebView2, which Windows 10 and 11 already include. On
a PC without it, Paper Trading opens in your web browser instead and says so; installing
WebView2 from https://developer.microsoft.com/microsoft-edge/webview2/ gives it its own window.

### Running it from these files instead

With Python 3.10 or newer (from https://www.python.org/downloads/, tick **"Add python.exe to
PATH"**), double-click **`Paper Trading.bat`** in this folder, or run `python3 start.py` on
macOS or Linux. The first start offers to install `tzdata` (Windows only: New York time
decides when the market is open) and `pywebview` (the program window; without it the page
opens in your browser). Answer Y.

## The page

The banner at the top always says **pretend money** and shows whether you are on live or demo
prices. Next to it: whether the market is open, a **Refresh prices** button, and the account
folder with an **Open folder** button.

| Tab | What it is for |
|---|---|
| **Trade** | The order ticket: type a symbol, **Get quote**, choose buy or sell, the order type, quantity and time in force, then **Review order** and confirm. The watchlist is here too; click a symbol to put it on the ticket. |
| **Portfolio** | What you hold: shares, average cost, today's price, market value, gain or loss. Below it, a chart of the account's value over time against the starting balance. |
| **Orders** | Open orders (with a Cancel button) and the order history, newest first. Each order shows its status: open, filled, cancelled, expired or rejected, with a note saying why. |
| **Activity** | Every fill: when, what, how many, the price, the commission, and for sells the realized profit or loss. |
| **Settings** | Commission, slippage, fractional shares and practice fills (see below), and **New account**. |

Prices of open orders, positions and the watchlist are refreshed every 30 seconds while the
program runs.

## How orders fill

**Order types**

- **Market**: fills at the current price.
- **Limit**: fills only at your price or better, slippage included. A buy limit fills once
  the price plus slippage is at or below your limit; a sell limit once the price minus
  slippage is at or above it. (Slippage stands for the gap between buyers' and sellers'
  prices, so a limit order at today's price doesn't avoid it.)
- **Stop**: waits until the price reaches your stop, then fills like a market order. A buy
  stop triggers when the price rises to the stop; a sell stop (a "stop-loss") when it falls to
  it. The fill can be worse than the stop if the price jumped past it. A buy stop must be
  above the current price and a sell stop below it; otherwise use a market or limit order.

**Time in force**

- **Day**: if it hasn't filled by the close of its session, it expires. An order placed while
  the market is closed belongs to the next session. This holds on demo prices and with
  practice fills too.
- **GTC** (good till cancelled): stays open until it fills or you cancel it.

**Costs.** Every fill pays the **slippage** you set: buys fill that much above the price,
sells that much below (in basis points; 1 bp = 0.01%, default 2 bp). Each order also pays the
**commission** you set (dollars per order, default $0). Each fill shows its price, with the
slippage already in it, and its commission; the total commission is on the account summary.

**Market hours.** Real-price orders fill only during the regular New York session, 9:30 am to
4:00 pm Eastern, Monday to Friday, except market holidays. On the half days (2026-11-27,
2026-12-24 and 2027-11-26) the market closes at 1:00 pm. An order placed while the market is
closed waits, with a note saying so, and is checked again once it opens. Just after the open,
an order also waits until the quote shows a price from the new day, so it doesn't fill at last
night's closing price. Market holidays are listed for 2026 and 2027; after that, every
weekday counts as a trading day until the list is updated.

**US-dollar stocks only.** A symbol priced in another currency (for example Toyota, 7203.T, in
yen) is refused, because the account is in dollars. Class shares can be typed either way:
BRK.B or BRK-B.

**Buying power.** Cash minus the money set aside for your open buy orders (at their limit or
stop price, or the last price for a market order, plus slippage and commission). A buy that
needs more than your buying power is refused. If prices move while an order waits and there is
no longer enough cash when it would fill, it is **rejected** with a note.

**No short selling.** You can sell only shares you hold, minus shares already promised to your
other open sell orders.

**Whole shares** unless you turn on **fractional shares** in Settings (quantities like 0.5,
up to 6 decimals). You can't turn fractional shares off while you hold a fractional amount.

**Profit and loss.** Realized P/L on a sale is what you got (after commission) minus what those
shares cost on average (including the commission you paid buying them).

## Live prices or demo prices

- **Live** (the default): real prices from Yahoo Finance's public chart service, **delayed by up
  to about 15 minutes**. That service is unofficial and meant for personal use: Yahoo can change
  or block it at any time, and its terms don't allow republishing the prices. This program only
  shows them to you on your own computer and doesn't store or share them.
  The only thing sent is the stock symbol you look up; nothing about you or your account is
  sent. You need an internet connection; if Yahoo can't be reached the page says so and
  orders wait.
- **Demo**: made-up prices that wander like a stock (about 2% a day). No internet needed,
  any symbol works, and orders fill at any hour, so you can try everything on a weekend.
  Demo prices have nothing to do with the real stock.

You choose between them when you start a **New account** (Settings).

## Practice fills

With **Practice fills** on (Settings), orders on live prices also fill while the market is
closed, at the last price Yahoo showed. This is **not realistic**: a real order placed at night
fills at the next open, often at a different price. It is only for trying the program; those
fills are marked "Practice fill" in the history.

## New account and backups

**Settings > New account** starts over with the balance you choose (from $1 to $100 million)
and live or demo prices. Your watchlist and settings carry over. The old account is not
deleted: it is kept in the account folder as `account.bak-<date>-<time>.json`.

If the account file is ever damaged (for example the computer lost power while it was being
saved), the program keeps the damaged file as `account.corrupt-<date>-<time>.json`, starts a
fresh $100,000 account, and says so at the top of the page.

## Where the files are

The installed program keeps everything in **`%APPDATA%\Paper Trading`** (paste that into
File Explorer's address bar, or press **Open folder** in the program): `account.json` (the
account: cash, orders, fills, positions, settings), any backups, and `paper_trading.log` (what
the program reports, for troubleshooting). Run from these files, it uses **`paper_data/`** in
this folder instead; that folder is listed in `.gitignore`, so it is not uploaded if you put
this program in a git repository.

To keep the account somewhere else, set the Windows user environment variable
`QT_PAPER_HOME` to a folder, or start it with `--home <folder>` (a full path such as
`--home D:\practice`).

## Safety

- No broker is connected and there is no broker code in this program. It cannot place a real
  order anywhere.
- It reads no API keys or passwords.
- The window talks to the program over this computer's own address (127.0.0.1) only. Other
  computers on your network can't reach it, and web sites can't send it orders.
- The only internet request is the price lookup described above.

## How realistic is it?

Treat the results as practice, not as proof of what you would have made:

- Quotes are delayed about 15 minutes, so a fill here is at a price from up to 15 minutes ago,
  not what a broker would give you now.
- Every order fills completely at one price. Real orders can fill in pieces, wait in a queue
  behind other orders at the same limit price, or not fill at all when a limit is only just
  touched.
- Slippage is a fixed amount you set; real slippage depends on the stock, the size of the
  order and the moment.
- Dividends, splits, borrowing and taxes are not modelled.

## Command line

```
"Paper Trading.exe" [--home <folder>] [--port 8778] [--browser]
python start.py     [--home <folder>] [--port 8778] [--browser]   # from these files
```

`--home` uses another account folder, `--port` another local port, and `--browser` opens it in
your web browser instead of its own window. `--headless` runs it with no window at all (for
testing; open http://127.0.0.1:8778/ yourself).

## Troubleshooting

- **Nothing opens, or it closes at once**: look in `paper_trading.log` in the account folder
  for the reason. Run from these files, a black window that flashes and vanishes means Python
  isn't installed or not on PATH.
- **It opened in the browser, not its own window**: WebView2 is missing; see "Installing it".
- **"No price for ..."**: Yahoo couldn't be reached (check the internet connection) or the
  symbol doesn't exist. Switch to demo prices with a New account if you want to practise
  offline.
- **My market order hasn't filled**: the market is closed (see the note on the order). It
  fills after the next open, or turn on Practice fills to try things now.
- **My limit order hasn't filled**: the price hasn't reached your limit. Day orders expire at
  the close.
- **Windows protected your PC**: click "More info", then "Run anyway".

## Files

| File | What it is |
|---|---|
| `window.py` | The program: starts the engine and shows the screen in its own window |
| `paper_app.py` | Accounts, orders, fills, prices and the local server the window talks to |
| `paper_page.html` | The screen inside the window |
| `Paper Trading.bat`, `start.py` | Run it from these files with Python (Windows / any system) |
| `packaging/` | Builds `Paper Trading.exe` and `Paper Trading Setup.exe` (done by GitHub Actions) |

## License

MIT (see `LICENSE`).
