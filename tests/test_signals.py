"""Tests for the indicator duel's referee (quantum/signals.py) and Claude's entry."""
from __future__ import annotations

import json
import math
import subprocess
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path

import numpy as np

import quantum.signals as signals_mod
from quantum.signals import (BOT_CONFIG, TEST, TRAIN, Indicator, _cut_points, causality_violations, config_for,
                             evaluate, flat_by_for, forward_status, load_indicator, prepare, rank, run_window,
                             sessions, split_windows)

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


def _windows(bars, warmup=10, test=20):
    """(train, test) date windows for synthetic data, laid out like the pre-registered ones."""
    days = sessions(bars)
    return (days[warmup], days[-test - 1]), (days[-test], days[-1])


def _write_csv(bars, path):
    with Path(path).open("w") as fh:
        fh.write("datetime,ticker,open,high,low,close,volume\n")
        for t, b in bars.items():
            for i in range(b["close"].size):
                fh.write(f"{b['datetime'][i]},{t},{b['open'][i]:.4f},{b['high'][i]:.4f},{b['low'][i]:.4f},"
                         f"{b['close'][i]:.4f},1000\n")


def _peek(b):
    """Look-ahead: the next bar's move decides this bar's signals."""
    c = b["close"]
    up = np.r_[c[1:] > c[:-1], False]
    return {"entry": up, "exit": ~up}


def _honest(b):
    c = b["close"]
    return {"entry": np.r_[False, c[1:] > c[:-1]], "exit": np.r_[False, c[1:] < c[:-1]]}


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

    def test_lookahead_on_any_ticker_is_caught(self):
        bars = _universe(4, 10)
        marker = bars["T9"]["close"][0]  # sorted() puts T9 tenth, past the old 8-ticker limit

        def fn(b):
            return _peek(b) if b["close"][0] == marker else _honest(b)
        self.assertTrue(any(v.startswith("T9:") for v in causality_violations(_ind(fn), bars)))

    def test_early_lookahead_is_caught(self):
        # Peeks only in the first 30 bars: cuts starting from n // 3 would never see it.
        def fn(b):
            n = b["close"].size
            e = np.zeros(n, bool)
            e[:30] = np.arange(min(n, 30)) + 1 < n  # "is there a next bar?"
            return {"entry": e, "exit": np.zeros(n, bool)}
        self.assertTrue(causality_violations(_ind(fn), _universe(6, 1)))

    def test_mid_session_lookahead_is_caught(self):
        # Knows whether its own session is finished: invisible to cuts at session boundaries.
        def fn(b):
            day = np.array([str(d)[:10] for d in b["datetime"]])
            full = np.array([np.count_nonzero(day == d) == 78 for d in day])
            return {"entry": full, "exit": ~full}
        bars = _universe(6, 2)
        n = bars["T0"]["close"].size
        cuts = _cut_points(bars["T0"]["datetime"], 8)
        self.assertEqual(cuts[0], 20)
        self.assertTrue(any(c % 78 for c in cuts))                       # cuts inside a session
        self.assertGreaterEqual(sum(1 for c in cuts if c % 78 == 39), 3)  # including mid-session ones
        self.assertTrue(all(20 <= c < n for c in cuts))
        self.assertTrue(causality_violations(_ind(fn), bars))

    def test_caching_cannot_mask_lookahead(self):
        # Answers later calls from the longest result it has seen: if the full
        # history ran first, every truncated run would just be a slice of it.
        cache = {}

        def fn(b):
            key, n = (str(b["datetime"][0]), float(b["close"][0])), b["close"].size
            if key not in cache or cache[key]["entry"].size < n:
                cache[key] = _peek(b)
            return {k: v[:n] for k, v in cache[key].items()}
        self.assertTrue(causality_violations(_ind(fn), _universe(6, 2)))

    def test_mutating_the_input_cannot_mask_lookahead(self):
        def fn(b):
            out = _peek(b)
            b["close"][:] = 1.0  # scribbles over what it was given
            return out
        bars = _universe(6, 2)
        before = bars["T0"]["close"].copy()
        self.assertTrue(causality_violations(_ind(fn), bars))
        np.testing.assert_array_equal(bars["T0"]["close"], before)

    def test_load_indicator_checks_the_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.py"
            p.write_text("NAME='x'\nTIMEFRAME=7\ndef signals(b): pass\n")
            with self.assertRaisesRegex(ValueError, "TIMEFRAME"):
                load_indicator(p)
            p.write_text("NAME='x'\nTIMEFRAME=15\n")
            with self.assertRaisesRegex(ValueError, "signals"):
                load_indicator(p)


class TestRules(unittest.TestCase):
    def test_pre_registered_windows(self):
        self.assertEqual(TRAIN, ("2026-07-21", "2026-08-28"))
        self.assertEqual(TEST, ("2026-08-31", "2026-09-28"))
        self.assertEqual(signals_mod.FROZEN_END, TEST[1])
        # The frozen cache: 10 warm-up sessions from Jul 7, then 29 training, then 20 test.
        days = [str(d) for d in np.arange(np.datetime64("2026-07-07"), np.datetime64("2026-09-29"))
                if np.is_busday(d, holidays=["2026-09-07"])]
        self.assertEqual(len(days), 59)
        tr, te = split_windows(days)
        self.assertEqual((tr[0], tr[-1], len(tr)), (TRAIN[0], TRAIN[1], 29))
        self.assertEqual((te[0], te[-1], len(te)), (TEST[0], TEST[1], 20))
        self.assertEqual(split_windows(days + ["2026-09-29", "2026-09-30"]), (tr, te))  # later data is cut off
        for bad in (days[1:],                          # a rolled download: one warm-up session short
                    [d for d in days if d != "2026-09-15"],  # a missing test session
                    [d for d in days if d != "2026-07-21"],  # training starts late
                    ["2026-07-06"] + days):            # an extra warm-up session shifts the count split
            with self.assertRaisesRegex(ValueError, "pre-registered windows"):
                split_windows(bad)

    def test_evaluate_refuses_data_that_misses_the_windows(self):
        bars = _universe(40, 2)  # June-July 2026: not the pre-registered dates
        with self.assertRaisesRegex(ValueError, "pre-registered windows"):
            evaluate(bars, _ind(_honest), random_runs=0)
        tr, te = _windows(bars)
        with self.assertRaisesRegex(ValueError, "pre-registered windows"):
            evaluate(bars, _ind(_honest), random_runs=0, windows=((tr[0], tr[1]), (sessions(bars)[-21], te[1])))

    def test_flat_by_per_timeframe(self):
        self.assertEqual({tf: flat_by_for(tf) for tf in (1, 5, 15, 30, 60)},
                         {1: "15:55", 5: "15:55", 15: "15:45", 30: "15:30", 60: "15:30"})
        for tf in signals_mod.TIMEFRAMES:
            self.assertEqual(config_for(tf).flat_by, flat_by_for(tf))
            self.assertEqual(config_for(tf).cash, BOT_CONFIG.cash)

    def test_flat_by_is_applied_on_every_timeframe(self):
        bars = _universe(4, 1)
        days = sessions(bars)
        for tf, last_open in ((5, "15:55"), (15, "15:45"), (30, "15:30"), (60, "15:30")):
            ind = _ind(lambda b: {"entry": np.ones(b["close"].size, bool), "exit": np.zeros(b["close"].size, bool)},
                       tf=tf)
            prepared = prepare(bars, tf, "2099-01-01")
            res = run_window(prepared, ind, days[1], days[-1])
            self.assertEqual(res["config"]["flat_by"], last_open)
            self.assertTrue(res["trades"])
            for t in res["trades"]:
                self.assertEqual(t["exit_time"][11:16], last_open, (tf, t))
                i = list(prepared["T0"]["datetime"]).index(t["exit_time"])
                self.assertAlmostEqual(t["exit_price"], prepared["T0"]["open"][i] * 0.999)  # at that bar's open
            rep = evaluate(bars, ind, random_runs=0, forward=True, forward_window=(days[0], days[-1]))
            self.assertEqual(rep["flat_by"], last_open)

    def test_forward_incomplete_is_not_scored(self):
        bars = _universe(12, 2)
        days = sessions(bars)
        win = (days[2], days[-1])  # 10 sessions
        ind = _ind(_honest)
        rep = evaluate(bars, ind, random_runs=0, forward=True, forward_window=win)
        self.assertEqual(rep["forward"]["status"], "incomplete")  # needs 20
        self.assertEqual((rep["forward"]["sessions_have"], rep["forward"]["sessions_needed"]), (10, 20))
        self.assertNotIn("return", rep["forward"])
        st = forward_status(bars, win, n_sessions=10)
        self.assertEqual(st["status"], "complete")
        # The last session stops at 12:00: not through the close.
        cut = {t: {k: v[b["datetime"] < f"{days[-1]} 12:00"] for k, v in b.items()} for t, b in bars.items()}
        st = forward_status(cut, win, n_sessions=10)
        self.assertEqual((st["status"], st["sessions_have"], st["last_session_complete"], st["last_bar"]),
                         ("incomplete", 10, False, "11:55"))
        # A missing session in the middle.
        gap = {t: {k: v[~np.char.startswith(b["datetime"].astype(str), days[5])] for k, v in b.items()}
               for t, b in bars.items()}
        self.assertEqual(forward_status(gap, win, n_sessions=10)["status"], "incomplete")

    def test_forward_complete_is_scored(self):
        bars = _universe(22, 2)
        days = sessions(bars)
        rep = evaluate(bars, _ind(_honest), random_runs=0, forward=True, forward_window=(days[2], days[-1]))
        self.assertEqual(rep["forward"]["status"], "complete")
        self.assertEqual(rep["forward"]["sessions"], [days[2], days[-1], 20])
        self.assertTrue(math.isfinite(rep["forward"]["return"]))

    def test_lookahead_is_never_ranked_ahead(self):
        clean = {"name": "clean", "causality": [], "gates": {"a": False, "b": False}, "test": {"return": -0.5},
                 "forward": {"status": "complete", "return": -0.5}}
        cheat = {"name": "cheat", "causality": ["T0: 'entry' ..."], "gates": {"a": True, "b": True},
                 "test": {"return": 9.0}, "forward": {"status": "complete", "return": 9.0}}
        self.assertEqual(rank([cheat, clean])[0]["name"], "clean")
        self.assertEqual(rank([cheat, clean], forward=True)[0]["name"], "clean")
        self.assertIsNone(rank([cheat])[0])
        pending = dict(clean, forward={"status": "incomplete", "sessions_have": 3, "sessions_needed": 20})
        best, why = rank([pending, dict(clean, name="other")], forward=True)
        self.assertIsNone(best)
        self.assertIn("incomplete", why)

    def test_evaluated_lookahead_entry_loses_the_ranking(self):
        bars = _universe(40, 3)
        win = _windows(bars)
        peek = evaluate(bars, _ind(_peek, "peek"), random_runs=0, windows=win)
        honest = evaluate(bars, _ind(_honest, "honest"), random_runs=0, windows=win)
        self.assertTrue(peek["causality"])
        self.assertFalse(peek["gates"]["no_lookahead"])
        self.assertGreater(peek["test"]["return"], honest["test"]["return"])  # it cheats well...
        self.assertEqual(rank([peek, honest])[0]["name"], "honest")          # ...and still is not ahead


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
        rep = evaluate(bars, ind, random_runs=3, windows=_windows(bars))
        self.assertEqual(rep["flat_by"], "15:45")
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
        # Alerts fire on the rising edge of the entry condition, not on every bar while it holds.
        self.assertIn("entryEdge = entry and not entry[1]", pine)
        self.assertIn('alertcondition(entryEdge, "Claude ST: buy"', pine)
        self.assertNotIn("alertcondition(entry,", pine)
        # The flatten bar matches flat_by_for: 9:30 + floor((15:55 - 9:30) / tf) * tf.
        self.assertIn("flatMin  = 570 + math.floor((955 - 570) / tfMin) * tfMin", pine)
        self.assertIn('alertcondition(flatBar,   "Claude ST: flatten"', pine)
        for tf in (1, 5, 15, 30, 60):
            m = 570 + (955 - 570) // tf * tf
            self.assertEqual(f"{m // 60:02d}:{m % 60:02d}", flat_by_for(tf))

    def test_every_bundled_indicator_follows_the_contract(self):
        bars = _universe(8, 2)
        for f in sorted((ROOT / "indicators").glob("*.py")):
            if f.name.startswith("_"):
                continue
            ind = load_indicator(f)
            self.assertEqual(causality_violations(ind, prepare(bars, ind.timeframe, "2099-01-01")), [], f.name)


def _load_script():
    spec = importlib.util.spec_from_file_location("indicator_duel_script", ROOT / "scripts" / "indicator_duel.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestDuelScript(unittest.TestCase):
    def _run(self, bars, *argv, forward_window=None):
        """Run the CLI in a subprocess with the pre-registered windows moved onto the synthetic data."""
        tr, te = _windows(bars)
        code = ("import sys, runpy; import quantum.signals as s; s.TRAIN = %r; s.TEST = %r; s.FROZEN_END = %r; "
                "sys.argv = ['x'] + %r; runpy.run_path(%r, run_name='__main__')"
                % (tr, te, te[1], [str(a) for a in argv], str(ROOT / "scripts" / "indicator_duel.py")))
        return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=600, cwd=ROOT)

    def test_cli_scores_two_files(self):
        bars = _universe(40, 3, seed=2)
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "bars.csv"
            _write_csv(bars, src)
            out = Path(d) / "new" / "dir" / "r.json"  # --out's directory is created
            r = self._run(bars, "--bars", src, "--random-runs", "2", "--out", out,
                          ROOT / "indicators" / "claude.py", ROOT / "indicators" / "kama_baseline.py")
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            self.assertIn("PASSED:", r.stdout)
            self.assertIn("Ahead on gates passed", r.stdout)
            self.assertIn("forward window decides", r.stdout)
            rep = json.loads(out.read_text())
            self.assertEqual([x["timeframe"] for x in rep], [5, 5])
            self.assertTrue(all(math.isfinite(x["test"]["return"]) for x in rep))
            self.assertEqual(signals_mod.FORWARD[0] > signals_mod.FROZEN_END, True)

    def test_cli_refuses_data_off_the_windows(self):
        bars = _universe(40, 2, seed=2)
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "bars.csv"
            _write_csv({t: {k: v[78:] for k, v in b.items()} for t, b in bars.items()}, src)  # one session short
            r = self._run(bars, "--bars", src, "--random-runs", "0", "--out", Path(d) / "r.json",
                          ROOT / "indicators" / "claude.py")
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("pre-registered windows", r.stderr)

    def test_cli_never_ranks_lookahead_ahead(self):
        bars = _universe(40, 2, seed=2)
        with tempfile.TemporaryDirectory() as d:
            src, cheat = Path(d) / "bars.csv", Path(d) / "cheat.py"
            _write_csv(bars, src)
            cheat.write_text("import numpy as np\nNAME='cheat'\nTIMEFRAME=5\n"
                             "def signals(b):\n    c = b['close']\n    up = np.r_[c[1:] > c[:-1], False]\n"
                             "    return {'entry': up, 'exit': ~up}\n")
            r = self._run(bars, "--bars", src, "--random-runs", "0", "--out", Path(d) / "r.json",
                          cheat, ROOT / "indicators" / "claude.py")
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            self.assertIn("LOOKAHEAD", r.stdout)
            self.assertIn("Ahead on", r.stdout)
            self.assertNotIn(": cheat", r.stdout.split("Ahead on")[1].splitlines()[0])

    def test_cli_reports_bad_indicator_files_without_a_traceback(self):
        bars = _universe(40, 2, seed=2)
        with tempfile.TemporaryDirectory() as d:
            src, broken, nofields = Path(d) / "bars.csv", Path(d) / "broken.py", Path(d) / "nofields.py"
            _write_csv(bars, src)
            broken.write_text("def signals(b) return 1\n")
            nofields.write_text("NAME = 'x'\n")
            out = Path(d) / "r.json"
            r = self._run(bars, "--bars", src, "--random-runs", "0", "--out", out,
                          ROOT / "indicators" / "claude.py", broken, nofields, Path(d) / "missing.py")
            self.assertEqual(r.returncode, 2, r.stdout[-2000:])
            self.assertNotIn("Traceback", r.stderr)
            for name in ("broken.py", "nofields.py", "missing.py"):
                self.assertIn(name, r.stderr)
            self.assertIn("missing TIMEFRAME", r.stderr)
            self.assertNotIn("PASSED:", r.stdout)  # nothing is scored on a partial field
            self.assertFalse(out.exists())

    def test_cli_forward_incomplete_declares_nobody_ahead(self):
        bars = _universe(40, 2, seed=2)
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "bars.csv"
            _write_csv(bars, src)  # June-July 2026: no forward sessions at all
            r = self._run(bars, "--bars", src, "--forward", "--out", Path(d) / "r.json",
                          ROOT / "indicators" / "claude.py", ROOT / "indicators" / "kama_baseline.py")
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            self.assertIn("incomplete: 0 of 20 sessions", r.stdout)
            self.assertIn("Nobody is ahead: the forward window is incomplete", r.stdout)
            self.assertNotIn("Ahead on", r.stdout)
            rep = json.loads((Path(d) / "r.json").read_text())
            self.assertEqual({x["forward"]["status"] for x in rep}, {"incomplete"})

    def test_fetch_never_touches_the_frozen_cache(self):
        mod = _load_script()
        calls = []

        def fake_run(cmd, check):
            calls.append(cmd)
            Path(cmd[cmd.index("--out") + 1]).write_text("fresh\n")
        mod.subprocess = types.SimpleNamespace(run=fake_run)
        with tempfile.TemporaryDirectory() as d:
            cache = Path(d) / "bars_5m.csv"
            cache.write_text("frozen\n")
            fresh = Path(d) / "sub" / "bars_5m_fresh.csv"
            self.assertEqual(mod.fetch(fresh, protected=[cache]), fresh)
            self.assertEqual(cache.read_text(), "frozen\n")
            self.assertEqual(fresh.read_text(), "fresh\n")
            for same in (cache, Path(d) / "sub" / ".." / "bars_5m.csv"):
                with self.assertRaises(SystemExit):
                    mod.fetch(same, protected=[cache])
            self.assertEqual(len(calls), 1)
            self.assertEqual(cache.read_text(), "frozen\n")
            # The CLI's defaults write --fetch to a different file from the frozen cache.
            ap_defaults = mod.DATA / "bars_5m.csv", mod.DATA / "bars_5m_fresh.csv"
            self.assertNotEqual(*ap_defaults)
            src = (ROOT / "scripts" / "indicator_duel.py").read_text()
            self.assertIn("fetch(args.fresh, protected=[args.cache]", src)


if __name__ == "__main__":
    unittest.main()
