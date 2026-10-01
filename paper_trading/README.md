# Paper Trading: buy and sell by hand with pretend money

Paper Trading is a small program for practising trades yourself. You start an account with a
balance you choose, look up a stock, and buy or sell it. Nothing is real: **there is no broker,
no real money, and no keys**. It is plain Python with a page in your browser, and it runs only
on your own computer.

> **Not financial advice.** This is a practice tool. Its results are not a prediction of what
> real trading would make, and nothing in it is a recommendation to buy or sell anything.

## Starting it (Windows)

1. You need Python 3.10 or newer. If you don't have it,
   install it from https://www.python.org/downloads/windows/ and tick
   **"Add python.exe to PATH"** in the installer.
2. Double-click **`Paper Trading.bat`** in this folder.
3. The first start on Windows may ask to install `tzdata` (Windows' Python has no time-zone
   data, and New York time decides when the market is open). Answer Y. Nothing else is needed.
4. A black window opens and stays open: that is the program. The page opens in your browser
   at **http://127.0.0.1:8778/**.

Keep the black window open while you use it. Close it to stop; your account is saved after
every change, and open orders are checked again the next time you start it.

On macOS or Linux, run `python3 start.py` in this folder.

If you start it twice, the second window says the port is in use and just opens the page
of the one already running.

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
fresh $100,000 account, and says so at the top of the page and in the black window.

## Where the files are

Everything is in **`paper_data/`** in this folder: `account.json` (the account: cash, orders,
fills, positions, settings) and any backups. The folder is listed in `.gitignore`, so it is
not uploaded if you put this program in a git repository.

To keep the account somewhere else, set the Windows user environment variable
`QT_PAPER_HOME` to a folder, or start it with `--home <folder>` (a full path such as
`--home D:\practice`; a short name is taken inside this program's folder).

## Safety

- No broker is connected and there is no broker code in this program. It cannot place a real
  order anywhere.
- It reads no API keys or passwords.
- The page is served only on this computer (127.0.0.1). Other computers on your network
  can't open it, and other web sites can't send it orders.
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
python start.py                               # same as the .bat
python start.py --port 8778 --home <folder> --no-browser
```

`--port` picks another port, `--home` another account folder, and `--no-browser` doesn't open
the browser (open http://127.0.0.1:8778/ yourself).

## Troubleshooting

- **A window flashes and vanishes**: Python is probably not installed or not on PATH. Install
  it as in step 1, then double-click again.
- **"Port 8778 is in use"**: Paper Trading is already open in another window. Use that one, or
  close it first.
- **"No price for ..."**: Yahoo couldn't be reached (check the internet connection) or the
  symbol doesn't exist. Switch to demo prices with a New account if you want to practise
  offline.
- **My market order hasn't filled**: the market is closed (see the note on the order). It
  fills after the next open, or turn on Practice fills to try things now.
- **My limit order hasn't filled**: the price hasn't reached your limit. Day orders expire at
  the close.
- **The page doesn't open**: open your browser yourself and go to http://127.0.0.1:8778/
  while the black window is open.
- **Windows protected your PC**: click "More info", then "Run anyway". The .bat is a plain
  text file you can open in Notepad.

## Files

| File | What it is |
|---|---|
| `Paper Trading.bat` | Double-click to start (Windows) |
| `start.py` | Checks Python and `tzdata`, then starts the program |
| `paper_app.py` | Accounts, orders, fills, prices and the local web server |
| `paper_page.html` | The page in your browser |

## License

MIT (see `LICENSE`).
