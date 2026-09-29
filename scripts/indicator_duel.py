#!/usr/bin/env python3
"""Score indicator files against each other under the duel's pre-registered rules.

    python3 scripts/indicator_duel.py --bars bars_5m.csv indicators/claude.py indicators/codex.py
    python3 scripts/indicator_duel.py --fetch indicators/claude.py indicators/codex.py
    python3 scripts/indicator_duel.py --fetch --forward indicators/claude.py indicators/codex.py

``--fetch`` downloads the 5-minute bars for live/intraday/universe.txt from
Yahoo into ``--cache`` (not the repository: the data is Yahoo's).  Without
``--forward`` the frozen window through quantum.signals.FROZEN_END is scored
(training + test, the pass bar, random baselines).  With ``--forward`` the
forward window quantum.signals.FORWARD is scored: the sessions that decide
the duel, which nobody had seen when the rules were written.

Writes a JSON report next to the table (``--out``).  See docs/indicator_duel.md.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantum.intraday import load_bars  # noqa: E402
from quantum.signals import FORWARD, FORWARD_SCORE_BY, FROZEN_END, evaluate, load_indicator  # noqa: E402


def pct(x):
    return "–" if x is None else f"{x:+.2%}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("indicators", nargs="+", help="indicator files (see quantum/signals.py for the contract)")
    ap.add_argument("--bars", help="5-minute bars CSV (datetime,ticker,open,high,low,close,volume)")
    ap.add_argument("--fetch", action="store_true", help="download the bars from Yahoo first")
    ap.add_argument("--cache", default=str(Path.home() / "duel_data" / "bars_5m.csv"))
    ap.add_argument("--forward", action="store_true", help=f"score the forward window {FORWARD[0]}..{FORWARD[1]}")
    ap.add_argument("--random-runs", type=int, default=None, help="random baselines (default: the rule's 40)")
    ap.add_argument("--out", default="duel_report.json")
    args = ap.parse_args()

    path = args.bars or args.cache
    if args.fetch:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, str(ROOT / "scripts" / "fetch_intraday.py"), "--tickers-file",
                        str(ROOT / "live" / "intraday" / "universe.txt"), "--interval", "5m", "--range", "60d",
                        "--out", path, "--pause", "0.2"], check=True)
    if not Path(path).exists():
        ap.error(f"no bars at {path}; pass --bars or --fetch")
    bars = load_bars(path)
    reports = []
    for f in args.indicators:
        ind = load_indicator(f)
        kw = {} if args.random_runs is None else {"random_runs": args.random_runs}
        rep = evaluate(bars, ind, forward=args.forward, **kw)
        reports.append(rep)
        print(f"\n== {ind.name}  ({f}, {ind.timeframe}m)")
        if rep["causality"]:
            print("  LOOKAHEAD: " + "; ".join(rep["causality"][:3]))
        if args.forward:
            fw = rep["forward"]
            if fw is None:
                print(f"  no forward sessions in the data yet ({FORWARD[0]} onward; score by {FORWARD_SCORE_BY})")
            else:
                print(f"  forward {fw['sessions'][0]}..{fw['sessions'][1]} ({fw['sessions'][2]} sessions): "
                      f"{pct(fw['return'])}, {fw['trades']} trades, won {fw['win_rate'] or 0:.0%}, "
                      f"worst drawdown {fw['max_dd']:.1%}")
            continue
        w = rep["windows"]
        print(f"  train {w['train'][0]}..{w['train'][1]}: {pct(rep['train']['return'])} ({rep['train']['trades']} trades)")
        print(f"  test  {w['test'][0]}..{w['test'][1]}: {pct(rep['test']['return'])} ({rep['test']['trades']} trades, "
              f"won {rep['test']['win_rate'] or 0:.0%}, worst drawdown {rep['test']['max_dd']:.1%})")
        print(f"  test halves {pct(rep['test_half1']['return'])} / {pct(rep['test_half2']['return'])};"
              f" at 0.25% per side {pct(rep['test_stress']['return'])};"
              f" beats {rep['random_beaten']:.0%} of random runs (median {pct(rep['random_median'])})")
        for gate, ok in rep["gates"].items():
            print(f"    [{'x' if ok else ' '}] {gate}")
        print(f"  PASSED: {'yes' if rep['passed'] else 'no'}")
    if len(reports) > 1:
        key = (lambda r: (r["forward"] or {}).get("return", float("-inf"))) if args.forward else \
              (lambda r: (sum(r["gates"].values()), r["test"]["return"]))
        best = max(reports, key=key)
        label = "forward return" if args.forward else f"gates passed, then test return (frozen through {FROZEN_END})"
        print(f"\nAhead on {label}: {best['name']}")
    Path(args.out).write_text(json.dumps(reports, indent=1, default=str), encoding="utf-8")
    print(f"report: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
