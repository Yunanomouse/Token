"""Score every candidate on the TRAINING window only and apply the pick rule.

    python3 indicators/research/search_train.py /path/to/bars_5m.csv

The pick rule, fixed before this was run (docs/indicator_duel.md):
eligible if at least 40 training trades and profitable in each half of the
training window at 0.10% per side; among those, the highest training
return at 0.25% per side.  Only the pick's test window is opened by
scripts/indicator_duel.py afterwards.
"""
import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "indicators" / "research"))

from claude_candidates import grid  # noqa: E402
from quantum.intraday import load_bars  # noqa: E402
from quantum.signals import (BOT_CONFIG, STRESS_SLIPPAGE_BPS, TEST_SESSIONS, WARMUP_SESSIONS,  # noqa: E402
                             SignalPolicy, _until, prepare, run_window, sessions)


def main():
    bars5 = load_bars(sys.argv[1])
    rows = []
    for ind in grid():
        prepared = prepare(bars5, ind.timeframe)
        days = sessions(prepared)
        train = days[WARMUP_SESSIONS:-TEST_SESSIONS]
        half = len(train) // 2
        pol = SignalPolicy(_until(prepared, train[-1]), ind)  # test bars never reach the indicator
        run = lambda a, z, cfg=BOT_CONFIG: run_window(prepared, ind, a, z, cfg, pol)["summary"]
        full, h1, h2 = run(train[0], train[-1]), run(train[0], train[half - 1]), run(train[half], train[-1])
        stress = run(train[0], train[-1], replace(BOT_CONFIG, slippage_bps=STRESS_SLIPPAGE_BPS))
        rows.append({"name": ind.name, "trades": full["n_trades"], "ret": full["total_return"],
                     "h1": h1["total_return"], "h2": h2["total_return"], "ret_025": stress["total_return"],
                     "win": full["win_rate"]})
        r = rows[-1]
        print(f"{r['name']:32} trades {r['trades']:4}  train {r['ret']:+7.2%}  halves {r['h1']:+7.2%} {r['h2']:+7.2%}"
              f"  at 0.25% {r['ret_025']:+7.2%}  won {r['win'] or 0:.0%}", flush=True)
    eligible = [r for r in rows if r["trades"] >= 40 and r["h1"] > 0 and r["h2"] > 0]
    pick = max(eligible, key=lambda r: r["ret_025"]) if eligible else None
    print("\nPICK:", pick["name"] if pick else "none eligible")
    (ROOT / "indicators" / "research" / "train_results.json").write_text(
        json.dumps({"window": [train[0], train[-1], len(train)], "rows": rows, "pick": pick}, indent=1))


if __name__ == "__main__":
    main()
