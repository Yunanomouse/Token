"""Paper Trading as a desktop program: the trading screen in its own window.

Starts the local server (``paper_app``) and shows its page in a program
window of its own, with its own taskbar entry, not in a browser.  On Windows
the window is drawn by Microsoft Edge WebView2, which Windows 10 and 11
include.  Closing the window stops the program.

If no window can be opened (WebView2 missing, or pywebview not installed when
run from source), the page opens in the default browser instead, and a
message box (Windows) or this console says how to stop it.

    python window.py                 # the window
    python window.py --browser       # the browser instead
    python window.py --headless      # the server only, until stopped (for tests)
    python window.py --smoke 60      # open the window, check the page connects, exit 0 or 1

The installed program (``Paper Trading.exe``) is this file, built by
packaging/build.py.  It keeps the account in your user folder:
%APPDATA%\\Paper Trading on Windows (``QT_PAPER_HOME`` or ``--home`` override).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path

import paper_app

TITLE = "Paper Trading (pretend money)"
FROZEN = bool(getattr(sys, "frozen", False))


def data_home() -> Path | None:
    """Where the installed program keeps the account; None means paper_app's
    own default (``QT_PAPER_HOME``, else paper_data/ next to the files)."""
    if os.environ.get("QT_PAPER_HOME") or not FROZEN:
        return None
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "Paper Trading"


def account_home(home: Path | None) -> Path:
    """The folder the account (and the log and window data) will be in."""
    return Path(home or os.environ.get("QT_PAPER_HOME") or Path(paper_app.HERE) / "paper_data")


def is_paper_trading(port: int, timeout: float = 3.0) -> bool:
    """True if Paper Trading already answers on this port."""
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/account", headers={"Host": f"127.0.0.1:{port}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return "starting_cash" in json.loads(r.read())
    except (OSError, ValueError):
        return False


def start_server(port: int, home: Path | str | None):
    """(server, url).  server is None when a copy already running on ``port``
    is reused; another program on the port means a free port is used."""
    try:
        server = paper_app.serve(port, open_browser=False, home=home, block=False)
    except OSError:
        if is_paper_trading(port):
            return None, f"http://127.0.0.1:{port}/"
        server = paper_app.serve(0, open_browser=False, home=home, block=False)
    return server, f"http://127.0.0.1:{server.server_address[1]}/"


def stop_server(server) -> None:
    if server is not None:
        server.stop_refresh.set()
        server.shutdown()
        server.server_close()


def message_box(text: str, title: str = TITLE) -> None:
    """A Windows message box (blocks until OK); elsewhere, the console."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, text, title, 0x40)  # MB_ICONINFORMATION
            return
        except Exception:
            pass
    print(text)
    if sys.stdin is not None and sys.stdin.isatty():
        try:
            input("Press Enter to stop Paper Trading. ")
            return
        except EOFError:
            pass
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


def open_window(url: str, storage: Path, smoke: float | None = None) -> bool | None:
    """Show ``url`` in a program window until it is closed.

    Returns None if no window could be opened.  With ``smoke`` (seconds), the
    window closes itself once the page shows "connected", and the result is
    True (it did) or False (it didn't in time)."""
    try:
        import webview
    except ImportError:
        return None
    result = {"ok": False}

    def check(window) -> None:
        deadline = time.monotonic() + smoke
        try:
            window.events.loaded.wait(smoke)
            while time.monotonic() < deadline:
                text = window.evaluate_js("(document.getElementById('conn') || {}).textContent || ''")
                if isinstance(text, str) and text.strip() == "connected":
                    result["ok"] = True
                    break
                time.sleep(0.5)
        finally:
            window.destroy()

    try:
        window = webview.create_window(TITLE, url, width=1320, height=900, min_size=(400, 600),
                                       text_select=True, zoomable=True)
        storage.mkdir(parents=True, exist_ok=True)
        # Not private: the page remembers its last tab (localStorage) between runs.
        webview.start(check if smoke else None, (window,) if smoke else None,
                      private_mode=False, storage_path=str(storage))
    except Exception:
        traceback.print_exc()
        return None
    return result["ok"] if smoke else True


def _log_to_file(home: Path | None) -> None:
    """The built program has no console: keep what it prints in a log."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    folder = account_home(home)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        log = open(folder / "paper_trading.log", "a", encoding="utf-8", buffering=1)
    except OSError:
        return
    sys.stdout = sys.stdout or log
    sys.stderr = sys.stderr or log
    print(f"--- started {time.strftime('%Y-%m-%d %H:%M:%S')}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="Paper Trading", description=__doc__.split("\n")[0])
    ap.add_argument("--port", type=int, default=paper_app.DEFAULT_PORT)
    ap.add_argument("--home", default=None, help="the account folder")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--browser", action="store_true", help="open in the browser instead of a window")
    mode.add_argument("--headless", action="store_true", help="run the server only, until stopped")
    mode.add_argument("--smoke", type=float, metavar="SECONDS", help="check the window works, then exit")
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)

    home = Path(args.home) if args.home else data_home()
    _log_to_file(home)
    try:
        server, url = start_server(args.port, home)
    except Exception as exc:
        traceback.print_exc()
        message_box(f"Paper Trading could not start:\n\n{exc}")
        return 1
    # The window's own data (the remembered tab) sits beside the account.
    storage = (server.book.home if server is not None else account_home(home)) / ".window"
    try:
        if args.headless:
            print(f"serving {url} (Ctrl-C to stop)")
            try:
                while True:
                    time.sleep(3600)
            except KeyboardInterrupt:
                return 0
        if not args.browser:
            shown = open_window(url, storage, smoke=args.smoke)
            if args.smoke is not None:
                print("window: page connected" if shown else "window: FAILED")
                return 0 if shown else 1
            if shown:
                return 0
            print("No program window could be opened; using the browser.")
        webbrowser.open(url)
        message_box("Paper Trading is open in your web browser at\n"
                    f"{url}\n\n"
                    + ("" if args.browser else
                       "(It couldn't open its own window. On Windows, installing Microsoft Edge WebView2 "
                       "from https://developer.microsoft.com/microsoft-edge/webview2/ fixes that.)\n\n")
                    + "Click OK to stop Paper Trading. Your account is saved.")
        return 0
    finally:
        stop_server(server)


if __name__ == "__main__":
    sys.exit(main())
