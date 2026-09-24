"""Tests for the intraday KAMA backtester (quantum.intraday).

The indicator is checked against a plain loop written straight from
Kaufman's formulas; the engine is checked on tiny synthetic sessions where
the right fill, the right screen pick and the right cash balance can be
worked out by hand.

Run with::

    python3 -m pytest tests/test_intraday.py -q
"""

from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from quantum.intraday import (
    IntradayConfig,
    backtest,
    efficiency_ratio,
    kama,
    kama_signals,
    daily_ranges,
    load_bars,
    random_baseline,
    volatility_screen,
)

DATES = ["2026-09-21", "2026-09-22", "2026-09-23"]


def _times(date: str, n: int = 390) -> list[str]:
    return [f"{date} {9 + (30 + m) // 60:02d}:{(30 + m) % 60:02d}:00" for m in range(n)]


def make_ticker(closes_by_day, gap=0.001):
    """Minute bars from per-day close paths; each open sits ``gap`` (relative)
    below the previous close so an open fill is distinguishable from a close
    fill."""
    dts, o, h, l, c = [], [], [], [], []
    prev = None
    for date, closes in closes_by_day:
        closes = list(map(float, closes))
        dts += _times(date, len(closes))
        for x in closes:
            op = x if prev is None else prev * (1 - gap)
            o.append(op)
            h.append(max(op, x) * 1.0005)
            l.append(min(op, x) * 0.9995)
            c.append(x)
            prev = x
    return {"datetime": np.array(dts), "open": np.array(o), "high": np.array(h),
            "low": np.array(l), "close": np.array(c), "volume": np.full(len(c), 1000.0)}


def noisy_day(rng, start, n=390, vol=0.002):
    return start * np.exp(np.cumsum(rng.normal(0, vol, n)))


def wave_day(start, n=390, amp=0.03, period=60):
    m = np.arange(n)
    return start * (1 + amp * np.sin(2 * np.pi * m / period))


def reference_kama(close, n=10, fast=2, slow=30):
    fsc, ssc = 2 / (fast + 1), 2 / (slow + 1)
    out = [math.nan] * len(close)
    if len(close) <= n:
        return out
    out[n] = close[n]
    for t in range(n + 1, len(close)):
        change = abs(close[t] - close[t - n])
        vol = sum(abs(close[i] - close[i - 1]) for i in range(t - n + 1, t + 1))
        er = change / vol if vol else 0.0
        sc = (er * (fsc - ssc) + ssc) ** 2
        out[t] = out[t - 1] + sc * (close[t] - out[t - 1])
    return out


class TestKama(unittest.TestCase):
    def test_matches_reference_loop(self):
        rng = np.random.default_rng(1)
        c = 20 * np.exp(np.cumsum(rng.normal(0, 0.01, 300)))
        c[50:70] = c[50]  # a flat stretch: zero-volatility windows
        for n, fast, slow in [(10, 2, 30), (5, 3, 20)]:
            np.testing.assert_allclose(kama(c, n, fast, slow), reference_kama(list(c), n, fast, slow),
                                       rtol=1e-12, equal_nan=True)

    def test_seed_and_nan_prefix(self):
        c = np.arange(30, dtype=float)
        k = kama(c, 10)
        self.assertTrue(np.all(np.isnan(k[:10])))
        self.assertEqual(k[10], c[10])

    def test_efficiency_ratio_line_and_noise(self):
        line = np.linspace(10, 20, 100)
        np.testing.assert_allclose(efficiency_ratio(line, 10)[10:], 1.0)
        noise = 10 + 0.1 * (np.arange(100) % 2)
        self.assertLess(np.nanmax(efficiency_ratio(noise, 10)), 1e-9)
        flat = np.full(50, 5.0)
        np.testing.assert_array_equal(efficiency_ratio(flat, 10)[10:], 0.0)

    def test_causal(self):
        rng = np.random.default_rng(2)
        c = 30 * np.exp(np.cumsum(rng.normal(0, 0.01, 200)))
        c2 = c.copy()
        c2[120:] *= 1.5
        cfg = IntradayConfig()
        np.testing.assert_array_equal(kama(c, 10)[:120], kama(c2, 10)[:120])
        np.testing.assert_array_equal(efficiency_ratio(c, 10)[:120], efficiency_ratio(c2, 10)[:120])
        s1, s2 = kama_signals(c, cfg), kama_signals(c2, cfg)
        for key in ("kama", "filter", "entry"):
            np.testing.assert_array_equal(s1[key][:120], s2[key][:120])


class TestLoad(unittest.TestCase):
    def test_load_bars(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bars.csv"
            p.write_text("datetime,ticker,open,high,low,close,volume\n"
                         "2026-09-23 09:30:00,AAA,1,2,0.5,1.5,100\n"
                         "2026-09-23 09:30:00,BBB,3,4,2.5,3.5,200\n"
                         "2026-09-23 09:31:00,AAA,1.5,2,1,1.8,50\n")
            bars = load_bars(p)
        self.assertEqual(sorted(bars), ["AAA", "BBB"])
        self.assertEqual(list(bars["AAA"]["datetime"]), ["2026-09-23 09:30:00", "2026-09-23 09:31:00"])
        np.testing.assert_array_equal(bars["AAA"]["close"], [1.5, 1.8])
        self.assertEqual(bars["BBB"]["volume"][0], 200.0)


class TestExecution(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(3)
        self.bars = {"AAA": make_ticker([(DATES[0], noisy_day(rng, 20.0)),
                                         (DATES[1], wave_day(20.0))])}

    def test_fill_at_next_open_with_slippage(self):
        cfg = IntradayConfig(slippage_bps=10)
        res = backtest(self.bars, cfg)
        self.assertTrue(res["trades"])
        b = self.bars["AAA"]
        entry = kama_signals(b["close"], cfg)["entry"]
        first_day2 = next(i for i, d in enumerate(b["datetime"]) if d.startswith(DATES[1]))
        j = first_day2 + int(np.flatnonzero(entry[first_day2:])[0])
        t0 = res["trades"][0]
        self.assertEqual(t0["entry_time"], b["datetime"][j + 1])
        self.assertAlmostEqual(t0["entry_price"], b["open"][j + 1] * 1.001, places=12)
        self.assertNotAlmostEqual(t0["entry_price"], b["close"][j] * 1.001, places=6)
        if t0["reason"] == "signal":
            i = int(np.flatnonzero(b["datetime"] == t0["exit_time"])[0])
            self.assertAlmostEqual(t0["exit_price"], b["open"][i] * 0.999, places=12)

    def test_stop_fills_at_min_of_stop_and_open(self):
        cfg = IntradayConfig(slippage_bps=0, stop_loss_pct=0.02, settled_cash_only=True)
        base = backtest(self.bars, cfg)
        t0 = base["trades"][0]
        b = {k: v.copy() for k, v in self.bars["AAA"].items()}
        e = int(np.flatnonzero(b["datetime"] == t0["entry_time"])[0])
        stop = t0["entry_price"] * 0.98
        # Gap: bar e+2 opens 10% below entry, well under the stop.
        gapped = {k: v.copy() for k, v in b.items()}
        gapped["open"][e + 2] = t0["entry_price"] * 0.90
        gapped["low"][e + 2] = t0["entry_price"] * 0.89
        tr = backtest({"AAA": gapped}, cfg)["trades"][0]
        self.assertEqual(tr["reason"], "stop")
        self.assertEqual(tr["exit_time"], b["datetime"][e + 2])
        self.assertAlmostEqual(tr["exit_price"], t0["entry_price"] * 0.90, places=12)
        # No gap: opens above the stop, trades through it -> fills at the stop.
        dip = {k: v.copy() for k, v in b.items()}
        dip["open"][e + 2] = t0["entry_price"]
        dip["low"][e + 2] = t0["entry_price"] * 0.95
        tr = backtest({"AAA": dip}, cfg)["trades"][0]
        self.assertEqual(tr["reason"], "stop")
        self.assertAlmostEqual(tr["exit_price"], stop, places=12)


def _universe(seed=4, days=5, n_tickers=6):
    rng = np.random.default_rng(seed)
    dates = [f"2026-09-{d:02d}" for d in range(14, 14 + days)]
    bars = {}
    for k in range(n_tickers):
        start = rng.uniform(3, 30)
        per_day, px = [], start
        for d in dates:
            path = noisy_day(rng, px, vol=0.001 * (k + 1)) if k % 2 else wave_day(px, amp=0.01 * (k + 1))
            per_day.append((d, path))
            px = path[-1]
        bars[f"T{k}"] = make_ticker(per_day)
    return bars


class TestRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bars = _universe()

    def test_never_overnight_and_flat_by(self):
        res = backtest(self.bars, IntradayConfig())
        self.assertTrue(res["trades"])
        for t in res["trades"]:
            self.assertEqual(t["entry_time"][:10], t["exit_time"][:10])
            self.assertLessEqual(t["exit_time"][11:16], "15:55")
            self.assertLess(t["entry_time"][11:16], "15:55")

    def test_whole_shares_and_cash_never_negative(self):
        for settled in (True, False):
            cfg = IntradayConfig(settled_cash_only=settled, deploy_fraction=0.8)
            res = backtest(self.bars, cfg)
            eq = {e["date"]: e["equity"] for e in res["equity"]}
            dates = sorted(eq)
            cash = cfg.cash
            by_day: dict[str, list] = {}
            for t in res["trades"]:
                self.assertEqual(t["shares"], math.floor(t["shares"]))
                self.assertGreaterEqual(t["shares"], 1)
                by_day.setdefault(t["entry_time"][:10], []).append(t)
            for d in dates:
                # Replay the day's cash: flat at each exit, so cash after
                # each buy is start-of-day cash plus realised pnl so far.
                for t in sorted(by_day.get(d, []), key=lambda x: x["entry_time"]):
                    cost = t["shares"] * t["entry_price"]
                    self.assertLessEqual(cost, cash + 1e-9)
                    if settled:
                        cash -= cost  # proceeds do not come back today
                    else:
                        cash += t["pnl"]
                cash = eq[d]
                self.assertGreaterEqual(cash, 0.0)

    def test_max_trades_per_day(self):
        loose = backtest(self.bars, IntradayConfig(settled_cash_only=False, max_trades_per_day=100))
        per = lambda r: np.unique([t["entry_time"][:10] for t in r["trades"]], return_counts=True)[1]
        self.assertGreater(per(loose).max(), 2)
        capped = backtest(self.bars, IntradayConfig(settled_cash_only=False, max_trades_per_day=2))
        self.assertLessEqual(per(capped).max(), 2)
        self.assertEqual(per(capped).max(), 2)

    def test_settled_cash_only_blocks_same_day_reuse(self):
        # $50, all-in, a ~$30 stock: after one round trip only ~$20 is settled.
        bars = {"AAA": make_ticker([(DATES[0], wave_day(30.0)), (DATES[1], wave_day(30.0)),
                                    (DATES[2], wave_day(30.0))])}
        free = backtest(bars, IntradayConfig(deploy_fraction=1.0, settled_cash_only=False))
        cash_acct = backtest(bars, IntradayConfig(deploy_fraction=1.0, settled_cash_only=True))
        count = lambda r: np.unique([t["entry_time"][:10] for t in r["trades"]], return_counts=True)[1]
        self.assertGreater(count(free).max(), 1)
        self.assertEqual(count(cash_acct).max(), 1)
        self.assertEqual(len({t["entry_time"][:10] for t in cash_acct["trades"]}), 2)

    def test_baseline_same_conditions(self):
        cfg = IntradayConfig(settled_cash_only=False)
        res = backtest(self.bars, cfg)
        base = random_baseline(self.bars, cfg, res["trades"], seed=7)
        again = random_baseline(self.bars, cfg, res["trades"], seed=7)
        self.assertEqual(base["trades"], again["trades"])
        self.assertTrue(base["trades"])
        self.assertLessEqual(len(base["trades"]), len(res["trades"]))
        for t in base["trades"]:
            self.assertEqual(t["entry_time"][:10], t["exit_time"][:10])
        for key in ("total_return", "win_rate", "max_drawdown_daily", "time_invested_fraction"):
            self.assertIn(key, base["summary"])


class TestScreen(unittest.TestCase):
    def test_uses_prior_day_only(self):
        rng = np.random.default_rng(5)
        quiet, wild = noisy_day(rng, 10.0, vol=0.0005), noisy_day(rng, 10.0, vol=0.01)
        # Day 1: A wild, B quiet.  Day 2: B wild, A quiet.
        a = make_ticker([(DATES[0], wild), (DATES[1], quiet * wild[-1] / quiet[0])])
        b = make_ticker([(DATES[0], quiet), (DATES[1], wild * quiet[-1] / wild[0])])
        bars = {"A": a, "B": b}
        ranges = daily_ranges(bars)
        self.assertGreater(ranges["B"][DATES[1]][0], ranges["A"][DATES[1]][0])
        self.assertEqual(volatility_screen(ranges, DATES[1], 35.0, top_n=1), ["A"])
        self.assertEqual(volatility_screen(ranges, DATES[0], 35.0, top_n=1), [])
        res = backtest(bars, IntradayConfig(top_n=1))
        self.assertTrue(res["trades"])
        self.assertTrue(all(t["ticker"] == "A" for t in res["trades"]))

    def test_budget_filter(self):
        ranges = {"CHEAP": {DATES[0]: (0.02, 5.0)}, "DEAR": {DATES[0]: (0.09, 60.0)}}
        self.assertEqual(volatility_screen(ranges, DATES[1], 35.0, top_n=5), ["CHEAP"])
        self.assertEqual(volatility_screen(ranges, DATES[1], 100.0, top_n=5), ["DEAR", "CHEAP"])


if __name__ == "__main__":
    unittest.main()


class TestLiveSession(unittest.TestCase):
    """trade_from and open_session: what a live paper run sees mid-day."""

    @classmethod
    def setUpClass(cls):
        cls.bars = _universe()
        cls.last = sorted({d[:10] for d in cls.bars["T0"]["datetime"]})[-1]

    def _cut(self, until):
        return {t: {k: v[b["datetime"] <= until] for k, v in b.items()} for t, b in self.bars.items()}

    def test_trade_from_starts_fresh_on_that_day(self):
        cfg = IntradayConfig(trade_from=self.last)
        res = backtest(self.bars, cfg)
        self.assertEqual([e["date"] for e in res["equity"]], [self.last])
        self.assertTrue(all(t["entry_time"][:10] == self.last for t in res["trades"]))
        self.assertEqual(res["summary"]["initial_equity"], cfg.cash)

    def test_mid_session_run_is_a_prefix_of_the_full_day(self):
        cfg = IntradayConfig(trade_from=self.last, settled_cash_only=False)
        full = backtest(self.bars, cfg)["trades"]
        self.assertGreaterEqual(len(full), 2)
        checked_open = False
        for until in (f"{self.last} 10:30:00", f"{self.last} 12:00:00", f"{self.last} 14:45:00"):
            part = backtest(self._cut(until), cfg, open_session=True)
            done = [t for t in full if t["exit_time"] <= until]
            self.assertEqual(part["trades"], done)
            running = [t for t in full if t["entry_time"] <= until < t["exit_time"]]
            got = part["open"]["positions"]
            self.assertEqual([p["ticker"] for p in got], [t["ticker"] for t in running])
            for p, t in zip(got, running):
                checked_open = True
                self.assertEqual(p["entry_time"], t["entry_time"])
                self.assertEqual(p["shares"], t["shares"])
                self.assertAlmostEqual(p["entry_price"], t["entry_price"])
        self.assertTrue(checked_open)

    def test_open_session_never_closes_on_the_partial_last_bar(self):
        cfg = IntradayConfig(trade_from=self.last)
        part = backtest(self._cut(f"{self.last} 13:00:00"), cfg, open_session=True)
        self.assertFalse([t for t in part["trades"] if t["reason"] == "eod"])
