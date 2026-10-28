#!/usr/bin/env python3
"""Run the KAMA intraday strategy on today's session so far, on paper.

    python3 scripts/intraday_live.py --out live/intraday/status.json
    python3 scripts/intraday_live.py --interval 1m --out live/intraday/status.json

Settings, including ``"interval": "5m"`` or ``"1m"``, come from
live/intraday/config.json; ``--interval`` overrides the file for one run.
    python3 scripts/intraday_live.py --bars-csv bars_5m.csv --date 2026-09-23 --out status.json

A replay treats the newest session in the file as still trading when its
last bar starts before 15:55 (a file saved mid-session); any other session
is replayed to its close (see ``session_is_open``).

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

# NYSE early closes (13:00) in 2026-2027.  The rules: the day after
# Thanksgiving closes early, and so does Christmas Eve when it is a weekday
# and not itself the observed Christmas holiday; the day before Independence
# Day closes early only when July 3 is a regular weekday session.
#   2026: Nov 27 (after Thanksgiving) and Thu Dec 24.  July 4 is a Saturday,
#         so Fri Jul 3 is the holiday and Thu Jul 2 is a full day.
#   2027: Nov 26 (after Thanksgiving).  Christmas is a Saturday, so Fri Dec 24
#         is the holiday (closed) and Dec 23 is a full day; July 4 is a
#         Sunday, observed Mon Jul 5, and Fri Jul 2 is a full day.
# A date missing here is caught by the staleness check in session_is_open.
EARLY_CLOSE = {"2026-11-27", "2026-12-24", "2027-11-26"}
STALE_MINUTES = 15


def session_close(date: str) -> str:
    """The regular session's closing time (HH:MM) on ``date``."""
    return "13:00" if date in EARLY_CLOSE else "16:00"


def session_is_open(mode: str, date: str, newest: str, last_bar: str, now_ny: datetime,
                    minutes: int) -> bool:
    """Whether ``date`` is to be treated as a session still trading.

    Live: it is today, the clock is before that day's close, and the newest
    finished bar is recent (it ended less than ``STALE_MINUTES`` ago, plus
    the bar length beyond 5 minutes; a
    session whose bars have stopped coming is over, e.g. an early close not
    in ``EARLY_CLOSE``).

    Replay (``--bars-csv``): it is the newest session in the file and its
    last bar starts before the last bar of a full day for the bar length
    (:func:`last_bar_start`: 15:55 for 5-minute bars on a normal day).  A file saved mid-session is then
    replayed as that session so far, with the position kept open, not
    force-closed on its last bar as if the day had ended; any earlier or
    complete session is replayed to its close."""
    close = session_close(date)
    h, m = map(int, close.split(":"))
    if mode == "replay":
        return date == newest and bool(last_bar) and last_bar[11:16] < last_bar_start(h * 60 + m, minutes)
    if date != now_ny.strftime("%Y-%m-%d") or now_ny.strftime("%H:%M") >= close or not last_bar:
        return False
    ended = datetime.strptime(last_bar[:19], "%Y-%m-%d %H:%M:%S") + timedelta(minutes=minutes)
    # The newest finished bar can be up to one bar old before the next one
    # finishes; allow that on top of the delay (5-minute bars: 15 minutes).
    stale = STALE_MINUTES + max(0, minutes - 5)
    return now_ny.replace(tzinfo=None) - ended < timedelta(minutes=stale)


def last_bar_start(close_minute: int, minutes: int) -> str:
    """HH:MM at which a full day's last ``minutes``-minute bar starts, with
    bars from 09:30 and the session closing at ``close_minute`` (minutes after
    midnight): 15:55 for 5m, 15:45 for 15m, 15:30 for 30m and 60m."""
    open_minute = 9 * 60 + 30
    n = -(-(close_minute - open_minute) // minutes)  # bars in the session, the last one possibly short
    t = open_minute + (n - 1) * minutes
    return f"{t // 60:02d}:{t % 60:02d}"


def fetch_range(cfg: IntradayConfig, minutes: int) -> str:
    """Yahoo range to fetch: a few sessions warm up the KAMA and feed the
    range screen; the rvol screen and the ATR stop need ``rvol_days`` prior
    sessions (plus today and a spare), so they get a longer range.  Yahoo
    serves 1m bars for about 7 days, and 2m-15m bars for 60 days."""
    if cfg.screen != "rvol" and not cfg.stop_atr_mult:
        return "5d" if minutes <= 15 else "1mo"
    sessions = cfg.rvol_days + 2
    if minutes < 2:
        print(f"WARNING: the rvol screen / ATR stop need {sessions} sessions; Yahoo serves "
              "1m bars for about 7 days, so they will find too little history", file=sys.stderr)
        return "7d"
    if sessions <= 19:  # 1mo is about 21 sessions
        return "1mo"
    days = sessions * 7 // 5 + 7  # calendar days, with room for holidays
    if days > 60:
        print(f"WARNING: {sessions} sessions need more than Yahoo's 60 days of intraday bars",
              file=sys.stderr)
    return f"{min(days, 60)}d"


def fetch(tickers: list[str], minutes: int, rng: str | None = None) -> tuple[list[tuple], list[str]]:
    """Bars for every ticker (a ticker that fails is skipped and listed).

    ``rng`` defaults to a few sessions, which warm up the KAMA and feed
    the range screen; longer bars need a longer range to give the same
    number of bars (see :func:`fetch_range`)."""
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
    try:
        cfg = IntradayConfig(**settings)
    except (TypeError, ValueError) as exc:
        ap.error(f"{args.config}: {exc}")
    failed: list[str] = []
    if args.bars_csv:
        bars, mode = load_bars(args.bars_csv), "replay"
    else:
        tickers = [ln.split("#")[0].strip().upper() for ln in Path(args.universe).read_text().splitlines()]
        rows, failed = fetch([t for t in tickers if t], minutes, fetch_range(cfg, minutes))
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
    last_bar = max((str(b["datetime"][-1]) for b in bars.values() if b["datetime"].size), default="")
    open_session = session_is_open(mode, date, dates[-1], last_bar, now_ny, minutes)
    cfg = IntradayConfig(**settings, trade_from=date)
    doc = status(bars, date, cfg, open_session, mode, minutes, failed)
    Path(args.out).write_text(json.dumps(doc, indent=1), encoding="utf-8")
    pos = ", ".join(f"{p['ticker']} x{p['shares']:g}" for p in doc["positions"]) or "none"
    print(f"{mode} {date} to {doc['last_bar'][11:16]}: equity {doc['equity']:.2f}, "
          f"{len(doc['trades'])} closed trades, open: {pos}, pending buys: {doc['pending_buys'] or 'none'}"
          + (f"; {len(failed)} tickers not fetched: {', '.join(failed)}" if failed else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
