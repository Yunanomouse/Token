"""Engine.reconcile's cases beyond a plain split or dividend, the ledger's
bookkeeping fills, the snapshot's ``adjusted`` flag, and the price fetcher's
cut-off for a session that is still trading."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from quantum.live import Bar, Engine, EngineConfig, RiskLimits, snapshot, trade_ledger

ROOT = Path(__file__).resolve().parents[1]
DAYS = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
BASE = [(100.0, 50.0), (102.0, 51.0), (104.0, 50.5), (103.0, 50.0)]


def _engine(tmp: str) -> Engine:
    cfg = EngineConfig(["AAA", "BBB"], strategy="equal_weight", window=3, rebalance_every=100,
                       initial_cash=1000.0, fee_rate=0.0,
                       limits=RiskLimits(min_history=3, max_drawdown=0.5, max_turnover=1.0, max_weight=0.6),
                       state_path=f"{tmp}/s.json")
    engine = Engine(cfg)
    bars = [Bar(d, {"AAA": a, "BBB": b}) for d, (a, b) in zip(DAYS, BASE)]
    engine.run(type("Feed", (), {"bars": lambda self: iter(bars), "history": lambda self: []})())
    return engine


def _feed(rows) -> list[Bar]:
    return [Bar(d, {"AAA": a, "BBB": b}) for d, (a, b) in zip(DAYS, rows)]


class TestReconcileCases(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.engine = _engine(self._tmp.name)
        st = self.engine.state
        self.held, self.cash = dict(st.positions), st.cash
        self.assertEqual(sorted(self.held), ["AAA", "BBB"])
        self.assertFalse(snapshot(self.engine)[0]["adjusted"])

    def tearDown(self):
        self._tmp.cleanup()

    def test_revised_last_close_replaces_only_that_price(self):
        # The newest stored bar was taken mid-session; the feed now has the close.
        rows = BASE[:-1] + [(101.0, 50.0)]
        changes = self.engine.reconcile(_feed(rows))
        self.assertEqual([(c["ticker"], c["kind"], c["factor"]) for c in changes], [("AAA", "revision", 1.0)])
        st = self.engine.state
        self.assertEqual([r[0] for r in st.prices], [100.0, 102.0, 104.0, 101.0])
        self.assertEqual(st.positions, self.held)
        self.assertFalse(any(f.get("note") for f in st.fills))
        self.assertFalse(snapshot(self.engine)[0]["adjusted"])
        self.assertEqual(self.engine.reconcile(_feed(rows)), [])

    def test_uneven_move_is_a_basis_change_and_leaves_shares(self):
        rows = [(a * m, b) for (a, b), m in zip(BASE, (0.97, 0.98, 0.99, 1.0))]
        changes = self.engine.reconcile(_feed(rows))
        self.assertEqual([(c["ticker"], c["kind"]) for c in changes], [("AAA", "basis")])
        st = self.engine.state
        self.assertEqual([round(r[0], 9) for r in st.prices], [round(a, 9) for a, _ in rows])
        self.assertEqual(st.positions, self.held)
        self.assertAlmostEqual(st.cash, self.cash)

    def test_consistent_rise_below_half_is_not_a_corporate_action(self):
        # Past prices up 20% at once fits neither a dividend nor a reverse split.
        rows = [(a * 1.25, b) for a, b in BASE[:-1]] + [BASE[-1]]
        changes = self.engine.reconcile(_feed(rows))
        self.assertEqual([(c["ticker"], c["kind"]) for c in changes], [("AAA", "basis")])
        self.assertEqual(self.engine.state.positions, self.held)

    def test_reverse_split_divides_the_shares(self):
        # 1:10 reverse split of BBB: every past price is ten times higher in the feed.
        before = self.engine.equity(Bar(DAYS[-1], dict(zip(["AAA", "BBB"], self.engine.state.prices[-1]))))
        rows = [(a, b * 10) for a, b in BASE[:-1]] + [(BASE[-1][0], 500.0)]
        changes = self.engine.reconcile(_feed(rows))
        self.assertEqual([(c["ticker"], c["kind"]) for c in changes], [("BBB", "split")])
        self.assertAlmostEqual(changes[0]["factor"], 0.1)
        st = self.engine.state
        self.assertAlmostEqual(st.positions["BBB"], self.held["BBB"] / 10)
        self.assertEqual(st.positions["AAA"], self.held["AAA"])
        after = self.engine.equity(Bar(DAYS[-1], {"AAA": BASE[-1][0], "BBB": 500.0}))
        self.assertAlmostEqual(after, before, places=6)
        self.assertTrue(snapshot(self.engine)[0]["adjusted"])
        led = trade_ledger(st.fills, dict(zip(st.tickers, st.prices[-1])))
        self.assertAlmostEqual(led["positions"]["BBB"]["shares"], st.positions["BBB"])
        self.assertAlmostEqual(led["total_pnl"], after - 1000.0, places=6)


class TestLedgerNoteFills(unittest.TestCase):
    def test_share_change_keeps_the_cost(self):
        fills = [
            {"ticker": "A", "quantity": 10.0, "price": 10.0, "fee": 0.0, "date": "d1"},
            {"ticker": "A", "quantity": 30.0, "price": 0.0, "fee": 0.0, "date": "d2", "note": "adjustment x4"},
        ]
        led = trade_ledger(fills, {"A": 2.6})
        pos = led["positions"]["A"]
        self.assertEqual((pos["shares"], pos["cost_basis"], pos["avg_cost"]), (40.0, 100.0, 2.5))
        self.assertAlmostEqual(led["unrealized_pnl"], 4.0)
        self.assertEqual(led["realized_pnl"], 0.0)
        self.assertEqual(led["n_round_trips"], 0)

    def test_share_change_to_zero_books_the_cost_as_a_loss(self):
        fills = [
            {"ticker": "A", "quantity": 3.0, "price": 10.0, "fee": 1.0, "date": "d1"},
            {"ticker": "A", "quantity": -3.0, "price": 0.0, "fee": 0.0, "date": "d2", "note": "adjustment x0.1"},
        ]
        led = trade_ledger(fills, {"A": 100.0})
        self.assertNotIn("A", led["positions"])
        self.assertAlmostEqual(led["realized_pnl"], -31.0)
        self.assertEqual(led["n_round_trips"], 1)
        self.assertEqual(led["round_trips"][0]["exit_date"], "d2")

    def test_cash_in_lieu_is_a_sale(self):
        fills = [
            {"ticker": "A", "quantity": 3.0, "price": 10.0, "fee": 0.0, "date": "d1"},
            {"ticker": "A", "quantity": -0.5, "price": 12.0, "fee": 0.0, "date": "d2", "note": "cash in lieu"},
        ]
        led = trade_ledger(fills, {"A": 12.0})
        self.assertAlmostEqual(led["realized_pnl"], 1.0)
        self.assertAlmostEqual(led["positions"]["A"]["shares"], 2.5)


class TestUnfinishedSession(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("fetch_prices", ROOT / "scripts" / "fetch_prices.py")
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    def at(self, iso):
        return self.mod.unfinished_session(datetime.fromisoformat(iso).replace(tzinfo=timezone.utc))

    def test_today_is_dropped_until_half_past_four_new_york(self):
        self.assertEqual(self.at("2026-09-29T16:55:00"), "2026-09-29")  # 12:55 EDT, mid-session
        self.assertEqual(self.at("2026-09-29T20:29:00"), "2026-09-29")  # 16:29 EDT
        self.assertIsNone(self.at("2026-09-29T20:30:00"))               # 16:30 EDT
        self.assertIsNone(self.at("2026-09-29T21:30:00"))               # the scheduled run
        self.assertIsNone(self.at("2026-12-01T21:30:00"))               # 16:30 EST
        self.assertEqual(self.at("2026-12-01T21:29:00"), "2026-12-01")  # 16:29 EST

    def test_after_midnight_utc_is_still_the_new_york_day(self):
        # 00:30 UTC on the 30th is 20:30 on the 29th in New York: the 29th is final.
        self.assertIsNone(self.at("2026-09-30T00:30:00"))
        # 13:00 UTC is 09:00 New York, before the open: that day has no bar to drop.
        self.assertEqual(self.at("2026-09-30T13:00:00"), "2026-09-30")


if __name__ == "__main__":
    unittest.main()
