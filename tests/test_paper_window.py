"""Paper Trading's desktop launcher (paper_trading/window.py).

The window library (pywebview) is replaced by a stand-in, so these run
anywhere without a display; the real window is exercised by the Windows
build in .github/workflows/paper-trading-app.yml (``--smoke``).
"""

import json
import sys
import tempfile
import types
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "paper_trading"))
import paper_app  # noqa: E402
import window  # noqa: E402


class FakeWindow:
    def __init__(self, page_text):
        self.page_text = page_text
        self.destroyed = False
        self.events = types.SimpleNamespace(loaded=types.SimpleNamespace(wait=lambda t: True))

    def evaluate_js(self, js):
        return self.page_text

    def destroy(self):
        self.destroyed = True


def fake_webview(page_text="connected", fail=False):
    mod = types.ModuleType("webview")
    mod.made = []

    def create_window(title, url, **kw):
        w = FakeWindow(page_text)
        w.title, w.url, w.kw = title, url, kw
        mod.made.append(w)
        return w

    def start(func=None, args=None, **kw):
        mod.start_kw = kw
        if fail:
            raise RuntimeError("WebView2 runtime not found")
        if func:
            func(*args)

    mod.create_window, mod.start = create_window, start
    return mod


class TestDataHome(unittest.TestCase):
    def test_from_source_the_account_stays_next_to_the_files(self):
        with mock.patch.object(window, "FROZEN", False), mock.patch.dict("os.environ", {}, clear=False):
            self.assertIsNone(window.data_home())

    def test_installed_program_uses_the_user_folder(self):
        with mock.patch.object(window, "FROZEN", True), mock.patch.object(sys, "platform", "win32"), \
                mock.patch.dict("os.environ", {"APPDATA": r"C:\Users\me\AppData\Roaming"}):
            import os
            os.environ.pop("QT_PAPER_HOME", None)
            self.assertEqual(window.data_home(), Path(r"C:\Users\me\AppData\Roaming") / "Paper Trading")

    def test_qt_paper_home_wins(self):
        with mock.patch.object(window, "FROZEN", True), mock.patch.dict("os.environ", {"QT_PAPER_HOME": "/x"}):
            self.assertIsNone(window.data_home())  # paper_app reads QT_PAPER_HOME itself


class TestServer(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        quiet = mock.patch("builtins.print")
        quiet.start()
        self.addCleanup(quiet.stop)

    def tearDown(self):
        self._tmp.cleanup()

    def test_starts_and_stops(self):
        server, url = window.start_server(0, self.home)
        try:
            self.assertEqual(url, f"http://127.0.0.1:{server.server_address[1]}/")
            self.assertTrue(window.is_paper_trading(server.server_address[1]))
        finally:
            window.stop_server(server)

    def test_a_running_copy_is_reused(self):
        first, url = window.start_server(0, self.home)
        try:
            port = first.server_address[1]
            server, url2 = window.start_server(port, self.home / "other")
            self.assertIsNone(server)
            self.assertEqual(url2, f"http://127.0.0.1:{port}/")
            self.assertFalse((self.home / "other").exists())
        finally:
            window.stop_server(first)

    def test_another_program_on_the_port_means_another_port(self):
        other = paper_app.PaperServer(("127.0.0.1", 0), None)  # answers, but isn't Paper Trading
        self.addCleanup(other.server_close)
        port = other.server_address[1]
        server, url = window.start_server(port, self.home)
        try:
            self.assertIsNotNone(server)
            self.assertNotEqual(server.server_address[1], port)
        finally:
            window.stop_server(server)


class TestWindow(unittest.TestCase):
    def test_no_window_library_means_none(self):
        with mock.patch.dict(sys.modules, {"webview": None}):
            self.assertIsNone(window.open_window("http://x/", Path(tempfile.mkdtemp())))

    def test_window_failure_means_none(self):
        with mock.patch.dict(sys.modules, {"webview": fake_webview(fail=True)}), \
                mock.patch("traceback.print_exc"):
            self.assertIsNone(window.open_window("http://x/", Path(tempfile.mkdtemp())))

    def test_window_settings(self):
        wv = fake_webview()
        store = Path(tempfile.mkdtemp()) / ".window"
        with mock.patch.dict(sys.modules, {"webview": wv}):
            self.assertTrue(window.open_window("http://127.0.0.1:1/", store))
        w = wv.made[0]
        self.assertEqual((w.title, w.url), (window.TITLE, "http://127.0.0.1:1/"))
        self.assertIn("pretend money", w.title)
        self.assertEqual(wv.start_kw, {"private_mode": False, "storage_path": str(store)})
        self.assertTrue(store.is_dir())

    def test_smoke_passes_when_the_page_connects_and_closes_the_window(self):
        wv = fake_webview("connected")
        with mock.patch.dict(sys.modules, {"webview": wv}):
            self.assertTrue(window.open_window("http://x/", Path(tempfile.mkdtemp()), smoke=2))
        self.assertTrue(wv.made[0].destroyed)

    def test_smoke_fails_when_it_doesnt(self):
        wv = fake_webview("connecting…")
        with mock.patch.dict(sys.modules, {"webview": wv}), mock.patch("time.sleep"):
            self.assertFalse(window.open_window("http://x/", Path(tempfile.mkdtemp()), smoke=0.05))
        self.assertTrue(wv.made[0].destroyed)


class TestMain(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = self._tmp.name
        for p in (mock.patch("builtins.print"), mock.patch("webbrowser.open")):
            self.mocked = p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self._tmp.cleanup()

    def test_window_mode_serves_the_page_to_the_window_then_stops(self):
        seen = {}

        def fake_open(url, storage, smoke=None):
            req = urllib.request.Request(url + "api/account", headers={"Host": url[7:-1]})
            seen["account"] = json.loads(urllib.request.urlopen(req, timeout=5).read())
            seen["storage"] = storage
            return True

        with mock.patch.object(window, "open_window", fake_open):
            self.assertEqual(window.main(["--port", "0", "--home", self.home]), 0)
        self.assertEqual(seen["account"]["starting_cash"], 100000.0)
        self.assertEqual(seen["storage"], Path(self.home).resolve() / ".window")

    def test_no_window_falls_back_to_the_browser_and_says_how_to_stop(self):
        with mock.patch.object(window, "open_window", return_value=None), \
                mock.patch.object(window, "message_box") as box, mock.patch("webbrowser.open") as browser:
            self.assertEqual(window.main(["--port", "0", "--home", self.home]), 0)
        browser.assert_called_once()
        self.assertIn("WebView2", box.call_args[0][0])
        self.assertIn("Click OK to stop", box.call_args[0][0])

    def test_browser_mode(self):
        with mock.patch.object(window, "open_window") as win, \
                mock.patch.object(window, "message_box") as box, mock.patch("webbrowser.open") as browser:
            self.assertEqual(window.main(["--browser", "--port", "0", "--home", self.home]), 0)
        win.assert_not_called()
        browser.assert_called_once()
        self.assertNotIn("WebView2", box.call_args[0][0])

    def test_smoke_exit_codes(self):
        for shown, code in ((True, 0), (False, 1), (None, 1)):
            with self.subTest(shown=shown), mock.patch.object(window, "open_window", return_value=shown):
                self.assertEqual(window.main(["--smoke", "1", "--port", "0", "--home", self.home]), code)

    def test_a_start_failure_is_shown_not_swallowed(self):
        with mock.patch.object(window, "start_server", side_effect=PermissionError("folder is read-only")), \
                mock.patch.object(window, "message_box") as box, mock.patch("traceback.print_exc"):
            self.assertEqual(window.main(["--home", self.home]), 1)
        self.assertIn("folder is read-only", box.call_args[0][0])

    def test_no_console_writes_a_log(self):
        with mock.patch.object(sys, "stdout", None), mock.patch.object(sys, "stderr", None):
            window._log_to_file(Path(self.home))
            log = sys.stdout
            sys.stdout.write("hello\n")
            self.assertIs(sys.stderr, log)
        log.close()
        self.assertIn("hello", (Path(self.home) / "paper_trading.log").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
