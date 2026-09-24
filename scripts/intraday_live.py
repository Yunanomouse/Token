#!/usr/bin/env python3
"""Run the KAMA intraday strategy on today's session so far, on paper.

    python3 scripts/intraday_live.py --out live/intraday/status.json
    python3 scripts/intraday_live.py --bars-csv bars_5m.csv --date 2026-09-23 --out status.json

Each run fetches the last few sessions of 5-minute bars for the universe
(earlier sessions warm up the KAMA and feed the volatility screen), drops
the bar still forming, and replays today from a fresh $50 with
quantum.intraday.backtest.  The strategy is causal and fills at the next
bar's open, so re-running the whole day each time gives the same trades a
bot stepping bar by bar would have made.  Nothing is sent to any broker.

The output is one JSON document for the dashboard: account, trades, the
open position, pending orders, the day's screen, and each screened
stock's price and KAMA for the chart.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from fetch_intraday import yahoo_intraday  # noqa: E402
from quantum.intraday import IntradayConfig, backtest, kama_signals, load_bars  # noqa: E402

NY = ZoneInfo("America/New_York")
BAR_MINUTES = 5


def fetch(tickers: list[str], rng: str = "5d") -> tuple[list[tuple], list[str]]:
    def one(t):
        try:
            return t, yahoo_intraday(t, f"{BAR_MINUTES}m", rng)
        except Exception as exc:  # skip a ticker that fails
            print(f"{t:6} FAILED: {exc}", file=sys.stderr)
            return t, []
    rows, failed = [], []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for t, bars in pool.map(one, tickers):
            if not bars:
                failed.append(t)
            rows += [(dt, t, o, h, l, c, v) for dt, o, h, l, c, v in bars]
    return rows, failed


def write_csv(rows: list[tuple], path: Path, now_ny: datetime) -> None:
    """Keep only bars that have finished by ``now_ny``."""
    done = now_ny.replace(tzinfo=None) - timedelta(minutes=BAR_MINUTES)
    rows = sorted((r for r in rows if r[0] <= done), key=lambda r: (r[0], r[1]))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("datetime,ticker,open,high,low,close,volume\n")
        for dt, t, o, h, l, c, v in rows:
            fh.write(f"{dt:%Y-%m-%d %H:%M:%S},{t},{o:.4f},{h:.4f},{l:.4f},{c:.4f},{v}\n")


def status(bars: dict, date: str, cfg: IntradayConfig, open_session: bool, mode: str) -> dict:
    res = backtest(bars, cfg, open_session=True)
    op = res["open"]
    equity = res["equity"][-1]["equity"] if res["equity"] else cfg.cash
    last_bar = max((str(b["datetime"][-1]) for b in bars.values() if b["datetime"].size), default="")
    shown = list(dict.fromkeys(op["screen"] + [t["ticker"] for t in res["trades"]]
                               + [p["ticker"] for p in op["positions"]]))
    charts = {}
    for t in shown:
        b = bars[t]
        today = [i for i, d in enumerate(b["datetime"]) if str(d).startswith(date)]
        if not today:
            continue
        k = kama_signals(b["close"], cfg)["kama"]
        charts[t] = {"time": [str(b["datetime"][i])[11:16] for i in today],
                     "close": [round(float(b["close"][i]), 4) for i in today],
                     "kama": [None if k[i] != k[i] else round(float(k[i]), 4) for i in today]}
    return {
        "schema": 1,
        "mode": mode,
        "session_open": open_session,
        "date": date,
        "last_bar": last_bar,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "start_cash": cfg.cash,
        "equity": round(float(equity), 4),
        "cash_settled": round(op["cash_settled"], 4),
        "cash_unsettled": round(op["cash_unsettled"], 4),
        "entries_today": op["entries_today"],
        "max_trades_per_day": cfg.max_trades_per_day,
        "screen": op["screen"],
        "positions": op["positions"],
        "pending_buys": op["pending_buys"],
        "trades": res["trades"],
        "charts": charts,
        "config": {k: v for k, v in cfg.to_dict().items() if k not in ("trade_from",)},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--universe", default=str(ROOT / "live/intraday/universe.txt"))
    ap.add_argument("--bars-csv", help="use this bar file instead of fetching (a replay)")
    ap.add_argument("--date", help="session to trade (default: the newest in the data)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    now_ny = datetime.now(NY)
    if args.bars_csv:
        bars, mode = load_bars(args.bars_csv), "replay"
    else:
        tickers = [ln.split("#")[0].strip().upper() for ln in Path(args.universe).read_text().splitlines()]
        rows, failed = fetch([t for t in tickers if t])
        if not rows:
            print("ERROR: no bars fetched", file=sys.stderr)
            return 1
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bars.csv"
            write_csv(rows, path, now_ny)
            bars = load_bars(path)
        mode = "live"
    dates = sorted({str(d)[:10] for b in bars.values() for d in b["datetime"]})
    date = args.date or dates[-1]
    bars = {t: {k: v[b["datetime"] < f"{date}~"] for k, v in b.items()} for t, b in bars.items()}
    open_session = (mode == "live" and date == now_ny.strftime("%Y-%m-%d")
                    and now_ny.strftime("%H:%M") < "16:00")
    doc = status(bars, date, IntradayConfig(trade_from=date), open_session, mode)
    Path(args.out).write_text(json.dumps(doc, indent=1), encoding="utf-8")
    pos = ", ".join(f"{p['ticker']} x{p['shares']:g}" for p in doc["positions"]) or "none"
    print(f"{mode} {date} to {doc['last_bar'][11:16]}: equity {doc['equity']:.2f}, "
          f"{len(doc['trades'])} closed trades, open: {pos}, pending buys: {doc['pending_buys'] or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
