QUANTUM TRADING - standalone app (paper trading)
================================================

Nothing else to install: Python and numpy are included.

On Windows the easiest way is "Quantum Trading Setup.exe" from the same
download page: double-click it, click Next, and it adds Quantum Trading to
the Start menu (and the desktop if you like), with an uninstaller under
Settings > Apps. Uninstalling closes the program if it is open and removes
everything, including your saved paper book; installing a newer version
over the old one keeps the book. If Windows says "Windows protected your PC", click
"More info", then "Run anyway" (the program is not code-signed).
Once installed, open it from the Start menu and skip to step 3.

Without installing, from the zip:

1. Unzip the download. Keep the whole folder together and put it somewhere
   you can write to (Documents, Desktop). Do not run it from inside the zip.
2. Start it:
     Windows : double-click  "Quantum Trading.exe"
               If "Windows protected your PC" appears: More info > Run anyway.
     macOS   : double-click  "Open Quantum Trading.command"
               First time only: right-click it > Open > Open (the app is not
               signed by Apple). It clears the download block on this folder
               and starts the program.
     Linux   : double-click  "Quantum Trading"  or run  ./"Quantum Trading"
3. A terminal window opens and stays open: that is the engine. The dashboard
   opens in your browser at http://127.0.0.1:8765/  (open it yourself if it
   does not). Close the terminal window to stop.

Everything is PAPER trading: fills at the daily close, no slippage, no
exchange connection. It cannot place real orders. Your paper book is saved
in this folder (live_state.json) and picks up where it left off.

Try first: set "Replay speed" to 40, press Start, and watch it trade real
prices. The positions and fills show what each holding and each sale gained
or lost.

The same program runs the engine from a terminal, with the commands of
"python -m quantum". From inside this folder:
     Windows : "Quantum Trading.exe" live --replay data\prices\us_equities_1989_2018.csv --tickers AAPL,XOM,JPM,WMT --start 2012-01-01
     macOS / Linux : ./"Quantum Trading" live --replay data/prices/us_equities_1989_2018.csv --tickers AAPL,XOM,JPM,WMT --start 2012-01-01
     ... backtest --csv data/prices/us_equities_1989_2018.csv
     ... --help   for every command

quantum-trading.html is the same simulator as a single web page that runs in
any browser with no program at all.

If port 8765 is busy:  "Quantum Trading" desktop --port 8800
