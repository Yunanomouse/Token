# Quantum Station: every bot on your own computer

Quantum Station runs the three paper bots on your PC, on a timer, with a dashboard in your
browser. GitHub isn't involved. It is **paper trading only**: no job can reach a broker,
whatever is set on the computer.

| Bot | When it runs | What it does |
|---|---|---|
| $100k daily bot | Once each trading day, after 4:30 pm New York time | Fetches the day's closes and runs the engine over every new day |
| $40 whole-share bot | Same | Same, and writes the day's orders for you to place by hand if you choose |
| $50 intraday bot (5-minute KAMA) | Every 5 minutes while the market is open | Replays today so far from fresh bars. After the close, archives the day's result |

## Starting it (Windows)

1. Install Python 3.10 or newer from https://www.python.org/downloads/windows/ and tick
   **"Add python.exe to PATH"** in the installer.
2. Double-click **`Quantum Station.bat`** in this folder.
3. The first start asks to install two small packages: `numpy`, and `tzdata` (Windows'
   Python has no time-zone data, and New York time decides when the bots run). Answer Y.
4. A black window opens and stays open: that is the station. The dashboard opens in your
   browser at http://127.0.0.1:8777/.

**The bots run only while that black window is open and the computer is awake.** If the PC
is off or asleep at 4:30 pm, the daily bots catch up the next time the station starts. The
engine processes every missed day, so nothing is lost. A missed intraday session is not
replayed. Each intraday day is independent, and that day's status simply isn't archived.

On macOS or Linux, run `python3 station.py` in this folder.

### Starting it with Windows (optional)

Press Win+R, type `shell:startup` and press Enter. A folder opens. Right-click
`Quantum Station.bat`, choose **Create shortcut**, and move the shortcut into that folder.
The station then opens each time you sign in. To stop that, delete the shortcut.

## The dashboard

- **Overview:** one card per bot, with equity, change since start, drawdown and its last run.
  Also the market status and when each job runs next.
- **Daily bots:** the equity curve, positions with average cost and open gain, recent trades,
  and the scorecard against equal weight. For the $40 bot, today's orders. In paper mode
  these are for information only. They are what the bot would place if it were real money,
  and nothing is sent.
- **Intraday:** today's account, trades, open position and the stocks screened, plus a
  table of past days.
- **Tools:**
  - *Download intraday bars:* 60 days of 5-minute bars for the intraday stock list.
  - *Backtest the $100k or $40 bot:* replays the bot's rules over its last two years of
    prices. This runs in a separate folder and doesn't touch the live books.
  - *Backtest the intraday bot:* runs the live intraday rules on the downloaded bars and
    compares them with random entries. This is in-sample, so it checks the machinery and
    costs, not whether there is an edge.
  - *Test the indicators:* scores every file in `indicators/` and in the station's own
    `indicators/` folder on the last 20 complete sessions. This is unofficial. The
    registered duel uses fixed dates and `scripts/indicator_duel.py`.
- **Jobs and logs:** every run, its result and its full output.
- **Pause** stops the timer without closing anything. **Run now** buttons start any job at
  once. **Reset** starts a daily bot's paper book over. The old files are kept with a
  `.bak` date stamp, not deleted.

## Where everything is

All the station's files are in `local_data/` in this folder: each bot's config, state,
prices and snapshot, the intraday history, downloaded bars, tool results and a log per day.
The **Open folder** button on the dashboard shows it.

On the first start the folder is seeded from the repository's `live/` files. The local bots
pick up the same paper books where the GitHub bot left them, and from then on they are
independent. To start every bot from scratch instead, delete `local_data/` before the first
start, or use **Reset**. To keep the data somewhere else, set the environment variable
`QT_LOCAL_HOME` to a folder path.

To change a bot's settings, edit its `config.json` in `local_data/` while the station is
closed. The intraday bot's costs (`tick_slippage`, `open_slippage_mult`) and its $2 minimum
price are in `local_data/intraday/config.json`.

## Prices

The daily bots use `scripts/fetch_prices.py`. It tries free keyed sources first if their keys
are set (Financial Modeling Prep, Twelve Data), then Yahoo, then Stooq. Today's bar is never
stored before 4:30 pm New York. To use keys, set them as Windows user environment variables
(`FMP_API_KEY`, `TWELVEDATA_API_KEY`, `STOOQ_API_KEY`) in *Settings > System > About >
Advanced system settings > Environment Variables*, then restart the station. Never paste a key
into a chat or a file in this repository.

## Safety

- Every job runs as its own Python process with `QT_BROKER`, `QT_ALLOW_REAL_MONEY` and every
  `ALPACA_*` variable removed, and `--broker paper` on the command line.
- The dashboard listens on 127.0.0.1 only, so other computers can't reach it. Like the
  older dashboard (`quantum/desktop.py`), it refuses requests that name another host, POSTs
  that aren't JSON, and POSTs from other websites. It never takes a file name from a request.
- The GitHub bot (`.github/workflows/live-bot.yml`) is separate and keeps its own books in
  `live/`. You can leave it running as a backup or disable it under the repository's
  **Actions** tab. The two never write to each other's files.

## Command line

```
python -m quantum.local                    # start the station (port 8777)
python -m quantum.local --no-scheduler     # dashboard only; jobs run when you press a button
python -m quantum.local run daily          # run one job now and exit
python -m quantum.local --port 8800        # another port
```

Jobs: `daily`, `intraday`, `intraday_close`, `fetch_bars`, `backtest_main`, `backtest_small`,
`backtest_intraday`, `indicator_test`.

## Troubleshooting

- **"Port 8777 is in use"**: the station is probably already open in another window. Use
  that one, or start with `--port 8800`.
- **A job failed**: open *Jobs and logs* and click it to read the full output. A failed job
  is retried automatically after 20 minutes. Yahoo sometimes refuses or rate-limits for a
  while.
- **The market calendar warning**: holidays are listed for 2026 and 2027. Outside those
  years every weekday counts as a trading day. On a holiday the bots simply find no new bar.
