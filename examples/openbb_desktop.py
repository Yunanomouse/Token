#!/usr/bin/env python3
"""A small desktop price viewer for OpenBB data: windowed, borderless, or fullscreen.

Setup (one time):  pip install openbb
                   Tkinter ships with python.org and Windows installers; on
                   Debian/Ubuntu it is a separate package (python3-tk).
Run:               python examples/openbb_desktop.py AAPL
                   python examples/openbb_desktop.py SHOP.TO --days 180 --mode fullscreen
                   python examples/openbb_desktop.py AAPL --csv examples/market_data/AAPL.csv
                   python examples/openbb_desktop.py --demo          (no network, no openbb)

Data comes from the same call examples/openbb_quickstart.py uses — the free
Yahoo Finance provider, so no API key is needed. See docs/openbb_setup.md.

Display modes (switchable at run time, in any order):
    windowed     normal OS window, resizable, remembers its size
    borderless   no title bar; drag the in-app header strip to move it
    fullscreen   fills the screen without grabbing -topmost

Keys: F11/F fullscreen · B borderless · W windowed · Esc back to windowed ·
Ctrl+Q (Cmd+Q) quit. The same three modes are buttons in the header.

The chart is drawn directly on a Tkinter canvas — no matplotlib, no Qt, nothing
outside the standard library except OpenBB itself.
"""

from __future__ import annotations

import argparse
import csv
import random
import re
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

# Imported here rather than in main() so the whole module can be linted and
# byte-compiled on a machine without Tk; main() turns the missing module into a
# readable message *after* argparse, which keeps --help working either way.
try:
    import tkinter as tk
except ImportError:  # pragma: no cover - depends on the Python build
    tk = None  # type: ignore[assignment]

TK_MISSING = """\
This viewer needs Tkinter, which is missing from this Python installation.

  Debian/Ubuntu : sudo apt install python3-tk
  Fedora        : sudo dnf install python3-tkinter
  macOS         : use the installer from python.org (Homebrew: brew install python-tk)
  Windows       : re-run the Python installer, "Modify", and tick "tcl/tk and IDLE"

Then run this script again."""

# Dark palette, picked so the chart reads on a projector as well as a laptop.
BG = "#11151c"
PANEL = "#1a212b"
GRID = "#2a3442"
TEXT = "#e6edf3"
MUTED = "#8b98a9"
LINE = "#4da3ff"
FILL = "#18293d"
UP = "#3fb950"
DOWN = "#f85149"
WARN = "#e3b341"

# "900x600+40+30", and Tk writes negative offsets as "+-40".
GEOMETRY_RE = re.compile(r"^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$")

MODES = ("windowed", "borderless", "fullscreen")
DEFAULT_GEOMETRY = "1100x700"


@dataclass
class Series:
    """A ticker's closes, or the reason there are none."""

    symbol: str
    dates: list[str] = field(default_factory=list)
    closes: list[float] = field(default_factory=list)
    source: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return len(self.closes) >= 2


def _one_line(exc: Exception) -> str:
    """OpenBB errors are multi-line and often start with a newline."""
    text = " ".join(str(exc).split())
    return text or type(exc).__name__


def _stamp(value: object) -> str:
    """Index entries arrive as dates, Timestamps or strings depending on provider."""
    text = str(value)
    return text[:10]


def fetch_series(symbol: str, days: int) -> Series:
    """Pull daily closes from OpenBB, reporting failures instead of raising."""
    try:
        # Lazy: importing openbb costs seconds and may not be installed at all,
        # and neither should stop the window from opening.
        from openbb import obb
    except Exception as exc:  # noqa: BLE001 - ImportError or a broken install
        return Series(symbol, error=f"OpenBB is not available: {_one_line(exc)}")

    start = date.today() - timedelta(days=days)
    try:
        result = obb.equity.price.historical(
            symbol, start_date=str(start), provider="yfinance"
        )
        df = result.to_df()
    except Exception as exc:  # noqa: BLE001 - network, symbol, provider, all alike
        return Series(symbol, error=_one_line(exc))

    if df.empty or "close" not in df:
        return Series(symbol, error=f"no rows returned for {symbol}")

    closes = [float(v) for v in df["close"].tolist()]
    dates = [_stamp(v) for v in df.index.tolist()]
    return Series(symbol, dates, closes, source=f"yfinance · {len(closes)} sessions")


def load_csv_series(path: Path, symbol: str) -> Series:
    """Read a CSV written by openbb_quickstart.py (or anything with a close column)."""
    try:
        with open(path, newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as exc:
        return Series(symbol, error=f"could not read {path}: {exc.strerror or exc}")

    if not rows:
        return Series(symbol, error=f"{path.name} has no rows")

    fields = list(rows[0].keys())
    close_key = next((f for f in fields if f and f.strip().lower() == "close"), "")
    if not close_key:
        return Series(symbol, error=f"{path.name} has no 'close' column")
    # df.to_csv() writes the date index as the first column, sometimes unnamed.
    date_key = next((f for f in fields if f and f.strip().lower() in {"date", "index"}), fields[0])

    dates: list[str] = []
    closes: list[float] = []
    for row in rows:
        try:
            closes.append(float(row[close_key]))
        except (TypeError, ValueError):
            continue  # blank or non-numeric line; skip rather than abort the load
        dates.append(_stamp(row.get(date_key, "")))

    if len(closes) < 2:
        return Series(symbol, error=f"{path.name} has fewer than two usable closes")
    return Series(symbol, dates, closes, source=f"{path.name} · {len(closes)} rows")


def demo_series(symbol: str, days: int) -> Series:
    """A seeded random walk, for exercising the UI with no network and no OpenBB.

    Seeded from the symbol so the same ticker always draws the same chart —
    a moving fake chart makes UI bugs impossible to reproduce.
    """
    rng = random.Random(sum(ord(c) for c in symbol.upper()) or 1)
    price = 50.0 + rng.random() * 200.0
    today = date.today()
    dates: list[str] = []
    closes: list[float] = []
    for offset in range(max(days, 2), 0, -1):
        day = today - timedelta(days=offset)
        if day.weekday() >= 5 and days >= 7:
            continue  # weekends have no closes, but a tiny window needs every day
        price = max(1.0, price * (1.0 + rng.gauss(0.0004, 0.014)))
        dates.append(day.isoformat())
        closes.append(round(price, 2))
    return Series(symbol, dates, closes, source=f"demo data · {len(closes)} sessions")


def build_series(args: argparse.Namespace) -> Series:
    if args.csv:
        series = load_csv_series(Path(args.csv), args.ticker)
    elif args.demo:
        series = demo_series(args.ticker, args.days)
    else:
        series = fetch_series(args.ticker, args.days)

    if series.error and args.demo:
        # Only an explicit --demo may paper over a failure with synthetic prices;
        # otherwise the error stays on screen so nobody trades off a random walk.
        series = demo_series(args.ticker, args.days)
    return series


class PriceChart:
    """A line chart drawn straight onto a canvas, redrawn on every resize."""

    def __init__(self, parent: "tk.Misc", series: Series) -> None:
        self.series = series
        self.canvas = tk.Canvas(parent, bg=BG, highlightthickness=0, bd=0)
        self._size = (0, 0)
        self.canvas.bind("<Configure>", self._on_configure)

    def _on_configure(self, event: "tk.Event") -> None:
        # Tk fires <Configure> for moves and restacks too; only geometry matters.
        size = (event.width, event.height)
        if size != self._size:
            self._size = size
            self.redraw()

    def set_series(self, series: Series) -> None:
        self.series = series
        self.redraw()

    def redraw(self) -> None:
        canvas = self.canvas
        canvas.delete("all")
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width < 40 or height < 40:
            return  # not mapped yet; the next <Configure> will land here again

        if not self.series.ok:
            self._draw_placeholder(width, height)
            return

        left, right, top, bottom = 24, 86, 96, 44
        plot_w = width - left - right
        plot_h = height - top - bottom
        if plot_w < 40 or plot_h < 40:
            return

        closes = self.series.closes
        low, high = min(closes), max(closes)
        span = high - low or max(abs(high), 1.0) * 0.02  # flat series still needs a scale
        low, high = low - span * 0.08, high + span * 0.08
        span = high - low

        def x_at(index: int) -> float:
            if len(closes) == 1:
                return left + plot_w / 2
            return left + plot_w * index / (len(closes) - 1)

        def y_at(value: float) -> float:
            return top + plot_h * (high - value) / span

        for step in range(5):
            value = high - span * step / 4
            y = y_at(value)
            canvas.create_line(left, y, left + plot_w, y, fill=GRID)
            canvas.create_text(
                left + plot_w + 10, y, text=f"{value:,.2f}", anchor="w",
                fill=MUTED, font=("TkDefaultFont", 9),
            )

        points: list[float] = []
        for index, value in enumerate(closes):
            points.extend((x_at(index), y_at(value)))

        base = top + plot_h
        canvas.create_polygon(
            [left, base, *points, left + plot_w, base],
            fill=FILL, outline="",
        )
        canvas.create_line(*points, fill=LINE, width=2, smooth=False)

        if self.series.dates:
            canvas.create_text(
                left, base + 16, text=self.series.dates[0], anchor="w",
                fill=MUTED, font=("TkDefaultFont", 9),
            )
            canvas.create_text(
                left + plot_w, base + 16, text=self.series.dates[-1], anchor="e",
                fill=MUTED, font=("TkDefaultFont", 9),
            )

        self._draw_readout(left, closes)

    def _draw_readout(self, left: int, closes: list[float]) -> None:
        last = closes[-1]
        change = last - closes[-2]
        pct = change / closes[-2] * 100 if closes[-2] else 0.0
        period = (last / closes[0] - 1) * 100 if closes[0] else 0.0
        colour = UP if change >= 0 else DOWN

        canvas = self.canvas
        canvas.create_text(
            left, 20, text=self.series.symbol.upper(), anchor="nw",
            fill=TEXT, font=("TkDefaultFont", 17, "bold"),
        )
        canvas.create_text(
            left, 46, text=f"{last:,.2f}", anchor="nw",
            fill=TEXT, font=("TkDefaultFont", 26, "bold"),
        )
        canvas.create_text(
            left + 150, 56, text=f"{change:+,.2f}  ({pct:+.2f}%)", anchor="nw",
            fill=colour, font=("TkDefaultFont", 13, "bold"),
        )
        canvas.create_text(
            left + 150, 76, text=f"period {period:+.2f}%  ·  {self.series.source}",
            anchor="nw", fill=MUTED, font=("TkDefaultFont", 9),
        )

    def _draw_placeholder(self, width: int, height: int) -> None:
        """No data is a state to render, not a crash and not a blank window."""
        message = self.series.error or "no price data"
        self.canvas.create_text(
            width / 2, height / 2 - 30, text=self.series.symbol.upper(),
            fill=TEXT, font=("TkDefaultFont", 20, "bold"),
        )
        self.canvas.create_text(
            width / 2, height / 2 + 4, text="Could not load prices",
            fill=WARN, font=("TkDefaultFont", 13, "bold"),
        )
        self.canvas.create_text(
            width / 2, height / 2 + 34, text=message, fill=MUTED,
            font=("TkDefaultFont", 10), width=max(width - 120, 200), justify="center",
        )
        self.canvas.create_text(
            width / 2, height / 2 + 84,
            text="Display modes still work — try F11, B, W, Esc. "
                 "Re-run with --demo for sample data.",
            fill=MUTED, font=("TkDefaultFont", 9),
        )


class DesktopApp:
    """The window itself: header strip, chart, and the three display modes."""

    def __init__(self, series: Series, mode: str = "windowed") -> None:
        self.root = tk.Tk()
        self.root.title(f"{series.symbol.upper()} — OpenBB desktop")
        self.root.configure(bg=BG)
        self.root.geometry(DEFAULT_GEOMETRY)
        self.root.minsize(520, 340)
        self.mode = "windowed"
        self._windowed_geometry = DEFAULT_GEOMETRY
        self._drag_origin: tuple[int, int, int, int] | None = None

        self._build_header()
        self.chart = PriceChart(self.root, series)
        self.chart.canvas.pack(fill="both", expand=True)

        self._bind_keys()
        self.set_mode(mode)

    # ---------------------------------------------------------------- layout

    def _build_header(self) -> None:
        self.header = tk.Frame(self.root, bg=PANEL, height=44)
        self.header.pack(fill="x", side="top")
        self.header.pack_propagate(False)

        self.hint = tk.Label(
            self.header, text="", bg=PANEL, fg=MUTED, font=("TkDefaultFont", 9),
            anchor="w", padx=12,
        )
        self.hint.pack(side="left", fill="y")

        self.buttons: dict[str, tk.Button] = {}
        for label, mode in (("Windowed", "windowed"),
                            ("Borderless", "borderless"),
                            ("Fullscreen", "fullscreen")):
            button = tk.Button(
                self.header, text=label, command=lambda m=mode: self.set_mode(m),
                bg=PANEL, fg=TEXT, activebackground=GRID, activeforeground=TEXT,
                relief="flat", bd=0, highlightthickness=0, padx=12, pady=4,
                font=("TkDefaultFont", 9),
            )
            button.pack(side="left", padx=3, pady=8)
            self.buttons[mode] = button

        # Borderless windows have no OS close box, so the app must supply one.
        tk.Button(
            self.header, text="✕", command=self.quit, bg=PANEL, fg=MUTED,
            activebackground=DOWN, activeforeground=TEXT, relief="flat", bd=0,
            highlightthickness=0, padx=12, pady=4, font=("TkDefaultFont", 11),
        ).pack(side="right", padx=(3, 8), pady=8)

        # The header strip doubles as the drag handle in borderless mode.
        for widget in (self.header, self.hint):
            widget.bind("<ButtonPress-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_move)
            widget.bind("<ButtonRelease-1>", self._drag_end)

    def _bind_keys(self) -> None:
        root = self.root
        root.bind("<F11>", lambda _e: self.toggle_fullscreen())
        root.bind("<KeyPress-f>", lambda _e: self.toggle_fullscreen())
        root.bind("<KeyPress-F>", lambda _e: self.toggle_fullscreen())
        root.bind("<KeyPress-b>", lambda _e: self.set_mode("borderless"))
        root.bind("<KeyPress-B>", lambda _e: self.set_mode("borderless"))
        root.bind("<KeyPress-w>", lambda _e: self.set_mode("windowed"))
        root.bind("<KeyPress-W>", lambda _e: self.set_mode("windowed"))
        root.bind("<Escape>", lambda _e: self.set_mode("windowed"))
        root.bind("<Control-q>", lambda _e: self.quit())
        root.bind("<Control-Q>", lambda _e: self.quit())
        try:
            root.bind("<Command-q>", lambda _e: self.quit())  # macOS
        except tk.TclError:  # pragma: no cover - older Tk without the modifier
            pass
        root.protocol("WM_DELETE_WINDOW", self.quit)

    # ----------------------------------------------------------------- modes

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            return
        if mode == self.mode:
            self._refresh_header()
            return

        if self.mode == "windowed":
            # Save before leaving: geometry() reports the fullscreen/borderless
            # size once the switch has happened, which would lose the real one.
            self.root.update_idletasks()
            self._windowed_geometry = self.root.geometry()

        was_borderless = self.mode == "borderless"
        self.root.attributes("-fullscreen", False)
        self.root.overrideredirect(False)

        if was_borderless:
            # Some window managers only re-decorate on a fresh map.
            self.root.withdraw()
            self.root.deiconify()

        if mode == "fullscreen":
            # Deliberately no "-topmost": that turns a viewer into a window that
            # fights every dialog and notification on the desktop.
            self.root.attributes("-fullscreen", True)
        elif mode == "borderless":
            self.root.overrideredirect(True)
            self.root.geometry(self._windowed_geometry)
        else:
            self.root.geometry(self._windowed_geometry)

        self.mode = mode
        self._refresh_header()
        # overrideredirect() can leave the window unmanaged and therefore without
        # keyboard focus on several window managers, which would kill the Esc/W
        # escape hatch. Forcing focus after every switch keeps the keys alive.
        self.root.focus_force()
        self.root.after_idle(self.chart.redraw)

    def toggle_fullscreen(self) -> None:
        self.set_mode("windowed" if self.mode == "fullscreen" else "fullscreen")

    def _refresh_header(self) -> None:
        for mode, button in self.buttons.items():
            active = mode == self.mode
            button.configure(
                bg=GRID if active else PANEL,
                fg=TEXT if active else MUTED,
            )
        hint = "F11 fullscreen · B borderless · W windowed · Esc back · Ctrl+Q quit"
        if self.mode == "borderless":
            hint = "Drag this bar to move · " + hint
        self.hint.configure(text=hint)

    # ------------------------------------------------------------- dragging

    def _window_position(self) -> tuple[int, int]:
        """Window origin as geometry() reports it.

        Not winfo_x()/winfo_y(): under reparenting window managers those can be
        frame-relative, and mixing them with geometry() makes a drag jump by the
        width of the title bar on the first motion event.
        """
        match = GEOMETRY_RE.match(self.root.geometry())
        if not match:  # not mapped yet, so there is nothing to drag from
            return self.root.winfo_x(), self.root.winfo_y()
        return int(match.group(3)), int(match.group(4))

    def _drag_start(self, event: "tk.Event") -> None:
        # Remember where the press happened and where the window was; motion is
        # then applied as a delta, so the window never jumps on grab.
        self._drag_origin = (event.x_root, event.y_root, *self._window_position())

    def _drag_move(self, event: "tk.Event") -> None:
        if self._drag_origin is None or self.mode != "borderless":
            return  # in windowed mode the WM already handles moving
        press_x, press_y, win_x, win_y = self._drag_origin
        self.root.geometry(
            f"+{win_x + event.x_root - press_x}+{win_y + event.y_root - press_y}"
        )

    def _drag_end(self, _event: "tk.Event") -> None:
        self._drag_origin = None

    # ---------------------------------------------------------------- driving

    def quit(self) -> None:
        self.root.destroy()

    def run(self) -> None:
        self.root.after(60, self.chart.redraw)  # first paint once Tk knows the size
        self.root.mainloop()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Tkinter desktop viewer for OpenBB price data.",
        epilog="Keys: F11/F fullscreen, B borderless, W windowed, Esc windowed, Ctrl+Q quit.",
    )
    parser.add_argument("ticker", nargs="?", default="AAPL",
                        help="Yahoo symbol, e.g. AAPL, SHOP.TO, BTC-USD (default: AAPL)")
    parser.add_argument("--days", type=int, default=365,
                        help="days of history to fetch (default: 365)")
    parser.add_argument("--mode", choices=MODES, default="windowed",
                        help="display mode at startup (default: windowed)")
    parser.add_argument("--csv", metavar="PATH",
                        help="read a saved CSV instead of calling the network")
    parser.add_argument("--demo", action="store_true",
                        help="use seeded synthetic prices; needs neither openbb nor a network")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)  # before the Tk check, so --help works without Tk

    if tk is None:
        print(TK_MISSING, file=sys.stderr)
        return 2
    if args.days < 2:
        print("--days needs to be at least 2 to draw a line.", file=sys.stderr)
        return 1

    series = build_series(args)
    if series.error:
        print(f"{series.symbol}: {series.error}", file=sys.stderr)

    try:
        app = DesktopApp(series, args.mode)
    except tk.TclError as exc:
        # Almost always a headless machine: no DISPLAY, no window to open.
        print(f"Could not open a window: {_one_line(exc)}", file=sys.stderr)
        return 2

    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
