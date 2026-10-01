"""Quantum Station: every bot, run on this computer alone.  Paper trading only.

    python -m quantum.local                 # start the station and open the dashboard
    python -m quantum.local --no-browser    # start without opening a browser
    python -m quantum.local run daily       # run one job now and exit (daily, intraday, ...)

On Windows, double-click ``Quantum Station.bat`` in the repository folder.

What runs, on a timer, while the station is open:

* **Daily bots** (the $100k bot and the $40 whole-share bot): once each
  trading day after 16:30 New York time, fetch the day's closes and run the
  engine over every new bar.  A day missed because the computer was off is
  caught up at the next start.  The $40 bot writes the day's orders for a
  person to place by hand (``small/orders.json``); nothing is sent anywhere.
* **Intraday bot** ($50, 5-minute KAMA): every 5 minutes during the session,
  replay today so far from fresh bars; after the close, archive the day.

Everything lives in one folder (``local_data/`` next to the repository, or
``QT_LOCAL_HOME``): each bot's config, state, prices, snapshot and the job
logs.  On the first start the folder is seeded from the repository's
``live/`` configs and saved state, so the local bots continue the same paper
books; after that they are independent of GitHub.

Every job runs as a separate Python process with the broker settings
(``QT_BROKER``, ``ALPACA_*``, ``QT_ALLOW_REAL_MONEY``) removed from its
environment and ``--broker paper`` on its command line, so no job here can
reach a real account whatever this computer's settings are.

The dashboard is a small HTTP server on 127.0.0.1 with the same protections
as ``quantum.desktop``: loopback Host only, JSON-only POSTs with no foreign
Origin, and no file name taken from a request.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time as dtime, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from .desktop import _Handler

__all__ = [
    "NY", "ROOT", "DEFAULT_PORT", "JOBS", "is_trading_day", "session_close", "last_completed_session",
    "due_jobs", "Station", "serve", "main",
]

NY = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PORT = 8777
PAGE_FILE = Path(__file__).with_name("local_page.html")

# --------------------------------------------------------------------------
# NYSE calendar
# --------------------------------------------------------------------------

# Full-day closures, from the exchange's published schedule.
HOLIDAYS = {
    # 2026
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19",
    "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    # 2027 (Juneteenth falls on a Saturday: observed Friday 18th; Independence
    # Day on a Sunday: observed Monday 5th; Christmas on a Saturday: Friday 24th)
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18",
    "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
}
# 13:00 closes (same list as scripts/intraday_live.py).
EARLY_CLOSE = {"2026-11-27", "2026-12-24", "2027-11-26"}
KNOWN_YEARS = {2026, 2027}
OPEN = dtime(9, 30)
DAILY_AFTER = timedelta(minutes=30)      # closes are final well within this
INTRADAY_LAG = timedelta(seconds=40)     # let the bar that just ended be published
INTRADAY_EVERY = timedelta(minutes=5)
RETRY_AFTER = timedelta(minutes=20)      # a failed job is tried again after this


def is_trading_day(d: date) -> bool:
    """A weekday that is not a listed NYSE holiday.  Years without a holiday
    list (outside ``KNOWN_YEARS``) count every weekday; a holiday there just
    finds no new bar."""
    return d.weekday() < 5 and d.isoformat() not in HOLIDAYS


def session_close(d: date) -> dtime:
    return dtime(13, 0) if d.isoformat() in EARLY_CLOSE else dtime(16, 0)


def _at(d: date, t: dtime) -> datetime:
    return datetime.combine(d, t, tzinfo=NY)


def last_completed_session(now: datetime) -> date:
    """The newest trading day whose close was at least ``DAILY_AFTER`` ago."""
    now = now.astimezone(NY)
    d = now.date()
    while not (is_trading_day(d) and now >= _at(d, session_close(d)) + DAILY_AFTER):
        d -= timedelta(days=1)
        now = _at(d, dtime(23, 59))
    return d


def intraday_slot(now: datetime) -> str | None:
    """``YYYY-MM-DD#n`` for the n-th 5-minute bar finished today (1 = the
    09:30 bar, done at 09:35), or None outside a trading session."""
    now = now.astimezone(NY)
    d = now.date()
    if not is_trading_day(d):
        return None
    start, close = _at(d, OPEN), _at(d, session_close(d))
    if now < start + INTRADAY_EVERY + INTRADAY_LAG or now >= close + INTRADAY_EVERY + INTRADAY_LAG:
        return None
    n = int((now - start - INTRADAY_LAG) / INTRADAY_EVERY)
    return f"{d.isoformat()}#{n}"


def due_jobs(now: datetime, sched: dict) -> list[str]:
    """Which scheduled jobs should start at ``now`` given the scheduler's
    memory ``sched`` (``daily_done``, ``intraday_slot``, ``archived``,
    ``retry`` = {job: iso time}).  Pure, so the timing rules are testable."""
    now = now.astimezone(NY)
    due = []
    retry = sched.get("retry", {})

    def ready(job: str) -> bool:
        at = retry.get(job)
        return not at or now >= datetime.fromisoformat(at)

    if sched.get("daily_done", "") < last_completed_session(now).isoformat() and ready("daily"):
        due.append("daily")
    slot = intraday_slot(now)
    if slot and slot != sched.get("intraday_slot") and ready("intraday"):
        due.append("intraday")
    d = now.date()
    if (is_trading_day(d) and now >= _at(d, session_close(d)) + INTRADAY_EVERY + INTRADAY_LAG
            and sched.get("archived", "") < d.isoformat() and ready("intraday_close")):
        due.append("intraday_close")
    return due


# --------------------------------------------------------------------------
# The station's folder
# --------------------------------------------------------------------------

DAILY_BOTS = {
    "main": {"title": "$100k daily bot", "config": "live/config.json", "state": "live/state.json"},
    "small": {"title": "$40 whole-share bot", "config": "live/real/config.json", "state": "live/real/state.json"},
}
BROKER_ENV = ("QT_BROKER", "QT_ALLOW_REAL_MONEY", "ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY", "ALPACA_BASE_URL")


def default_home() -> Path:
    return Path(os.environ.get("QT_LOCAL_HOME") or ROOT / "local_data")


def paper_env() -> dict:
    """This process's environment without any broker setting."""
    env = {k: v for k, v in os.environ.items() if k not in BROKER_ENV and not k.startswith("ALPACA_")}
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def seed(home: Path, root: Path = ROOT, copy_state: bool = True) -> list[str]:
    """Create the station's folder from the repository's ``live/`` files;
    files already there are left alone.  Returns what was created."""
    made = []
    for name, spec in DAILY_BOTS.items():
        d = home / name
        d.mkdir(parents=True, exist_ok=True)
        cfg_path = d / "config.json"
        if not cfg_path.exists():
            cfg = json.loads((root / spec["config"]).read_text(encoding="utf-8"))
            cfg["state_path"] = str(d / "state.json")
            cfg["mode"] = "paper"
            cfg_path.write_text(json.dumps(cfg, indent=1), encoding="utf-8")
            made.append(str(cfg_path))
            src_state = root / spec["state"]
            if copy_state and src_state.exists() and not (d / "state.json").exists():
                shutil.copy2(src_state, d / "state.json")
                made.append(str(d / "state.json"))
    d = home / "intraday"
    (d / "history").mkdir(parents=True, exist_ok=True)
    for fname in ("config.json", "universe.txt"):
        if not (d / fname).exists():
            shutil.copy2(root / "live/intraday" / fname, d / fname)
            made.append(str(d / fname))
    for sub in ("data", "logs", "indicators", "tools"):
        (home / sub).mkdir(parents=True, exist_ok=True)
    return made


def _read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write_json(path: Path, obj) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1), encoding="utf-8")
    os.replace(tmp, path)


# --------------------------------------------------------------------------
# Jobs
# --------------------------------------------------------------------------


@dataclass
class JobRun:
    job: str
    started: str
    finished: str = ""
    ok: bool | None = None          # None while running
    steps: list = field(default_factory=list)  # [{"cmd", "code", "seconds"}]
    output: str = ""


# name: (title, scheduled?, what it does)
JOBS = {
    "daily": ("Run the daily bots", True, "fetch closes and run the $100k and $40 bots"),
    "intraday": ("Run the intraday bot", True, "replay today so far for the $50 bot"),
    "intraday_close": ("Archive the intraday day", True, "final intraday run after the close, then archive it"),
    "fetch_bars": ("Download intraday bars", False, "60 days of 5-minute bars for the intraday universe"),
    "backtest_main": ("Backtest the $100k bot", False, "replay the bot's rules over its last two years of prices"),
    "backtest_small": ("Backtest the $40 bot", False, "replay the bot's rules over its last two years of prices"),
    "backtest_intraday": ("Backtest the intraday bot", False, "the live intraday rules on the downloaded bars, against random entries"),
    "indicator_test": ("Test the indicators", False, "every indicator file on the downloaded bars: last 20 sessions as test"),
}


class Station:
    """Owns the folder, the scheduler thread and the job processes."""

    def __init__(self, home: str | Path | None = None, python: str | None = None,
                 clock=None, copy_state: bool = True) -> None:
        self.home = Path(home) if home else default_home()
        self.python = python or sys.executable
        self.clock = clock or (lambda: datetime.now(NY))
        self.created = seed(self.home, copy_state=copy_state)
        self.sched_path = self.home / "scheduler.json"
        self.sched = _read_json(self.sched_path, {}) or {}
        self.sched.setdefault("paused", False)
        self.sched.setdefault("retry", {})
        self.lock = threading.Lock()
        self.running: dict[str, JobRun] = {}
        self.history: deque[JobRun] = deque(maxlen=60)
        self.messages: deque[str] = deque(maxlen=200)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.scheduler_active = False
        self.runs_path = self.home / "logs" / "runs.json"
        for r in reversed(_read_json(self.runs_path, []) or []):  # the last runs, from before a restart
            try:
                self.history.appendleft(JobRun(**r))
            except TypeError:
                pass
        for p in self.created:
            self.note(f"created {p}")

    # -- messages ---------------------------------------------------------
    def note(self, line: str) -> None:
        stamp = self.clock().strftime("%Y-%m-%d %H:%M:%S")
        text = f"{stamp} {line}"
        self.messages.append(text)
        try:
            with open(self.home / "logs" / f"{stamp[:10]}.log", "a", encoding="utf-8") as fh:
                fh.write(text + "\n")
        except OSError:
            pass

    def _save_sched(self) -> None:
        with self.lock:
            _write_json(self.sched_path, self.sched)

    # -- running commands -------------------------------------------------
    def _cmd(self, run: JobRun, args: list[str], timeout: float = 900.0) -> int:
        """Run one step in a child process (cwd = repository), recording it."""
        cmd = [self.python] + args
        t0 = time.time()
        try:
            proc = subprocess.run(cmd, cwd=ROOT, env=paper_env(), capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=timeout)
            code, out = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
        except subprocess.TimeoutExpired as exc:
            code, out = -1, f"timed out after {timeout:.0f}s\n{exc.stdout or ''}"
        except OSError as exc:
            code, out = -1, f"could not start: {exc}"
        shown = " ".join(Path(a).name if os.path.isabs(a) else a for a in args)
        run.steps.append({"cmd": shown, "code": code, "seconds": round(time.time() - t0, 1)})
        run.output += f"$ {shown}\n{out.rstrip()}\n[exit {code}]\n\n"
        return code

    def start(self, job: str, wait: bool = False) -> dict:
        """Start ``job`` in a thread (or run it here with ``wait``)."""
        if job not in JOBS:
            return {"ok": False, "error": f"unknown job {job!r}"}
        with self.lock:
            if job in self.running:
                return {"ok": False, "error": f"{job} is already running"}
            run = JobRun(job, self.clock().isoformat(timespec="seconds"))
            self.running[job] = run
        if wait:
            self._execute(run)
            return {"ok": bool(run.ok), "job": asdict(run)}
        threading.Thread(target=self._execute, args=(run,), name=f"job-{job}", daemon=True).start()
        return {"ok": True, "started": job}

    def _execute(self, run: JobRun) -> None:
        self.note(f"{run.job}: started")
        try:
            run.ok = bool(getattr(self, f"_job_{run.job}")(run))
        except Exception as exc:  # a bug in a job must not kill the scheduler
            run.output += f"error: {exc!r}\n"
            run.ok = False
        run.finished = self.clock().isoformat(timespec="seconds")
        # The log is on disk before the job stops showing as running, so a
        # reader that waits for it to finish always finds the whole output.
        try:
            (self.home / "logs" / f"last_{run.job}.txt").write_text(run.output, encoding="utf-8")
        except OSError:
            pass
        with self.lock:  # one step, so the scheduler never sees a failed job without its retry time
            if run.ok:
                self.sched["retry"].pop(run.job, None)
            else:
                self.sched["retry"][run.job] = (self.clock() + RETRY_AFTER).isoformat(timespec="seconds")
            self.running.pop(run.job, None)
            self.history.appendleft(run)
            kept = [dict(asdict(r), output=r.output[-4000:]) for r in list(self.history)[:60]]
        try:
            _write_json(self.runs_path, kept)
        except OSError:
            pass
        self._save_sched()
        failed = [s["cmd"] for s in run.steps if s["code"] != 0]
        self.note(f"{run.job}: {'done' if run.ok else 'FAILED'}" + (f" ({'; '.join(failed)})" if failed else ""))

    # -- the jobs ---------------------------------------------------------
    def _daily_bot(self, run: JobRun, name: str) -> bool:
        d = self.home / name
        if self._cmd(run, ["scripts/fetch_prices.py", "--config", str(d / "config.json"),
                           "--out", str(d / "prices.csv")], timeout=600) != 0:
            return False
        args = ["-m", "quantum", "live", "--config", str(d / "config.json"), "--feed", str(d / "prices.csv"),
                "--catch-up", "--poll", "0", "--broker", "paper", "--snapshot", str(d / "snapshot.json")]
        if name == "small":
            args += ["--orders", str(d / "orders.json")]
        return self._cmd(run, args) == 0

    def _job_daily(self, run: JobRun) -> bool:
        target = last_completed_session(self.clock()).isoformat()
        ok = all([self._daily_bot(run, name) for name in DAILY_BOTS])
        if ok:
            with self.lock:
                self.sched["daily_done"] = target
        return ok

    def _intraday(self, run: JobRun) -> bool:
        d = self.home / "intraday"
        return self._cmd(run, ["scripts/intraday_live.py", "--config", str(d / "config.json"),
                               "--universe", str(d / "universe.txt"), "--out", str(d / "status.json")],
                         timeout=600) == 0

    def _job_intraday(self, run: JobRun) -> bool:
        slot = intraday_slot(self.clock())
        ok = self._intraday(run)
        if slot:
            with self.lock:
                self.sched["intraday_slot"] = slot
        return ok

    def _job_intraday_close(self, run: JobRun) -> bool:
        today = self.clock().astimezone(NY).date().isoformat()
        if not self._intraday(run):
            return False
        d = self.home / "intraday"
        status = _read_json(d / "status.json")
        if status and status.get("date") == today:
            _write_json(d / "history" / f"{today}.json", status)
            summary = [s for s in (_read_json(d / "history" / "summary.json", []) or []) if s.get("date") != today]
            start = float(status.get("start_cash") or 0) or 1.0
            equity = status.get("equity")
            summary.append({"date": today, "start_cash": status.get("start_cash"), "equity": equity,
                            "return": (float(equity) if equity is not None else start) / start - 1.0,
                            "trades": len(status.get("trades") or [])})
            _write_json(d / "history" / "summary.json", sorted(summary, key=lambda s: s["date"]))
            run.output += f"archived {today}: equity {status.get('equity')}\n"
        else:
            run.output += f"no intraday status for {today} (holiday or no data); nothing archived\n"
        with self.lock:
            self.sched["archived"] = today
        return True

    def _job_fetch_bars(self, run: JobRun) -> bool:
        return self._cmd(run, ["scripts/fetch_intraday.py", "--tickers-file",
                               str(self.home / "intraday" / "universe.txt"), "--interval", "5m",
                               "--range", "60d", "--out", str(self.home / "data" / "bars_5m.csv")],
                         timeout=1200) == 0

    def _backtest_daily(self, run: JobRun, name: str) -> bool:
        d = self.home / name
        prices = d / "prices.csv"
        if not prices.exists():
            run.output += f"no {prices.name} yet: run the daily bots once first\n"
            return False
        cfg = _read_json(d / "config.json", {})
        cfg.pop("trade_from", None)  # trade the whole history, not only from the live start
        tmp = self.home / "tools" / f"backtest_{name}"
        tmp.mkdir(parents=True, exist_ok=True)
        cfg["state_path"] = str(tmp / "state.json")
        _write_json(tmp / "config.json", cfg)
        return self._cmd(run, ["-m", "quantum", "live", "--config", str(tmp / "config.json"),
                               "--replay", str(prices), "--fresh", "--broker", "paper",
                               "--snapshot", str(tmp / "snapshot.json")]) == 0

    def _job_backtest_main(self, run: JobRun) -> bool:
        return self._backtest_daily(run, "main")

    def _job_backtest_small(self, run: JobRun) -> bool:
        return self._backtest_daily(run, "small")

    def _bars(self, run: JobRun) -> Path | None:
        bars = self.home / "data" / "bars_5m.csv"
        if not bars.exists():
            run.output += "no downloaded bars yet: run 'Download intraday bars' first\n"
            return None
        return bars

    def _job_backtest_intraday(self, run: JobRun) -> bool:
        bars = self._bars(run)
        return bool(bars) and self._cmd(run, ["-m", "quantum.local", "_backtest_intraday", str(bars),
                                              str(self.home / "intraday" / "config.json"),
                                              str(self.home / "tools" / "backtest_intraday.json")]) == 0

    def _job_indicator_test(self, run: JobRun) -> bool:
        bars = self._bars(run)
        if not bars:
            return False
        files = sorted(str(p) for p in (ROOT / "indicators").glob("*.py") if not p.name.startswith("_"))
        files += sorted(str(p) for p in (self.home / "indicators").glob("*.py"))
        return self._cmd(run, ["-m", "quantum.local", "_indicator_test", str(bars),
                               str(self.home / "tools" / "indicator_test.json")] + files, timeout=1800) == 0

    # -- scheduler ---------------------------------------------------------
    def tick(self) -> list[str]:
        """Start whatever is due now; returns the jobs started."""
        if self.sched.get("paused"):
            return []
        with self.lock:
            busy = set(self.running)
            sched = json.loads(json.dumps(self.sched))
        started = []
        for job in due_jobs(self.clock(), sched):
            if job == "intraday_close" and "intraday" in busy:
                continue
            if job not in busy and self.start(job).get("ok"):
                started.append(job)
        return started

    def run_forever(self, every: float = 20.0) -> None:
        def loop():
            while not self._stop.is_set():
                try:
                    self.tick()
                except Exception as exc:  # keep the scheduler alive
                    self.note(f"scheduler error: {exc!r}")
                self._stop.wait(every)
        self._thread = threading.Thread(target=loop, name="scheduler", daemon=True)
        self._thread.start()
        self.scheduler_active = True

    def stop(self) -> None:
        self._stop.set()

    def set_paused(self, paused: bool) -> dict:
        with self.lock:
            self.sched["paused"] = bool(paused)
        self._save_sched()
        self.note("scheduler paused" if paused else "scheduler resumed")
        return {"ok": True, "paused": bool(paused)}

    def reset(self, bot: str) -> dict:
        """Start a daily bot's paper book over: its state is moved aside, not deleted."""
        if bot not in DAILY_BOTS:
            return {"ok": False, "error": f"unknown bot {bot!r}"}
        if "daily" in self.running:
            return {"ok": False, "error": "the daily job is running; try again when it finishes"}
        d = self.home / bot
        stamp = self.clock().strftime("%Y%m%d-%H%M%S")
        moved = []
        for f in ("state.json", "snapshot.json", "snapshot_prices.json", "orders.json"):
            if (d / f).exists():
                (d / f).rename(d / f"{f}.{stamp}.bak")
                moved.append(f)
        with self.lock:
            self.sched.pop("daily_done", None)
        self._save_sched()
        self.note(f"{bot}: reset ({', '.join(moved) or 'nothing to move'}); the next daily run rebuilds it")
        return {"ok": True, "moved": moved}

    def next_events(self) -> dict:
        """When each scheduled job will next be due (approximate, for display)."""
        now = self.clock().astimezone(NY)
        out = {}
        if self.sched.get("daily_done", "") < last_completed_session(now).isoformat():
            out["daily"] = now.isoformat(timespec="minutes")  # due now (or retrying)
        else:
            d = now.date()
            for _ in range(10):
                at = _at(d, session_close(d)) + DAILY_AFTER
                if is_trading_day(d) and at > now:
                    out["daily"] = at.isoformat(timespec="minutes")
                    break
                d += timedelta(days=1)
        d = now.date()
        for _ in range(10):
            if is_trading_day(d):
                first = _at(d, OPEN) + INTRADAY_EVERY + INTRADAY_LAG
                end = _at(d, session_close(d)) + INTRADAY_EVERY + INTRADAY_LAG  # the last bar's run
                if now < end:
                    nxt = first if now < first else now + INTRADAY_EVERY - (now - first) % INTRADAY_EVERY
                    out["intraday"] = nxt.isoformat(timespec="minutes")
                    break
            d += timedelta(days=1)
        return out

    # -- what the dashboard shows ------------------------------------------
    def overview(self) -> dict:
        now = self.clock().astimezone(NY)
        bots = {}
        for name, spec in DAILY_BOTS.items():
            d = self.home / name
            bots[name] = {
                "title": spec["title"],
                "config": _read_json(d / "config.json", {}),
                "snapshot": _read_json(d / "snapshot.json"),
                "orders": _read_json(d / "orders.json") if name == "small" else None,
            }
        d = self.home / "intraday"
        with self.lock:
            running = {k: asdict(v) for k, v in self.running.items()}
            history = [asdict(r) for r in list(self.history)[:25]]
            sched = json.loads(json.dumps(self.sched))
        for h in history:
            h["output"] = h["output"][-4000:]
        tools = {name: _read_json(self.home / "tools" / f"{name}.json")
                 for name in ("backtest_intraday", "indicator_test")}
        for name in DAILY_BOTS:
            tools[f"backtest_{name}"] = _read_json(self.home / "tools" / f"backtest_{name}" / "snapshot.json")
        bars = self.home / "data" / "bars_5m.csv"
        return {
            "now": now.isoformat(timespec="seconds"),
            "home": str(self.home),
            "paper": True,
            "market": {
                "trading_day": is_trading_day(now.date()),
                "open": is_trading_day(now.date()) and _at(now.date(), OPEN) <= now < _at(now.date(), session_close(now.date())),
                "close": session_close(now.date()).strftime("%H:%M"),
                "calendar_known": now.year in KNOWN_YEARS,
                "last_completed_session": last_completed_session(now).isoformat(),
            },
            "scheduler": dict(sched, active=self.scheduler_active),
            "next": self.next_events(),
            "jobs": {k: {"title": v[0], "scheduled": v[1], "about": v[2]} for k, v in JOBS.items()},
            "running": running,
            "history": history,
            "bots": bots,
            "intraday": {
                "config": _read_json(d / "config.json", {}),
                "status": _read_json(d / "status.json"),
                "history": _read_json(d / "history" / "summary.json", []) or [],
            },
            "tools": tools,
            "bars_file": {"exists": bars.exists(),
                          "modified": datetime.fromtimestamp(bars.stat().st_mtime, NY).isoformat(timespec="minutes")
                          if bars.exists() else None},
            "messages": list(self.messages)[-80:],
        }


# --------------------------------------------------------------------------
# Tool workers (run in a child process by the jobs above)
# --------------------------------------------------------------------------


def _complete_sessions(bars):
    """Drop today's session while it may still be trading."""
    from .signals import _until, sessions
    days = sessions(bars)
    now = datetime.now(NY)
    if days and days[-1] == now.date().isoformat() and now < _at(now.date(), session_close(now.date())) + DAILY_AFTER:
        return _until(bars, days[-2]) if len(days) > 1 else {}
    return bars


def _backtest_intraday(bars_path: str, config_path: str, out_path: str, runs: int = 40) -> int:
    import numpy as np
    from .intraday import IntradayConfig, backtest, load_bars, random_baseline
    from .signals import sessions
    bars = _complete_sessions(load_bars(bars_path))
    settings = _read_json(Path(config_path), {}) or {}
    settings.pop("interval", None)
    days = sessions(bars)
    if len(days) < 3:
        print("not enough sessions in the bar file")
        return 1
    cfg = IntradayConfig(**settings, trade_from=days[1])
    res = backtest(bars, cfg)
    s = res["summary"]
    rand = [random_baseline(bars, cfg, res["trades"], seed=k)["summary"]["total_return"] for k in range(runs)] \
        if res["trades"] else []
    beat = float(np.mean([s["total_return"] > r for r in rand])) if rand else 0.0
    report = {"sessions": [days[1], days[-1], len(days) - 1], "total_return": s["total_return"],
              "n_trades": s["n_trades"], "win_rate": s.get("win_rate"), "max_drawdown": s.get("max_drawdown_daily"),
              "random_runs": len(rand), "beats_random": beat,
              "random_median": float(np.median(rand)) if rand else None,
              "equity_curve": res["equity"], "trades": res["trades"][-200:],
              "note": "In-sample: the live settings were chosen on recent data. A result here is a check "
                      "of the machinery and the costs, not evidence of an edge."}
    _write_json(Path(out_path), report)
    print(f"{days[1]}..{days[-1]} ({len(days) - 1} sessions): return {s['total_return']:+.2%}, "
          f"{s['n_trades']} trades; beats {beat:.0%} of {len(rand)} random-entry runs")
    return 0


def _indicator_test(bars_path: str, out_path: str, files: list[str]) -> int:
    from .intraday import load_bars
    from .signals import TEST_SESSIONS, WARMUP_SESSIONS, evaluate, load_indicator, sessions
    bars = _complete_sessions(load_bars(bars_path))
    days = sessions(bars)
    if len(days) < WARMUP_SESSIONS + TEST_SESSIONS + 5:
        print(f"need at least {WARMUP_SESSIONS + TEST_SESSIONS + 5} sessions; the file has {len(days)}")
        return 1
    windows = ((days[WARMUP_SESSIONS], days[-TEST_SESSIONS - 1]), (days[-TEST_SESSIONS], days[-1]))
    reports = []
    for f in files:
        try:
            ind = load_indicator(f)
            r = evaluate(bars, ind, random_runs=20, windows=windows)
            reports.append({k: r.get(k) for k in ("name", "timeframe", "path", "windows", "train", "test",
                                                   "test_stress", "random_beaten", "random_median", "gates",
                                                   "passed", "causality")})
            print(f"{ind.name}: test {r['test']['return']:+.2%} on {r['test']['trades']} trades; "
                  f"passed {r['passed']}")
        except Exception as exc:
            reports.append({"path": f, "error": f"{type(exc).__name__}: {exc}"})
            print(f"{Path(f).name}: {type(exc).__name__}: {exc}")
    _write_json(Path(out_path), {"windows": windows, "reports": reports,
                                 "note": "Unofficial: the last 20 complete sessions as test. The registered "
                                         "duel scores fixed dates with scripts/indicator_duel.py."})
    return 0


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------


class StationServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False  # a second station on the same port must fail, not share it

    def __init__(self, address: tuple[str, int], station: Station) -> None:
        super().__init__(address, _StationHandler)
        self.station = station


class _StationHandler(_Handler):
    server: StationServer  # _json (inherited) sends no NaN or Infinity

    def do_GET(self) -> None:  # noqa: N802
        if not self._allowed(post=False):
            return
        path = urlparse(self.path).path
        st = self.server.station
        if path in ("/", "/index.html"):
            try:
                page = PAGE_FILE.read_bytes()
            except OSError:
                page = b"<!doctype html><title>Quantum Station</title><p>local_page.html is missing.</p>"
            self._send(200, page, "text/html; charset=utf-8")
        elif path == "/api/overview":
            self._json(st.overview())
        elif path.startswith("/api/log/"):
            job = path.rsplit("/", 1)[-1]
            if job not in JOBS:
                self._json({"error": "unknown job"}, 404)
                return
            try:
                text = (st.home / "logs" / f"last_{job}.txt").read_text(encoding="utf-8")
            except OSError:
                text = ""
            self._json({"job": job, "output": text[-20000:]})
        elif path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        if not self._allowed(post=True):
            return
        path = urlparse(self.path).path
        st = self.server.station
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._json({"ok": False, "error": "bad JSON"}, 400)
            return
        if not isinstance(body, dict):
            self._json({"ok": False, "error": "expected a JSON object"}, 400)
            return
        if path == "/api/run":
            self._json(st.start(str(body.get("job", ""))))
        elif path == "/api/pause":
            self._json(st.set_paused(bool(body.get("paused", True))))
        elif path == "/api/reset":
            self._json(st.reset(str(body.get("bot", ""))))
        elif path == "/api/open-folder":
            self._json(open_folder(st.home))
        else:
            self._json({"error": "not found"}, 404)


def open_folder(path: Path) -> dict:
    """Show the station's folder in the file manager (this computer only)."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return {"ok": True}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}


def serve(port: int = DEFAULT_PORT, open_browser: bool = True, home: str | Path | None = None,
          block: bool = True, scheduler: bool = True) -> StationServer:
    station = Station(home)
    try:
        server = StationServer(("127.0.0.1", port), station)
    except OSError:
        url = f"http://127.0.0.1:{port}/"
        print(f"Port {port} is in use: the station is probably already running. Opening {url}")
        if open_browser:
            webbrowser.open(url)
        raise
    threading.Thread(target=server.serve_forever, name="station-http", daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    if scheduler:
        station.run_forever()
    print(f"Quantum Station: {url}")
    print(f"Folder: {station.home}")
    print("PAPER trading only. Keep this window open; close it or press Ctrl-C to stop.")
    if open_browser:
        webbrowser.open(url)
    if block:
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            print("stopping")
            station.stop()
            server.shutdown()
    return server


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "_backtest_intraday":
        return _backtest_intraday(*argv[1:4])
    if argv and argv[0] == "_indicator_test":
        return _indicator_test(argv[1], argv[2], argv[3:])
    ap = argparse.ArgumentParser(prog="python -m quantum.local", description=__doc__.split("\n")[0])
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--home", default=None, help="the station's folder (default: local_data/ or QT_LOCAL_HOME)")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--no-scheduler", action="store_true", help="dashboard only; jobs run when you press a button")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run", help="run one job now and exit")
    r.add_argument("job", choices=sorted(JOBS))
    args = ap.parse_args(argv)
    if args.cmd == "run":
        station = Station(args.home)
        res = station.start(args.job, wait=True)
        print(res["job"]["output"])
        return 0 if res["ok"] else 1
    try:
        serve(args.port, not args.no_browser, args.home, scheduler=not args.no_scheduler)
    except OSError as exc:
        print(f"could not start: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
