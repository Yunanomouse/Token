"""Paper Trading (paper_trading/paper_app.py): buying and selling by hand with pretend money.

Covers market hours, order validation and fills (market, limit, stop; day
and GTC; slippage and commission), buying power, persistence and backups,
settings, the watchlist, the equity curve, demo prices, the Yahoo quote
parser and the local HTTP server's protections.

No test reaches the network: every Book gets a fake ``quotes`` function and
a fixed ``clock``, and ``yahoo_quote`` is tested with ``urlopen`` mocked.
"""

import http.client
import io
import json
import math
import re
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "paper_trading"))
import paper_app as paper  # noqa: E402
from paper_app import (  # noqa: E402
    NY,
    DEFAULT_CASH, Book, DemoQuotes, PaperServer, clean_ticker, market_open, next_session, yahoo_quote,
)

UTC = timezone.utc


def ny(y, mo, d, h=0, mi=0, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=NY)


OPEN_THU = ny(2026, 10, 1, 11, 0)      # Thursday, market open
CLOSED_THU = ny(2026, 10, 1, 17, 0)    # Thursday evening
OPEN_FRI = ny(2026, 10, 2, 10, 0)
SATURDAY = ny(2026, 10, 3, 12, 0)


class FakeQuotes:
    """Stands in for yahoo_quote: a mutable price table, ValueError for an
    unknown symbol and OSError when ``offline``."""

    def __init__(self, prices=None, time=None):
        self.prices = dict(prices or {"AAPL": 100.0, "MSFT": 400.0, "SPY": 500.0})
        self.time = time
        self.offline = False
        self.calls = []

    def __call__(self, ticker):
        self.calls.append(ticker)
        if self.offline:
            raise OSError("no connection")
        if ticker not in self.prices:
            raise ValueError(f"{ticker}: no such symbol")
        return {"ticker": ticker, "price": self.prices[ticker], "prev_close": self.prices[ticker] - 1,
                "time": self.time, "name": ticker, "currency": "USD", "source": "yahoo"}


class BookCase(unittest.TestCase):
    """A Book in a scratch folder with fake quotes and a settable clock.
    The quote cache is turned off so a changed price is seen at once."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name) / "acct"
        self.now = OPEN_THU
        self.q = FakeQuotes()
        ttl = mock.patch.object(paper, "QUOTE_TTL", 0)
        ttl.start()
        self.addCleanup(ttl.stop)
        self.book = self.make()
        self.book.update_settings({"commission": 1, "slippage_bps": 10})

    def tearDown(self):
        self._tmp.cleanup()

    def make(self):
        return Book(self.home, quotes=self.q, clock=lambda: self.now)

    def order(self, **form):
        form.setdefault("ticker", "AAPL")
        form.setdefault("side", "buy")
        return self.book.place(form)

    def ok(self, **form):
        r = self.order(**form)
        self.assertTrue(r["ok"], r)
        return r["order"]


# --------------------------------------------------------------------------
# Market hours
# --------------------------------------------------------------------------


class TestMarketHours(unittest.TestCase):
    def test_normal_day(self):
        self.assertTrue(market_open(ny(2026, 10, 1, 9, 30)))
        self.assertTrue(market_open(ny(2026, 10, 1, 15, 59, 59)))
        self.assertEqual(next_session(ny(2026, 10, 1, 12)), date(2026, 10, 1))

    def test_before_open(self):
        self.assertFalse(market_open(ny(2026, 10, 1, 9, 29, 59)))
        self.assertEqual(next_session(ny(2026, 10, 1, 8)), date(2026, 10, 1))

    def test_after_close(self):
        self.assertFalse(market_open(ny(2026, 10, 1, 16, 0)))
        self.assertEqual(next_session(ny(2026, 10, 1, 16, 0)), date(2026, 10, 2))

    def test_weekend(self):
        self.assertFalse(market_open(SATURDAY))
        self.assertEqual(next_session(SATURDAY), date(2026, 10, 5))
        self.assertEqual(next_session(ny(2026, 10, 2, 16, 30)), date(2026, 10, 5))

    def test_holiday(self):
        self.assertFalse(market_open(ny(2026, 11, 26, 11)))  # Thanksgiving
        self.assertEqual(next_session(ny(2026, 11, 26, 11)), date(2026, 11, 27))
        self.assertEqual(next_session(ny(2026, 11, 25, 17)), date(2026, 11, 27))

    def test_half_day(self):
        self.assertTrue(market_open(ny(2026, 11, 27, 12, 59)))
        self.assertFalse(market_open(ny(2026, 11, 27, 13, 0)))
        self.assertEqual(next_session(ny(2026, 11, 27, 12)), date(2026, 11, 27))
        self.assertEqual(next_session(ny(2026, 11, 27, 13, 0)), date(2026, 11, 30))

    def test_utc_input(self):
        self.assertTrue(market_open(datetime(2026, 10, 1, 15, 0, tzinfo=UTC)))  # 11:00 New York
        self.assertFalse(market_open(datetime(2026, 10, 1, 21, 0, tzinfo=UTC)))


# --------------------------------------------------------------------------
# Fills and money
# --------------------------------------------------------------------------


class TestFills(BookCase):
    def test_market_buy(self):
        o = self.ok(qty=10)
        self.assertEqual(o["status"], "filled")
        self.assertAlmostEqual(o["fill_price"], 100.1)
        self.assertEqual(o["fee"], 1.0)
        a = self.book.acct
        self.assertAlmostEqual(a["cash"], DEFAULT_CASH - 1002.0)
        self.assertEqual(a["positions"]["AAPL"]["shares"], 10)
        self.assertAlmostEqual(a["positions"]["AAPL"]["cost"], 1002.0)
        self.assertAlmostEqual(a["fees"], 1.0)
        self.assertEqual(len(a["fills"]), 1)
        self.assertIsNone(a["fills"][0]["realized"])

    def test_sell_realized_from_average_cost_and_partial(self):
        self.ok(qty=10)
        self.q.prices["AAPL"] = 110.0
        s = self.ok(side="sell", qty=4)
        self.assertAlmostEqual(s["fill_price"], 109.89)
        proceeds = 4 * 109.89 - 1
        realized = proceeds - 1002.0 * 0.4
        a = self.book.acct
        self.assertAlmostEqual(a["realized"], realized)
        self.assertAlmostEqual(a["fills"][-1]["realized"], realized, places=5)
        self.assertEqual(a["positions"]["AAPL"]["shares"], 6)
        self.assertAlmostEqual(a["positions"]["AAPL"]["cost"], 1002.0 * 0.6)
        self.assertAlmostEqual(a["cash"], DEFAULT_CASH - 1002.0 + proceeds, places=5)
        self.ok(side="sell", qty=6)
        self.assertNotIn("AAPL", self.book.acct["positions"])
        self.assertAlmostEqual(self.book.acct["fees"], 3.0)

    def test_average_cost_over_two_buys(self):
        self.ok(qty=10)
        self.q.prices["AAPL"] = 200.0
        self.ok(qty=10)
        pos = self.book.acct["positions"]["AAPL"]
        self.assertAlmostEqual(pos["cost"], 1002.0 + 2003.0)
        snap = self.book.snapshot()
        self.assertAlmostEqual(snap["positions"][0]["avg_cost"], 3005.0 / 20)

    def test_snapshot_values(self):
        self.ok(qty=10)
        self.q.prices["AAPL"] = 110.0
        self.book.refresh()
        s = self.book.snapshot()
        self.assertAlmostEqual(s["equity"], s["cash"] + 1100.0)
        self.assertAlmostEqual(s["positions"][0]["unrealized"], 1100.0 - 1002.0)
        self.assertAlmostEqual(s["total_pl"], s["equity"] - DEFAULT_CASH)
        self.assertFalse(s["equity_unknown"])
        self.assertAlmostEqual(s["positions"][0]["day_change"], 10.0)  # prev_close is price - 1


class TestValidation(BookCase):
    def test_whole_shares_unless_fractional(self):
        r = self.order(qty=1.5)
        self.assertFalse(r["ok"])
        self.assertIn("Whole shares", r["error"])
        self.assertTrue(self.book.update_settings({"fractional": True})["ok"])
        o = self.ok(qty=0.12345678)
        self.assertEqual(o["qty"], 0.123457)
        r = self.order(qty=0.0000001)
        self.assertFalse(r["ok"])
        self.assertIn("too small", r["error"])

    def test_bad_quantities(self):
        for qty in (0, -1, float("nan"), "nan", "inf", "abc", True, False, None, 1e12, [1], {}):
            r = self.order(qty=qty)
            self.assertFalse(r["ok"], qty)
        self.assertEqual(self.book.acct["orders"], [])
        self.assertTrue(self.order(qty="2")["ok"])  # a numeric string is fine

    def test_bad_prices(self):
        for price in (0, -5, "x", None, float("inf"), True, 2e6):
            self.assertFalse(self.order(qty=1, type="limit", limit_price=price)["ok"], price)
            self.assertFalse(self.order(qty=1, type="stop", stop_price=price)["ok"], price)

    def test_bad_choices(self):
        self.assertFalse(self.order(qty=1, side="short")["ok"])
        self.assertFalse(self.order(qty=1, type="trailing")["ok"])
        self.assertFalse(self.order(qty=1, tif="ioc")["ok"])
        self.assertFalse(self.order(qty=1, side=None)["ok"])
        self.assertTrue(self.order(qty=1, side=" BUY ", type="Market", tif="GTC")["ok"])

    def test_tickers(self):
        self.assertEqual(clean_ticker(" aapl "), "AAPL")
        self.assertEqual(clean_ticker("brk.b"), "BRK.B")
        self.assertEqual(clean_ticker("ABCDEFGHIJ"), "ABCDEFGHIJ")
        for bad in ("../x", "", "   ", "ABCDEFGHIJK", ".A", "-A", "A B", "A/B", None, 5, "AAPL\nX"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                clean_ticker(bad)
        o = self.ok(ticker="aapl", qty=1)
        self.assertEqual(o["ticker"], "AAPL")
        self.assertFalse(self.order(ticker="../x", qty=1)["ok"])

    def test_unknown_symbol_and_offline(self):
        r = self.order(ticker="ZZZZ", qty=1)
        self.assertFalse(r["ok"])
        self.assertIn("no such symbol", r["error"])
        self.q.offline = True
        r = self.order(qty=1)
        self.assertFalse(r["ok"])
        self.assertIn("No price", r["error"])
        self.assertEqual(self.book.acct["orders"], [])

    def test_quote_crash_becomes_oserror(self):
        def broken(ticker):
            raise KeyError("x")
        self.book._live_quotes = broken
        with self.assertRaises(OSError):
            self.book.quote("AAPL")
        self.assertIn("KeyError", self.book.quote_errors["AAPL"])


class TestBuyingPower(BookCase):
    def test_open_buy_orders_are_reserved(self):
        self.ok(qty=10, type="limit", limit_price=90)
        reserved = 10 * 90 * 1.001 + 1
        self.assertAlmostEqual(self.book.snapshot()["buying_power"], DEFAULT_CASH - reserved)
        r = self.order(qty=999, type="limit", limit_price=100)  # 99,900 + ... > what is left
        self.assertFalse(r["ok"])
        self.assertIn("buying power", r["error"])

    def test_not_enough_cash(self):
        r = self.order(qty=1000)
        self.assertFalse(r["ok"])
        self.assertIn("Not enough buying power", r["error"])
        self.assertAlmostEqual(self.book.acct["cash"], DEFAULT_CASH)

    def test_reserved_after_restart(self):
        """An open market buy keeps its cash reserved after the program is
        restarted, before any new quote for it arrives."""
        self.now = CLOSED_THU
        self.ok(qty=500)  # about $50,000, waits for Friday
        before = self.book.snapshot()["buying_power"]
        self.assertLess(before, 50_100)
        self.book = self.make()
        self.assertAlmostEqual(self.book.snapshot()["buying_power"], before)
        r = self.order(ticker="MSFT", qty=130)  # $52,000: fits only if the $50,000 is forgotten
        self.assertFalse(r["ok"], r)

    def test_no_short_selling(self):
        r = self.order(side="sell", qty=1)
        self.assertFalse(r["ok"])
        self.assertIn("no short selling", r["error"])

    def test_cannot_oversell_with_open_sells(self):
        self.ok(qty=10)
        self.ok(side="sell", qty=6, type="limit", limit_price=200)
        r = self.order(side="sell", qty=5)
        self.assertFalse(r["ok"])
        self.assertIn("at most 4", r["error"])
        self.assertTrue(self.order(side="sell", qty=4)["ok"])


class TestOrderTypes(BookCase):
    def test_limit_buy(self):
        o = self.ok(qty=10, type="limit", limit_price=95, tif="gtc")
        self.assertEqual(o["status"], "open")
        self.q.prices["AAPL"] = 96
        self.book.refresh()
        self.assertEqual(self.book.acct["orders"][0]["status"], "open")
        self.q.prices["AAPL"] = 94.97
        self.assertEqual(self.book.refresh()["changed"], 1)
        o = self.book.acct["orders"][0]
        self.assertEqual(o["status"], "filled")
        self.assertLessEqual(o["fill_price"], 95)
        self.assertAlmostEqual(o["fill_price"], 95.0)  # 94.97 * 1.001 is above the limit: capped

    def test_limit_buy_below(self):
        o = self.ok(qty=1, type="limit", limit_price=150)  # marketable at once
        self.assertEqual(o["status"], "filled")
        self.assertAlmostEqual(o["fill_price"], 100.1)

    def test_limit_sell(self):
        self.ok(qty=10)
        o = self.ok(side="sell", qty=10, type="limit", limit_price=105)
        self.assertEqual(o["status"], "open")
        self.q.prices["AAPL"] = 105.05
        self.book.refresh()
        o = self.book.acct["orders"][-1]
        self.assertEqual(o["status"], "filled")
        self.assertGreaterEqual(o["fill_price"], 105)

    def test_stop_buy_and_sell(self):
        self.ok(qty=10)
        sell = self.ok(side="sell", qty=10, type="stop", stop_price=90)
        buy = self.ok(ticker="MSFT", qty=1, type="stop", stop_price=410)
        self.assertEqual((sell["status"], buy["status"]), ("open", "open"))
        self.q.prices.update(AAPL=95, MSFT=405)
        self.book.refresh()
        self.assertEqual([o["status"] for o in self.book.acct["orders"]], ["filled", "open", "open"])
        self.q.prices.update(AAPL=89, MSFT=412)
        self.book.refresh()
        orders = {o["id"]: o for o in self.book.acct["orders"]}
        self.assertEqual(orders[sell["id"]]["status"], "filled")
        self.assertAlmostEqual(orders[sell["id"]]["fill_price"], round(89 * 0.999, 4))
        self.assertEqual(orders[buy["id"]]["status"], "filled")
        self.assertAlmostEqual(orders[buy["id"]]["fill_price"], round(412 * 1.001, 4))


class TestMarketClosed(BookCase):
    def test_market_order_waits_then_fills(self):
        self.now = CLOSED_THU
        o = self.ok(qty=5)
        self.assertEqual(o["status"], "open")
        self.assertIn("2026-10-02", o["note"])
        self.assertEqual(o["session"], "2026-10-02")
        self.now = ny(2026, 10, 2, 9, 0)
        self.book.refresh()
        self.assertEqual(self.book.acct["orders"][0]["status"], "open")
        self.now = OPEN_FRI
        self.book.refresh()
        o = self.book.acct["orders"][0]
        self.assertEqual(o["status"], "filled")
        self.assertEqual(o["note"], "")

    def test_limit_note_when_closed(self):
        self.now = SATURDAY
        o = self.ok(qty=1, type="limit", limit_price=200)
        self.assertEqual(o["status"], "open")
        self.assertIn("checked again once it opens", o["note"])

    def test_stale_quote_at_the_open_waits(self):
        """At 9:31 Yahoo still shows last night's close: an overnight market
        order waits for a price from the new session instead of filling at it."""
        self.q.time = datetime(2026, 10, 1, 20, 0, tzinfo=UTC).isoformat()  # Thursday 16:00 NY
        self.now = CLOSED_THU
        self.ok(qty=5)
        self.now = ny(2026, 10, 2, 9, 31)
        self.book.refresh()
        self.assertEqual(self.book.acct["orders"][0]["status"], "open")
        self.q.time = datetime(2026, 10, 2, 13, 31, tzinfo=UTC).isoformat()  # Friday 9:31 NY
        self.q.prices["AAPL"] = 103.0
        self.book.refresh()
        o = self.book.acct["orders"][0]
        self.assertEqual(o["status"], "filled")
        self.assertAlmostEqual(o["fill_price"], round(103 * 1.001, 4))

    def test_day_order_expires(self):
        o = self.ok(qty=1, type="limit", limit_price=50)
        self.assertEqual(o["session"], "2026-10-01")
        self.now = ny(2026, 10, 1, 15, 59)
        self.book.refresh()
        self.assertEqual(self.book.acct["orders"][0]["status"], "open")
        self.now = ny(2026, 10, 1, 16, 0)
        self.q.prices["AAPL"] = 40  # too late: the session is over
        self.book.refresh()
        o = self.book.acct["orders"][0]
        self.assertEqual(o["status"], "expired")
        self.assertIn("session ended", o["note"])
        self.assertAlmostEqual(self.book.snapshot()["buying_power"], self.book.acct["cash"])

    def test_day_order_expires_without_a_quote(self):
        self.ok(qty=1, type="limit", limit_price=50)
        self.q.offline = True
        self.now = ny(2026, 10, 1, 16, 1)
        self.assertEqual(self.book.refresh()["changed"], 1)
        self.assertEqual(self.book.acct["orders"][0]["status"], "expired")

    def test_half_day_expiry(self):
        self.now = ny(2026, 11, 27, 12, 0)
        self.ok(qty=1, type="limit", limit_price=50)
        self.now = ny(2026, 11, 27, 13, 0)
        self.book.refresh()
        self.assertEqual(self.book.acct["orders"][0]["status"], "expired")

    def test_gtc_does_not_expire(self):
        self.ok(qty=1, type="limit", limit_price=50, tif="gtc")
        self.now = ny(2026, 10, 5, 17)
        self.book.refresh()
        self.assertEqual(self.book.acct["orders"][0]["status"], "open")
        self.now = ny(2026, 10, 6, 10)
        self.q.prices["AAPL"] = 49
        self.book.refresh()
        self.assertEqual(self.book.acct["orders"][0]["status"], "filled")

    def test_practice_fills(self):
        self.book.update_settings({"practice_fills": True})
        self.now = SATURDAY
        o = self.ok(qty=2)
        self.assertEqual(o["status"], "filled")
        self.assertIn("Practice fill", o["note"])
        self.assertTrue(self.book.snapshot()["market"]["can_fill"])

    def test_demo_prices_fill_any_time(self):
        self.book.reset({"starting_cash": 10_000, "prices": "demo"})
        self.now = SATURDAY
        o = self.ok(ticker="ANYTHING", qty=1)
        self.assertEqual(o["status"], "filled")
        self.assertEqual(o["note"], "")
        self.assertEqual(self.book.acct["fills"][0]["source"], "demo")
        self.assertEqual(self.q.calls, [])  # demo prices never ask the live source

    def test_rejected_at_fill_when_cash_ran_short(self):
        self.book.reset({"starting_cash": 10_000})
        self.now = CLOSED_THU
        a = self.ok(qty=45)
        b = self.ok(qty=45)
        self.assertEqual((a["status"], b["status"]), ("open", "open"))
        self.q.prices["AAPL"] = 120
        self.now = OPEN_FRI
        self.book.refresh()
        orders = self.book.acct["orders"]
        self.assertEqual([o["status"] for o in orders], ["filled", "rejected"])
        self.assertIn("Not enough cash", orders[1]["note"])
        self.assertGreaterEqual(self.book.acct["cash"], 0)

    def test_cancel(self):
        o = self.ok(qty=1, type="limit", limit_price=50)
        r = self.book.cancel(o["id"])
        self.assertTrue(r["ok"])
        self.assertEqual(r["order"]["status"], "cancelled")
        self.assertIn("already cancelled", self.book.cancel(o["id"])["error"])
        f = self.ok(qty=1)
        self.assertIn("already filled", self.book.cancel(f["id"])["error"])
        self.assertEqual(self.book.cancel(999)["error"], "No such order")
        self.assertEqual(self.book.cancel(True)["error"], "No such order")
        self.assertEqual(self.book.cancel("1")["error"], "No such order")


# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------


class TestPersistence(BookCase):
    def test_reload_equals(self):
        self.ok(qty=3)
        self.ok(qty=1, type="limit", limit_price=50, tif="gtc")
        self.book.watch("TSLA", True)
        again = self.make()
        self.assertEqual(again.acct, self.book.acct)
        self.assertEqual(again.notes, [])

    def test_new_account(self):
        a = self.book.acct
        self.assertEqual(a["cash"], DEFAULT_CASH)
        self.assertEqual(a["prices"], "live")
        self.assertTrue((self.home / "account.json").exists())

    def _broken(self, text):
        (self.home / "account.json").write_text(text, encoding="utf-8")
        book = self.make()
        kept = list(self.home.glob("account.corrupt-*.json"))
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].read_text(encoding="utf-8"), text)
        self.assertEqual(len(book.notes), 1)
        self.assertIn(kept[0].name, book.notes[0])
        self.assertEqual(book.acct["cash"], DEFAULT_CASH)
        return book

    def test_corrupt_json(self):
        self._broken("{not json")

    def test_invalid_schema(self):
        acct = dict(self.book.acct, schema=99)
        self._broken(json.dumps(acct))

    def test_invalid_shapes(self):
        for i, text in enumerate(("[]", "null", json.dumps(dict(self.book.acct, cash="lots")),
                                  json.dumps(dict(self.book.acct, prices="real")),
                                  json.dumps(dict(self.book.acct, positions=[])))):
            with self.subTest(i=i):
                for f in self.home.glob("account.corrupt-*.json"):
                    f.unlink()
                self._broken(text)

    def test_unknown_settings_dropped_and_missing_filled(self):
        acct = dict(self.book.acct, settings={"commission": 2, "live_money": True})
        del acct["realized"]
        (self.home / "account.json").write_text(json.dumps(acct), encoding="utf-8")
        book = self.make()
        self.assertEqual(book.acct["settings"]["commission"], 2)
        self.assertNotIn("live_money", book.acct["settings"])
        self.assertEqual(book.acct["realized"], 0.0)

    def test_reset(self):
        self.ok(qty=3)
        self.book.watch("TSLA", True)
        self.book.update_settings({"practice_fills": True})
        r = self.book.reset({"starting_cash": 5000, "prices": "demo"})
        self.assertTrue(r["ok"], r)
        kept = self.home / r["kept"]
        self.assertTrue(kept.name.startswith("account.bak-"))
        self.assertEqual(len(json.loads(kept.read_text(encoding="utf-8"))["orders"]), 1)
        a = self.book.acct
        self.assertEqual((a["cash"], a["starting_cash"], a["prices"]), (5000, 5000, "demo"))
        self.assertEqual(a["orders"], [])
        self.assertEqual(a["positions"], {})
        self.assertIn("TSLA", a["watchlist"])
        self.assertTrue(a["settings"]["practice_fills"])
        self.assertEqual(a["settings"]["commission"], 1)
        self.assertEqual(self.make().acct, a)
        r2 = self.book.reset({"starting_cash": 7000})
        self.assertNotEqual(r2["kept"], r["kept"])  # same second: a second backup, not an overwrite
        self.assertEqual(self.book.acct["prices"], "live")

    def test_reset_validation(self):
        for form in ({"starting_cash": 0}, {"starting_cash": -1}, {"starting_cash": 2e8},
                     {"starting_cash": "abc"}, {"starting_cash": True}, {"starting_cash": float("nan")},
                     {"prices": "real"}, {"prices": None}):
            r = self.book.reset(form)
            self.assertFalse(r["ok"], form)
        self.assertEqual(list(self.home.glob("account.bak-*.json")), [])
        self.assertTrue(self.book.reset({})["ok"])
        self.assertEqual(self.book.acct["cash"], DEFAULT_CASH)

    def test_trim_keeps_every_open_order(self):
        """With more open orders than KEEP_ORDERS, the old closed ones go."""
        with mock.patch.object(paper, "KEEP_ORDERS", 2):
            self.book.acct["orders"] = [
                {"id": i, "status": s} for i, s in
                enumerate(["filled", "open", "cancelled", "open", "expired"], 1)]
            self.book._trim()
            self.assertEqual([o["id"] for o in self.book.acct["orders"]], [2, 4])
            self.book.acct["orders"] = [
                {"id": i, "status": s} for i, s in enumerate(["filled", "open", "cancelled", "expired"], 1)]
            self.book._trim()
            self.assertEqual([o["id"] for o in self.book.acct["orders"]], [2, 4])


class TestSettings(BookCase):
    def test_valid(self):
        r = self.book.update_settings({"commission": "4.95", "slippage_bps": 0, "fractional": "true",
                                       "practice_fills": 1})
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["settings"], {"commission": 4.95, "slippage_bps": 0, "fractional": True,
                                         "practice_fills": True})
        self.assertEqual(self.make().acct["settings"], r["settings"])

    def test_invalid(self):
        for form in ({"commission": -1}, {"commission": 101}, {"commission": "x"}, {"commission": True},
                     {"slippage_bps": 501}, {"slippage_bps": float("nan")},
                     {"fractional": "maybe"}, {"fractional": "yes"}, {"fractional": 2},
                     {"practice_fills": None}):
            r = self.book.update_settings(form)
            self.assertFalse(r["ok"], form)
        self.assertEqual(self.book.acct["settings"]["commission"], 1)
        self.assertFalse(self.book.acct["settings"]["fractional"])

    def test_unknown_keys_ignored(self):
        r = self.book.update_settings({"live": True})
        self.assertTrue(r["ok"])
        self.assertNotIn("live", r["settings"])

    def test_fractional_off_while_holding_fractions(self):
        self.book.update_settings({"fractional": True})
        self.ok(qty=0.5)
        r = self.book.update_settings({"fractional": False})
        self.assertFalse(r["ok"])
        self.assertIn("fractional", r["error"])
        self.ok(side="sell", qty=0.5)
        self.assertTrue(self.book.update_settings({"fractional": False})["ok"])


class TestWatchlist(BookCase):
    def test_add_remove_dedupe(self):
        self.assertEqual(self.book.acct["watchlist"], ["AAPL", "MSFT", "SPY"])
        self.assertEqual(self.book.watch("msft", True)["watchlist"], ["AAPL", "MSFT", "SPY"])
        self.assertEqual(self.book.watch("tsla", True)["watchlist"], ["AAPL", "MSFT", "SPY", "TSLA"])
        self.assertEqual(self.book.watch("AAPL", False)["watchlist"], ["MSFT", "SPY", "TSLA"])
        self.assertTrue(self.book.watch("NOPE", "false")["ok"])
        self.assertEqual(self.make().acct["watchlist"], ["MSFT", "SPY", "TSLA"])

    def test_cap(self):
        for i in range(47):
            self.assertTrue(self.book.watch(f"T{i}", True)["ok"])
        self.assertEqual(len(self.book.acct["watchlist"]), 50)
        r = self.book.watch("ONE", True)
        self.assertFalse(r["ok"])
        self.assertIn("50", r["error"])
        self.assertTrue(self.book.watch("AAPL", True)["ok"])  # already there: fine

    def test_validation(self):
        self.assertFalse(self.book.watch("../x", True)["ok"])
        self.assertFalse(self.book.watch("", True)["ok"])
        self.assertFalse(self.book.watch("TSLA", "maybe")["ok"])
        self.assertNotIn("TSLA", self.book.acct["watchlist"])

    def test_unknown_watched_symbol_shows_an_error(self):
        self.book.watch("ZZZZ", True)
        self.book.refresh()
        w = {x["ticker"]: x for x in self.book.snapshot()["watchlist"]}
        self.assertIn("no such symbol", w["ZZZZ"]["error"])
        self.assertEqual(w["AAPL"]["price"], 100.0)


class TestEquityCurve(BookCase):
    def test_every_five_minutes_and_forced_on_orders(self):
        self.book.refresh()
        self.assertEqual(len(self.book.acct["equity"]), 1)
        self.now += timedelta(minutes=4)
        self.book.refresh()
        self.assertEqual(len(self.book.acct["equity"]), 1)
        self.ok(qty=1)  # forced
        self.assertEqual(len(self.book.acct["equity"]), 2)
        self.now += timedelta(minutes=4)
        self.book.refresh()
        self.assertEqual(len(self.book.acct["equity"]), 2)
        self.now += timedelta(minutes=1)
        self.book.refresh()
        self.assertEqual(len(self.book.acct["equity"]), 3)
        self.assertEqual(self.make().acct["equity"], self.book.acct["equity"])

    def test_unknown_price_records_nothing(self):
        self.ok(qty=1)
        n = len(self.book.acct["equity"])
        self.q.offline = True
        self.book = self.make()  # restarted: no quotes known
        self.now += timedelta(hours=1)
        self.book.refresh()
        s = self.book.snapshot()
        self.assertTrue(s["equity_unknown"])
        self.assertIsNone(s["positions"][0]["price"])
        self.assertEqual(len(self.book.acct["equity"]), n)
        self.assertIn("no connection", s["quote_errors"]["AAPL"])
        json.dumps(s, allow_nan=False)

    def test_snapshot_is_strict_json(self):
        self.book.update_settings({"fractional": True})
        self.ok(qty=0.333333)
        self.ok(qty=1, type="limit", limit_price=1, tif="gtc")
        self.book.refresh()
        s = self.book.snapshot()
        text = json.dumps(s, allow_nan=False)
        self.assertEqual(json.loads(text)["prices"], "live")
        for key in ("cash", "equity", "buying_power", "total_pl", "total_pl_pct", "realized", "fees"):
            self.assertTrue(math.isfinite(s[key]), key)
        self.assertEqual(len(s["open_orders"]), 1)
        self.assertEqual(s["market"], {"open": True, "next_session": "2026-10-01", "can_fill": True})


# --------------------------------------------------------------------------
# Demo prices
# --------------------------------------------------------------------------


class TestDemoQuotes(unittest.TestCase):
    def test_base_is_deterministic(self):
        self.assertEqual(DemoQuotes.base("AAPL"), DemoQuotes.base("AAPL"))
        self.assertNotEqual(DemoQuotes.base("AAPL"), DemoQuotes.base("MSFT"))
        for t in ("AAPL", "X", "ZZZZZZZZZZ", "BRK.B"):
            self.assertTrue(20 <= DemoQuotes.base(t) < 400, t)

    def test_any_symbol_and_positive_prices(self):
        now = [SATURDAY]
        state = {}
        dq = DemoQuotes(state, lambda: now[0])
        first = dq("NOTAREALONE")
        self.assertEqual(first["price"], DemoQuotes.base("NOTAREALONE"))
        self.assertEqual(first["source"], "demo")
        self.assertEqual(dq("NOTAREALONE")["price"], first["price"])  # no time passed: no move
        for _ in range(2000):
            now[0] += timedelta(days=3)
            self.assertGreater(dq("NOTAREALONE")["price"], 0)
        self.assertIn("NOTAREALONE", state)

    def test_same_path_for_same_times(self):
        def path():
            now = [SATURDAY]
            dq = DemoQuotes({}, lambda: now[0])
            out = []
            for _ in range(20):
                now[0] += timedelta(hours=7)
                out.append(dq("AAPL")["price"])
            return out
        self.assertEqual(path(), path())

    def test_persists_across_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = [SATURDAY]
            q = FakeQuotes()
            book = Book(Path(tmp), quotes=q, clock=lambda: now[0])
            book.reset({"prices": "demo"})
            p0 = book.quote("DEMO")["price"]
            now[0] += timedelta(days=5)
            book.refresh()  # DEMO is not watched: not moved
            book.watch("DEMO", True)
            with mock.patch.object(paper, "QUOTE_TTL", 0):
                book.refresh()
            p1 = book.acct["demo_state"]["DEMO"]["price"]
            again = Book(Path(tmp), quotes=q, clock=lambda: now[0])
            self.assertEqual(again.acct["demo_state"]["DEMO"]["price"], p1)
            self.assertEqual(again.quote("DEMO")["price"], p1)
            self.assertGreater(p0, 0)
            self.assertEqual(q.calls, [])


# --------------------------------------------------------------------------
# Yahoo parsing (urlopen mocked: no network)
# --------------------------------------------------------------------------


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _payload(price=187.5, **meta):
    m = {"regularMarketPrice": price, "chartPreviousClose": 185.0, "regularMarketTime": 1790000000,
         "longName": "Apple Inc.", "currency": "USD"}
    m.update(meta)
    return json.dumps({"chart": {"result": [{"meta": m}], "error": None}}).encode()


class TestYahoo(unittest.TestCase):
    def call(self, body=None, exc=None):
        def fake(req, timeout=None):
            fake.req = req
            if exc is not None:
                raise exc
            return _Resp(body)
        with mock.patch("urllib.request.urlopen", fake):
            out = yahoo_quote("AAPL")
        return out, fake.req

    def test_good(self):
        q, req = self.call(_payload())
        self.assertEqual(q["price"], 187.5)
        self.assertEqual(q["prev_close"], 185.0)
        self.assertEqual(q["name"], "Apple Inc.")
        self.assertEqual(q["source"], "yahoo")
        self.assertTrue(q["time"].endswith("+00:00"))
        self.assertIn("/v8/finance/chart/AAPL?", req.full_url)
        self.assertTrue(req.full_url.startswith("https://query1.finance.yahoo.com/"))
        headers = {k.lower(): v for k, v in req.header_items()}
        self.assertEqual(set(headers), {"user-agent"})  # nothing about the user is sent

    def test_symbol_is_url_quoted(self):
        with mock.patch("urllib.request.urlopen") as m:
            m.return_value = _Resp(_payload())
            yahoo_quote("BRK.B/../X")
        self.assertIn("/chart/BRK.B%2F..%2FX?", m.call_args[0][0].full_url)

    def test_bad_previous_close_is_dropped(self):
        q, _ = self.call(_payload(chartPreviousClose=None, previousClose=-1))
        self.assertIsNone(q["prev_close"])

    def test_chart_error(self):
        body = json.dumps({"chart": {"result": None, "error": {"code": "Not Found"}}}).encode()
        with self.assertRaises(ValueError):
            self.call(body)

    def test_http_errors(self):
        with self.assertRaises(ValueError):
            self.call(exc=urllib.error.HTTPError("u", 404, "Not Found", {}, None))
        with self.assertRaises(OSError):
            self.call(exc=urllib.error.HTTPError("u", 500, "Oops", {}, None))
        with self.assertRaises(OSError):
            self.call(exc=urllib.error.URLError("no route"))
        with self.assertRaises(OSError):
            self.call(exc=TimeoutError("slow"))

    def test_garbage(self):
        for body in (b"<html>", b"", b"\xff\xfe", b"[1, 2]", b'"text"', b'{"chart": 5}',
                     b'{"chart": {"result": {"meta": 1}}}', b'{"chart": {"result": [5]}}',
                     b'{"chart": {"result": [{"meta": [1]}]}}'):
            with self.assertRaises(OSError, msg=body):
                self.call(body)

    def test_missing_or_bad_price(self):
        for price in (None, float("nan"), 0, -3, "12", True):
            with self.assertRaises(ValueError, msg=repr(price)):
                self.call(_payload(price))
        with self.assertRaises(ValueError):
            self.call(json.dumps({"chart": {"result": [{}]}}).encode())


# --------------------------------------------------------------------------
# HTTP server
# --------------------------------------------------------------------------


class TestServer(BookCase):
    def setUp(self):
        super().setUp()
        self.srv = PaperServer(("127.0.0.1", 0), self.book)
        self.port = self.srv.server_address[1]
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        super().tearDown()

    def request(self, method, path, body=None, headers=None, host=None, raw=False):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            conn.putheader("Host", host if host is not None else f"127.0.0.1:{self.port}")
            data = b"" if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
            hdrs = {"Content-Type": "application/json"} if method == "POST" else {}
            hdrs.update(headers or {})
            for k, v in hdrs.items():
                if v is not None:
                    conn.putheader(k, v)
            if method == "POST":
                conn.putheader("Content-Length", str(len(data)))
            conn.endheaders(data if method == "POST" else None)
            r = conn.getresponse()
            payload = r.read()
            return r.status, (payload if raw else json.loads(payload or b"{}")), r.getheader("Content-Type")
        finally:
            conn.close()

    def test_page(self):
        status, body, ctype = self.request("GET", "/", raw=True)
        self.assertEqual(status, 200)
        self.assertTrue(ctype.startswith("text/html"))
        self.assertIn(b"Paper Trading", body)

    def test_missing_page_fallback(self):
        with mock.patch.object(paper, "PAGE_FILE", self.home / "nope.html"):
            status, body, _ = self.request("GET", "/index.html", raw=True)
        self.assertEqual(status, 200)
        self.assertIn(b"paper_page.html is missing", body)

    def test_forbidden_host(self):
        for host in ("evil.example", f"evil.example:{self.port}", "127.0.0.1:1", ""):
            status, body, _ = self.request("GET", "/api/account", host=host)
            self.assertEqual(status, 403, host)
        status, _, _ = self.request("GET", "/api/account", host=f"localhost:{self.port}")
        self.assertEqual(status, 200)

    def test_post_needs_json(self):
        status, body, _ = self.request("POST", "/api/refresh", body=b"{}", headers={"Content-Type": "text/plain"})
        self.assertEqual(status, 415)
        status, _, _ = self.request("POST", "/api/refresh", body=b"{}", headers={"Content-Type": None})
        self.assertEqual(status, 415)

    def test_cross_origin(self):
        status, _, _ = self.request("POST", "/api/order", body={"ticker": "AAPL", "side": "buy", "qty": 1},
                                    headers={"Origin": "https://evil.example"})
        self.assertEqual(status, 403)
        self.assertEqual(self.book.acct["orders"], [])
        status, body, _ = self.request("POST", "/api/refresh", body={},
                                       headers={"Origin": f"http://127.0.0.1:{self.port}"})
        self.assertEqual(status, 200)

    def test_bad_json(self):
        for raw in (b"{oops", b"[1]", b"\xff"):
            status, _, _ = self.request("POST", "/api/order", body=raw)
            self.assertEqual(status, 400, raw)

    def test_order_round_trip(self):
        status, r, _ = self.request("POST", "/api/order", body={"ticker": "aapl", "side": "buy", "qty": 2})
        self.assertEqual(status, 200)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["order"]["status"], "filled")
        status, snap, ctype = self.request("GET", "/api/account")
        self.assertEqual(ctype, "application/json")
        self.assertEqual(snap["positions"][0]["ticker"], "AAPL")
        self.assertEqual(snap["positions"][0]["shares"], 2)
        status, r, _ = self.request("POST", "/api/order", body={"ticker": "AAPL", "side": "buy", "qty": "x"})
        self.assertFalse(r["ok"])

    def test_cancel(self):
        _, r, _ = self.request("POST", "/api/order", body={"ticker": "AAPL", "side": "buy", "qty": 1,
                                                           "type": "limit", "limit_price": 50})
        oid = r["order"]["id"]
        for bad in ("1", 1.0, True, None):
            _, r, _ = self.request("POST", "/api/cancel", body={"id": bad})
            self.assertEqual(r, {"ok": False, "error": "id must be an order number"}, bad)
        _, r, _ = self.request("POST", "/api/cancel", body={"id": oid})
        self.assertTrue(r["ok"])
        _, r, _ = self.request("POST", "/api/cancel", body={"id": 12345})
        self.assertFalse(r["ok"])

    def test_settings_watch_reset(self):
        _, r, _ = self.request("POST", "/api/settings", body={"commission": 2})
        self.assertTrue(r["ok"])
        _, r, _ = self.request("POST", "/api/watch", body={"ticker": "tsla"})
        self.assertIn("TSLA", r["watchlist"])
        _, r, _ = self.request("POST", "/api/watch", body={"ticker": "TSLA", "add": False})
        self.assertNotIn("TSLA", r["watchlist"])
        _, r, _ = self.request("POST", "/api/reset", body={"starting_cash": 2500, "prices": "demo"})
        self.assertTrue(r["ok"])
        self.assertEqual(self.book.acct["cash"], 2500)

    def test_quote(self):
        status, r, _ = self.request("GET", "/api/quote?t=msft")
        self.assertEqual(status, 200)
        self.assertEqual(r["quote"]["price"], 400.0)
        self.assertNotIn("fetched", r["quote"])
        _, r, _ = self.request("GET", "/api/quote?t=ZZZZ")
        self.assertFalse(r["ok"])
        self.assertIn("no such symbol", r["error"])
        _, r, _ = self.request("GET", "/api/quote?t=../x")
        self.assertFalse(r["ok"])
        _, r, _ = self.request("GET", "/api/quote")
        self.assertFalse(r["ok"])
        self.q.offline = True
        _, r, _ = self.request("GET", "/api/quote?t=AAPL")
        self.assertFalse(r["ok"])
        self.assertIn("No price", r["error"])

    def test_unknown_paths(self):
        self.assertEqual(self.request("GET", "/api/nothing")[0], 404)
        self.assertEqual(self.request("GET", "/../account.json")[0], 404)
        self.assertEqual(self.request("POST", "/api/nothing", body={})[0], 404)
        self.assertEqual(self.request("GET", "/favicon.ico", raw=True)[0], 204)



class TestRefresh(BookCase):
    def test_refresh_button_skips_the_quote_cache(self):
        with mock.patch.object(paper, "QUOTE_TTL", 3600):
            self.ok(type="limit", limit_price=90, qty=1)
            self.q.prices["AAPL"] = 89.0
            self.book.refresh()  # the background check may reuse the cached 100
            self.assertEqual(self.book.acct["orders"][-1]["status"], "open")
            self.book.refresh(fresh=True)
            self.assertEqual(self.book.acct["orders"][-1]["status"], "filled")

    def test_errors_for_symbols_no_longer_followed_are_dropped(self):
        self.assertFalse(self.order(ticker="NOPE", qty=1)["ok"])
        self.assertIn("NOPE", self.book.quote_errors)
        self.book.refresh()
        self.assertNotIn("NOPE", self.book.snapshot()["quote_errors"])

    def test_bad_symbol_in_the_account_file_is_reported(self):
        self.book.acct["watchlist"].append("../x")
        self.book.refresh()
        self.assertIn("../x", self.book.snapshot()["quote_errors"])

    def test_refresh_endpoint_is_fresh(self):
        server = PaperServer(("127.0.0.1", 0), self.book)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        with mock.patch.object(self.book, "refresh", wraps=self.book.refresh) as spy:
            port = server.server_address[1]
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            conn.request("POST", "/api/refresh", body="{}",
                         headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{port}"})
            self.assertTrue(json.loads(conn.getresponse().read())["ok"])
            spy.assert_called_once_with(fresh=True)

# --------------------------------------------------------------------------
# Safety
# --------------------------------------------------------------------------


class TestSafety(unittest.TestCase):
    SRC = Path(paper.__file__).read_text(encoding="utf-8")

    def test_no_broker_code(self):
        low = self.SRC.lower()
        for word in ("alpaca", "questrade", "api_key", "apikey", "selenium", "playwright", "pyautogui"):
            self.assertNotIn(word, low)

    def test_reads_only_its_own_environment_variable(self):
        uses = re.findall(r"os\.environ[^\n]*", self.SRC)
        self.assertTrue(uses)
        for line in uses:
            self.assertIn("QT_PAPER_HOME", line)
        self.assertNotIn("getenv", self.SRC)

    def test_imports(self):
        imports = re.findall(r"^\s*(?:from|import)\s+(\S+)", self.SRC, re.M)
        for mod in imports:
            self.assertNotIn("alpaca", mod)
        # Standard library only, so the folder can be copied out on its own.
        tops = {m.split(".")[0] for m in imports}
        self.assertFalse({m for m in tops if m != "__future__" and m not in sys.stdlib_module_names})

    def test_runs_without_the_rest_of_the_project(self):
        # A fresh Python with only paper_trading/ on the path: no numpy, no quantum package.
        code = ("import sys; import paper_app; "
                "print(sorted(m for m in sys.modules if m.split('.')[0] in ('numpy', 'quantum')))")
        out = subprocess.run([sys.executable, "-c", code], cwd=Path(paper.__file__).parent,
                             capture_output=True, text=True, timeout=60, check=True)
        self.assertEqual(out.stdout.strip(), "[]")

    def test_listens_on_loopback_only(self):
        self.assertIn('PaperServer(("127.0.0.1", port), book)', self.SRC)
        self.assertNotIn("0.0.0.0", self.SRC)

    def test_env_home(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict("os.environ", {"QT_PAPER_HOME": tmp}):
            book = Book(quotes=FakeQuotes(), clock=lambda: OPEN_THU)
            self.assertEqual(book.home, Path(tmp).resolve())
            self.assertTrue((Path(tmp) / "account.json").exists())


if __name__ == "__main__":
    unittest.main()
