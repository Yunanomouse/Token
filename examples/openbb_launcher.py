#!/usr/bin/env python3
"""Open the OpenBB Workspace UI in a Chromium-family browser.

Setup (one time):  nothing to install — standard library only. You do need a
                   Chromium, Chrome, Edge, or Brave binary somewhere on the
                   machine; the script finds it for you.
Run:               python examples/openbb_launcher.py
                   python examples/openbb_launcher.py --mode borderless
                   python examples/openbb_launcher.py --mode fullscreen --kiosk
                   python examples/openbb_launcher.py --url http://127.0.0.1:6900

Three display modes:
    window      normal browser window, tabs and address bar included
    borderless  Chromium "app mode" — no tabs or address bar, still movable
    fullscreen  fills the screen; add --kiosk to lock it down (no F11 exit)

Use --dry-run to print the exact command without launching anything, which is
also how you check that browser detection picked the binary you expected.

Exits 2 when the URL is rejected or no browser could be found, so a failure is
visible to whatever ran the script.
"""

import argparse
import os
import platform
import shlex
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_URL = "https://pro.openbb.co"

# Tried in order, after the Playwright and platform paths below.
PATH_NAMES = [
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
    "brave-browser",
    "microsoft-edge",
]

# Playwright names its download directories chromium-<build>, so glob rather
# than pin a build number. chromium_headless_shell-* is deliberately not
# matched: it has no window to show.
PLAYWRIGHT_GLOBS = {
    "Linux": ["chromium-*/chrome-linux/chrome", "chromium/chrome-linux/chrome"],
    "Darwin": [
        "chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium",
        "chromium/chrome-mac/Chromium.app/Contents/MacOS/Chromium",
    ],
    "Windows": ["chromium-*/chrome-win/chrome.exe", "chromium/chrome-win/chrome.exe"],
}

PLATFORM_PATHS = {
    "Linux": [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/microsoft-edge",
        "/usr/bin/brave-browser",
        "/snap/bin/chromium",
        "/opt/google/chrome/chrome",
        "/opt/microsoft/msedge/msedge",
        "/opt/brave.com/brave/brave",
    ],
    "Darwin": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    ],
    "Windows": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    ],
}


def _playwright_roots() -> list[Path]:
    """Where Playwright keeps downloaded browsers on this machine."""
    override = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if override and override != "0":
        return [Path(override)]

    system = platform.system()
    if system == "Darwin":
        return [Path.home() / "Library" / "Caches" / "ms-playwright"]
    if system == "Windows":
        local = os.environ.get("LOCALAPPDATA")
        return [Path(local) / "ms-playwright"] if local else []
    return [Path.home() / ".cache" / "ms-playwright"]


def _windows_local_paths() -> list[Path]:
    """Per-user installs under %LOCALAPPDATA%, which Chrome prefers."""
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return []
    base = Path(local)
    return [
        base / "Google" / "Chrome" / "Application" / "chrome.exe",
        base / "Chromium" / "Application" / "chrome.exe",
        base / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        base / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
    ]


def candidate_paths() -> list[Path]:
    """Every absolute location worth checking, in priority order."""
    system = platform.system()
    candidates: list[Path] = []

    for root in _playwright_roots():
        for pattern in PLAYWRIGHT_GLOBS.get(system, PLAYWRIGHT_GLOBS["Linux"]):
            # Newest build first, so a stale download is not preferred.
            candidates.extend(sorted(root.glob(pattern), reverse=True))

    candidates.extend(Path(p) for p in PLATFORM_PATHS.get(system, []))
    if system == "Windows":
        candidates.extend(_windows_local_paths())
    return candidates


def find_browser() -> str | None:
    """First usable Chromium-family binary, or None if there is none."""
    for path in candidate_paths():
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)

    for name in PATH_NAMES:
        found = shutil.which(name)
        if found:
            return found
    return None


def searched_description() -> str:
    """Human-readable list of everything find_browser() looked at."""
    lines = [f"  {path}" for path in candidate_paths()]
    lines.append("  on PATH: " + ", ".join(PATH_NAMES))
    return "\n".join(lines)


def validate_url(url: str) -> str:
    """Only http(s) — file:// and javascript: would run local content."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"unsupported URL scheme {parsed.scheme or '(none)'!r} in {url!r}; "
            "only http:// and https:// are allowed"
        )
    if not parsed.netloc:
        raise ValueError(f"URL {url!r} has no host")
    return url


def parse_position(text: str) -> str:
    """Accept "X,Y" and hand back the same string, validated."""
    parts = text.split(",")
    if len(parts) != 2:
        raise ValueError(f"--position expects X,Y (got {text!r})")
    try:
        x, y = (int(p.strip()) for p in parts)
    except ValueError:
        raise ValueError(f"--position expects two integers (got {text!r})") from None
    return f"{x},{y}"


def build_command(browser: str, args: argparse.Namespace) -> list[str]:
    """Map the chosen mode onto Chromium's command-line flags."""
    command = [browser]

    if args.profile:
        command.append(f"--user-data-dir={Path(args.profile).expanduser()}")

    if args.mode == "fullscreen":
        command.append("--kiosk" if args.kiosk else "--start-fullscreen")
    else:
        # Size and position are ignored by a fullscreen window.
        if args.width and args.height:
            command.append(f"--window-size={args.width},{args.height}")
        if args.position:
            command.append(f"--window-position={args.position}")

    if args.mode == "borderless":
        # --app= already drops the tab strip and address bar.
        command.append(f"--app={args.url}")
    else:
        command.append(args.url)
    return command


def launch(command: list[str], wait: bool) -> int:
    """Start the browser; return an exit code for the caller."""
    kwargs: dict[str, object] = {}
    if not wait:
        # Survive the parent shell closing, and keep Chromium's chatter off
        # the terminal we are handing straight back to the user.
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
        if os.name == "posix":
            kwargs["start_new_session"] = True

    try:
        process = subprocess.Popen(command, **kwargs)  # noqa: S603 - no shell
    except OSError as exc:
        print(f"Could not start {command[0]}: {exc}", file=sys.stderr)
        return 2

    if wait:
        return process.wait()

    print(f"Launched {command[0]} (pid {process.pid}).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Open the OpenBB Workspace UI in a Chromium-family browser.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  %(prog)s --mode borderless --width 1400 --height 900\n"
            "  %(prog)s --mode fullscreen --kiosk --url http://127.0.0.1:6900\n"
            "  %(prog)s --dry-run --mode window\n"
        ),
    )
    parser.add_argument(
        "--mode",
        choices=("window", "borderless", "fullscreen"),
        default="window",
        help="display mode (default: %(default)s)",
    )
    parser.add_argument(
        "--url", default=DEFAULT_URL, help="http(s) URL to open (default: %(default)s)"
    )
    parser.add_argument(
        "--browser", help="path to a browser binary, overriding auto-detection"
    )
    parser.add_argument(
        "--width", type=int, help="window width (window and borderless modes)"
    )
    parser.add_argument(
        "--height", type=int, help="window height (window and borderless modes)"
    )
    parser.add_argument(
        "--position", help='window position as "X,Y" (window and borderless modes)'
    )
    parser.add_argument(
        "--profile", help="directory for a dedicated browser profile (--user-data-dir)"
    )
    parser.add_argument(
        "--kiosk",
        action="store_true",
        help="locked-down kiosk mode; requires --mode fullscreen",
    )
    parser.add_argument(
        "--wait", action="store_true", help="block until the browser exits"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the command that would run, then exit",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.kiosk and args.mode != "fullscreen":
        parser.error(f"--kiosk requires --mode fullscreen (got --mode {args.mode})")

    try:
        args.url = validate_url(args.url)
        if args.position:
            args.position = parse_position(args.position)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if (args.width is None) != (args.height is None):
        print("error: --width and --height must be given together", file=sys.stderr)
        return 2

    browser = args.browser or find_browser()

    if browser and not Path(browser).is_file() and not shutil.which(browser):
        print(f"error: browser {browser!r} does not exist", file=sys.stderr)
        return 2

    if browser is None:
        if args.mode != "window":
            print(
                f"error: no Chromium-family browser found, and --mode "
                f"{args.mode} needs one for its command-line flags.\n"
                f"Searched:\n{searched_description()}\n"
                "Install Chrome, Chromium, Edge, or Brave, or pass --browser "
                "with an explicit path.",
                file=sys.stderr,
            )
            return 2

        # Window mode is the one mode plain webbrowser can still deliver;
        # --width/--height/--position/--profile have no equivalent there.
        print(
            "No Chromium-family browser found; falling back to the system "
            "default browser. Size, position, and profile options are ignored."
        )
        if args.dry_run:
            print(f"Would open {args.url} in the default browser.")
            return 0
        return 0 if webbrowser.open(args.url) else 2

    command = build_command(browser, args)

    if args.dry_run:
        print(shlex.join(command))
        return 0

    return launch(command, args.wait)


if __name__ == "__main__":
    sys.exit(main())
