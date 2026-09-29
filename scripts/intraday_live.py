#!/usr/bin/env python3
"""Run the KAMA intraday strategy on today's session so far, on paper.

    python3 scripts/intraday_live.py --out live/intraday/status.json
    python3 scripts/intraday_live.py --interval 1m --out live/intraday/status.json

Settings, including ``"interval": "5m"`` or ``"1m"``, come from
live/intraday/config.json; ``--interval`` overrides the file for one run.
    python3 scripts/intraday_live.py --bars-csv bars_5m.csv --date 2026-09-23 --out status.json

Each run fetches the last few sessions of 1- or 5-minute bars for the universe
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
from dataclasses import fields
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from fetch_intraday import INTERVALS, yahoo_intraday  # noqa: E402
from quantum.intraday import IntradayConfig, backtest, kama_signals, load_bars  # noqa: E402

NY = ZoneInfo("America/New_York")


def fetch(tickers: list[str], minutes: int, rng: str | None = None) -> tuple[list[tuple], list[str]]:
    """Bars for every ticker (a ticker that fails is skipped and listed).

    A few sessions warm up the KAMA and feed the screen; longer bars need
    a longer range to give the same number of bars."""
    rng = rng or ("5d" if minutes <= 15 else "1mo")

    def one(t):
        try:
            return t, yahoo_intraday(t, f"{minutes}m", rng)
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


def write_csv(rows: list[tuple], path: Path, now_ny: datetime, minutes: int) -> None:
    """Keep only bars that have finished by ``now_ny``."""
    done = now_ny.replace(tzinfo=None) - timedelta(minutes=minutes)
    rows = sorted((r for r in rows if r[0] <= done), key=lambda r: (r[0], r[1]))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("datetime,ticker,open,high,low,close,volume\n")
        for dt, t, o, h, l, c, v in rows:
            fh.write(f"{dt:%Y-%m-%d %H:%M:%S},{t},{o:.4f},{h:.4f},{l:.4f},{c:.4f},{v}\n")


def status(bars: dict, date: str, cfg: IntradayConfig, open_session: bool, mode: str,
           minutes: int, failed: list[str] | None = None) -> dict:
    # A session that has ended is replayed to its close, so nothing is left
    # "open" on a finished day; only a session still trading keeps a position.
    res = backtest(bars, cfg, open_session=open_session)
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
        "bar_minutes": minutes,
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
        "failed_tickers": list(failed or []),
        "config": {k: v for k, v in cfg.to_dict().items() if k not in ("trade_from",)},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--universe", default=str(ROOT / "live/intraday/universe.txt"))
    ap.add_argument("--bars-csv", help="use this bar file instead of fetching (a replay)")
    ap.add_argument("--config", default=str(ROOT / "live/intraday/config.json"),
                    help="JSON with 'interval' (1m or 5m) and any IntradayConfig fields")
    ap.add_argument("--interval", choices=INTERVALS,
                    help="bar length (overrides the config); 1m or 5m for day trading")
    ap.add_argument("--date", help="session to trade (default: the newest in the data)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    now_ny = datetime.now(NY)
    settings = json.loads(Path(args.config).read_text()) if Path(args.config).exists() else {}
    interval = args.interval or settings.pop("interval", "5m")
    settings.pop("interval", None)
    settings.pop("trade_from", None)  # the session traded is chosen below
    if interval not in INTERVALS:
        ap.error(f"interval must be one of {', '.join(INTERVALS)}, not {interval!r}")
    unknown = sorted(set(settings) - {f.name for f in fields(IntradayConfig)})
    if unknown:
        ap.error(f"{args.config}: unknown settings {unknown}")
    minutes = int(interval[:-1])
    failed: list[str] = []
    if args.bars_csv:
        bars, mode = load_bars(args.bars_csv), "replay"
    else:
        tickers = [ln.split("#")[0].strip().upper() for ln in Path(args.universe).read_text().splitlines()]
        rows, failed = fetch([t for t in tickers if t], minutes)
        if not rows:
            print("ERROR: no bars fetched", file=sys.stderr)
            return 1
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bars.csv"
            write_csv(rows, path, now_ny, minutes)
            bars = load_bars(path)
        mode = "live"
    dates = sorted({str(d)[:10] for b in bars.values() for d in b["datetime"]})
    if not dates:
        print("ERROR: no finished bars to trade on", file=sys.stderr)
        return 1
    date = args.date or dates[-1]
    if date not in dates:
        ap.error(f"no bars for {date}; sessions in the data run {dates[0]} to {dates[-1]}")
    bars = {t: {k: v[b["datetime"] < f"{date}~"] for k, v in b.items()} for t, b in bars.items()}
    open_session = (mode == "live" and date == now_ny.strftime("%Y-%m-%d")
                    and now_ny.strftime("%H:%M") < "16:00")
    try:
        cfg = IntradayConfig(**settings, trade_from=date)
    except (TypeError, ValueError) as exc:
        ap.error(f"{args.config}: {exc}")
    doc = status(bars, date, cfg, open_session, mode, minutes, failed)
    Path(args.out).write_text(json.dumps(doc, indent=1), encoding="utf-8")
    pos = ", ".join(f"{p['ticker']} x{p['shares']:g}" for p in doc["positions"]) or "none"
    print(f"{mode} {date} to {doc['last_bar'][11:16]}: equity {doc['equity']:.2f}, "
          f"{len(doc['trades'])} closed trades, open: {pos}, pending buys: {doc['pending_buys'] or 'none'}"
          + (f"; {len(failed)} tickers not fetched: {', '.join(failed)}" if failed else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
