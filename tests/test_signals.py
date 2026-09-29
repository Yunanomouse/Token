"""Tests for the indicator duel's referee (quantum/signals.py) and Claude's entry."""
from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

from quantum.signals import (Indicator, causality_violations, evaluate, load_indicator, prepare, run_window,
                             sessions)

ROOT = Path(__file__).resolve().parents[1]


def _universe(n_days=40, n_tickers=4, seed=0):
    """5-minute bars, 78 a session, on weekdays from 2026-06-01."""
    rng = np.random.default_rng(seed)
    days, d = [], np.datetime64("2026-06-01")
    while len(days) < n_days:
        if np.is_busday(d):
            days.append(str(d))
        d += 1
    times = [f"{9 + (30 + 5 * m) // 60:02d}:{(30 + 5 * m) % 60:02d}:00" for m in range(78)]
    bars = {}
    for k in range(n_tickers):
        c = rng.uniform(5, 25) * np.exp(np.cumsum(rng.normal(0, 0.004 * (k + 1), n_days * 78)))
        o = np.r_[c[0], c[:-1]]
        bars[f"T{k}"] = {"datetime": np.array([f"{day} {t}" for day in days for t in times]), "open": o,
                         "high": np.maximum(o, c) * 1.002, "low": np.minimum(o, c) * 0.998, "close": c,
                         "volume": np.full(c.size, 1000.0)}
    return bars


def _ind(fn, name="t", tf=5):
    return Indicator(name, tf, lambda b, **_: fn(b))


class TestContract(unittest.TestCase):
    def test_bad_outputs_are_refused(self):
        b = _universe(3, 1)["T0"]
        n = b["close"].size
        for bad, msg in ((lambda b: {"entry": np.zeros(n, bool)}, "'exit'"),
                         (lambda b: {"entry": np.zeros(n - 1, bool), "exit": np.zeros(n, bool)}, "shape"),
                         (lambda b: {"entry": np.full(n, np.nan), "exit": np.zeros(n, bool)}, "NaN")):
            with self.assertRaisesRegex(ValueError, msg):
                _ind(bad)(b)

    def test_lookahead_is_caught(self):
        bars = _universe(6, 2)
        peek = _ind(lambda b: {"entry": np.r_[b["close"][1:] > b["close"][:-1], False],
                               "exit": np.zeros(b["close"].size, bool)})
        honest = _ind(lambda b: {"entry": np.r_[False, b["close"][1:] > b["close"][:-1]],
                                 "exit": np.zeros(b["close"].size, bool)})
        self.assertTrue(causality_violations(peek, bars))
        self.assertEqual(causality_violations(honest, bars), [])

    def test_load_indicator_checks_the_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.py"
            p.write_text("NAME='x'\nTIMEFRAME=7\ndef signals(b): pass\n")
            with self.assertRaisesRegex(ValueError, "TIMEFRAME"):
                load_indicator(p)
            p.write_text("NAME='x'\nTIMEFRAME=15\n")
            with self.assertRaisesRegex(ValueError, "signals"):
                load_indicator(p)


class TestEngine(unittest.TestCase):
    def test_signals_fill_at_next_open_and_close_by_the_end_of_the_day(self):
        bars = _universe(4, 1)
        always = _ind(lambda b: {"entry": np.ones(b["close"].size, bool), "exit": np.zeros(b["close"].size, bool)})
        days = sessions(bars)
        res = run_window(bars, always, days[1], days[-1])
        b = bars["T0"]
        first = int(np.flatnonzero(np.char.startswith(b["datetime"].astype(str), days[1]))[0])
        t0 = res["trades"][0]
        self.assertEqual(t0["entry_time"], b["datetime"][first + 1])  # the first bar's signal, filled at the next
        self.assertAlmostEqual(t0["entry_price"], b["open"][first + 1] * 1.001)
        self.assertEqual({t["reason"] for t in res["trades"]}, {"eod"})
        self.assertTrue(all(t["entry_time"][:10] == t["exit_time"][:10] for t in res["trades"]))

    def test_resample_and_evaluate_report(self):
        bars = _universe(40, 3)
        ind = _ind(lambda b: {"entry": np.r_[False, b["close"][1:] > b["close"][:-1]],
                              "exit": np.r_[False, b["close"][1:] < b["close"][:-1]]}, tf=15)
        prepared = prepare(bars, 15, end="2099-01-01")
        self.assertEqual(prepared["T0"]["close"].size, 40 * 26)
        rep = evaluate(bars, ind, end="2099-01-01", random_runs=3)
        self.assertEqual(rep["windows"]["test"][2], 20)
        self.assertEqual(rep["windows"]["train"][2], 40 - 10 - 20)
        self.assertEqual(set(rep["gates"]), {"profitable_test_and_train", "profitable_both_test_halves",
                                              "profitable_at_0.25pct", "beats_90pct_of_random",
                                              "at_least_30_test_trades", "no_lookahead"})
        self.assertEqual(rep["passed"], all(rep["gates"].values()))
        # One pass of the signals serves every window: same result as a fresh run of that window.
        days = sessions(prepared)
        test = days[-20:]
        fresh = run_window(prepared, ind, test[0], test[-1])["summary"]["total_return"]
        self.assertAlmostEqual(rep["test"]["return"], fresh, places=12)


def _pine_supertrend(h, l, c, factor=3.0, n=10):
    """TradingView's documented ta.supertrend, transliterated line by line with Pine's na/nz rules."""
    na = float("nan")
    isna = lambda x: x != x  # noqa: E731
    N = len(c)
    tr, atr = [na] * N, [na] * N
    for i in range(N):
        tr[i] = h[i] - l[i] if i == 0 else max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        if i == n - 1:
            atr[i] = sum(tr[:n]) / n
        elif i >= n:
            atr[i] = (atr[i - 1] * (n - 1) + tr[i]) / n
    lo, up, st, d = [na] * N, [na] * N, [na] * N, [1] * N
    for i in range(N):
        src = (h[i] + l[i]) / 2
        ub, lb = src + factor * atr[i], src - factor * atr[i]
        pl = 0.0 if (i == 0 or isna(lo[i - 1])) else lo[i - 1]
        pu = 0.0 if (i == 0 or isna(up[i - 1])) else up[i - 1]
        c1 = c[i - 1] if i else na
        if not isna(lb):
            lb = lb if (lb > pl or c1 < pl) else pl
        if not isna(ub):
            ub = ub if (ub < pu or c1 > pu) else pu
        lo[i], up[i] = lb, ub
        if i == 0 or isna(atr[i - 1]):
            d[i] = 1
        elif st[i - 1] == up[i - 1]:
            d[i] = -1 if c[i] > ub else 1
        else:
            d[i] = 1 if c[i] < lb else -1
        st[i] = lb if d[i] == -1 else ub
    return np.array(st), np.array(d)


class TestClaudeEntry(unittest.TestCase):
    def test_matches_tradingview_supertrend(self):
        mod = load_indicator(ROOT / "indicators" / "claude.py")
        import importlib.util
        spec = importlib.util.spec_from_file_location("claude_entry", ROOT / "indicators" / "claude.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        rng = np.random.default_rng(1)
        for _ in range(100):
            n = int(rng.integers(12, 300))
            c = 20 * np.exp(np.cumsum(rng.normal(0, rng.uniform(0.002, 0.03), n)))
            h, l = c * (1 + rng.uniform(0, 0.01, n)), c * (1 - rng.uniform(0, 0.01, n))
            s1, d1 = m.supertrend(h, l, c, 3.0, 10)
            s2, d2 = _pine_supertrend(list(h), list(l), list(c))
            ok = ~np.isnan(s2)
            np.testing.assert_array_equal(np.isnan(s1), ~ok)
            np.testing.assert_allclose(s1[ok], s2[ok], rtol=0, atol=1e-12)
            np.testing.assert_array_equal(d1[ok], d2[ok])
        self.assertEqual((mod.timeframe, mod.params), (5, {"atr_period": 10, "factor": 3.0}))
        self.assertEqual(causality_violations(mod, _universe(8, 3)), [])

    def test_pine_file_uses_the_same_settings(self):
        pine = (ROOT / "pine" / "claude_supertrend.pine").read_text()
        self.assertIn("//@version=5", pine)
        self.assertIn('input.int(10, "ATR length"', pine)
        self.assertIn('input.float(3.0, "ATR factor"', pine)
        self.assertIn("ta.supertrend(factor, atrPeriod)", pine)
        self.assertIn('"0930-1530"', pine)  # the engine's last entry, 15:30

    def test_every_bundled_indicator_follows_the_contract(self):
        bars = _universe(8, 2)
        for f in sorted((ROOT / "indicators").glob("*.py")):
            if f.name.startswith("_"):
                continue
            ind = load_indicator(f)
            self.assertEqual(causality_violations(ind, prepare(bars, ind.timeframe, "2099-01-01")), [], f.name)


class TestDuelScript(unittest.TestCase):
    def test_cli_scores_two_files(self):
        bars = _universe(36, 3, seed=2)
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "bars.csv"
            with src.open("w") as fh:
                fh.write("datetime,ticker,open,high,low,close,volume\n")
                for t, b in bars.items():
                    for i in range(b["close"].size):
                        fh.write(f"{b['datetime'][i]},{t},{b['open'][i]:.4f},{b['high'][i]:.4f},{b['low'][i]:.4f},"
                                 f"{b['close'][i]:.4f},1000\n")
            out = Path(d) / "r.json"
            import quantum.signals as s
            end = sessions(bars)[-1]
            code = ("import sys, runpy; import quantum.signals as s; s.FROZEN_END = %r; "
                    "sys.argv = ['x', '--bars', %r, '--random-runs', '2', '--out', %r, %r, %r]; "
                    "runpy.run_path(%r, run_name='__main__')"
                    % (end, str(src), str(out), str(ROOT / "indicators" / "claude.py"),
                       str(ROOT / "indicators" / "kama_baseline.py"), str(ROOT / "scripts" / "indicator_duel.py")))
            r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300, cwd=ROOT)
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            self.assertIn("PASSED:", r.stdout)
            self.assertIn("Ahead on", r.stdout)
            rep = json.loads(out.read_text())
            self.assertEqual([x["timeframe"] for x in rep], [5, 5])
            self.assertTrue(all(math.isfinite(x["test"]["return"]) for x in rep))
            self.assertEqual(s.FORWARD[0] > s.FROZEN_END, True)


if __name__ == "__main__":
    unittest.main()
