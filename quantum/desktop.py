"""The desktop face of the engine: a local dashboard you double-click to open.

``python3 -m quantum desktop`` starts a small HTTP server on ``127.0.0.1``,
opens the dashboard in the default browser, and keeps serving until the
window is closed or the process is stopped.  The launchers at the repository
root (``Quantum Trading.bat``, ``quantum_trading.command``,
``quantum-trading.desktop``) do exactly that on a double-click.

Everything is the standard library plus the package: no web framework, no
JavaScript build, no dependency that can rot.  The page is one HTML file
embedded below; it polls ``/api/state`` once a second and draws the equity
curve, drawdown, positions, fills and log on a canvas.

The dashboard *controls* the engine in :mod:`quantum.live`.  It can start a
paper replay of a price CSV (at a chosen speed, so you can watch it trade),
start tailing a CSV for live bars, stop, and reset the state file.  It cannot
connect to a real venue: the same rule as the command line -- a
:class:`quantum.live.Broker` for your venue has to be written and passed in
code.  The status banner says PAPER on every screen for that reason.

Security note: the server binds to loopback only and has no authentication.
Anything on the same machine can drive it.  Do not bind it to a public
interface.
"""

from __future__ import annotations

import json
import os
import threading
import time
import webbrowser
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse

from .live import (
    Bar,
    Engine,
    EngineConfig,
    EngineState,
    FileFeed,
    PriceFeed,
    ReplayFeed,
    RiskLimits,
    trade_ledger,
)

__all__ = ["Controller", "DashboardServer", "serve", "DEFAULT_PORT"]

DEFAULT_PORT = 8765
DEFAULT_TICKERS = ["AAPL", "XOM", "JPM", "WMT", "PFE", "AMZN", "BAC", "T"]


# --------------------------------------------------------------------------
# Controller: owns the engine thread
# --------------------------------------------------------------------------


class _Stoppable(PriceFeed):
    """Wrap a feed so the engine loop can be interrupted and throttled."""

    def __init__(self, inner: PriceFeed, stop: threading.Event, bars_per_second: float | None) -> None:
        self.inner = inner
        self.stop = stop
        self.delay = (1.0 / bars_per_second) if bars_per_second and bars_per_second > 0 else 0.0
        self.tickers = inner.tickers

    def bars(self) -> Iterator[Bar]:
        for bar in self.inner.bars():
            if self.stop.is_set():
                return
            yield bar
            if self.delay:
                # Sleep in slices so a stop request lands within ~50 ms.
                end = time.monotonic() + self.delay
                while time.monotonic() < end:
                    if self.stop.is_set():
                        return
                    time.sleep(min(0.05, max(end - time.monotonic(), 0.0)))


class Controller:
    """Start, stop, reset and observe one engine.  Thread-safe for the UI."""

    def __init__(self, workdir: str | Path | None = None) -> None:
        self.workdir = Path(workdir or os.getcwd())
        self.lock = threading.Lock()
        self.engine: Engine | None = None
        self.config: EngineConfig | None = None
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.mode = "idle"
        self.error = ""
        self.source = ""
        self.started_at: float | None = None
        self.messages: list[str] = []

    # -- helpers -----------------------------------------------------------
    def _note(self, line: str) -> None:
        with self.lock:
            self.messages.append(f"{time.strftime('%H:%M:%S')} {line}")
            self.messages = self.messages[-200:]

    @property
    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def price_files(self) -> list[str]:
        found: list[str] = []
        for base in (self.workdir / "data" / "prices", self.workdir):
            if base.is_dir():
                found.extend(str(p.relative_to(self.workdir)) for p in sorted(base.glob("*.csv")))
        return found

    @staticmethod
    def config_from_form(form: dict) -> EngineConfig:
        tickers = form.get("tickers", DEFAULT_TICKERS)
        if isinstance(tickers, str):
            tickers = [t.strip().upper() for t in tickers.replace(";", ",").split(",") if t.strip()]
        limits = RiskLimits(
            max_weight=float(form.get("max_weight", 0.40)),
            max_turnover=float(form.get("max_turnover", 0.50)),
            max_drawdown=float(form.get("max_drawdown", 0.25)),
            rearm_after=int(form.get("rearm_after", 0)),
            min_history=int(form.get("window", 252)),
        )
        return EngineConfig(
            tickers=tickers,
            strategy=str(form.get("strategy", "cardinality")),
            cardinality=int(form.get("cardinality", 4)),
            risk_aversion=float(form.get("risk_aversion", 2.0)),
            solver=str(form.get("solver", "simulated_annealing")),
            window=int(form.get("window", 252)),
            rebalance_every=int(form.get("rebalance_every", 21)),
            initial_cash=float(form.get("initial_cash", 100_000.0)),
            fee_rate=float(form.get("fee_rate", 0.0005)),
            limits=limits,
            state_path=str(form.get("state_path", "live_state.json")),
            seed=int(form.get("seed", 0)),
        )

    # -- commands ----------------------------------------------------------
    def start(self, form: dict) -> dict:
        result = self._start(form)
        if not result.get("ok"):
            self._note(f"start refused: {result.get('error')}")
        return result

    def _start(self, form: dict) -> dict:
        if self.running:
            return {"ok": False, "error": "engine is already running; stop it first"}
        try:
            config = self.config_from_form(form)
        except (ValueError, TypeError) as exc:
            return {"ok": False, "error": f"bad config: {exc}"}
        mode = str(form.get("mode", "replay"))
        csv_path = self.workdir / str(form.get("csv", "data/prices/us_equities_1989_2018.csv"))
        if not csv_path.exists():
            return {"ok": False, "error": f"price file not found: {csv_path}"}
        state_path = self.workdir / config.state_path
        fresh = bool(form.get("fresh", False))
        try:
            state = EngineState.load(state_path) if state_path.exists() and not fresh else None
            if state is not None and state.tickers != config.tickers:
                return {"ok": False, "error": "the state file was written for different tickers; "
                                              "tick 'start fresh' or change the state file name"}
            engine = Engine(config, state=state, log=self._note)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": f"could not start: {exc}"}

        if mode == "replay":
            inner: PriceFeed = ReplayFeed(csv_path, config.tickers,
                                          start=form.get("start") or None, end=form.get("end") or None)
            if len(inner) == 0:
                return {"ok": False, "error": "no bars in that date range with all tickers present"}
            if engine.state.dates:
                # Resuming: drop bars the state already holds *before* the
                # throttle, so a paced replay does not sleep through history.
                last = engine.state.dates[-1]
                inner._bars = [b for b in inner._bars if b.date > last]
                if not inner._bars:
                    return {"ok": False, "error": f"nothing new to replay after {last}; tick 'start fresh' to rerun"}
            speed = form.get("bars_per_second")
            feed = _Stoppable(inner, self.stop_event, float(speed) if speed not in (None, "", 0, "0") else None)
            self.source = f"replay {csv_path.name} ({len(inner)} bars)"
        elif mode == "feed":
            last = engine.state.dates[-1] if engine.state.dates else None
            inner = FileFeed(csv_path, config.tickers, poll_seconds=float(form.get("poll_seconds", 5.0)), after=last)
            feed = _Stoppable(inner, self.stop_event, None)
            self.source = f"tailing {csv_path.name}"
        else:
            return {"ok": False, "error": f"unknown mode {mode!r}"}

        self.stop_event.clear()
        self.engine, self.config, self.mode, self.error = engine, config, mode, ""
        self.started_at = time.time()
        self._note(f"start {mode}: {self.source}, strategy {config.strategy}, {len(config.tickers)} tickers")

        def worker() -> None:
            try:
                engine.run(feed, state_path=state_path)
                if not self.stop_event.is_set():
                    self._note("finished: feed exhausted")
            except Exception as exc:  # surface, never hide, an engine crash
                self.error = f"{type(exc).__name__}: {exc}"
                self._note(f"ERROR {self.error}")
            finally:
                self.mode = "idle"

        self.thread = threading.Thread(target=worker, name="engine", daemon=True)
        self.thread.start()
        return {"ok": True}

    def stop(self) -> dict:
        if not self.running:
            return {"ok": True, "note": "not running"}
        self.stop_event.set()
        self.thread.join(timeout=30)
        self._note("stopped by user; state saved")
        return {"ok": not self.running}

    def reset(self, state_path: str = "live_state.json") -> dict:
        if self.running:
            return {"ok": False, "error": "stop the engine before resetting"}
        path = self.workdir / state_path
        if path.exists():
            path.unlink()
        self.engine = None
        self._note(f"reset: removed {path.name}")
        return {"ok": True}

    def resume_halt(self, state_path: str = "live_state.json") -> dict:
        """Clear the kill switch -- the one deliberate manual override."""
        if self.running:
            return {"ok": False, "error": "stop the engine first"}
        path = self.workdir / state_path
        if not path.exists():
            return {"ok": False, "error": "no state file"}
        state = EngineState.load(path)
        state.halted, state.halt_reason, state.peak_equity = False, "", (state.equity_curve[-1] if state.equity_curve else 0.0)
        state.save(path)
        self.engine = None  # snapshots read the file again until the next start
        self._note("kill switch cleared by user; peak reset to current equity")
        return {"ok": True}

    # -- observation -------------------------------------------------------
    def snapshot(self, state_path: str = "live_state.json", points: int = 600) -> dict:
        engine = self.engine
        state = engine.state if engine else None
        if state is None:
            path = self.workdir / state_path
            if path.exists():
                try:
                    state = EngineState.load(path)
                except (OSError, json.JSONDecodeError, TypeError):
                    state = None
        out = {
            "running": self.running,
            "mode": self.mode if self.running else "idle",
            "source": self.source if self.running else "",
            "error": self.error,
            "messages": self.messages[-40:],
            "files": self.price_files(),
            "config": self.config.to_dict() if self.config else None,
            "paper": True,
        }
        files = out["files"]
        out["default_file"] = next((f for f in files if "us_equities" in f), files[0] if files else "")
        if state is None or not state.equity_curve:
            out.update(bars=0, equity=None, curve=[], dates=[], drawdown=[], positions={}, weights={},
                       target_weights={}, fills=[], n_fills=0, fees=0.0, pnl=None, log=[], halted=False,
                       halt_reason="", cash=None, prices={}, tickers=[])
            return out
        eq = state.equity_curve
        n = len(eq)
        step = max(1, n // points)
        idx = list(range(0, n, step))
        if idx[-1] != n - 1:
            idx.append(n - 1)
        peak = 0.0
        dd = []
        for v in eq:
            peak = max(peak, v)
            dd.append(1.0 - v / peak if peak > 0 else 0.0)
        last_prices = dict(zip(state.tickers, state.prices[-1]))
        weights = {t: q * last_prices[t] / eq[-1] for t, q in state.positions.items()} if eq[-1] > 0 else {}
        ledger = trade_ledger(state.fills, last_prices)
        total = eq[-1] / eq[0] - 1.0
        years = max(n / 252.0, 1e-9)
        out.update(
            bars=n, first_date=state.dates[0], last_date=state.dates[-1],
            equity=eq[-1], start_equity=eq[0], total_return=total,
            annual_return=(1 + total) ** (1 / years) - 1 if total > -1 else -1.0,
            max_drawdown=max(dd), drawdown_now=dd[-1],
            curve=[eq[i] for i in idx], dates=[state.dates[i] for i in idx], drawdown=[dd[i] for i in idx],
            positions=state.positions, weights=weights, target_weights=state.target_weights,
            cash=state.cash, prices=last_prices,
            fills=ledger["fills"][-25:][::-1], n_fills=len(state.fills),
            pnl={k: v for k, v in ledger.items() if k not in ("fills", "round_trips")},
            fees=sum(f.get("fee", 0.0) for f in state.fills),
            log=state.log[-30:][::-1], halted=state.halted, halt_reason=state.halt_reason,
            tickers=state.tickers,
        )
        return out


# --------------------------------------------------------------------------
# HTTP layer
# --------------------------------------------------------------------------


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], controller: Controller) -> None:
        super().__init__(address, _Handler)
        self.controller = controller


class _Handler(BaseHTTPRequestHandler):
    server: DashboardServer

    def log_message(self, fmt: str, *args) -> None:  # quiet the console
        pass

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status: int = 200) -> None:
        self._send(status, json.dumps(obj).encode("utf-8"), "application/json")

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        ctl = self.server.controller
        if path in ("/", "/index.html"):
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/api/state":
            self._json(ctl.snapshot())
        elif path == "/api/files":
            self._json({"files": ctl.price_files()})
        elif path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        ctl = self.server.controller
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._json({"ok": False, "error": "bad JSON"}, 400)
            return
        if path == "/api/start":
            self._json(ctl.start(body))
        elif path == "/api/stop":
            self._json(ctl.stop())
        elif path == "/api/reset":
            self._json(ctl.reset(str(body.get("state_path", "live_state.json"))))
        elif path == "/api/resume":
            self._json(ctl.resume_halt(str(body.get("state_path", "live_state.json"))))
        else:
            self._json({"error": "not found"}, 404)


def serve(port: int = DEFAULT_PORT, open_browser: bool = True, workdir: str | Path | None = None,
          block: bool = True) -> DashboardServer:
    """Start the dashboard.  Returns the server (already serving in a thread)."""
    controller = Controller(workdir)
    server = DashboardServer(("127.0.0.1", port), controller)
    thread = threading.Thread(target=server.serve_forever, name="dashboard", daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Quantum Trading dashboard: {url}")
    print("Paper trading only. Close this window or press Ctrl-C to stop.")
    if open_browser:
        webbrowser.open(url)
    if block:
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            pass
        finally:
            controller.stop()
            server.shutdown()
    return server


# --------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Quantum Trading</title>
<style>
:root {
  color-scheme: light;
  --surface-0:#f4f4f2; --surface-1:#fcfcfb; --surface-2:#ececea; --border:#dcdbd6;
  --text-primary:#0b0b0b; --text-secondary:#52514e; --text-muted:#7b7a75;
  --series-1:#2a78d6; --series-2:#eb6834; --series-8:#e34948;
  --good:#0ca30c; --warning:#fab219; --critical:#d03b3b;
  --grid:#e6e5e1;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --surface-0:#121211; --surface-1:#1a1a19; --surface-2:#242422; --border:#33332f;
    --text-primary:#ffffff; --text-secondary:#c3c2b7; --text-muted:#8f8e86;
    --series-1:#3987e5; --series-2:#d95926; --series-8:#e66767; --grid:#2a2a27;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --surface-0:#121211; --surface-1:#1a1a19; --surface-2:#242422; --border:#33332f;
  --text-primary:#ffffff; --text-secondary:#c3c2b7; --text-muted:#8f8e86;
  --series-1:#3987e5; --series-2:#d95926; --series-8:#e66767; --grid:#2a2a27;
}
* { box-sizing: border-box; }
body { margin:0; background:var(--surface-0); color:var(--text-primary);
  font: 14px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
header { display:flex; align-items:center; gap:16px; padding:12px 16px; background:var(--surface-1);
  border-bottom:1px solid var(--border); position:sticky; top:0; z-index:2; flex-wrap:wrap; }
header h1 { font-size:18px; margin:0; font-weight:600; }
.badge { padding:3px 10px; border-radius:999px; font-size:12px; font-weight:600; letter-spacing:.04em;
  border:1px solid var(--border); color:var(--text-secondary); }
.badge.paper { border-color:var(--warning); color:var(--text-primary); }
.badge.run  { border-color:var(--good); }
.badge.halted { border-color:var(--critical); color:var(--text-primary); }
.spacer { flex:1; }
main { display:grid; grid-template-columns: 320px 1fr; gap:16px; padding:16px; max-width:1500px; margin:0 auto; }
@media (max-width: 900px) { main { grid-template-columns: 1fr; padding:16px; } }
.card { background:var(--surface-1); border:1px solid var(--border); border-radius:10px; padding:14px 16px; }
.card h2 { font-size:13px; font-weight:600; color:var(--text-secondary); margin:0 0 10px; text-transform:uppercase; letter-spacing:.06em; }
label { display:block; font-size:12px; color:var(--text-secondary); margin:8px 0 3px; }
input, select { width:100%; padding:7px 9px; border:1px solid var(--border); border-radius:6px;
  background:var(--surface-0); color:var(--text-primary); font:inherit; }
.row { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
.buttons { display:flex; gap:8px; margin-top:14px; flex-wrap:wrap; }
button { padding:9px 14px; border-radius:7px; border:1px solid var(--border); background:var(--surface-2);
  color:var(--text-primary); font:inherit; font-weight:600; cursor:pointer; }
button.primary { background:var(--series-1); border-color:var(--series-1); color:#fff; }
button.danger { border-color:var(--critical); }
button:disabled { opacity:.45; cursor:not-allowed; }
.tiles { display:grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap:12px; margin-bottom:16px; }
.tile { background:var(--surface-1); border:1px solid var(--border); border-radius:10px; padding:12px 14px; }
.tile .label { font-size:12px; color:var(--text-secondary); }
.tile .value { font-size:24px; font-weight:600; margin-top:2px; }
.tile .sub { font-size:12px; color:var(--text-muted); margin-top:2px; }
.chart { position:relative; height:260px; }
.chart canvas { width:100%; height:100%; display:block; }
.chart.small { height:120px; }
.tip { position:absolute; pointer-events:none; background:var(--surface-1); border:1px solid var(--border);
  border-radius:6px; padding:6px 9px; font-size:12px; display:none; box-shadow:0 2px 8px rgba(0,0,0,.12); }
.tip b { font-size:13px; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th, td { text-align:left; padding:5px 6px; border-bottom:1px solid var(--grid); }
th { color:var(--text-secondary); font-weight:600; font-size:12px; }
td.num, th.num { text-align:right; font-variant-numeric: tabular-nums; }
.bar { height:6px; background:var(--series-1); border-radius:3px; }
pre { margin:0; font:12px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; white-space:pre-wrap;
  color:var(--text-secondary); max-height:220px; overflow:auto; }
.stack { display:grid; gap:16px; }
.two { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
@media (max-width: 1100px) { .two { grid-template-columns:1fr; } }
.error { color:var(--critical); font-weight:600; margin-top:8px; min-height:1.2em; }
.note { color:var(--text-muted); font-size:12px; margin-top:8px; }
.halt { border:1px solid var(--critical); border-radius:8px; padding:10px 12px; margin-bottom:12px; display:none; }
</style>
</head>
<body>
<header>
  <h1>Quantum Trading</h1>
  <span class="badge paper" title="Fills at the close, no slippage, no exchange connection">PAPER</span>
  <span id="status" class="badge">IDLE</span>
  <span id="source" class="note"></span>
  <span class="spacer"></span>
  <span id="clock" class="note"></span>
</header>
<main>
  <aside class="stack">
    <div class="card">
      <h2>Run</h2>
      <label>Mode</label>
      <select id="mode">
        <option value="replay">Replay a price file (paper)</option>
        <option value="feed">Tail a price file for live bars (paper)</option>
      </select>
      <label>Price file (CSV: date + one close column per ticker)</label>
      <select id="csv"></select>
      <label>Tickers (comma-separated, must be columns in the file)</label>
      <input id="tickers" value="AAPL,XOM,JPM,WMT,PFE,AMZN,BAC,T">
      <div class="row">
        <div><label>Start date</label><input id="start" placeholder="2010-01-01" value="2010-01-01"></div>
        <div><label>End date</label><input id="end" placeholder="(none)"></div>
      </div>
      <div class="row">
        <div><label>Replay speed (bars/s, 0 = max)</label><input id="speed" type="number" value="40" min="0"></div>
        <div><label>Poll (s, live mode)</label><input id="poll" type="number" value="5" min="0"></div>
      </div>
      <label><input type="checkbox" id="fresh" style="width:auto;margin-right:6px">Start fresh (discard saved state)</label>
      <div class="buttons">
        <button class="primary" id="btnStart">Start</button>
        <button id="btnStop" disabled>Stop</button>
        <button class="danger" id="btnReset">Reset state</button>
      </div>
      <div id="error" class="error"></div>
      <div class="note">State is saved after every bar to <code id="statefile">live_state.json</code>; restarting resumes.</div>
    </div>
    <div class="card">
      <h2>Strategy</h2>
      <label>Strategy</label>
      <select id="strategy">
        <option value="cardinality">Cardinality-constrained mean-variance (QUBO)</option>
        <option value="markowitz">Markowitz long-only</option>
        <option value="equal_weight">Equal weight (benchmark)</option>
      </select>
      <div class="row">
        <div><label>Hold exactly N names</label><input id="cardinality" type="number" value="4" min="1"></div>
        <div><label>Risk aversion</label><input id="risk_aversion" type="number" value="2" step="0.5" min="0.1"></div>
      </div>
      <label>Solver</label>
      <select id="solver">
        <option value="simulated_annealing">Simulated annealing</option>
        <option value="simulated_bifurcation">Simulated bifurcation</option>
        <option value="subspace_qaoa">Subspace QAOA (slow, small universes)</option>
        <option value="exhaustive">Exhaustive (proves the optimum)</option>
      </select>
      <div class="row">
        <div><label>Fit window (bars)</label><input id="window" type="number" value="252" min="3"></div>
        <div><label>Rebalance every (bars)</label><input id="rebalance_every" type="number" value="21" min="1"></div>
      </div>
    </div>
    <div class="card">
      <h2>Money and risk</h2>
      <div class="row">
        <div><label>Starting cash</label><input id="initial_cash" type="number" value="100000" min="1"></div>
        <div><label>Fee per fill (fraction)</label><input id="fee_rate" type="number" value="0.0005" step="0.0001" min="0"></div>
      </div>
      <div class="row">
        <div><label>Max weight per name</label><input id="max_weight" type="number" value="0.40" step="0.05" min="0.01" max="1"></div>
        <div><label>Max turnover per rebalance</label><input id="max_turnover" type="number" value="0.50" step="0.05" min="0" max="1"></div>
      </div>
      <div class="row">
        <div><label>Kill switch: max drawdown (fraction)</label><input id="max_drawdown" type="number" value="0.25" step="0.01" min="0.01" max="1"></div>
        <div><label>Re-arm after (bars in cash, 0 = never)</label><input id="rearm_after" type="number" value="63" step="1" min="0"></div>
      </div>
      <div class="note">On breach the engine liquidates and sits in cash; it resumes after the re-arm period, or with 0 only when you clear it.</div>
    </div>
  </aside>

  <section class="stack">
    <div id="haltbox" class="halt">
      <b>Kill switch tripped.</b> <span id="haltreason"></span>
      <div class="buttons"><button id="btnResume">Clear kill switch and allow trading</button></div>
    </div>
    <div class="tiles">
      <div class="tile"><div class="label">Equity</div><div class="value" id="tEquity">–</div><div class="sub" id="tEquitySub"></div></div>
      <div class="tile"><div class="label">Total return</div><div class="value" id="tReturn">–</div><div class="sub" id="tReturnSub"></div></div>
      <div class="tile"><div class="label">Drawdown now</div><div class="value" id="tDD">–</div><div class="sub" id="tDDSub"></div></div>
      <div class="tile"><div class="label">Bars</div><div class="value" id="tBars">–</div><div class="sub" id="tBarsSub"></div></div>
      <div class="tile"><div class="label">Fills</div><div class="value" id="tFills">–</div><div class="sub" id="tFillsSub"></div></div>
      <div class="tile"><div class="label">Gains / losses</div><div class="value" id="tPnl">–</div><div class="sub" id="tPnlSub"></div></div>
    </div>
    <div class="card">
      <h2>Equity curve</h2>
      <div class="chart"><canvas id="cEquity"></canvas><div class="tip" id="tipEquity"></div></div>
      <h2 style="margin-top:14px">Drawdown</h2>
      <div class="chart small"><canvas id="cDD"></canvas></div>
    </div>
    <div class="two">
      <div class="card">
        <h2>Positions</h2>
        <table><thead><tr><th>Ticker</th><th class="num">Shares</th><th class="num">Avg cost</th><th class="num">Price</th><th class="num">Gain/loss</th><th class="num">Weight</th><th style="width:20%"></th></tr></thead>
        <tbody id="positions"></tbody></table>
        <div class="note" id="cash"></div>
      </div>
      <div class="card">
        <h2>Recent fills</h2>
        <table><thead><tr><th>Date</th><th>Ticker</th><th class="num">Qty</th><th class="num">Price</th><th class="num">Fee</th><th class="num">Realized</th></tr></thead>
        <tbody id="fills"></tbody></table>
      </div>
    </div>
    <div class="two">
      <div class="card"><h2>Engine log</h2><pre id="log"></pre></div>
      <div class="card"><h2>Dashboard messages</h2><pre id="messages"></pre></div>
    </div>
  </section>
</main>
<script>
(function () {
  const $ = id => document.getElementById(id);
  const fmtMoney = v => v == null ? '–' : v.toLocaleString(undefined, {maximumFractionDigits: 2, minimumFractionDigits: 2});
  const fmtPct = v => v == null ? '–' : (v * 100).toFixed(2) + '%';
  const fmtSigned = v => v == null ? '–' : (v > 0 ? '+' : v < 0 ? '−' : '') + fmtMoney(Math.abs(v));
  const fmtSigned0 = v => v == null ? '–' : (v > 0 ? '+' : v < 0 ? '−' : '') + Math.round(Math.abs(v)).toLocaleString();
  const fmtSignedPct = v => v == null ? '–' : (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v * 100).toFixed(1) + '%';
  const signColor = v => v > 0 ? 'var(--good)' : v < 0 ? 'var(--critical)' : '';
  const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  let last = null;

  function form() {
    return {
      mode: $('mode').value, csv: $('csv').value, tickers: $('tickers').value,
      start: $('start').value, end: $('end').value, bars_per_second: Number($('speed').value),
      poll_seconds: Number($('poll').value), fresh: $('fresh').checked,
      strategy: $('strategy').value, cardinality: Number($('cardinality').value),
      risk_aversion: Number($('risk_aversion').value), solver: $('solver').value,
      window: Number($('window').value), rebalance_every: Number($('rebalance_every').value),
      initial_cash: Number($('initial_cash').value), fee_rate: Number($('fee_rate').value),
      max_weight: Number($('max_weight').value), max_turnover: Number($('max_turnover').value),
      max_drawdown: Number($('max_drawdown').value), rearm_after: Number($('rearm_after').value), state_path: 'live_state.json',
    };
  }
  async function post(path, body) {
    const r = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body || {})});
    return r.json();
  }
  $('btnStart').onclick = async () => { $('error').textContent = ''; const r = await post('/api/start', form()); if (!r.ok) $('error').textContent = r.error || 'failed'; refresh(); };
  $('btnStop').onclick = async () => { await post('/api/stop'); refresh(); };
  $('btnReset').onclick = async () => { if (!confirm('Delete the saved state file? The paper book starts over.')) return; const r = await post('/api/reset', {state_path: 'live_state.json'}); if (!r.ok) $('error').textContent = r.error; refresh(); };
  $('btnResume').onclick = async () => { const r = await post('/api/resume', {state_path: 'live_state.json'}); if (!r.ok) $('error').textContent = r.error; refresh(); };

  function setText(id, text) { $(id).textContent = text; }

  function drawLine(canvas, xs, ys, opts) {
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth, h = canvas.clientHeight;
    canvas.width = w * dpr; canvas.height = h * dpr;
    const ctx = canvas.getContext('2d'); ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);
    const padL = 56, padR = 12, padT = 10, padB = 22;
    if (!ys.length) { ctx.fillStyle = css('--text-muted'); ctx.font = '12px system-ui'; ctx.fillText('no data yet', padL, h / 2); return null; }
    let lo = Math.min(...ys), hi = Math.max(...ys);
    if (opts.zeroTop) { hi = 0; lo = Math.min(lo, -0.01); }
    if (hi === lo) { hi += 1; lo -= 1; }
    const X = i => padL + (i / Math.max(ys.length - 1, 1)) * (w - padL - padR);
    const Y = v => padT + (1 - (v - lo) / (hi - lo)) * (h - padT - padB);
    ctx.strokeStyle = css('--grid'); ctx.lineWidth = 1; ctx.fillStyle = css('--text-secondary'); ctx.font = '11px system-ui';
    for (let k = 0; k <= 4; k++) {
      const v = lo + (hi - lo) * k / 4, y = Math.round(Y(v)) + 0.5;
      ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke();
      ctx.textAlign = 'right'; ctx.fillText(opts.fmt(v), padL - 6, y + 4);
    }
    ctx.textAlign = 'left';
    if (xs.length) { ctx.fillText(xs[0], padL, h - 6); ctx.textAlign = 'right'; ctx.fillText(xs[xs.length - 1], w - padR, h - 6); }
    if (opts.fill) {
      ctx.beginPath(); ctx.moveTo(X(0), Y(hi));
      ys.forEach((v, i) => ctx.lineTo(X(i), Y(v)));
      ctx.lineTo(X(ys.length - 1), Y(hi)); ctx.closePath();
      ctx.globalAlpha = 0.18; ctx.fillStyle = opts.color; ctx.fill(); ctx.globalAlpha = 1;
    }
    ctx.beginPath(); ys.forEach((v, i) => i ? ctx.lineTo(X(i), Y(v)) : ctx.moveTo(X(i), Y(v)));
    ctx.strokeStyle = opts.color; ctx.lineWidth = 2; ctx.lineJoin = 'round'; ctx.stroke();
    return {X, Y, padL, padR, w, h};
  }

  let geom = null;
  function render(s) {
    last = s;
    const running = s.running;
    $('status').textContent = s.halted ? 'HALTED' : (running ? 'RUNNING' : 'IDLE');
    $('status').className = 'badge ' + (s.halted ? 'halted' : running ? 'run' : '');
    setText('source', s.source || '');
    $('btnStart').disabled = running; $('btnStop').disabled = !running; $('btnReset').disabled = running;
    $('haltbox').style.display = s.halted ? 'block' : 'none';
    setText('haltreason', s.halt_reason || '');
    if (s.error) $('error').textContent = s.error;
    const sel = $('csv');
    if (sel.options.length !== (s.files || []).length) {
      const cur = sel.value; sel.innerHTML = '';
      (s.files || []).forEach(f => { const o = document.createElement('option'); o.value = f; o.textContent = f; sel.appendChild(o); });
      sel.value = cur || s.default_file || '';
    }
    setText('tEquity', s.equity == null ? '–' : fmtMoney(s.equity));
    setText('tEquitySub', s.equity == null ? 'no bars yet' : 'from ' + fmtMoney(s.start_equity) + (s.cash != null ? ' · cash ' + fmtMoney(s.cash) : ''));
    setText('tReturn', s.equity == null ? '–' : fmtPct(s.total_return));
    setText('tReturnSub', s.equity == null ? '' : fmtPct(s.annual_return) + ' / yr (paper, no slippage)');
    setText('tDD', s.equity == null ? '–' : fmtPct(s.drawdown_now));
    setText('tDDSub', s.equity == null ? '' : 'worst ' + fmtPct(s.max_drawdown) + ' · limit ' + fmtPct(Number($('max_drawdown').value)));
    setText('tBars', s.bars || 0);
    setText('tBarsSub', s.bars ? s.first_date + ' → ' + s.last_date : '');
    setText('tFills', s.n_fills || 0);
    setText('tFillsSub', s.n_fills ? 'fees ' + fmtMoney(s.fees) : '');
    const pl = s.pnl;
    setText('tPnl', pl ? fmtSigned0(pl.total_pnl) : '–');
    setText('tPnlSub', pl ? 'realized ' + fmtSigned0(pl.realized_pnl) + ' · open ' + fmtSigned0(pl.unrealized_pnl) +
      (pl.n_round_trips ? ' · ' + pl.n_wins + '/' + pl.n_round_trips + ' round trips won' : '') : '');
    $('tPnl').style.color = pl ? signColor(pl.total_pnl) : '';

    geom = drawLine($('cEquity'), s.dates || [], s.curve || [], {color: css('--series-1'), fmt: v => v.toLocaleString(undefined, {maximumFractionDigits: 0}), fill: true});
    drawLine($('cDD'), s.dates || [], (s.drawdown || []).map(v => -v), {color: css('--series-8'), fmt: v => (v * 100).toFixed(0) + '%', zeroTop: true, fill: true});

    const pos = $('positions'); pos.innerHTML = '';
    const names = Object.keys(s.positions || {}).sort((a, b) => (s.weights[b] || 0) - (s.weights[a] || 0));
    names.forEach(t => {
      const tr = document.createElement('tr');
      const w = s.weights[t] || 0;
      const p = (s.pnl && s.pnl.positions[t]) || {};
      [t, (s.positions[t]).toFixed(2), fmtMoney(p.avg_cost), fmtMoney(s.prices[t]),
       p.unrealized_pnl == null ? '–' : fmtSigned0(p.unrealized_pnl) + ' (' + fmtSignedPct(p.unrealized_pct) + ')', fmtPct(w)].forEach((v, i) => {
        const td = document.createElement('td'); td.textContent = v; if (i) td.className = 'num';
        if (i === 4 && p.unrealized_pnl != null) td.style.color = signColor(p.unrealized_pnl);
        tr.appendChild(td); });
      const td = document.createElement('td'); const bar = document.createElement('div'); bar.className = 'bar'; bar.style.width = Math.max(2, w * 100) + '%'; td.appendChild(bar); tr.appendChild(td);
      pos.appendChild(tr);
    });
    if (!names.length) { const tr = document.createElement('tr'); const td = document.createElement('td'); td.colSpan = 7; td.textContent = s.bars ? 'all cash' : 'no positions'; td.style.color = 'var(--text-muted)'; tr.appendChild(td); pos.appendChild(tr); }
    setText('cash', s.cash == null ? '' : 'cash ' + fmtMoney(s.cash) + (s.target_weights && Object.keys(s.target_weights).length ? ' · targets: ' + Object.entries(s.target_weights).map(([k, v]) => k + ' ' + fmtPct(v)).join(', ') : ''));

    const fills = $('fills'); fills.innerHTML = '';
    (s.fills || []).forEach(f => {
      const tr = document.createElement('tr');
      const sold = f.quantity < 0 && f.realized_pnl != null;
      [f.date, f.ticker, f.quantity.toFixed(2), fmtMoney(f.price), fmtMoney(f.fee), sold ? fmtSigned(f.realized_pnl) : ''].forEach((v, i) => {
        const td = document.createElement('td'); td.textContent = v; if (i >= 2) td.className = 'num';
        if (i === 5 && sold) td.style.color = signColor(f.realized_pnl);
        tr.appendChild(td); });
      fills.appendChild(tr);
    });
    setText('log', (s.log || []).join('\n'));
    setText('messages', (s.messages || []).slice().reverse().join('\n'));
    setText('clock', new Date().toLocaleTimeString());
  }

  const tip = $('tipEquity'), cE = $('cEquity');
  cE.addEventListener('pointermove', e => {
    if (!geom || !last || !last.curve.length) return;
    const rect = cE.getBoundingClientRect(); const x = e.clientX - rect.left;
    const n = last.curve.length; const i = Math.max(0, Math.min(n - 1, Math.round((x - geom.padL) / (geom.w - geom.padL - geom.padR) * (n - 1))));
    tip.style.display = 'block'; tip.style.left = Math.min(x + 12, geom.w - 160) + 'px'; tip.style.top = '8px';
    tip.innerHTML = ''; const b = document.createElement('b'); b.textContent = fmtMoney(last.curve[i]); tip.appendChild(b);
    tip.appendChild(document.createTextNode(' ' + last.dates[i] + ' · dd ' + fmtPct(last.drawdown[i])));
  });
  cE.addEventListener('pointerleave', () => { tip.style.display = 'none'; });

  async function refresh() {
    try { const r = await fetch('/api/state'); render(await r.json()); }
    catch (e) { $('status').textContent = 'DISCONNECTED'; $('status').className = 'badge halted'; }
  }
  refresh(); setInterval(refresh, 1000);
  window.addEventListener('resize', () => last && render(last));
})();
</script>
</body>
</html>
"""
