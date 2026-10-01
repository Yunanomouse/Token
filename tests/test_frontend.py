"""Browser tests for the three dashboards (Playwright, headless Chromium).

* Quantum Station: ``quantum/local_page.html`` served by ``quantum.local``.
* The desktop replay dashboard: the page embedded in ``quantum/desktop.py``.
* The static page ``web/quantum-trading.html`` opened from a file:// URL.

Everything is local and deterministic: the station runs on a temporary home
with an injected clock, its jobs never start a process (``Station._cmd`` is
mocked), its data is seeded as JSON files, and every request that would
leave the machine (the static page's web fonts) is answered with an empty
body by the test, never sent.

The whole module is skipped when Playwright is not installed or no Chromium
can be launched, so ``pytest tests`` passes on machines without a browser.
In CI: ``pip install playwright && python -m playwright install --with-deps
chromium``.
"""

import json
import math
import os
import re
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:  # the module is skipped below
    expect = sync_playwright = None

from quantum.desktop import serve as desktop_serve
from quantum.local import Station, StationServer

ROOT = Path(__file__).resolve().parents[1]
WEB_PAGE = ROOT / "web" / "quantum-trading.html"
NY = ZoneInfo("America/New_York")
LOCAL_CHROMIUM = "/opt/pw-browsers/chromium"  # a pre-installed browser, used when present

XSS_IMG = '<img src=x onerror="window.__xss=1">'
XSS_SCRIPT = '</script><script>window.__xss=1</script>'
DESKTOP, PHONE = 1300, 390
WAIT = 10_000  # ms, for anything that waits on a poll

_pw = None
_browser = None


def setUpModule():  # noqa: N802
    global _pw, _browser
    if sync_playwright is None:
        raise unittest.SkipTest("playwright is not installed (pip install playwright)")
    try:
        _pw = sync_playwright().start()
    except Exception as exc:  # e.g. a running asyncio loop, missing driver
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


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------


class _PageCase(unittest.TestCase):
    """Opens pages in fresh browser contexts and records every console error,
    uncaught page error and request that tried to leave the machine."""

    def setUp(self):
        self.contexts = []
        self.console_errors = []
        self.page_errors = []
        self.external = []

    def tearDown(self):
        for ctx in self.contexts:
            try:
                ctx.close()
            except Exception:
                pass

    def open(self, url, scheme="light", width=DESKTOP, init_script=None, clock=False, wait_for=None):
        ctx = _browser.new_context(color_scheme=scheme, viewport={"width": width, "height": 900})
        self.contexts.append(ctx)

        def route(r):
            u = r.request.url
            if u.startswith(("file:", "data:", "blob:", "http://127.0.0.1:", "http://localhost:")):
                r.continue_()
            else:  # never reach the network: answer locally, record it
                self.external.append(u)
                r.fulfill(status=200, body="", content_type="text/css" if "css" in u else "application/octet-stream")
        ctx.route("**/*", route)
        page = ctx.new_page()
        page.set_default_timeout(WAIT)
        page.on("console", lambda m: m.type == "error" and self.console_errors.append(m.text))
        page.on("pageerror", lambda e: self.page_errors.append(str(e)))
        if init_script:
            page.add_init_script(init_script)
        if clock:
            page.clock.install()
        page.goto(url)
        if wait_for:
            wait_for(page)
        return page

    def assert_clean(self, allow=()):
        errors = [e for e in self.console_errors if not any(a in e for a in allow)]
        self.assertEqual(errors, [], "console errors")
        self.assertEqual(self.page_errors, [], "uncaught page errors")

    def assert_no_hscroll(self, page):
        sw, iw = page.evaluate("[Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),"
                               " window.innerWidth]")
        self.assertLessEqual(sw, iw, f"page is {sw}px wide in a {iw}px window")

    def assert_in_view(self, locator):
        expect(locator).to_be_visible()
        box = locator.bounding_box()
        vh = locator.page.viewport_size["height"]
        self.assertTrue(box and box["y"] < vh and box["y"] + box["height"] > 0, f"not in the viewport: {box}")

    def assert_dark(self, page, dark):
        rgb = page.evaluate("getComputedStyle(document.body).backgroundColor")
        nums = [int(x) for x in rgb[rgb.index("(") + 1:rgb.index(")")].split(",")[:3]]
        self.assertEqual(sum(nums) / 3 < 100, dark, f"body background {rgb}")

    def assert_no_xss(self, page, *payloads):
        self.assertIsNone(page.evaluate("window.__xss === undefined ? null : window.__xss"), "an injected handler ran")
        self.assertEqual(page.locator('img[src="x"]').count(), 0, "a payload became an <img> element")
        text = page.evaluate("document.body.innerText + '\\n' + Array.from(document.querySelectorAll('option'))"
                             ".map(o => o.textContent).join('\\n')")
        for p in payloads:
            self.assertIn(p, text, "the payload should show as literal text")


def _rows(page, selector, rows=" tbody tr"):
    """The text of each body row of a table, as lists of cell texts."""
    return page.eval_on_selector_all(selector + rows,
                                     "trs => trs.map(tr => Array.from(tr.cells).map(td => td.innerText.trim()))")


# --------------------------------------------------------------------------
# Quantum Station
# --------------------------------------------------------------------------

STATION_NOW = datetime(2026, 10, 1, 17, 0, tzinfo=NY)


def _main_snapshot():
    """The repository's own $100k snapshot (equity $99,847.17), read-only."""
    return json.loads((ROOT / "live" / "snapshot.json").read_text(encoding="utf-8"))


def _small_snapshot():
    return {
        "schema": 1, "updated_at": "2026-09-30T22:51:44+00:00", "mode": "paper",
        "config": {"tickers": ["NOK", "VALE"], "strategy": "equal_weight", "initial_cash": 40.0,
                   "limits": {"max_drawdown": 0.25}},
        "last_date": "2026-09-30", "bars_seen": 300, "live_bars": 6, "equity": 41.25, "cash": 15.55,
        "peak_equity": 41.9, "positions": {"NOK": 1.0, "VALE": 1.0}, "last_prices": {"NOK": 4.7, "VALE": 21.0},
        "target_weights": {"NOK": 0.5, "VALE": 0.5}, "halted": False, "halt_reason": "",
        "curve_dates": ["2026-09-29", "2026-09-30"], "curve": [40.0, 41.25],
        "fills": [{"ticker": "NOK", "quantity": 1.0, "price": 4.5, "fee": 0.0, "date": "2026-09-23"}],
        "pnl": {"total_pnl": 1.25, "realized_pnl": 0.0, "unrealized_pnl": 1.25, "positions": {}},
        "n_fills": 1, "fees": 0.0, "log": ["2026-09-30 equity=41.25"],
        "evaluation": {"days": 5, "verdict": "too early"},
    }


ORDERS = {"schema": 1, "mode": "paper", "date": "2026-09-30", "generated_at": "2026-09-30T22:51:44+00:00",
          "budget": 40.0, "whole_shares": True, "cash_after": 3.15,
          "holdings_after": {"NOK": 2.0, "VALE": 1.0},
          "orders": [{"side": "buy", "ticker": "NOK", "shares": 1, "close": 4.7, "limit": 4.75},
                     {"side": "sell", "ticker": "GOLDX", "shares": 3, "close": 7.1, "limit": 7.05}]}


def _intraday_status():
    return {
        "date": "2026-10-01", "mode": "paper", "session_open": False, "start_cash": 50.0, "equity": 50.85,
        "cash_settled": 50.85, "cash_unsettled": 0.0, "entries_today": 2, "max_trades_per_day": 3,
        "last_bar": "2026-10-01T15:55:00-04:00", "bar_minutes": 5, "updated_at": "2026-10-01T16:05:40-04:00",
        "screen": ["SOFI", "PLUG"], "positions": [], "pending_buys": ["RIVN"], "failed_tickers": [],
        "trades": [
            {"ticker": "SOFI", "entry_time": "2026-10-01T10:05:00", "exit_time": "2026-10-01T11:40:00", "shares": 3,
             "entry_price": 7.10, "exit_price": 7.32, "pnl": 0.66, "pnl_pct": 0.031, "reason": "kama cross", "bars_held": 19},
            {"ticker": "PLUG", "entry_time": "2026-10-01T13:00:00", "exit_time": "2026-10-01T15:55:00", "shares": 10,
             "entry_price": 2.50, "exit_price": 2.519, "pnl": 0.19, "pnl_pct": 0.0076, "reason": "close", "bars_held": 35}],
        "charts": {"SOFI": {"time": ["09:30", "09:35", "09:40"], "close": [7.0, 7.1, 7.2], "kama": [7.0, 7.05, 7.1]}},
    }


INTRADAY_HISTORY = [
    {"date": "2026-09-29", "start_cash": 50.0, "equity": 49.4, "return": -0.012, "trades": 2},
    {"date": "2026-09-30", "start_cash": 50.0, "equity": 50.6, "return": 0.012, "trades": 1},
]

BACKTEST_INTRADAY = {
    "sessions": ["2026-07-07", "2026-09-30", 60], "total_return": -0.021, "n_trades": 41, "win_rate": 0.44,
    "max_drawdown": 0.035, "random_runs": 40, "beats_random": 0.3, "random_median": -0.01,
    "equity_curve": [{"date": "2026-07-07", "equity": 50.0}, {"date": "2026-09-30", "equity": 48.95}],
    "trades": [{"ticker": "SOFI", "entry_time": "2026-09-30T10:00:00", "exit_time": "2026-09-30T11:00:00",
                "pnl": -0.2, "pnl_pct": -0.004, "reason": "stop"}],
    "note": "In-sample: the live settings were chosen on recent data. A result here is a check "
            "of the machinery and the costs, not evidence of an edge.",
}

INDICATOR_TEST = {
    "windows": [["2026-07-20", "2026-09-01"], ["2026-09-02", "2026-09-30"]],
    "reports": [
        {"name": "kama_cross", "timeframe": "5m", "test": {"return": 0.004, "trades": 12},
         "gates": {"beats_random": False, "enough_trades": True}, "passed": False, "causality": []},
        {"path": "/somewhere/broken_indicator.py", "error": "SyntaxError: invalid syntax"},
    ],
    "note": "Unofficial: the last 20 complete sessions as test. The registered "
            "duel scores fixed dates with scripts/indicator_duel.py.",
}

RUNS = [  # newest first, as logs/runs.json keeps them
    {"job": "daily", "started": "2026-10-01T16:45:00-04:00", "finished": "2026-10-01T16:47:05-04:00", "ok": True,
     "steps": [{"cmd": "scripts/fetch_prices.py", "code": 0, "seconds": 4.0}],
     "output": "$ scripts/fetch_prices.py\nseeded daily run output\n[exit 0]\n"},
    {"job": "fetch_bars", "started": "2026-10-01T09:00:00-04:00", "finished": "2026-10-01T09:01:00-04:00",
     "ok": False, "steps": [{"cmd": "scripts/fetch_intraday.py", "code": 2, "seconds": 60.0}],
     "output": "$ scripts/fetch_intraday.py\nseeded fetch failure\n[exit 2]\n"},
]


def seed_station(home: Path, snapshots: bool = True) -> None:
    """Write the files the station's jobs would have produced."""
    for sub in ("main", "small", "intraday/history", "tools/backtest_main", "logs"):
        (home / sub).mkdir(parents=True, exist_ok=True)
    if not snapshots:
        return

    def put(rel, obj):
        (home / rel).write_text(json.dumps(obj), encoding="utf-8")
    put("main/snapshot.json", _main_snapshot())
    put("small/snapshot.json", _small_snapshot())
    put("small/orders.json", ORDERS)
    put("intraday/status.json", _intraday_status())
    put("intraday/history/summary.json", INTRADAY_HISTORY)
    put("tools/backtest_intraday.json", BACKTEST_INTRADAY)
    put("tools/indicator_test.json", INDICATOR_TEST)
    put("tools/backtest_main/snapshot.json", _main_snapshot())
    put("logs/runs.json", RUNS)
    (home / "logs" / "last_daily.txt").write_text("$ scripts/fetch_prices.py\nfull saved daily log line\n[exit 0]\n",
                                                   encoding="utf-8")


class _StationCase(_PageCase):
    home_name = "station"
    scheduler_active = False

    def setUp(self):
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name) / self.home_name
        self.seed(self.home)
        self.gate = threading.Event()
        self.gate.set()
        self.cmd_calls = []
        patcher = mock.patch.object(Station, "_cmd", autospec=True, side_effect=self._fake_cmd)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.st = Station(home=self.home, clock=lambda: STATION_NOW, copy_state=False)
        self.st.scheduler_active = self.scheduler_active  # the flag only: no scheduler thread ever runs
        self.srv = StationServer(("127.0.0.1", 0), self.st)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}/"
        self._served = True

    def seed(self, home):
        seed_station(home)

    def _fake_cmd(self, _station, run, args, timeout=900.0):
        """Stands in for a child process: no process, no network."""
        self.cmd_calls.append(list(args))
        self.gate.wait(15)
        shown = " ".join(Path(a).name if os.path.isabs(a) else a for a in args)
        run.steps.append({"cmd": shown, "code": 0, "seconds": 0.0})
        run.output += f"$ {shown}\nfake step output\n[exit 0]\n\n"
        return 0

    def stop_server(self):
        if self._served:
            self._served = False
            self.srv.shutdown()
            self.srv.server_close()

    def tearDown(self):
        self.gate.set()
        super().tearDown()
        self.stop_server()
        for _ in range(100):  # let a job thread finish before its folder goes
            if not self.st.running:
                break
            time.sleep(0.05)
        self._tmp.cleanup()

    def load(self, **kw):
        return self.open(self.url, wait_for=lambda p: expect(p.locator("#conn")).to_have_text("connected"), **kw)

    @staticmethod
    def tab(page, name):
        page.click(f"#tab-{name}")
        expect(page.locator(f"#panel-{name}")).to_be_visible()


class TestStationPage(_StationCase):
    scheduler_active = True

    def test_loads_clean_in_both_schemes_and_widths_with_the_banner_on_every_tab(self):
        for scheme in ("light", "dark"):
            for width in (DESKTOP, PHONE):
                with self.subTest(scheme=scheme, width=width):
                    page = self.load(scheme=scheme, width=width)
                    self.assert_dark(page, scheme == "dark")
                    for name in ("overview", "daily", "intraday", "tools", "jobs"):
                        self.tab(page, name)
                        page.evaluate("window.scrollTo(0, 0)")
                        banner = page.locator(".banner")
                        self.assert_in_view(banner)
                        expect(banner).to_contain_text("PAPER TRADING")
                        if width == PHONE:
                            self.assert_no_hscroll(page)
                    self.assert_clean()
                    page.context.close()
        self.assertEqual(self.external, [])

    def test_overview_cards_show_the_seeded_numbers(self):
        page = self.load()
        cards = page.locator("#ovCards > .card")
        expect(cards).to_have_count(3)
        expect(cards.nth(0)).to_contain_text("$100k daily bot")
        expect(cards.nth(0)).to_contain_text("$99,847.17")
        expect(cards.nth(0)).to_contain_text("started with $100,000.00")
        expect(cards.nth(1)).to_contain_text("$41.25")
        expect(cards.nth(2)).to_contain_text("$50.85")
        expect(cards.nth(2)).to_contain_text("2 days archived")
        expect(page.locator("#dailyDone")).to_have_text("not yet")
        expect(page.locator("#lastSession")).to_have_text("2026-10-01")
        expect(page.locator("#mktBadge")).to_have_text("CLOSED")
        self.assert_clean()

    def test_daily_tab_positions_fills_and_orders_match_the_snapshot(self):
        snap = _main_snapshot()
        page = self.load()
        self.tab(page, "daily")
        main = page.locator('section.bot[aria-label="main"]')
        expect(main.locator(".tiles")).to_contain_text("$99,847.17")
        rows = _rows(page, 'section.bot[aria-label="main"] .two .card:first-child')
        self.assertEqual(sorted(r[0] for r in rows), sorted(snap["positions"]))
        by = {r[0]: r for r in rows}
        for t, q in snap["positions"].items():
            self.assertEqual(by[t][1], f"{q:.4f}", t)                      # shares
            self.assertEqual(by[t][2], f"${snap['pnl']['positions'][t]['price']:,.2f}", t)  # price
        fills = _rows(page, 'section.bot[aria-label="main"] > .card:last-child')
        self.assertEqual(len(fills), len(snap["fills"]))
        self.assertEqual({r[1] for r in fills}, {f["ticker"] for f in snap["fills"]})
        # The $40 bot's hand-placed order list, labelled information only.
        small = page.locator('section.bot[aria-label="small"]')
        orders = small.locator(".card", has_text="Today's orders to place by hand")
        expect(orders.locator(".callout")).to_contain_text("Information only.")
        expect(orders.locator(".callout")).to_contain_text("nothing is sent to any broker")
        orows = orders.locator("tbody tr")
        expect(orows).to_have_count(2)
        expect(orows.nth(0)).to_contain_text("BUY")
        expect(orows.nth(0)).to_contain_text("NOK")
        expect(orows.nth(0)).to_contain_text("$4.75")
        expect(orows.nth(1)).to_contain_text("SELL")
        expect(orows.nth(1)).to_contain_text("GOLDX")
        expect(orders).to_contain_text("holdings after: NOK 2, VALE 1")
        self.assert_clean()

    def test_intraday_tab_shows_trades_and_history(self):
        page = self.load()
        self.tab(page, "intraday")
        expect(page.locator("#idTitle")).to_contain_text("2026-10-01")
        expect(page.locator("#idTiles")).to_contain_text("$50.85")
        trades = _rows(page, "#idTrades")
        self.assertEqual([r[0] for r in trades], ["SOFI", "PLUG"])
        self.assertEqual(trades[0][1:3], ["10:05", "11:40"])
        self.assertIn("+$0.66", trades[0][6])
        hist = _rows(page, "#idHistory")
        self.assertEqual([r[0] for r in hist], ["2026-09-30", "2026-09-29"])  # newest first
        self.assertEqual(hist[1][3], "−1.20%")
        expect(page.locator("#idScreen")).to_contain_text("SOFI")
        expect(page.locator("#idPending")).to_contain_text("RIVN")
        expect(page.locator("#idChartSel option")).to_have_count(1)
        self.assert_clean()

    def test_tools_tab_shows_results_with_in_sample_and_unofficial_notes(self):
        page = self.load()
        self.tab(page, "tools")
        res = page.locator("#toolResults")
        bi = res.locator(".card", has_text="Backtest: intraday bot")
        expect(bi.locator(".callout")).to_be_visible()
        expect(bi.locator(".callout")).to_contain_text("In-sample")
        expect(bi.locator(".callout")).to_contain_text("not evidence of an edge")
        expect(bi).to_contain_text("−2.10%")
        expect(bi).to_contain_text("40 runs with the same number of trades")
        it = res.locator(".card", has_text="Indicator test")
        expect(it.locator(".callout")).to_be_visible()
        expect(it.locator(".callout")).to_contain_text("Unofficial")
        rows = _rows(page, '#toolResults .card:has-text("Indicator test")')
        self.assertEqual(rows[0][0], "kama_cross")
        self.assertEqual(rows[0][4], "1 / 2")
        self.assertEqual(rows[1][0], "broken_indicator.py")
        self.assertIn("SyntaxError", rows[1][1])
        expect(res.locator(".card", has_text="Backtest: $100k bot")).to_contain_text("$99,847.17")
        expect(res.locator(".card", has_text="Backtest: $40 bot")).to_contain_text("No result yet")
        expect(page.locator("#barsInfo")).to_contain_text("not downloaded")
        self.assert_clean()

    def test_jobs_tab_lists_runs_and_shows_logs(self):
        page = self.load()
        self.tab(page, "jobs")
        hist = _rows(page, "#historyTable")
        self.assertEqual([r[0] for r in hist], ["Run the daily bots", "Download intraday bars"])
        self.assertEqual([r[1] for r in hist], ["ok", "failed"])
        self.assertIn("failed: scripts/fetch_intraday.py (exit 2)", hist[1][4])
        expect(page.locator("#allJobs .job")).to_have_count(8)
        # A run's own output, from the history.
        page.locator("#historyTable tbody tr").nth(1).click()
        expect(page.locator("#logOut")).to_contain_text("seeded fetch failure")
        expect(page.locator("#logTitle")).to_contain_text("Download intraday bars")
        expect(page.locator("#logTitle")).to_contain_text("FAILED")
        expect(page.locator("#historyTable tbody tr.selected")).to_have_count(1)
        # The job's full saved log, from /api/log/<job>.
        with page.expect_response(lambda r: r.url.endswith("/api/log/daily")):
            page.locator("#allJobs .job", has_text="Run the daily bots").get_by_role("button", name="Show the last output").click()
        expect(page.locator("#logOut")).to_have_text("$ scripts/fetch_prices.py\nfull saved daily log line\n[exit 0]\n")
        expect(page.locator("#logTitle")).to_have_text("Run the daily bots · last output")
        # A job with nothing saved yet says so.
        page.locator("#allJobs .job", has_text="Test the indicators").get_by_role("button", name="Show the last output").click()
        expect(page.locator("#logOut")).to_have_text("(no output saved for this job yet)")
        self.assert_clean()

    def test_run_button_posts_shows_running_then_ok(self):
        self.gate.clear()  # the mocked job blocks until released
        page = self.load()
        posts = []
        page.on("request", lambda r: r.method == "POST" and posts.append((r.url, r.post_data)))
        btn = page.locator('#ovJobs [data-job="daily"]')
        badge = page.locator("#ovJobs .job", has_text="Run the daily bots").locator(".badge")
        expect(btn).to_have_text("Run")
        expect(badge).to_have_text("ok · 16:47:05 · 2m 5s")  # the seeded run
        btn.click()
        expect(btn).to_have_text("Running…")
        expect(btn).to_be_disabled()
        expect(btn).to_have_attribute("aria-busy", "true")
        expect(badge).to_contain_text("running")
        expect(page.locator("#toast")).to_contain_text("Started: Run the daily bots")
        self.assertEqual(len(posts), 1)
        self.assertTrue(posts[0][0].endswith("/api/run"))
        self.assertEqual(json.loads(posts[0][1]), {"job": "daily"})
        # Every Run button for the same job shows it, on other tabs too.
        self.tab(page, "jobs")
        expect(page.locator('#allJobs [data-job="daily"]')).to_have_text("Running…")
        expect(page.locator("#runningList")).to_contain_text("Run the daily bots")
        self.gate.set()
        self.tab(page, "overview")
        expect(btn).to_have_text("Run", timeout=WAIT)
        expect(btn).to_be_enabled()
        expect(badge).to_have_text("ok · 17:00:00 · 0s")
        expect(page.locator("#dailyDone")).to_have_text("2026-10-01")
        # Four mocked steps (fetch + bot, twice), all paper, and nothing else ran.
        self.assertEqual(len(self.cmd_calls), 4)
        self.assertTrue(all("--broker" in a and a[a.index("--broker") + 1] == "paper"
                            for a in self.cmd_calls if "live" in a))
        self.assertEqual(len(posts), 1)
        self.assert_clean()

    def test_pause_and_resume_toggle_the_scheduler(self):
        page = self.load()
        badge, btn = page.locator("#schedBadge"), page.locator("#btnPause")
        expect(badge).to_have_text("RUNNING")
        expect(btn).to_have_text("Pause")
        btn.click()
        expect(badge).to_have_text("PAUSED")
        expect(btn).to_have_text("Resume")
        expect(btn).to_have_attribute("aria-pressed", "true")
        self.assertTrue(self.st.sched["paused"])
        self.assertTrue(json.loads((self.home / "scheduler.json").read_text())["paused"])
        btn.click()
        expect(badge).to_have_text("RUNNING")
        expect(btn).to_have_text("Pause")
        self.assertFalse(self.st.sched["paused"])
        self.assert_clean()

    def test_reset_asks_first_and_cancel_does_nothing(self):
        page = self.load()
        self.tab(page, "daily")
        posts = []
        page.on("request", lambda r: r.method == "POST" and posts.append(r.url))
        messages = []

        def answer(accept):
            def handler(d):
                messages.append(d.message)
                d.accept() if accept else d.dismiss()
            return handler
        reset = page.locator('section.bot[aria-label="main"]').get_by_role("button", name="Reset this bot…")
        page.once("dialog", answer(False))
        reset.click()
        page.wait_for_timeout(300)
        self.assertEqual(len(messages), 1)
        self.assertIn("Reset the $100k daily bot?", messages[0])
        self.assertEqual(posts, [])
        self.assertTrue((self.home / "main" / "snapshot.json").exists())
        expect(page.locator('section.bot[aria-label="main"] .tiles')).to_contain_text("$99,847.17")

        page.once("dialog", answer(True))
        with page.expect_response(lambda r: r.url.endswith("/api/reset")) as resp:
            reset.click()
        self.assertEqual(resp.value.json(), {"ok": True, "moved": ["snapshot.json"]})
        self.assertEqual(len(messages), 2)
        self.assertFalse((self.home / "main" / "snapshot.json").exists())
        self.assertEqual(len(list((self.home / "main").glob("snapshot.json.*.bak"))), 1)
        expect(page.locator("#toast")).to_contain_text("$100k daily bot reset (snapshot.json)")
        expect(page.locator('section.bot[aria-label="main"]')).to_contain_text("No data yet")
        self.assertTrue((self.home / "small" / "snapshot.json").exists())  # the other bot is untouched
        self.assert_clean()

    def test_tabs_follow_the_keyboard(self):
        page = self.load()
        names = ["overview", "daily", "intraday", "tools", "jobs"]

        def selected():
            return page.evaluate("document.activeElement.dataset.tab"), [
                n for n in names if page.get_attribute(f"#tab-{n}", "aria-selected") == "true"]
        page.focus("#tab-overview")
        for want in names[1:] + names[:1]:  # wraps round
            page.keyboard.press("ArrowRight")
            self.assertEqual(selected(), (want, [want]))
            expect(page.locator(f"#panel-{want}")).to_be_visible()
        page.keyboard.press("ArrowLeft")
        self.assertEqual(selected(), ("jobs", ["jobs"]))
        page.keyboard.press("Home")
        self.assertEqual(selected(), ("overview", ["overview"]))
        page.keyboard.press("End")
        self.assertEqual(selected(), ("jobs", ["jobs"]))
        self.assertEqual(page.evaluate("Array.from(document.querySelectorAll('[role=tab]')).map(t => t.tabIndex)"),
                         [-1, -1, -1, -1, 0])
        self.assertEqual([page.locator(f"#panel-{n}").is_hidden() for n in names], [True] * 4 + [False])
        self.assertTrue(page.url.endswith("#jobs"))
        self.assert_clean()

    def test_unreachable_station_warns_and_keeps_the_last_data(self):
        page = self.load(clock=True)
        self.tab(page, "daily")
        expect(page.locator('section.bot[aria-label="main"] .tiles')).to_contain_text("$99,847.17")
        self.stop_server()
        page.clock.run_for(3100)
        expect(page.locator("#conn")).to_have_text("disconnected")
        page.clock.run_for(3100)
        err = page.locator("#loadErr")
        expect(err).to_be_visible()
        expect(err).to_contain_text("Cannot reach the station")
        expect(err).to_contain_text("figures below are from the last good update")
        expect(page.locator('section.bot[aria-label="main"] .tiles')).to_contain_text("$99,847.17")
        self.tab(page, "overview")
        expect(page.locator("#ovCards")).to_contain_text("$99,847.17")
        # A button pressed now reports the failure instead of throwing.
        page.locator('#ovJobs [data-job="daily"]').click()
        expect(page.locator("#toast")).to_contain_text("could not reach the station")
        expect(page.locator('#ovJobs [data-job="daily"]')).to_have_text("Run")
        self.assert_clean(allow=("ERR_CONNECTION_REFUSED", "Failed to fetch"))


class TestStationEmpty(_StationCase):
    def seed(self, home):
        seed_station(home, snapshots=False)

    def test_no_snapshots_shows_no_data_yet(self):
        for width in (DESKTOP, PHONE):
            with self.subTest(width=width):
                page = self.load(width=width)
                cards = page.locator("#ovCards > .card")
                expect(cards).to_have_count(3)
                expect(cards.nth(0)).to_contain_text("No data yet: press Run the daily bots.")
                expect(cards.nth(1)).to_contain_text("No data yet: press Run the daily bots.")
                expect(cards.nth(2)).to_contain_text("No data yet: press Run the intraday bot.")
                expect(page.locator("#schedBadge")).to_have_text("OFF (buttons only)")
                expect(page.locator("#btnPause")).to_be_disabled()
                self.tab(page, "daily")
                for k in ("main", "small"):
                    expect(page.locator(f'section.bot[aria-label="{k}"] p.muted').first).to_have_text(
                        "No data yet: press Run the daily bots.")
                expect(page.locator('section.bot[aria-label="small"]')).to_contain_text("No orders yet")
                self.tab(page, "intraday")
                expect(page.locator("#idEmpty")).to_be_visible()
                expect(page.locator("#idEmpty")).to_contain_text("No data yet")
                expect(page.locator("#idHistory")).to_contain_text("No archived days yet")
                self.tab(page, "tools")
                expect(page.locator("#toolResults .muted")).to_have_count(4)
                self.tab(page, "jobs")
                expect(page.locator("#historyTable")).to_contain_text("No runs since the station started")
                expect(page.locator("#runningList")).to_have_text("Nothing is running.")
                if width == PHONE:
                    self.assert_no_hscroll(page)
                self.assert_clean()
                page.context.close()


class TestStationHostileData(_StationCase):
    # The data folder's own name is shown on the page too.
    home_name = XSS_IMG

    def seed(self, home):
        seed_station(home)
        snap = _main_snapshot()
        snap["positions"][XSS_IMG] = 1.0
        snap["last_prices"][XSS_IMG] = 10.0
        snap["target_weights"][XSS_SCRIPT] = 0.1
        snap["fills"].append({"ticker": XSS_SCRIPT, "quantity": 1.0, "price": 10.0, "fee": 0.0,
                              "date": "2026-09-30", "note": XSS_IMG})
        snap["halted"], snap["halt_reason"] = True, XSS_SCRIPT
        snap["evaluation"]["verdict"] = XSS_IMG
        (home / "main" / "snapshot.json").write_text(json.dumps(snap))
        orders = dict(ORDERS, date=XSS_SCRIPT)
        orders["orders"] = [dict(ORDERS["orders"][0], ticker=XSS_IMG)]
        (home / "small" / "orders.json").write_text(json.dumps(orders))
        st = _intraday_status()
        st["screen"] = [XSS_IMG, {"ticker": XSS_SCRIPT}]
        st["pending_buys"] = [XSS_SCRIPT]
        st["failed_tickers"] = [XSS_IMG]
        st["trades"][0]["ticker"] = XSS_IMG
        st["trades"][1]["reason"] = XSS_SCRIPT
        st["positions"] = [{"ticker": XSS_SCRIPT, "shares": 1, "entry_time": "x", "entry_price": 1, "last": 1,
                            "unrealized": 0}]
        st["charts"] = {XSS_IMG: st["charts"]["SOFI"]}
        (home / "intraday" / "status.json").write_text(json.dumps(st))
        it = json.loads(json.dumps(INDICATOR_TEST))
        it["reports"][0]["name"] = XSS_IMG
        it["reports"][0]["causality"] = [XSS_SCRIPT]
        it["reports"][1]["error"] = XSS_SCRIPT
        it["note"] = XSS_SCRIPT
        (home / "tools" / "indicator_test.json").write_text(json.dumps(it))
        bi = dict(BACKTEST_INTRADAY, note=XSS_IMG)
        bi["trades"] = [dict(BACKTEST_INTRADAY["trades"][0], ticker=XSS_SCRIPT)]
        (home / "tools" / "backtest_intraday.json").write_text(json.dumps(bi))
        runs = json.loads(json.dumps(RUNS))
        runs[0]["output"] = f"line one\n{XSS_IMG}\n{XSS_SCRIPT}\n"
        runs[1]["job"] = XSS_IMG  # an unknown job name in an old runs.json
        runs[1]["steps"][0]["cmd"] = XSS_SCRIPT
        (home / "logs" / "runs.json").write_text(json.dumps(runs))
        (home / "logs" / "last_daily.txt").write_text(f"{XSS_SCRIPT}\n{XSS_IMG}\n")

    def test_payloads_in_every_file_stay_text(self):
        self.st.note(f"message {XSS_IMG} {XSS_SCRIPT}")
        page = self.load()
        expect(page.locator("#homePathHdr")).to_contain_text(XSS_IMG)
        for name in ("overview", "daily", "intraday", "tools", "jobs"):
            self.tab(page, name)
        expect(page.locator('section.bot[aria-label="main"] .callout.bad')).to_contain_text(XSS_SCRIPT)
        expect(page.locator("#idChartSel option")).to_have_text([XSS_IMG])
        self.tab(page, "jobs")
        page.locator("#historyTable tbody tr").nth(0).click()
        expect(page.locator("#logOut")).to_contain_text(XSS_IMG)
        page.locator("#historyTable tbody tr").nth(1).click()  # the run with the hostile job name
        expect(page.locator("#logTitle")).to_contain_text(XSS_IMG)
        page.get_by_role("button", name="Full last output of this job").click()
        expect(page.locator("#logOut")).to_contain_text("could not load: unknown job")
        page.locator("#allJobs .job", has_text="Run the daily bots").get_by_role("button", name="Show the last output").click()
        expect(page.locator("#logOut")).to_contain_text(XSS_SCRIPT)
        expect(page.locator("#messages")).to_contain_text(XSS_IMG)
        page.wait_for_timeout(200)  # time for an injected <img> to fail and fire onerror
        self.assert_no_xss(page, XSS_IMG, XSS_SCRIPT)
        # The unknown job's log fetch is a 404 the page handles; nothing else may fail.
        self.assert_clean(allow=("404",))


class TestStationNonFinite(_StationCase):
    def seed(self, home):
        seed_station(home)
        snap = _main_snapshot()
        snap["equity"] = float("nan")
        snap["cash"] = float("inf")
        snap["peak_equity"] = float("-inf")
        snap["curve"][2] = float("nan")
        snap["curve"][3] = float("inf")
        snap["pnl"]["total_pnl"] = float("nan")
        first = next(iter(snap["pnl"]["positions"]))
        snap["pnl"]["positions"][first]["unrealized_pnl"] = float("inf")
        snap["evaluation"]["bot_return"] = float("nan")
        # json.dumps writes the bare NaN / Infinity tokens Python's json emits.
        (home / "main" / "snapshot.json").write_text(json.dumps(snap))
        st = _intraday_status()
        st["equity"] = float("nan")
        st["charts"]["SOFI"]["close"][1] = float("nan")
        (home / "intraday" / "status.json").write_text(json.dumps(st))
        hist = [dict(INTRADAY_HISTORY[0], **{"return": float("nan")}), INTRADAY_HISTORY[1]]
        (home / "intraday" / "history" / "summary.json").write_text(json.dumps(hist))
        (home / "tools" / "backtest_intraday.json").write_text(
            json.dumps(dict(BACKTEST_INTRADAY, total_return=float("inf"), random_median=float("nan"))))
        self.assertIn("NaN", (home / "main" / "snapshot.json").read_text())

    def test_nan_and_infinity_render_without_errors(self):
        page = self.load()
        strict = page.evaluate("fetch('/api/overview').then(r => r.text()).then(t => "
                               "{ const d = JSON.parse(t); return [d.bots.main.snapshot.equity, d.bots.main.snapshot.cash,"
                               " d.bots.main.snapshot.curve[2], d.intraday.status.equity]; })")
        self.assertEqual(strict, [None, None, None, None])
        expect(page.locator("#ovCards > .card").nth(0).locator(".tile.big .value")).to_have_text("–")
        for name in ("daily", "intraday", "tools", "jobs", "overview"):
            self.tab(page, name)
        self.tab(page, "daily")
        main = page.locator('section.bot[aria-label="main"]')
        expect(main.locator(".tile.big .value")).to_have_text("–")
        expect(main.locator("tbody tr").first).to_be_visible()
        self.tab(page, "intraday")
        expect(page.locator("#idTiles .tile.big .value")).to_have_text("–")
        self.assertEqual(page.locator("body").inner_text().count("NaN"), 0)
        self.assertEqual(page.locator("body").inner_text().count("Infinity"), 0)
        self.assert_clean()

    # An unknown equity (null from the server) reads as unknown, not as a total
    # loss: null - start would be -start in the page's arithmetic.
    def test_unknown_equity_is_not_shown_as_a_total_loss(self):
        page = self.load()
        cards = page.locator("#ovCards > .card")
        expect(cards.nth(0).locator(".tile.big .value")).to_have_text("–")
        for i in (0, 2):  # the $100k bot and the intraday bot
            text = cards.nth(i).inner_text()
            self.assertNotIn("−100.00%", text)
            self.assertNotIn("−$100,000.00", text)
            self.assertNotIn("−$50.00", text)


# --------------------------------------------------------------------------
# Desktop replay dashboard (quantum/desktop.py)
# --------------------------------------------------------------------------

TICKERS = ["AAA", "BBB"]


def _write_prices(path: Path, n: int, falling: bool = False) -> None:
    lines = ["date," + ",".join(TICKERS)]
    for i in range(n):
        day = f"2020-{1 + i // 28:02d}-{1 + i % 28:02d}"
        if falling:  # flat, then down 3% a day: trips any small kill switch
            row = [f"{(100.0 + 20 * j) * (0.97 ** max(0, i - 12)):.4f}" for j in range(len(TICKERS))]
        else:
            row = [f"{(100.0 + 20 * j) * (1.0 + 0.002 * i + 0.01 * math.sin(i / 3 + j)):.4f}" for j in range(len(TICKERS))]
        lines.append(day + "," + ",".join(row))
    path.write_text("\n".join(lines) + "\n")


class _DesktopCase(_PageCase):
    def setUp(self):
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory()
        self.work = Path(self._tmp.name) / "work"
        (self.work / "data" / "prices").mkdir(parents=True)
        _write_prices(self.work / "data" / "prices" / "synthetic.csv", 80)
        _write_prices(self.work / "data" / "prices" / "falling.csv", 40, falling=True)
        with mock.patch("builtins.print"):
            self.srv = desktop_serve(port=0, open_browser=False, workdir=self.work, block=False)
        self.ctl = self.srv.controller
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}/"
        self._served = True

    def stop_server(self):
        if self._served:
            self._served = False
            self.srv.shutdown()
            self.srv.server_close()

    def tearDown(self):
        super().tearDown()
        self.ctl.stop()
        self.stop_server()
        self._tmp.cleanup()

    def load(self, **kw):
        return self.open(self.url, wait_for=lambda p: expect(p.locator("#csv option")).not_to_have_count(0), **kw)

    @staticmethod
    def fill_form(page, csv="data/prices/synthetic.csv", speed="0", fresh=True, **fields):
        page.select_option("#csv", csv)
        page.fill("#tickers", ",".join(TICKERS))
        page.fill("#start", "")
        page.select_option("#strategy", "equal_weight")
        values = {"window": "10", "rebalance_every": "5", "speed": speed, "max_weight": "1", "rearm_after": "0"}
        values.update(fields)
        for k, v in values.items():
            page.fill(f"#{k}", v)
        page.set_checked("#fresh", fresh)

    def wait_idle(self):
        for _ in range(200):
            if not self.ctl.running:
                return
            time.sleep(0.05)
        self.fail("the replay did not finish")


class TestDesktopPage(_DesktopCase):
    def test_loads_clean_in_both_schemes_and_widths(self):
        for scheme in ("light", "dark"):
            for width in (DESKTOP, PHONE):
                with self.subTest(scheme=scheme, width=width):
                    page = self.load(scheme=scheme, width=width)
                    self.assert_dark(page, scheme == "dark")
                    self.assert_in_view(page.locator("header .badge.paper"))
                    expect(page.locator("header .badge.paper")).to_have_text("PAPER")
                    expect(page.locator("#status")).to_have_text("IDLE")
                    self.assert_clean()
                    page.context.close()
        self.assertEqual(self.external, [])

    # The positions and fills tables scroll inside their cards on a phone
    # instead of widening the page.
    def test_no_horizontal_overflow_at_phone_width(self):
        for scheme in ("light", "dark"):
            page = self.load(scheme=scheme, width=PHONE)
            self.assert_no_hscroll(page)
            page.context.close()

    def test_empty_state(self):
        page = self.load()
        expect(page.locator("#tEquity")).to_have_text("–")
        expect(page.locator("#tEquitySub")).to_have_text("no bars yet")
        expect(page.locator("#positions")).to_have_text("no positions")
        expect(page.locator("#csv option")).to_have_text(["data/prices/falling.csv", "data/prices/synthetic.csv"])
        expect(page.locator("#btnStop")).to_be_disabled()
        self.assert_clean()

    def test_replay_updates_then_stops_then_resumes(self):
        page = self.load()
        self.fill_form(page, speed="25")
        page.click("#btnStart")
        expect(page.locator("#status")).to_have_text("RUNNING")
        expect(page.locator("#btnStart")).to_be_disabled()
        expect(page.locator("#btnStop")).to_be_enabled()
        expect(page.locator("#source")).to_contain_text("replay synthetic.csv (80 bars)")
        expect(page.locator("#positions tr td:first-child")).to_have_text(TICKERS, timeout=WAIT)  # after the 10-bar warm-up
        expect(page.locator("#fills tr")).not_to_have_count(0)
        expect(page.locator("#tEquity")).not_to_have_text("–")
        page.click("#btnStop")
        expect(page.locator("#status")).to_have_text("IDLE")
        expect(page.locator("#btnStart")).to_be_enabled()
        bars = int(page.inner_text("#tBars"))
        self.assertTrue(10 < bars < 80, bars)
        self.assertIn("stopped by user", page.inner_text("#messages"))
        # Resume from the saved state at full speed: it runs to the end of the file.
        page.set_checked("#fresh", False)
        page.fill("#speed", "0")
        page.click("#btnStart")
        expect(page.locator("#tBars")).to_have_text("80")
        expect(page.locator("#tBarsSub")).to_have_text("2020-01-01 → 2020-03-24")
        st = self.ctl.snapshot()
        expect(page.locator("#tEquity")).to_have_text(f"{st['equity']:,.2f}")
        expect(page.locator("#tFills")).to_have_text(str(st["n_fills"]))
        self.assertEqual(page.locator("#fills tr").count(), min(25, len(st["fills"])))
        expect(page.locator("#status")).to_have_text("IDLE")
        self.assert_clean()

    def test_kill_switch_shows_halted_and_can_be_cleared(self):
        page = self.load()
        self.fill_form(page, csv="data/prices/falling.csv", max_drawdown="0.05")
        page.click("#btnStart")
        expect(page.locator("#status")).to_have_text("HALTED")
        box = page.locator("#haltbox")
        expect(box).to_be_visible()
        expect(page.locator("#haltreason")).to_contain_text("drawdown")
        expect(page.locator("#positions")).to_have_text("all cash")
        self.wait_idle()
        page.click("#btnResume")
        expect(box).to_be_hidden()
        expect(page.locator("#status")).to_have_text("IDLE")
        self.assertFalse(json.loads((self.work / "live_state.json").read_text())["halted"])
        self.assert_clean()

    def test_reset_asks_first(self):
        page = self.load()
        self.fill_form(page)
        page.click("#btnStart")
        expect(page.locator("#tBars")).to_have_text("80")
        self.wait_idle()
        state = self.work / "live_state.json"
        self.assertTrue(state.exists())
        posts = []
        page.on("request", lambda r: r.method == "POST" and posts.append(r.url))
        page.once("dialog", lambda d: d.dismiss())
        page.click("#btnReset")
        page.wait_for_timeout(300)
        self.assertEqual(posts, [])
        self.assertTrue(state.exists())
        page.once("dialog", lambda d: d.accept())
        with page.expect_response(lambda r: r.url.endswith("/api/reset")):
            page.click("#btnReset")
        self.assertFalse(state.exists())
        self.assert_clean()

    def test_unreachable_server_shows_disconnected_and_keeps_numbers(self):
        page = self.load(clock=True)
        self.fill_form(page)
        page.click("#btnStart")
        expect(page.locator("#tBars")).to_have_text("80")
        equity = page.inner_text("#tEquity")
        self.wait_idle()
        self.stop_server()
        page.clock.run_for(1500)
        expect(page.locator("#status")).to_have_text("DISCONNECTED")
        expect(page.locator("#tEquity")).to_have_text(equity)
        self.assert_clean(allow=("ERR_CONNECTION_REFUSED", "Failed to fetch"))


class TestDesktopHostileData(_DesktopCase):
    def test_file_name_log_and_messages_stay_text(self):
        # A price file whose name is markup (legal on Linux and macOS).
        _write_prices(self.work / f"{XSS_IMG}.csv", 30)
        # A state whose log and halt reason carry markup.
        self.assertTrue(self.ctl.start({"mode": "replay", "csv": "data/prices/synthetic.csv", "tickers": "AAA,BBB",
                                        "bars_per_second": 0, "fresh": True, "window": 10,
                                        "strategy": "equal_weight", "rebalance_every": 5})["ok"])
        self.wait_idle()
        path = self.work / "live_state.json"
        state = json.loads(path.read_text())
        state["log"] += [XSS_IMG, XSS_SCRIPT]
        state["halted"], state["halt_reason"] = True, XSS_SCRIPT
        path.write_text(json.dumps(state))
        self.ctl.engine = None  # show the file, as after a restart
        page = self.load()
        expect(page.locator("#csv option")).to_have_count(3)
        # A request the page itself sends, carrying markup, ends up in the messages.
        page.evaluate("p => fetch('/api/start', {method: 'POST', headers: {'Content-Type': 'application/json'},"
                      " body: JSON.stringify({csv: p + '.csv', tickers: 'AAA', strategy: 'equal_weight'})})", XSS_SCRIPT)
        expect(page.locator("#messages")).to_contain_text(XSS_SCRIPT, timeout=WAIT)
        expect(page.locator("#log")).to_contain_text(XSS_IMG)
        expect(page.locator("#haltreason")).to_have_text(XSS_SCRIPT)
        page.select_option("#csv", f"{XSS_IMG}.csv")
        page.wait_for_timeout(200)
        self.assert_no_xss(page, XSS_IMG, XSS_SCRIPT)
        self.assert_clean()


# --------------------------------------------------------------------------
# The static web page (web/quantum-trading.html)
# --------------------------------------------------------------------------


def _fake_claude(docs):
    """A stand-in for the claude.ai runtime the Live bot tab reads from."""
    return ("window.__docs = %s;\n"
            "window.claude = {use: cap => Promise.resolve(cap !== 'db' ? null : {doc: path => ({onSnapshot(ok, bad) {"
            " const d = window.__docs[path]; setTimeout(() => ok({exists: d != null, data: () => d}), 0);"
            " return () => {}; }})})};" % json.dumps(docs))


def _live_docs(**changes):
    status = _main_snapshot()
    status["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    status.update(changes)
    prices = json.loads((ROOT / "live" / "snapshot_prices.json").read_text(encoding="utf-8"))
    return {"bot/status": status, "bot/prices": prices}


class TestWebPage(_PageCase):
    url = WEB_PAGE.resolve().as_uri()

    def load(self, **kw):
        return self.open(self.url, wait_for=lambda p: p.wait_for_load_state("load"), **kw)

    def sim(self, page):
        page.click("#tabSim")
        expect(page.locator("#simView")).to_be_visible()

    def test_page_is_built_from_the_current_template_and_engine(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("web_build", ROOT / "web" / "build.py")
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        engine = (ROOT / "web" / "engine.js").read_text().replace(
            'if (typeof module !== "undefined") module.exports = QT;', "")
        want = (ROOT / "web" / "template.html").read_text().replace("/*__ENGINE__*/", engine).replace(
            "/*__DATA__*/", json.dumps(build.dataset(), separators=(",", ":")))
        self.assertTrue(WEB_PAGE.read_text() == want, "web/quantum-trading.html is stale: run python3 web/build.py")

    def test_loads_clean_in_both_schemes_and_widths_on_both_tabs(self):
        for scheme in ("light", "dark"):
            for width in (DESKTOP, PHONE):
                with self.subTest(scheme=scheme, width=width):
                    page = self.load(scheme=scheme, width=width)
                    self.assert_dark(page, scheme == "dark")
                    for tab in ("#tabSim", "#tabLive"):
                        page.click(tab)
                        page.evaluate("window.scrollTo(0, 0)")
                        self.assert_in_view(page.locator("header .pill.paper"))
                        expect(page.locator("header .pill.paper")).to_have_text("Paper")
                        if width == PHONE:
                            self.assert_no_hscroll(page)
                    self.assert_clean()
                    page.context.close()
        self.assertTrue(all("fonts.g" in u for u in self.external), self.external)

    def test_live_tab_without_the_runtime_says_so(self):
        page = self.load()
        expect(page.locator("#liveEmptyTitle")).to_have_text("The live bot can't be reached from here.")
        expect(page.locator("#liveBody")).to_be_hidden()
        self.assert_clean()

    def test_simulator_runs_a_backtest_from_its_controls(self):
        page = self.load()
        self.sim(page)
        expect(page.locator("#statusText")).to_have_text("Finished")  # the example run at load
        page.select_option("#strategy", "equal_weight")
        page.fill("#start", "2015-01-02")
        page.fill("#end", "2016-12-30")
        page.fill("#window", "60")
        page.select_option("#speed", "0")
        n = page.evaluate("BUILTIN.dates.filter(d => d >= '2015-01-02' && d <= '2016-12-30').length")
        page.click("#btnStart")
        expect(page.locator("#statusText")).to_have_text("Finished")
        expect(page.locator("#runinfo")).to_have_text(f"8 stocks · {n} of {n} trading days")
        expect(page.locator("#btnStart")).to_have_text("Run again")
        expect(page.locator("#tEquity")).to_have_text(re.compile(r"^\$[\d,]+$"))
        expect(page.locator("#positions tr")).to_have_count(8)  # equal weight holds every stock
        expect(page.locator("#fills tr")).not_to_have_count(0)
        expect(page.locator("#cashLine")).to_contain_text("prices as of 2016-12-30")
        expect(page.locator("#log")).not_to_have_text("")
        expect(page.locator("#tDDSub")).to_contain_text("limit 25%")
        # Bad settings are refused with a message, not an exception.
        page.fill("#window", "5")
        page.click("#btnStart")
        expect(page.locator("#error")).to_have_text("Look back must be at least 20 days.")
        self.assert_clean()

    def test_simulator_pause_continue_and_reset_confirmation(self):
        page = self.load()
        self.sim(page)
        page.select_option("#speed", "10")
        page.click("#btnStart")
        expect(page.locator("#statusText")).to_have_text("Running")
        page.click("#btnPause")
        expect(page.locator("#statusText")).to_have_text("Paused")
        expect(page.locator("#btnStart")).to_have_text("Continue")
        page.click("#btnReset")
        expect(page.locator("#confirmReset")).to_be_visible()
        page.click("#btnResetNo")
        expect(page.locator("#statusText")).to_have_text("Paused")
        page.click("#btnReset")
        page.click("#btnResetYes")
        expect(page.locator("#statusText")).to_have_text("Ready")
        expect(page.locator("#tEquity")).to_have_text("–")
        self.assert_clean()

    def test_simulator_runs_an_uploaded_csv_with_markup_in_its_header(self):
        lines = [f"date,AAA,{XSS_IMG},{XSS_SCRIPT}"]
        for i in range(60):
            lines.append(f"2021-{1 + i // 28:02d}-{1 + i % 28:02d},{100 + i},{50 + i % 7},{20 + 0.1 * i}")
        page = self.load()
        self.sim(page)
        page.set_input_files("#upload", files=[{"name": "mine.csv", "mimeType": "text/csv",
                                                 "buffer": "\n".join(lines).encode()}])
        expect(page.locator("#dataHint")).to_have_text("Your file: 3 stocks, 2021-01-01 to 2021-03-04.")
        expect(page.locator("#universe .chip span")).to_have_text(["AAA", XSS_IMG, XSS_SCRIPT])
        expect(page.locator("#builtinRow")).to_be_visible()
        page.select_option("#strategy", "equal_weight")
        page.fill("#window", "20")
        page.select_option("#speed", "0")
        page.click("#btnStart")
        expect(page.locator("#statusText")).to_have_text("Finished")
        expect(page.locator("#runinfo")).to_have_text("3 stocks · 60 of 60 trading days")
        expect(page.locator("#positions")).to_contain_text(XSS_IMG)
        page.wait_for_timeout(200)
        self.assert_no_xss(page, XSS_IMG, XSS_SCRIPT)
        page.click("#btnBuiltin")
        expect(page.locator("#dataHint")).to_contain_text("Built-in prices: 17 stocks")
        self.assert_clean()

    def test_live_tab_renders_a_seeded_snapshot_and_rechecks_it(self):
        docs = _live_docs()
        snap = docs["bot/status"]
        page = self.load(init_script=_fake_claude(docs))
        expect(page.locator("#liveBody")).to_be_visible()
        expect(page.locator("#lEquity")).to_have_text("$99,847")
        expect(page.locator("#lFills")).to_have_text(str(snap["n_fills"]))
        rows = _rows(page, "#lPositions", " tr")
        self.assertEqual(sorted(r[0] for r in rows), sorted(snap["positions"]))
        expect(page.locator("#lAsOf")).to_have_text(snap["last_date"])
        expect(page.locator("#lUpdated")).to_have_text("just now")
        expect(page.locator("#liveStale")).to_be_hidden()
        expect(page.locator("#liveHalt")).to_be_hidden()
        expect(page.locator("#lFillsTable tr")).to_have_count(len(snap["fills"]))
        # The page re-runs the bot's own rules on the bot's prices: it must land on the same cents.
        expect(page.locator("#lCheckText")).to_contain_text("exactly what the bot reported", timeout=20_000)
        expect(page.locator("#lCheckMark")).to_have_text("✓")
        self.sim(page)
        expect(page.locator("#statusText")).to_have_text("Finished")
        self.assert_clean()

    def test_live_tab_hostile_snapshot_stays_text(self):
        docs = _live_docs(halted=True, halt_reason=XSS_IMG)
        docs["bot/status"]["log"] = docs["bot/status"]["log"] + [XSS_SCRIPT, XSS_IMG]
        docs["bot/status"]["fills"][0]["note"] = XSS_SCRIPT
        page = self.load(init_script=_fake_claude(docs))
        expect(page.locator("#liveHalt")).to_be_visible()
        expect(page.locator("#liveHaltReason")).to_have_text(XSS_IMG)
        expect(page.locator("#lLog")).to_contain_text(XSS_SCRIPT)
        page.wait_for_timeout(200)
        self.assert_no_xss(page, XSS_IMG, XSS_SCRIPT)
        self.assert_clean()


if __name__ == "__main__":
    unittest.main()
