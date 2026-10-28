#!/usr/bin/env python3
"""Score indicator files against each other under the duel's pre-registered rules.

    python3 scripts/indicator_duel.py --bars bars_5m.csv indicators/claude.py indicators/codex.py
    python3 scripts/indicator_duel.py indicators/claude.py indicators/codex.py            # the frozen cache
    python3 scripts/indicator_duel.py --fetch --forward indicators/claude.py indicators/codex.py

The data scored is ``--bars`` if given, else the fresh download if
``--fetch``, else the frozen cache ``--cache``.  ``--fetch`` downloads the
5-minute bars for live/intraday/universe.txt from Yahoo into ``--fresh``
(not the repository: the data is Yahoo's); it never writes to the frozen
cache, and refuses a ``--fresh`` path that is the cache or ``--bars``.

Without ``--forward`` the frozen windows (quantum.signals.TRAIN and TEST,
through FROZEN_END) are scored: training + test, the pass bar, random
baselines; data that does not yield exactly those windows is refused.
With ``--forward`` the forward window quantum.signals.FORWARD is scored --
the sessions that decide the duel -- once the data holds all of it through
the last session's close; until then it is reported as incomplete and
nobody is declared ahead.  An entry showing look-ahead is never ranked
ahead.

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
from quantum.signals import FORWARD, FORWARD_SCORE_BY, evaluate, load_indicator, rank  # noqa: E402


DATA = Path.home() / "duel_data"


def pct(x):
    return "–" if x is None else f"{x:+.2%}"


def _same(a, b) -> bool:
    return b is not None and Path(a).expanduser().resolve() == Path(b).expanduser().resolve()


def fetch(dest, protected=()) -> Path:
    """Download fresh 5-minute bars into ``dest``, never onto a ``protected`` file (the frozen cache)."""
    dest = Path(dest).expanduser()
    for p in protected:
        if _same(dest, p):
            raise SystemExit(f"refusing to download onto {p}: that is the frozen data the scores are based on; "
                             "pass a different --fresh path")
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "fetch_intraday.py"), "--tickers-file",
                    str(ROOT / "live" / "intraday" / "universe.txt"), "--interval", "5m", "--range", "60d",
                    "--out", str(dest), "--pause", "0.2"], check=True)
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("indicators", nargs="+", help="indicator files (see quantum/signals.py for the contract)")
    ap.add_argument("--bars", help="5-minute bars CSV (datetime,ticker,open,high,low,close,volume)")
    ap.add_argument("--fetch", action="store_true", help="download fresh bars from Yahoo into --fresh first")
    ap.add_argument("--cache", default=str(DATA / "bars_5m.csv"), help="the frozen bars (never written)")
    ap.add_argument("--fresh", default=str(DATA / "bars_5m_fresh.csv"), help="where --fetch writes")
    ap.add_argument("--forward", action="store_true", help=f"score the forward window {FORWARD[0]}..{FORWARD[1]}")
    ap.add_argument("--random-runs", type=int, default=None, help="random baselines (default: the rule's 40)")
    ap.add_argument("--out", default="duel_report.json")
    args = ap.parse_args()

    if args.fetch:
        fetch(args.fresh, protected=[args.cache] + ([args.bars] if args.bars else []))
    path = str(Path(args.bars or (args.fresh if args.fetch else args.cache)).expanduser())
    if not Path(path).exists():
        ap.error(f"no bars at {path}; pass --bars or --fetch")
    # Load every file before scoring any: a field with one entry missing is
    # not the duel, so a bad file stops the run with one line per file.
    loaded, errors = [], []
    for f in args.indicators:
        try:
            loaded.append((f, load_indicator(f)))
        except Exception as e:  # the file is someone's code: any error is a bad entry
            msg = str(e) if isinstance(e, ValueError) else f"{type(e).__name__}: {e}"
            errors.append(msg if msg.startswith(str(Path(f))) else f"{f}: {msg}")
    if errors:
        ap.error("cannot load indicator file(s), nothing scored:\n  " + "\n  ".join(errors))
    bars = load_bars(path)
    reports = []
    for f, ind in loaded:
        kw = {} if args.random_runs is None else {"random_runs": args.random_runs}
        try:
            rep = evaluate(bars, ind, forward=args.forward, **kw)
        except ValueError as e:  # e.g. the data does not yield the pre-registered windows
            ap.error(f"{f}: {e}")
        reports.append(rep)
        print(f"\n== {ind.name}  ({f}, {ind.timeframe}m)")
        if rep["causality"]:
            print("  LOOKAHEAD (never ranked ahead): " + "; ".join(rep["causality"][:3]))
        if args.forward:
            fw = rep["forward"]
            if fw["status"] != "complete":
                print(f"  forward window {FORWARD[0]}..{FORWARD[1]} incomplete: {fw['sessions_have']} of "
                      f"{fw['sessions_needed']} sessions, last {fw['last_session'] or 'none'}"
                      f"{'' if fw['last_session_complete'] else ' (not through the close)'}"
                      f"; not scored (score by {FORWARD_SCORE_BY})")
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
        best, why = rank(reports, forward=args.forward)
        if best is None:
            print(f"\nNobody is ahead: {why}.")
        else:
            print(f"\nAhead on {why}: {best['name']}")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(reports, indent=1, default=str), encoding="utf-8")
    print(f"report: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
