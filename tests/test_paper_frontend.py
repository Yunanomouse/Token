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
        expect(page.locator("#dlgCancel")).to_have_text("Keep order")
        expect(page.locator("#dlgOk")).to_have_text("Cancel order")
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
        expect(page.locator("#ticketMsg")).to_contain_text("waits for the Wed, Sep 30 session")
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


def _big_account(now=OPEN_NOW, curve=None):
    """A $100M account (the most a new account can start with) that grew to about $110M."""
    acct = new_account(now, starting_cash=100_000_000.0)
    acct["cash"] = 109_952_599.92
    acct["realized"] = 9_952_599.92
    acct["equity"] = curve if curve is not None else [
        {"t": f"2026-09-2{d}T15:00:00+00:00", "equity": 100_000_000.0 + d * 1_350_000.0} for d in range(1, 9)]
    return acct


class TestFixes(_PaperCase):
    """Bugs found by the frontend test pass; each test failed on the page before its fix."""

    def poll(self, page, quote=False):
        """Let one 5-second poll run (the clock is installed) and wait for its answers."""
        with page.expect_response(lambda r: "/api/quote" in r.url if quote else "/api/account" in r.url):
            page.clock.run_for(5200)  # the ticket's symbol is re-quoted after the account answer
        page.evaluate("new Promise(r => setTimeout(r, 0))")  # let the answer render

    # 1
    def test_reopens_on_the_portfolio_tab_from_storage_or_hash(self):
        page = self.open(tab="portfolio")
        expect(page.locator("#panel-portfolio")).to_be_visible()
        expect(page.locator("#summary")).to_contain_text("$100,000.00")
        ctx = _browser.new_context(viewport={"width": DESKTOP, "height": 900})
        self.contexts.append(ctx)
        ctx.add_init_script("try { localStorage.setItem('paper-tab', 'portfolio') } catch (e) {}")
        page2 = ctx.new_page()
        page2.on("pageerror", lambda e: self.page_errors.append(str(e)))
        page2.goto(self.url)
        expect(page2.locator("#conn")).to_have_text("connected")
        expect(page2.locator("#panel-portfolio")).to_be_visible()
        page2.click("#tab-trade")
        expect(page2.locator("#panel-trade")).to_be_visible()
        self.assert_clean()

    # 2
    def test_quote_and_estimate_follow_the_price_while_polling(self):
        page = self.open(clock=True)
        page.fill("#sym", "AAPL")
        page.click("#btnQuote")
        expect(page.locator("#quoteBox")).to_contain_text("$150.00")
        page.fill("#qty", "10")
        expect(page.locator("#estimate")).to_contain_text("Estimated cost: $1,500.30")
        self.quotes.prices["AAPL"] = 160.0
        self.poll(page, quote=True)
        expect(page.locator("#quoteBox")).to_contain_text("$160.00")
        expect(page.locator("#estimate")).to_contain_text("Estimated cost: $1,600.32")
        self.assert_clean()

    def test_a_price_move_between_review_and_place_asks_again(self):
        page = self.open()
        self.order(page, "AAPL", 10)
        expect(page.locator("#confirmDlg")).to_contain_text("$1,500.30")
        self.quotes.prices["AAPL"] = 160.0   # +6.7% while the dialog is open
        page.click("#dlgOk")
        dlg = page.locator("#confirmDlg")
        expect(dlg).to_contain_text("The price moved")
        expect(dlg).to_contain_text("was $150.00 when you reviewed the order; it is now $160.00 (+6.67%)")
        page.click("#dlgCancel")
        expect(dlg).to_be_hidden()
        self.assertEqual(self.book.acct["orders"], [])
        # Asked again at the new price, placing goes through.
        self.order(page, "AAPL", 10)
        self.quotes.prices["AAPL"] = 150.0
        page.click("#dlgOk")
        self.confirm(page, "The price moved")
        expect(page.locator("#ticketMsg")).to_contain_text("Filled: bought 10 AAPL at $150.03")
        # A small move (under 2%) does not ask.
        self.order(page, "AAPL", 1)
        self.quotes.prices["AAPL"] = 151.0
        self.confirm(page)
        expect(page.locator("#ticketMsg")).to_contain_text("Filled: bought 1 AAPL at $151.03")
        self.assert_clean()

    # 3
    def test_idle_polls_do_not_touch_live_regions(self):
        page = self.open(clock=True)
        page.fill("#sym", "AAPL")
        page.click("#btnQuote")
        expect(page.locator("#quoteBox")).to_contain_text("$150.00")
        self.poll(page, quote=True)
        page.evaluate("""() => {
            window.__mut = {};
            for (const id of ['estimate', 'conn', 'loadErr', 'quoteBox', 'notes', 'toast', 'ticketMsg', 'closedNote']) {
                window.__mut[id] = 0;
                new MutationObserver(l => { window.__mut[id] += l.length; })
                    .observe(document.getElementById(id), {childList: true, subtree: true, characterData: true, attributes: true});
            }
        }""")
        for _ in range(3):
            self.poll(page, quote=True)
        self.assertEqual(page.evaluate("window.__mut"), {k: 0 for k in
                         ("estimate", "conn", "loadErr", "quoteBox", "notes", "toast", "ticketMsg", "closedNote")})
        # Disconnected: the alert is written once, at the transition, not on every failed poll.
        self.stop_server()
        page.clock.run_for(5200)
        expect(page.locator("#conn")).to_have_text("disconnected")
        expect(page.locator("#loadErr")).to_contain_text("Cannot reach Paper Trading")
        page.evaluate("window.__mut.loadErr = 0; window.__mut.conn = 0")
        for _ in range(3):
            page.clock.run_for(5200)
            page.wait_for_timeout(200)
        self.assertEqual(page.evaluate("[window.__mut.loadErr, window.__mut.conn]"), [0, 0])
        self.assert_clean(allow=("ERR_CONNECTION_REFUSED", "Failed to fetch", "ERR_EMPTY_RESPONSE"))

    # 4
    def test_pasted_symbols_with_spaces_are_trimmed_not_cut(self):
        page = self.open()
        page.fill("#sym", "       MSFT  ")
        page.click("#btnQuote")
        expect(page.locator("#quoteBox")).to_contain_text("Microsoft Corporation")
        page.fill("#watchSym", "        tsla   ")
        page.click("#btnWatchAdd")
        expect(page.locator("#watchTable")).to_contain_text("Tesla")
        self.assertIn("TSLA", self.book.acct["watchlist"])
        self.assert_clean()

    # 7
    def test_quantity_and_prices_have_upper_limits(self):
        page = self.open()
        page.fill("#sym", "AAPL")
        err = page.locator("#ticketErr")
        for qty, otype, px, msg in (("1e21", "market", None, "at most 10,000,000"),
                                    ("10000001", "market", None, "at most 10,000,000"),
                                    ("1", "limit", "1000001", "limit price can be at most $1,000,000"),
                                    ("1", "stop", "2e9", "stop price can be at most $1,000,000")):
            page.select_option("#otype", otype)
            if otype == "limit":
                page.fill("#limitPx", px)
            if otype == "stop":
                page.fill("#stopPx", px)
            page.fill("#qty", qty)
            page.click("#btnReview")
            expect(err).to_contain_text(msg)
            expect(page.locator("#confirmDlg")).to_be_hidden()
        self.assertEqual(self.book.acct["orders"], [])
        self.assert_clean()

    # 8
    def test_choosing_another_symbol_after_sell_goes_back_to_a_market_buy(self):
        page = self.open()
        self.place(page, "TSLA", 2)
        self.tab(page, "portfolio")
        page.click('#posTable button[aria-label="Sell TSLA"]')
        expect(page.locator("#sideSell")).to_be_checked()
        page.select_option("#otype", "limit")
        page.fill("#sym", "AAPL")   # typed a different symbol
        expect(page.locator("#sideBuy")).to_be_checked()
        expect(page.locator("#otype")).to_have_value("market")
        self.tab(page, "portfolio")
        page.click('#posTable button[aria-label="Sell TSLA"]')
        expect(page.locator("#sideSell")).to_be_checked()
        page.click('#watchTable button[aria-label="Trade SPY"]')   # chosen from the watchlist
        expect(page.locator("#sym")).to_have_value("SPY")
        expect(page.locator("#sideBuy")).to_be_checked()
        expect(page.locator("#otype")).to_have_value("market")
        self.assert_clean()

    # 12
    def test_text_contrast_is_at_least_4_5_in_both_schemes(self):
        js = """() => {
          const rgb = s => { const m = s.match(/[\\d.]+/g).map(Number); return {r: m[0], g: m[1], b: m[2], a: m.length > 3 ? m[3] : 1}; };
          const lum = c => [c.r, c.g, c.b].map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); })
              .reduce((s, v, i) => s + v * [0.2126, 0.7152, 0.0722][i], 0);
          const bgOf = el => { for (; el; el = el.parentElement) { const c = rgb(getComputedStyle(el).backgroundColor); if (c.a > 0.5) return c; }
              return rgb(getComputedStyle(document.body).backgroundColor); };
          const bad = [];
          for (const el of document.querySelectorAll('body *')) {
            if (el.closest('svg, [hidden], .sr-only, :disabled')) continue;
            if (![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) continue;
            const r = el.getBoundingClientRect(); if (!r.width || !r.height) continue;
            const cs = getComputedStyle(el); if (cs.visibility === 'hidden' || +cs.opacity === 0) continue;
            const a = lum(rgb(cs.color)), b = lum(bgOf(el));
            const ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
            if (ratio < 4.5) bad.push((el.id || el.className || el.tagName) + ' "' + el.textContent.trim().slice(0, 30) + '" ' + ratio.toFixed(2));
          }
          return bad;
        }"""
        self.place(page := self.open(), "AAPL", 1)
        self.place(page, "MSFT", 1, otype="limit", price=100)
        for scheme in ("light", "dark"):
            page = self.open(scheme=scheme)
            page.fill("#sym", "AAPL")
            page.click("#btnQuote")
            expect(page.locator("#quoteBox")).to_contain_text("$150.00")
            for name in TABS:
                self.tab(page, name)
                self.assertEqual(page.evaluate(js), [], f"{scheme} {name}")
            for sel in ("#btnReview", "#watchTable button.link"):
                self.tab(page, "trade")
                self.assertEqual(page.evaluate(js.replace("document.querySelectorAll('body *')",
                                                          f"document.querySelectorAll({json.dumps(sel)})")), [])
            # the dialog's primary button
            self.tab(page, "trade")
            page.click("#btnReview")
            expect(page.locator("#confirmDlg")).to_be_visible()
            self.assertEqual(page.evaluate(js.replace("document.querySelectorAll('body *')",
                                                      "document.querySelectorAll('#confirmDlg button')")), [], scheme)
            page.click("#dlgCancel")
        self.assert_clean()

    # 13
    def test_focus_stays_on_the_page_after_cancel_and_remove(self):
        page = self.open()
        self.place(page, "AAPL", 1, otype="limit", price=100)
        self.tab(page, "orders")
        page.click('#openTable button[aria-label="Cancel order 1"]')
        self.confirm(page)
        expect(page.locator("#openTable")).to_contain_text("No open orders")
        expect(page.locator("#ordMsg")).to_be_focused()
        self.tab(page, "trade")
        page.click('#watchTable button[aria-label="Remove MSFT from the watchlist"]')
        expect(page.locator("#watchTable")).not_to_contain_text("MSFT")
        self.assertNotEqual(page.evaluate("document.activeElement.tagName"), "BODY")
        expect(page.locator("#watchHead")).to_be_focused()
        self.assert_clean()

    # 14
    def test_disconnected_time_says_et_and_footer_names_the_live_source(self):
        page = self.open(clock=True)
        expect(page.locator("footer")).to_contain_text("Live prices come from Yahoo Finance")
        self.stop_server()
        page.clock.run_for(5200)
        expect(page.locator("#loadErr")).to_contain_text(re.compile(r"last good update at \d+:\d\d:\d\d [AP]M ET"))
        self.assert_clean(allow=("ERR_CONNECTION_REFUSED", "Failed to fetch", "ERR_EMPTY_RESPONSE"))

    # 11
    def test_phone_tabs_and_row_buttons_fit_without_sideways_scroll(self):
        page = self.open(width=PHONE)
        self.place(page, "AAPL", 2)
        self.place(page, "MSFT", 1, otype="limit", price=100, tif="gtc")
        self.tab(page, "trade")

        def inside(sel):
            for i in range(page.locator(sel).count()):
                b = page.locator(sel).nth(i)
                b.scroll_into_view_if_needed()
                box = b.bounding_box()
                self.assertTrue(box and box["x"] >= 0 and box["x"] + box["width"] <= PHONE,
                                f"{sel} #{i} at {box} in a {PHONE}px window")
                self.assertEqual(b.evaluate("el => (el.closest('.tablewrap') || {scrollLeft: 0}).scrollLeft"), 0)
        inside("#tablist button")
        inside("#watchTable button.small")
        self.tab(page, "portfolio")
        inside("#posTable button")
        self.tab(page, "orders")
        inside("#openTable button")
        # order times stay on one line
        lh = page.evaluate("parseFloat(getComputedStyle(document.querySelector('#histTable td.time')).lineHeight)")
        for i in range(page.locator("#histTable td.time").count()):
            self.assertLess(page.locator("#histTable td.time").nth(i).evaluate("el => el.getBoundingClientRect().height"), 2 * lh + 13)
        self.assert_no_hscroll(page)
        self.assert_clean()

    # 16
    def test_bad_hand_edited_times_show_a_dash(self):
        acct = self.book.acct
        self.place(page := self.open(), "AAPL", 1, otype="limit", price=100)
        self.book.acct["orders"][0]["created"] = "Dec 31, 7:00 PM ET"
        acct["fills"].append({"order_id": 9, "ticker": "AAPL", "side": "buy", "qty": 1.0, "price": 1.0, "fee": 0.0,
                              "time": "yesterday", "realized": None, "source": "yahoo"})
        page.reload()
        self.tab(page, "orders")
        row = page.locator("#openTable tbody tr").first
        expect(row).to_contain_text("AAPL")
        expect(row).not_to_contain_text("Dec 31")
        self.assertEqual(row.locator("td").nth(1).inner_text(), "–")
        self.tab(page, "activity")
        self.assertEqual(page.locator("#fillTable tbody tr td").first.inner_text(), "–")
        self.assert_clean()


class TestDemoWording(_PaperCase):

    def seed(self, home):
        (home / "account.json").write_text(json.dumps(new_account(OPEN_NOW, prices="demo")), encoding="utf-8")

    # 14
    def test_demo_quote_and_footer(self):
        page = self.open()
        page.fill("#sym", "AAPL")
        page.click("#btnQuote")
        qn = page.locator("#quoteBox .qn")
        expect(qn).to_have_text("AAPL · demo price")
        foot = page.locator("footer")
        expect(foot).to_contain_text("demo prices")
        expect(foot).not_to_contain_text("Yahoo")
        self.assert_clean()


class TestBigAccount(_PaperCase):

    def seed(self, home):
        (home / "account.json").write_text(json.dumps(_big_account()), encoding="utf-8")

    # 5
    def test_summary_figures_stay_on_one_line(self):
        for width in (DESKTOP, PHONE):
            page = self.open(width=width)
            expect(page.locator("#summary")).to_contain_text("$109,952,599.92")
            vals = page.evaluate("""() => [...document.querySelectorAll('#summary .tile .value')].map(el => {
                const cs = getComputedStyle(el);
                return [el.textContent, el.getBoundingClientRect().height, parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.45,
                        el.scrollWidth, el.clientWidth]; })""")
            for text, height, line, sw, cw in vals:
                self.assertLess(height, line * 1.5, f"{text!r} wraps at {width}px")
                self.assertLessEqual(sw, cw, f"{text!r} is cut off at {width}px")
            self.assert_no_hscroll(page)
        self.assert_clean()

    # 6
    def test_chart_labels_fit_inside_the_chart(self):
        for width in (DESKTOP, PHONE):
            page = self.open(width=width)
            self.tab(page, "portfolio")
            expect(page.locator("#eqChart svg")).to_be_visible()
            out = page.evaluate("""() => { const s = document.querySelector('#eqChart svg').getBoundingClientRect();
                return [...document.querySelectorAll('#eqChart text')].map(t => [t.textContent, t.getBoundingClientRect().left - s.left,
                    s.right - t.getBoundingClientRect().right]).filter(x => x[1] < 0 || x[2] < 0); }""")
            self.assertEqual(out, [], f"labels outside the chart at {width}px")
            labels = page.evaluate("[...document.querySelectorAll('#eqChart text')].map(t => t.textContent)")
            self.assertTrue(any(re.fullmatch(r"\$1\d\d\.\d+M", t) for t in labels), labels)
        self.assert_clean()


class TestAbsurdCurve(_PaperCase):

    def seed(self, home):
        curve = [{"t": "2026-09-21T15:00:00+00:00", "equity": 100_000.0},
                 {"t": "2026-09-22T15:00:00+00:00", "equity": 1e308},
                 {"t": "Dec 31, 7:00 PM ET", "equity": 100_500.0},
                 {"t": "2026-09-23T15:00:00+00:00", "equity": 101_000.0}]
        acct = new_account(OPEN_NOW)
        acct["equity"] = curve
        (home / "account.json").write_text(json.dumps(acct), encoding="utf-8")

    # 16
    def test_absurd_points_are_skipped(self):
        page = self.open()
        self.tab(page, "portfolio")
        svg = page.locator("#eqChart svg")
        expect(svg).to_be_visible()
        paths = page.evaluate("[...document.querySelectorAll('#eqChart path, #eqChart circle, #eqChart line')]"
                              ".map(e => e.outerHTML).join(' ')")
        self.assertNotIn("Infinity", paths)
        self.assertNotIn("NaN", paths)
        self.assertNotIn("e+308", svg.get_attribute("aria-label"))
        self.assertTrue(page.locator("#eqChart path").count() >= 2)
        self.assert_clean()


class TestLongHistory(_PaperCase):

    def seed(self, home):
        acct = new_account(OPEN_NOW)
        for i in range(1, 306):
            acct["orders"].append({"id": i, "ticker": "AAPL", "side": "buy", "type": "market", "tif": "day", "qty": 1.0,
                                   "limit_price": None, "stop_price": None, "status": "cancelled",
                                   "created": "2026-09-28T15:00:00+00:00", "session": "2026-09-28",
                                   "quote_at_entry": 100.0, "filled_at": None, "fill_price": None, "fee": None, "note": ""})
            acct["fills"].append({"order_id": i, "ticker": "AAPL", "side": "buy", "qty": 1.0, "price": 1.0, "fee": 0.0,
                                  "time": "2026-09-28T15:00:00+00:00", "realized": None, "source": "yahoo"})
        acct["next_id"] = 306
        (home / "account.json").write_text(json.dumps(acct), encoding="utf-8")

    # 10
    def test_cut_lists_say_how_many_there_are(self):
        page = self.open()
        self.tab(page, "orders")
        expect(page.locator("#histTable tbody tr")).to_have_count(300)
        expect(page.locator("#histMore")).to_have_text("Showing the latest 300 of 305 orders.")
        self.tab(page, "activity")
        expect(page.locator("#fillMore")).to_have_text("Showing the latest 300 of 305 fills.")
        self.assert_clean()


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
