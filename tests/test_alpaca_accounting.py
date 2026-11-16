"""Alpaca broker accounting: realized P&L stays in equity, replays and old bars
are never sent twice or late.  No network: a fake transport stands in."""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import os
import tempfile
import unittest
import unittest.mock

from quantum.alpaca import AlpacaBroker, BrokerRefused, net_cash_flow
from quantum.live import Bar, Order

TODAY = dt.date(2026, 9, 23)


class Fake:
    """Canned Alpaca replies; POST can be told to reject some symbols."""

    def __init__(self, cash="100000", positions=None, open_orders=None, reject=None):
        self.account = {"status": "ACTIVE", "cash": cash}
        self.positions = positions or []
        self.open_orders = open_orders or []
        self.reject = reject or {}
        self.calls = []

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path == "/v2/account":
            return self.account
        if path == "/v2/positions":
            return self.positions
        if path.startswith("/v2/orders") and method == "GET":
            return self.open_orders
        if path == "/v2/orders" and method == "POST":
            if body["symbol"] in self.reject:
                raise RuntimeError(self.reject[body["symbol"]])
            return {"id": f"o{len(self.calls)}", "status": "accepted"}
        raise AssertionError(f"unexpected call {method} {path}")

    def posted(self):
        return [b for m, p, b in self.calls if m == "POST"]


def broker(fake, budget=1000.0, fills=None, tickers=("AAPL", "XOM")):
    return AlpacaBroker(list(tickers), budget, fake, today=lambda: TODAY, fills=fills)


def equity(b, prices):
    return b.cash() + sum(q * prices[t] for t, q in b.positions().items())


def as_dicts(fills):
    return [{"ticker": f.ticker, "quantity": f.quantity, "price": f.price, "fee": f.fee,
             "date": f.date, "note": f.note} for f in fills]


DUP = ('Alpaca POST /v2/orders failed: HTTP 422 '
       '{"code":40010001,"message":"client_order_id must be unique"}')


class TestRealizedPnl(unittest.TestCase):
    def test_losing_sale_stays_lost(self):
        # Run 1: buy 10 @ 100 with a 1000 budget.
        b1 = broker(Fake(), fills=[])
        fills = b1.submit([Order("AAPL", 10)], Bar("2026-09-23", {"AAPL": 100.0, "XOM": 1.0}))
        self.assertEqual(len(fills), 1)
        self.assertAlmostEqual(equity(b1, {"AAPL": 100.0}), 1000.0)  # pending buy still counted
        history = as_dicts(fills)

        # Run 2: filled; price has halved.
        held = [{"symbol": "AAPL", "qty": "10", "cost_basis": "1000"}]
        b2 = broker(Fake(positions=held), fills=history)
        self.assertAlmostEqual(b2.cash(), 0.0)
        self.assertAlmostEqual(equity(b2, {"AAPL": 50.0}), 500.0)
        sold = b2.submit([Order("AAPL", -10)], Bar("2026-09-23", {"AAPL": 50.0, "XOM": 1.0}))
        self.assertAlmostEqual(equity(b2, {"AAPL": 50.0}), 500.0)  # not 1000
        history += as_dicts(sold)

        # Run 3: flat; the budget did not refill.
        b3 = broker(Fake(), fills=history)
        self.assertEqual(b3.positions(), {})
        self.assertAlmostEqual(b3.cash(), 500.0)

    def test_ledger_with_bookkeeping_and_cash_in_lieu(self):
        history = [
            {"ticker": "AAPL", "quantity": 4.0, "price": 100.0, "fee": 1.0, "date": "2026-09-01"},
            # a 2:1 split: bookkeeping, moves no cash
            {"ticker": "AAPL", "quantity": 4.0, "price": 0.0, "fee": 0.0, "date": "2026-09-10",
             "note": "adjustment x2.000000"},
            # cash in lieu of a fractional share: returns cash
            {"ticker": "AAPL", "quantity": -0.5, "price": 60.0, "fee": 0.0, "date": "2026-09-10",
             "note": "cash in lieu"},
            {"ticker": "XOM", "quantity": 2.0, "price": 50.0, "fee": 0.5, "date": "2026-09-15"},
        ]
        self.assertAlmostEqual(net_cash_flow(history), -401.0 + 30.0 - 100.5)
        held = [{"symbol": "AAPL", "qty": "7.5", "cost_basis": "400"},
                {"symbol": "XOM", "qty": "2", "cost_basis": "100"}]
        b = broker(Fake(positions=held), budget=1000.0, fills=history)
        self.assertAlmostEqual(b.cash(), 1000.0 - 401.0 + 30.0 - 100.5)
        # capped by the account's real cash, never negative
        self.assertAlmostEqual(broker(Fake(cash="200", positions=held), fills=history).cash(), 200.0)
        self.assertEqual(broker(Fake(positions=held), budget=100.0, fills=history).cash(), 0.0)

    def test_history_that_is_not_the_accounts_falls_back(self):
        # A paper state's fills, but the Alpaca account holds nothing.
        history = [{"ticker": "AAPL", "quantity": 5.0, "price": 100.0, "fee": 0.0, "date": "2026-09-01"}]
        lines = []
        b = AlpacaBroker(["AAPL"], 1000.0, Fake(), today=lambda: TODAY, fills=history, log=lines.append)
        self.assertAlmostEqual(b.cash(), 1000.0)
        self.assertTrue(any("does not match" in line for line in lines))


class TestReplayAndAge(unittest.TestCase):
    def test_duplicate_client_order_id_is_skipped(self):
        fake = Fake(positions=[{"symbol": "XOM", "qty": "3", "cost_basis": "300"}], reject={"XOM": DUP})
        lines = []
        b = AlpacaBroker(["AAPL", "XOM"], 1000.0, fake, today=lambda: TODAY, fills=None, log=lines.append)
        before = b.cash()
        fills = b.submit([Order("XOM", -3), Order("AAPL", 1)], Bar("2026-09-23", {"AAPL": 200.0, "XOM": 100.0}))
        self.assertEqual([s["symbol"] for s in fake.posted()], ["XOM", "AAPL"])  # both tried
        self.assertEqual([(f.ticker, f.quantity) for f in fills], [("AAPL", 1.0)])  # only AAPL recorded
        self.assertEqual([s["symbol"] for s in b.submitted], ["AAPL"])
        self.assertAlmostEqual(b.cash(), before - 200.0)
        self.assertTrue(any("already sent" in line and "XOM" in line for line in lines))

    def test_other_errors_still_raise(self):
        fake = Fake(reject={"AAPL": "Alpaca POST /v2/orders failed: HTTP 403 insufficient buying power"})
        with self.assertRaises(RuntimeError):
            broker(fake).submit([Order("AAPL", 1)], Bar("2026-09-23", {"AAPL": 200.0, "XOM": 1.0}))

    def test_two_day_old_bar_not_sent(self):
        fake = Fake()
        b = broker(fake, fills=[])
        self.assertEqual(b.submit([Order("AAPL", 1)], Bar("2026-09-21", {"AAPL": 200.0, "XOM": 1.0})), [])
        self.assertEqual(fake.posted(), [])
        self.assertAlmostEqual(b.cash(), 1000.0)
        self.assertEqual(len(b.submit([Order("AAPL", 1)], Bar("2026-09-23", {"AAPL": 200.0, "XOM": 1.0}))), 1)

    def test_today_is_new_york_date(self):
        # 01:30 UTC on the 24th is still the evening of the 23rd in New York.
        import quantum.alpaca as mod
        real = mod.datetime

        class Frozen(real):
            @classmethod
            def now(cls, tz=None):
                return real(2026, 9, 24, 1, 30, tzinfo=dt.timezone.utc).astimezone(tz)

        with unittest.mock.patch.object(mod, "datetime", Frozen):
            self.assertEqual(mod._new_york_today(), dt.date(2026, 9, 23))


class TestCliWiring(unittest.TestCase):
    def _run(self, fresh):
        from quantum.cli import main
        seen = {}

        def fake_env(tickers, budget, env=None, log=None, transport=None, fills=None):
            seen["fills"] = fills
            raise BrokerRefused("stop here")

        with tempfile.TemporaryDirectory() as tmp:
            with open("live/config.json", encoding="utf-8") as fh:
                cfg = json.load(fh)
            cfg["state_path"] = os.path.join(tmp, "state.json")
            path = os.path.join(tmp, "config.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(cfg, fh)
            fill = {"ticker": "AAPL", "quantity": 1.0, "price": 10.0, "fee": 0.0, "date": "2026-09-23"}
            with open(cfg["state_path"], "w", encoding="utf-8") as fh:
                json.dump({"tickers": cfg["tickers"], "fills": [fill]}, fh)
            argv = ["live", "--config", path, "--replay", "live/prices.csv", "--broker", "alpaca"]
            with unittest.mock.patch("quantum.alpaca.from_environment", fake_env), \
                    contextlib.redirect_stdout(io.StringIO()):
                code = main(argv + (["--fresh"] if fresh else []))
        self.assertEqual(code, 2)
        return seen["fills"]

    def test_cli_passes_prior_fills(self):
        self.assertEqual(self._run(fresh=False),
                         [{"ticker": "AAPL", "quantity": 1.0, "price": 10.0, "fee": 0.0, "date": "2026-09-23"}])

    def test_cli_fresh_passes_no_history(self):
        self.assertIsNone(self._run(fresh=True))


if __name__ == "__main__":
    unittest.main()
