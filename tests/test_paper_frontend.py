"""Browser tests for the Paper Trading page (``paper_trading/paper_page.html``).

A real ``PaperServer`` runs in a thread on a temporary account folder with
an injected clock and a fake quotes function, so nothing leaves the
machine: every request the page makes to anything but the local server is
answered by the test and recorded as a failure.

The module is skipped when Playwright is not installed or no Chromium can be
launched (as tests/test_frontend.py).
"""

import json
import os
import re
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:  # the module is skipped below
    expect = sync_playwright = None

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "paper_trading"))
import paper_app as paper  # noqa: E402
from paper_app import Book, PaperServer, new_account

LOCAL_CHROMIUM = "/opt/pw-browsers/chromium"
SCRATCH = os.environ.get("PAPER_SCREENSHOTS")  # a folder for screenshots, when set
XSS_IMG = '<img src=x onerror="window.__xss=1">'
XSS_SCRIPT = '</script><script>window.__xss=1</script>'
DESKTOP, PHONE = 1300, 390
WAIT = 10_000
OPEN_NOW = datetime(2026, 9, 29, 15, 0, tzinfo=timezone.utc)     # Tue 11:00 New York
CLOSED_NOW = datetime(2026, 9, 29, 22, 0, tzinfo=timezone.utc)   # Tue 18:00 New York
TABS = ["trade", "portfolio", "orders", "activity", "settings"]

_pw = None
_browser = None


def setUpModule():  # noqa: N802
    global _pw, _browser
    if sync_playwright is None:
        raise unittest.SkipTest("playwright is not installed (pip install playwright)")
    try:
        _pw = sync_playwright().start()
    except Exception as exc:
        raise unittest.SkipTest(f"playwright could not start: {exc}")
    try:
        kw = {"executable_path": LOCAL_CHROMIUM} if os.path.exists(LOCAL_CHROMIUM) else {}
        _browser = _pw.chromium.launch(**kw)
    except Exception as exc:
        _pw.stop()
        _pw = None
        raise unittest.SkipTest(f"no Chromium could be launched ({type(exc).__name__}); "
                                "run: python -m playwright install --with-deps chromium")


def tearDownModule():  # noqa: N802
    if _browser is not None:
        _browser.close()
    if _pw is not None:
        _pw.stop()


class FakeQuotes:
    """Stands in for Yahoo: mutable prices, ValueError for unknown symbols."""

    def __init__(self):
        self.prices = {"AAPL": 150.0, "MSFT": 400.0, "SPY": 500.0, "TSLA": 200.0}
        self.names = {"AAPL": "Apple Inc.", "MSFT": "Microsoft Corporation", "SPY": "SPDR S&P 500", "TSLA": "Tesla"}
        self.errors = {}  # ticker -> message raised as ValueError

    def __call__(self, ticker):
        if ticker in self.errors:
            raise ValueError(self.errors[ticker])
        if ticker not in self.prices:
            raise ValueError(f"{ticker}: no such symbol")
        p = self.prices[ticker]
        return {"ticker": ticker, "price": p, "prev_close": round(p / 1.02, 2), "time": "2026-09-29T14:59:00+00:00",
                "name": self.names.get(ticker, ""), "currency": "USD", "source": "yahoo"}


class _PaperCase(unittest.TestCase):
    now = OPEN_NOW

    def seed(self, home):
        """Write files into the account folder before the Book opens it."""

    def setUp(self):
        self.contexts, self.console_errors, self.page_errors, self.external = [], [], [], []
        ttl = mock.patch.object(paper, "QUOTE_TTL", 0.0)  # a price move shows at the next refresh
        ttl.start()
        self.addCleanup(ttl.stop)
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name) / "paper"
        self.home.mkdir()
        self.seed(self.home)
        self.quotes = FakeQuotes()
        self.book = Book(self.home, quotes=self.quotes, clock=lambda: self.now)
        self.srv = PaperServer(("127.0.0.1", 0), self.book)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}/"
        self._served = True

    def stop_server(self):
        if self._served:
            self._served = False
            self.srv.shutdown()
            self.srv.server_close()

    def tearDown(self):
        for ctx in self.contexts:
            try:
                ctx.close()
            except Exception:
                pass
        self.stop_server()
        self._tmp.cleanup()
        self.assertEqual(self.external, [], "requests that tried to leave the machine")

    def open(self, scheme="light", width=DESKTOP, clock=False, tab=None):
        ctx = _browser.new_context(color_scheme=scheme, viewport={"width": width, "height": 900})
        self.contexts.append(ctx)

        def route(r):
            u = r.request.url
            if u.startswith(("data:", "blob:", "http://127.0.0.1:", "http://localhost:")):
                r.continue_()
            else:
                self.external.append(u)
                r.fulfill(status=200, body="")
        ctx.route("**/*", route)
        page = ctx.new_page()
        page.set_default_timeout(WAIT)
        page.on("console", lambda m: m.type == "error" and self.console_errors.append(m.text))
        page.on("pageerror", lambda e: self.page_errors.append(str(e)))
        if clock:
            page.clock.install()
        page.goto(self.url + (f"#{tab}" if tab else ""))
        expect(page.locator("#conn")).to_have_text("connected")
        return page

    def assert_clean(self, allow=()):
        errors = [e for e in self.console_errors if not any(a in e for a in allow)]
        self.assertEqual(errors, [], "console errors")
        self.assertEqual(self.page_errors, [], "uncaught page errors")

    def assert_no_hscroll(self, page):
        sw, iw = page.evaluate("[Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),"
                               " window.innerWidth]")
        self.assertLessEqual(sw, iw, f"page is {sw}px wide in a {iw}px window")

    @staticmethod
    def tab(page, name):
        page.click(f"#tab-{name}")
        expect(page.locator(f"#panel-{name}")).to_be_visible()

    @staticmethod
    def confirm(page, expect_text=None):
        dlg = page.locator("#confirmDlg")
        expect(dlg).to_be_visible()
        if expect_text:
            expect(dlg).to_contain_text(expect_text)
        page.click("#dlgOk")
        expect(dlg).to_be_hidden()

    def order(self, page, sym, qty, side="buy", otype="market", price=None, tif="day", quote=True):
        self.tab(page, "trade")
        page.fill("#sym", sym)
        if quote:
            page.click("#btnQuote")
            expect(page.locator("#quoteBox")).to_contain_text(sym)
        page.check("#sideSell" if side == "sell" else "#sideBuy")
        page.select_option("#otype", otype)
        if otype == "limit":
            page.fill("#limitPx", str(price))
        elif otype == "stop":
            page.fill("#stopPx", str(price))
        page.fill("#qty", str(qty))
        page.select_option("#tif", tif)
        page.click("#btnReview")

    def place(self, page, *args, **kw):
        self.order(page, *args, **kw)
        self.confirm(page)


class TestPaperPage(_PaperCase):

    def test_loads_clean_in_both_schemes_and_widths_with_the_banner_on_every_tab(self):
        for scheme in ("light", "dark"):
            for width in (DESKTOP, PHONE):
                page = self.open(scheme=scheme, width=width)
                self.assertEqual(page.title(), "Paper Trading")
                expect(page.locator("#mktBadge")).to_have_text("Open")
                expect(page.locator("#watchTable")).to_contain_text("Apple Inc.")
                expect(page.locator("#summary")).to_contain_text("$100,000.00")
                for name in TABS:
                    self.tab(page, name)
                    banner = page.locator("#banner")
                    expect(banner).to_be_visible()
                    expect(banner).to_contain_text("PAPER TRADING — pretend money. No broker is connected.")
                    expect(page.locator("#demoTag")).to_be_hidden()
                    self.assert_no_hscroll(page)
                bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
                self.assertEqual(bg, "rgb(18, 18, 17)" if scheme == "dark" else "rgb(244, 244, 242)")
        self.assert_clean()

    def test_tabs_follow_the_keyboard(self):
        page = self.open()
        page.focus("#tab-trade")
        page.keyboard.press("ArrowRight")
        expect(page.locator("#panel-portfolio")).to_be_visible()
        expect(page.locator("#tab-portfolio")).to_be_focused()
        page.keyboard.press("End")
        expect(page.locator("#panel-settings")).to_be_visible()
        page.keyboard.press("ArrowRight")
        expect(page.locator("#panel-trade")).to_be_visible()
        expect(page.locator("#tab-trade")).to_have_attribute("aria-selected", "true")
        self.assert_clean()

    def test_quote_then_market_buy_updates_summary_positions_and_activity(self):
        page = self.open()
        page.fill("#sym", "aapl")
        page.click("#btnQuote")
        box = page.locator("#quoteBox")
        expect(box).to_contain_text("Apple Inc.")
        expect(box).to_contain_text("$150.00")
        expect(box).to_contain_text("+$2.94")   # vs prev close 147.06
        page.fill("#qty", "10")
        est = page.locator("#estimate")
        expect(est).to_contain_text("Estimated cost: $1,500.30")  # 10 x 150 + 2 bps slippage
        page.click("#btnReview")
        self.confirm(page, "Buy 10 AAPL")
        msg = page.locator("#ticketMsg")
        expect(msg).to_contain_text("Filled: bought 10 AAPL at $150.03")
        summary = page.locator("#summary")
        expect(summary).to_contain_text("$98,499.70")    # cash
        expect(summary).to_contain_text("−$0.30")       # total P/L: the slippage, with a minus sign
        self.tab(page, "portfolio")
        pos = page.locator("#posTable")
        expect(pos).to_contain_text("AAPL")
        expect(pos).to_contain_text("$1,500.00")
        expect(page.locator("#eqChart svg")).to_have_attribute("aria-label", re.compile("starting balance \\$100,000"))
        self.tab(page, "activity")
        expect(page.locator("#fillTable")).to_contain_text("$150.03")
        self.tab(page, "orders")
        expect(page.locator("#histTable")).to_contain_text("filled")
        self.assert_clean()

    def test_rejections_show_the_error(self):
        page = self.open()
        self.order(page, "AAPL", 1000)
        self.confirm(page)
        err = page.locator("#ticketErr")
        expect(err).to_contain_text("Not enough buying power")
        self.assertEqual(err.get_attribute("role"), "alert")
        self.order(page, "MSFT", 5, side="sell")
        self.confirm(page)
        expect(err).to_contain_text("You can sell at most 0 MSFT")
        self.order(page, "NOPE", 1, quote=False)
        self.confirm(page)
        expect(err).to_contain_text("NOPE: no such symbol")
        expect(page.locator("#notes")).to_be_hidden()  # a typo leaves no lasting warning
        # Cancelling the dialog places nothing.
        self.order(page, "AAPL", 1)
        page.click("#dlgCancel")
        expect(page.locator("#confirmDlg")).to_be_hidden()
        self.assertEqual(self.book.acct["orders"], [])
        self.assert_clean()

    def test_sell_button_prefills_the_ticket_and_sells(self):
        page = self.open()
        self.place(page, "TSLA", 4)
        expect(page.locator("#ticketMsg")).to_contain_text("Filled")
        self.tab(page, "portfolio")
        page.click('#posTable button[aria-label="Sell TSLA"]')
        expect(page.locator("#panel-trade")).to_be_visible()
        expect(page.locator("#sym")).to_have_value("TSLA")
        expect(page.locator("#qty")).to_have_value("4")
        expect(page.locator("#sideSell")).to_be_checked()
        expect(page.locator("#estimate")).to_contain_text("Estimated proceeds")
        page.click("#btnReview")
        self.confirm(page, "Sell 4 TSLA")
        expect(page.locator("#ticketMsg")).to_contain_text("Filled: sold 4 TSLA")
        self.tab(page, "activity")
        expect(page.locator("#fillTable")).to_contain_text("−$0.32")  # realized: two slippages
        self.assert_clean()

    def test_limit_orders_wait_cancel_and_fill_after_a_price_move(self):
        page = self.open()
        self.order(page, "AAPL", 5, otype="limit", price=100)
        expect(page.locator("#limitRow")).to_be_visible()
        expect(page.locator("#stopRow")).to_be_hidden()
        self.confirm(page, "Limit at $100.00")
        expect(page.locator("#ticketMsg")).to_contain_text("waiting")
        self.tab(page, "orders")
        open_t = page.locator("#openTable")
        expect(open_t).to_contain_text("limit $100.00")
        page.click('#openTable button[aria-label="Cancel order 1"]')
        expect(page.locator("#confirmDlg")).to_contain_text("Cancel order #1?")
        page.click("#dlgCancel")  # changing one's mind keeps it
        expect(open_t).to_contain_text("limit $100.00")
        page.click('#openTable button[aria-label="Cancel order 1"]')
        self.confirm(page)
        expect(page.locator("#ordMsg")).to_contain_text("Order #1 cancelled")
        expect(open_t).to_contain_text("No open orders")
        expect(page.locator("#histTable")).to_contain_text("cancelled")

        self.order(page, "AAPL", 5, otype="limit", price=140, tif="gtc")
        self.confirm(page)
        expect(page.locator("#ticketMsg")).to_contain_text("Order #2 placed and waiting")
        self.quotes.prices["AAPL"] = 139.0
        page.click("#btnRefresh")
        self.tab(page, "orders")
        expect(open_t).to_contain_text("No open orders")
        expect(page.locator("#histTable tbody tr").first).to_contain_text("filled")
        expect(page.locator("#histTable tbody tr").first).to_contain_text("$139.0278")
        self.assert_clean()

    def test_stop_field_shows_only_for_stop_orders(self):
        page = self.open()
        page.select_option("#otype", "stop")
        expect(page.locator("#stopRow")).to_be_visible()
        expect(page.locator("#limitRow")).to_be_hidden()
        page.select_option("#otype", "market")
        expect(page.locator("#stopRow")).to_be_hidden()
        page.fill("#sym", "AAPL")
        page.fill("#qty", "")
        page.click("#btnReview")
        expect(page.locator("#ticketErr")).to_contain_text("how many shares")
        page.fill("#qty", "1.5")
        page.click("#btnReview")
        expect(page.locator("#ticketErr")).to_contain_text("Whole shares only")
        self.assert_clean()

    def test_watchlist_add_remove_and_click_to_trade(self):
        page = self.open()
        watch = page.locator("#watchTable")
        expect(watch).to_contain_text("MSFT")
        page.fill("#watchSym", "tsla")
        page.click("#btnWatchAdd")
        expect(watch).to_contain_text("Tesla")
        expect(watch).to_contain_text("$200.00")
        self.assertIn("TSLA", self.book.acct["watchlist"])
        page.fill("#watchSym", "bad sym!")
        page.click("#btnWatchAdd")
        expect(page.locator("#watchErr")).to_contain_text("Enter a stock symbol")
        page.click('#watchTable button[aria-label="Remove MSFT from the watchlist"]')
        expect(watch).not_to_contain_text("MSFT")
        page.click('#watchTable button[aria-label="Trade SPY"]')
        expect(page.locator("#sym")).to_have_value("SPY")
        expect(page.locator("#quoteBox")).to_contain_text("SPDR S&P 500")
        self.assert_clean()

    def test_new_demo_account_with_40_dollars(self):
        page = self.open()
        self.tab(page, "settings")
        page.fill("#newCash", "40")
        page.check("#pricesDemo")
        page.click("#btnReset")
        self.confirm(page, "kept as a backup file")
        expect(page.locator("#resetMsg")).to_contain_text("account.bak-")
        expect(page.locator("#demoTag")).to_be_visible()
        expect(page.locator("#banner")).to_contain_text("DEMO PRICES (made up)")
        expect(page.locator("#mktBadge")).to_have_text("Demo: always open")
        expect(page.locator("#summary")).to_contain_text("$40.00")
        self.assertTrue(list(self.home.glob("account.bak-*.json")))
        # $40 can't buy a $67.70 demo AAPL share, but a demo buy of a cheaper
        # made-up stock fills at once.
        self.place(page, "AAPL", 1)
        expect(page.locator("#ticketErr")).to_contain_text("Not enough buying power")
        self.place(page, "BT", 1)  # DemoQuotes.base("BT") is under $35
        expect(page.locator("#ticketMsg")).to_contain_text("Filled: bought 1 BT")
        self.assert_clean()

    def test_settings_save_and_bad_values(self):
        page = self.open()
        self.tab(page, "settings")
        page.fill("#setCommission", "1.5")
        page.check("#setFractional")
        page.click("#btnSaveSettings")
        expect(page.locator("#setMsg")).to_contain_text("Settings saved")
        self.assertEqual(self.book.acct["settings"]["commission"], 1.5)
        self.assertTrue(self.book.acct["settings"]["fractional"])
        page.fill("#setSlip", "900")
        page.click("#btnSaveSettings")
        expect(page.locator("#setErr")).to_contain_text("between 0 and 500")
        self.tab(page, "trade")
        expect(page.locator("#qtyHint")).to_contain_text("Fractional shares allowed")
        self.place(page, "AAPL", 0.5)
        expect(page.locator("#ticketMsg")).to_contain_text("bought 0.5 AAPL")
        expect(page.locator("#ticketMsg")).to_contain_text("commission $1.50")
        self.assert_clean()


class TestClosedMarket(_PaperCase):
    now = CLOSED_NOW

    def test_market_order_waits_then_practice_fills_change_it(self):
        page = self.open()
        expect(page.locator("#mktBadge")).to_have_text("Closed — next session Wed, Sep 30")
        expect(page.locator("#closedNote")).to_contain_text("Market orders wait for the next session")
        expect(page.locator("#practiceBadge")).to_be_hidden()
        self.order(page, "AAPL", 2)
        self.confirm(page, "waits for the Wed, Sep 30 session")
        expect(page.locator("#ticketMsg")).to_contain_text("waits for the 2026-09-30 session")
        self.tab(page, "orders")
        expect(page.locator("#openTable")).to_contain_text("AAPL")

        self.tab(page, "settings")
        expect(page.locator("#panel-settings")).to_contain_text("not realistic, for trying the program")
        page.check("#setPractice")
        page.click("#btnSaveSettings")
        expect(page.locator("#setMsg")).to_contain_text("Settings saved")
        expect(page.locator("#practiceBadge")).to_be_visible()
        self.tab(page, "trade")
        expect(page.locator("#closedNote")).to_contain_text("practice fills are ON")
        self.place(page, "MSFT", 1)
        expect(page.locator("#ticketMsg")).to_contain_text("Filled: bought 1 MSFT")
        expect(page.locator("#ticketMsg")).to_contain_text("Practice fill")
        self.assert_clean()


class TestHostileData(_PaperCase):

    def seed(self, home):
        acct = new_account(OPEN_NOW)
        acct["watchlist"] = ["AAPL", "BAD"]
        acct["positions"] = {"GONE": {"shares": 3.0, "cost": 300.0}}
        acct["cash"] = 99_700.0
        acct["orders"] = [{"id": 1, "ticker": "GONE", "side": "buy", "type": "market", "tif": "day", "qty": 3.0,
                           "limit_price": None, "stop_price": None, "status": "filled",
                           "created": "2026-09-28T15:00:00+00:00", "session": "2026-09-28",
                           "quote_at_entry": 100.0, "filled_at": "2026-09-28T15:00:00+00:00",
                           "fill_price": 100.0, "fee": 0.0, "note": XSS_SCRIPT}]
        acct["next_id"] = 2
        (home / "account.json").write_text(json.dumps(acct), encoding="utf-8")

    def setUp(self):
        super().setUp()
        self.book.notes.append(XSS_IMG)
        self.quotes.names["AAPL"] = XSS_IMG
        self.quotes.errors["BAD"] = XSS_SCRIPT
        self.quotes.errors["GONE"] = "GONE: no such symbol"

    def test_payloads_stay_text_and_unknown_price_gives_approx_equity(self):
        page = self.open()
        notes = page.locator("#notes")
        expect(notes).to_contain_text(XSS_IMG)
        expect(notes).to_contain_text("No price for GONE")
        expect(page.locator("#watchTable")).to_contain_text("no price: " + XSS_SCRIPT)
        expect(page.locator("#watchTable")).to_contain_text(XSS_IMG)
        page.click('#watchTable button[aria-label="Trade AAPL"]')
        expect(page.locator("#quoteBox")).to_contain_text(XSS_IMG)
        summary = page.locator("#summary")
        expect(summary).to_contain_text("Equity (approx.)")
        expect(summary).to_contain_text("≈ $100,000.00")
        expect(summary).to_contain_text("no price yet for GONE")
        self.tab(page, "portfolio")
        expect(page.locator("#posTable")).to_contain_text("no price")
        self.tab(page, "orders")
        expect(page.locator("#histTable")).to_contain_text(XSS_SCRIPT)
        self.assertIsNone(page.evaluate("window.__xss"))
        self.assertEqual(page.locator("img").count(), 0)
        self.assert_clean()


class TestDisconnected(_PaperCase):

    def test_unreachable_server_warns_and_keeps_the_last_data(self):
        page = self.open(clock=True)
        expect(page.locator("#summary")).to_contain_text("$100,000.00")
        self.stop_server()
        page.clock.run_for(5200)
        expect(page.locator("#conn")).to_have_text("disconnected")
        err = page.locator("#loadErr")
        expect(err).to_be_visible()
        expect(err).to_contain_text("Cannot reach Paper Trading")
        expect(err).to_contain_text("last good update")
        expect(page.locator("#summary")).to_contain_text("$100,000.00")
        page.click("#btnRefresh")
        expect(page.locator("#toast")).to_contain_text("could not reach Paper Trading")
        self.assert_clean(allow=("ERR_CONNECTION_REFUSED", "Failed to fetch", "ERR_EMPTY_RESPONSE"))


@unittest.skipUnless(SCRATCH, "set PAPER_SCREENSHOTS to a folder to save screenshots")
class TestScreenshots(_PaperCase):

    def test_screenshots(self):
        for width, name in ((DESKTOP, "paper_desktop.png"), (PHONE, "paper_phone.png")):
            page = self.open(width=width)
            if not self.book.acct["fills"]:
                self.place(page, "AAPL", 10)
                self.place(page, "MSFT", 3)
                self.place(page, "SPY", 2, otype="limit", price=480, tif="gtc")
                self.quotes.prices["AAPL"] = 156.0
                page.click("#btnRefresh")
            page.fill("#sym", "AAPL")
            page.click("#btnQuote")
            page.fill("#qty", "5")
            expect(page.locator("#quoteBox")).to_contain_text("$156.00")
            page.screenshot(path=str(Path(SCRATCH) / name), full_page=True)
            page.evaluate("window.scrollTo(0, 0)")
            page.screenshot(path=str(Path(SCRATCH) / name.replace(".png", "_top.png")))
            self.tab(page, "portfolio")
            page.screenshot(path=str(Path(SCRATCH) / name.replace(".png", "_portfolio.png")), full_page=True)


if __name__ == "__main__":
    unittest.main()
