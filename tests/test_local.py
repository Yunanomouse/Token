"""Quantum Station (quantum/local.py): the local-only paper-trading station.

Covers the NYSE calendar and the scheduler's timing rules (pure functions),
the station's folder seeding, the broker-free child environment, job
bookkeeping with the child processes mocked, the intraday archive, the tool
workers on synthetic bars, and the dashboard's HTTP protections.

No test reaches the network: ``Station._cmd`` is always mocked (or
``subprocess.run`` under it), and the tool workers read local files.
"""

import http.client
import json
import os
import tempfile
import threading
import time
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import numpy as np

from quantum import local
from quantum.local import (
    NY, RETRY_AFTER, ROOT, JobRun, Station, StationServer, _backtest_intraday, _indicator_test,
    due_jobs, intraday_slot, is_trading_day, last_completed_session, paper_env, session_close,
)
from quantum.signals import TEST_SESSIONS, WARMUP_SESSIONS

UTC = timezone.utc


def ny(y, mo, d, h=0, mi=0, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=NY)


# --------------------------------------------------------------------------
# Calendar
# --------------------------------------------------------------------------


class TestCalendar(unittest.TestCase):
    def test_weekends_are_closed(self):
        self.assertFalse(is_trading_day(date(2026, 10, 3)))  # Saturday
        self.assertFalse(is_trading_day(date(2026, 10, 4)))  # Sunday
        self.assertFalse(is_trading_day(date(2027, 1, 2)))

    def test_holidays_2026_and_2027(self):
        for d in ("2026-01-01", "2026-04-03", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
                  "2027-01-18", "2027-03-26", "2027-06-18", "2027-07-05", "2027-11-25", "2027-12-24"):
            self.assertFalse(is_trading_day(date.fromisoformat(d)), d)

    def test_normal_days_are_open(self):
        for d in ("2026-10-01", "2026-11-25", "2026-11-27", "2026-12-24", "2027-06-17", "2027-12-23",
                  "2027-03-25", "2028-03-01"):
            self.assertTrue(is_trading_day(date.fromisoformat(d)), d)

    def test_session_close(self):
        self.assertEqual(session_close(date(2026, 11, 27)).strftime("%H:%M"), "13:00")
        self.assertEqual(session_close(date(2026, 12, 24)).strftime("%H:%M"), "13:00")
        self.assertEqual(session_close(date(2027, 11, 26)).strftime("%H:%M"), "13:00")
        for d in (date(2026, 10, 1), date(2026, 11, 25), date(2026, 12, 23), date(2027, 12, 23)):
            self.assertEqual(session_close(d).strftime("%H:%M"), "16:00", d)

    def test_last_completed_session(self):
        cases = [
            (ny(2026, 10, 1, 16, 29, 59), "2026-09-30"),   # Thursday, before 16:30
            (ny(2026, 10, 1, 16, 30), "2026-10-01"),       # exactly 16:30
            (ny(2026, 10, 1, 23, 0), "2026-10-01"),
            (ny(2026, 10, 1, 3, 0), "2026-09-30"),
            (ny(2026, 10, 3, 12, 0), "2026-10-02"),        # Saturday
            (ny(2026, 10, 4, 22, 0), "2026-10-02"),        # Sunday
            (ny(2026, 10, 5, 9, 0), "2026-10-02"),         # Monday morning -> Friday
            (ny(2026, 9, 8, 10, 0), "2026-09-04"),         # Tuesday after Labor Day
            (ny(2026, 9, 7, 18, 0), "2026-09-04"),         # Labor Day evening
            (ny(2026, 7, 6, 9, 0), "2026-07-02"),          # Monday after the 07-03 holiday
            (ny(2026, 11, 26, 20, 0), "2026-11-25"),       # Thanksgiving
            (ny(2026, 11, 27, 13, 29), "2026-11-25"),      # early close, before 13:30
            (ny(2026, 11, 27, 13, 30), "2026-11-27"),
            (ny(2026, 12, 24, 14, 0), "2026-12-24"),
            (ny(2026, 12, 25, 18, 0), "2026-12-24"),
            (ny(2027, 3, 26, 18, 0), "2027-03-25"),        # Good Friday
            (ny(2027, 12, 27, 9, 0), "2027-12-23"),        # Christmas 2027 observed Friday 24th
        ]
        for now, want in cases:
            self.assertEqual(last_completed_session(now).isoformat(), want, now)

    def test_last_completed_session_from_utc_and_across_dst(self):
        # 20:31 UTC on 2026-10-01 is 16:31 EDT (UTC-4).
        self.assertEqual(last_completed_session(datetime(2026, 10, 1, 20, 31, tzinfo=UTC)).isoformat(),
                         "2026-10-01")
        self.assertEqual(last_completed_session(datetime(2026, 10, 1, 20, 29, tzinfo=UTC)).isoformat(),
                         "2026-09-30")
        # DST ends on Sunday 2026-11-01: on Monday 11-02 New York is UTC-5, so
        # 20:31 UTC is only 15:31 there (it would have been 16:31 the week before).
        self.assertEqual(last_completed_session(datetime(2026, 10, 30, 20, 31, tzinfo=UTC)).isoformat(),
                         "2026-10-30")
        self.assertEqual(last_completed_session(datetime(2026, 11, 2, 20, 31, tzinfo=UTC)).isoformat(),
                         "2026-10-30")
        self.assertEqual(last_completed_session(datetime(2026, 11, 2, 21, 29, tzinfo=UTC)).isoformat(),
                         "2026-10-30")
        self.assertEqual(last_completed_session(datetime(2026, 11, 2, 21, 30, tzinfo=UTC)).isoformat(),
                         "2026-11-02")
        # Sunday of the change itself rolls back to Friday.
        self.assertEqual(last_completed_session(ny(2026, 11, 1, 1, 30)).isoformat(), "2026-10-30")


class TestIntradaySlot(unittest.TestCase):
    def test_slots_in_a_normal_session(self):
        self.assertIsNone(intraday_slot(ny(2026, 10, 1, 9, 35, 39)))
        self.assertEqual(intraday_slot(ny(2026, 10, 1, 9, 35, 40)), "2026-10-01#1")
        self.assertEqual(intraday_slot(ny(2026, 10, 1, 9, 40, 39)), "2026-10-01#1")
        self.assertEqual(intraday_slot(ny(2026, 10, 1, 9, 40, 40)), "2026-10-01#2")
        self.assertEqual(intraday_slot(ny(2026, 10, 1, 9, 45, 40)), "2026-10-01#3")
        self.assertEqual(intraday_slot(ny(2026, 10, 1, 16, 5, 39)), "2026-10-01#78")  # the 15:55 bar
        self.assertIsNone(intraday_slot(ny(2026, 10, 1, 16, 5, 40)))
        self.assertIsNone(intraday_slot(ny(2026, 10, 1, 8, 0)))
        self.assertIsNone(intraday_slot(ny(2026, 10, 1, 20, 0)))

    def test_slot_increments_every_five_minutes(self):
        t = ny(2026, 10, 1, 9, 35, 40)
        for n in range(1, 79):
            self.assertEqual(intraday_slot(t), f"2026-10-01#{n}")
            t += timedelta(minutes=5)
        self.assertIsNone(intraday_slot(t))

    def test_no_slot_on_closed_days(self):
        self.assertIsNone(intraday_slot(ny(2026, 10, 3, 11, 0)))   # Saturday
        self.assertIsNone(intraday_slot(ny(2026, 11, 26, 11, 0)))  # Thanksgiving
        self.assertIsNone(intraday_slot(ny(2027, 3, 26, 11, 0)))   # Good Friday

    def test_early_close(self):
        self.assertEqual(intraday_slot(ny(2026, 11, 27, 13, 5, 39)), "2026-11-27#42")  # the 12:55 bar
        self.assertIsNone(intraday_slot(ny(2026, 11, 27, 13, 5, 40)))
        self.assertIsNone(intraday_slot(ny(2026, 12, 24, 14, 0)))

    def test_slot_from_utc_after_dst_change(self):
        # Monday 2026-11-02 (EST, UTC-5): 14:35:40 UTC is 09:35:40 in New York.
        self.assertEqual(intraday_slot(datetime(2026, 11, 2, 14, 35, 40, tzinfo=UTC)), "2026-11-02#1")
        self.assertIsNone(intraday_slot(datetime(2026, 11, 2, 13, 35, 40, tzinfo=UTC)))


class TestDueJobs(unittest.TestCase):
    def test_daily_due_only_when_behind(self):
        now = ny(2026, 10, 1, 17, 0)
        self.assertIn("daily", due_jobs(now, {"daily_done": "2026-09-30"}))
        self.assertIn("daily", due_jobs(now, {}))
        self.assertNotIn("daily", due_jobs(now, {"daily_done": "2026-10-01"}))
        # Before 16:30 the last completed session is yesterday.
        self.assertNotIn("daily", due_jobs(ny(2026, 10, 1, 16, 0), {"daily_done": "2026-09-30"}))

    def test_catch_up_after_days_off_is_one_daily(self):
        jobs = due_jobs(ny(2026, 10, 5, 8, 0), {"daily_done": "2026-09-25"})
        self.assertEqual(jobs.count("daily"), 1)
        self.assertEqual(jobs, ["daily"])

    def test_intraday_once_per_slot(self):
        now = ny(2026, 10, 1, 10, 0, 40)
        slot = intraday_slot(now)
        base = {"daily_done": "2026-09-30"}
        self.assertEqual(due_jobs(now, dict(base)), ["intraday"])
        self.assertEqual(due_jobs(now, dict(base, intraday_slot=slot)), [])
        self.assertEqual(due_jobs(now + timedelta(minutes=5), dict(base, intraday_slot=slot)), ["intraday"])
        self.assertEqual(due_jobs(ny(2026, 10, 3, 11, 0), {"daily_done": "2026-10-02"}), [])

    def test_intraday_close_once_after_the_close(self):
        base = {"daily_done": "2026-10-01"}
        self.assertNotIn("intraday_close", due_jobs(ny(2026, 10, 1, 16, 5, 39), dict(base)))
        self.assertIn("intraday_close", due_jobs(ny(2026, 10, 1, 16, 5, 40), dict(base, archived="2026-09-30")))
        self.assertIn("intraday_close", due_jobs(ny(2026, 10, 1, 22, 0), dict(base)))
        self.assertNotIn("intraday_close", due_jobs(ny(2026, 10, 1, 22, 0), dict(base, archived="2026-10-01")))
        self.assertNotIn("intraday_close", due_jobs(ny(2026, 11, 26, 18, 0), {"daily_done": "2026-11-25"}))
        self.assertIn("intraday_close", due_jobs(ny(2026, 11, 27, 13, 5, 40), {"daily_done": "2026-11-25"}))

    def test_retry_time_suppresses_until_it_passes(self):
        now = ny(2026, 10, 1, 17, 0)
        sched = {"daily_done": "2026-09-30", "archived": "2026-10-01",
                 "retry": {"daily": (now + timedelta(minutes=5)).isoformat(timespec="seconds")}}
        self.assertEqual(due_jobs(now, sched), [])
        self.assertEqual(due_jobs(now + timedelta(minutes=5), sched), ["daily"])
        sched["retry"] = {"intraday_close": (now + timedelta(minutes=1)).isoformat(), "daily": "2000-01-01T00:00:00+00:00"}
        sched.pop("archived")
        self.assertEqual(due_jobs(now, sched), ["daily"])
        self.assertEqual(due_jobs(now + timedelta(minutes=1), sched), ["daily", "intraday_close"])


# --------------------------------------------------------------------------
# Station (folder, environment, jobs)
# --------------------------------------------------------------------------


class _StationCase(unittest.TestCase):
    copy_state = True

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name) / "station"
        self.now = ny(2026, 10, 1, 17, 0)
        self.st = Station(home=self.home, clock=lambda: self.now, copy_state=self.copy_state)
        self.calls = []
        self.fail_on = None   # substring of a command that should fail
        self.on_cmd = None    # extra side effect (args) -> None

    def tearDown(self):
        self._tmp.cleanup()

    def fake_cmd(self, run, args, timeout=900.0):
        self.calls.append(list(args))
        code = 1 if self.fail_on and any(self.fail_on in a for a in args) else 0
        if self.on_cmd:
            self.on_cmd(args)
        run.steps.append({"cmd": " ".join(args), "code": code, "seconds": 0.0})
        run.output += f"$ {' '.join(args)}\n[exit {code}]\n"
        return code

    def mocked(self):
        return mock.patch.object(Station, "_cmd", autospec=True,
                                 side_effect=lambda _self, run, args, timeout=900.0: self.fake_cmd(run, args, timeout))

    def wait_idle(self, st=None):
        st = st or self.st
        for _ in range(200):
            if not st.running:
                return
            time.sleep(0.01)
        self.fail("jobs did not finish")


class TestSeed(_StationCase):
    def test_folders_and_configs(self):
        for sub in ("main", "small", "intraday", "intraday/history", "data", "logs", "indicators", "tools"):
            self.assertTrue((self.home / sub).is_dir(), sub)
        for name, repo_cfg in (("main", "live/config.json"), ("small", "live/real/config.json")):
            cfg = json.loads((self.home / name / "config.json").read_text())
            self.assertEqual(cfg["state_path"], str(self.home / name / "state.json"))
            self.assertEqual(cfg["mode"], "paper")
            repo = json.loads((ROOT / repo_cfg).read_text())
            self.assertEqual(cfg["tickers"], repo["tickers"])
        for f in ("config.json", "universe.txt"):
            self.assertEqual((self.home / "intraday" / f).read_bytes(), (ROOT / "live/intraday" / f).read_bytes())

    def test_state_is_copied(self):
        self.assertEqual((self.home / "main" / "state.json").read_bytes(), (ROOT / "live/state.json").read_bytes())
        self.assertEqual((self.home / "small" / "state.json").read_bytes(),
                         (ROOT / "live/real/state.json").read_bytes())
        self.assertIn(str(self.home / "main" / "state.json"), self.st.created)

    def test_second_station_overwrites_nothing(self):
        cfg_path = self.home / "main" / "config.json"
        cfg = json.loads(cfg_path.read_text())
        cfg["mine"] = True
        cfg_path.write_text(json.dumps(cfg))
        (self.home / "main" / "state.json").write_text('{"mine": 1}')
        (self.home / "intraday" / "universe.txt").write_text("ZZZ\n")
        st2 = Station(home=self.home, clock=lambda: self.now)
        self.assertEqual(st2.created, [])
        self.assertTrue(json.loads(cfg_path.read_text())["mine"])
        self.assertEqual((self.home / "main" / "state.json").read_text(), '{"mine": 1}')
        self.assertEqual((self.home / "intraday" / "universe.txt").read_text(), "ZZZ\n")


class TestSeedWithoutState(_StationCase):
    copy_state = False

    def test_state_not_copied(self):
        self.assertTrue((self.home / "main" / "config.json").exists())
        self.assertFalse((self.home / "main" / "state.json").exists())
        self.assertFalse((self.home / "small" / "state.json").exists())


BROKER_VARS = {"QT_BROKER": "alpaca", "QT_ALLOW_REAL_MONEY": "yes", "ALPACA_API_KEY_ID": "k",
               "ALPACA_API_SECRET_KEY": "s", "ALPACA_BASE_URL": "https://api.alpaca.markets", "ALPACA_FOO": "x"}


class TestPaperEnv(_StationCase):
    def test_paper_env_drops_broker_settings(self):
        with mock.patch.dict(os.environ, dict(BROKER_VARS, PYTHONPATH="/somewhere")):
            env = paper_env()
        for k in BROKER_VARS:
            self.assertNotIn(k, env)
        parts = env["PYTHONPATH"].split(os.pathsep)
        self.assertEqual(parts[0], str(ROOT))
        self.assertIn("/somewhere", parts)
        with mock.patch.dict(os.environ, BROKER_VARS):
            os.environ.pop("PYTHONPATH", None)
            self.assertEqual(paper_env()["PYTHONPATH"], str(ROOT))

    def test_daily_engine_runs_with_broker_paper(self):
        with mock.patch.dict(os.environ, BROKER_VARS), self.mocked():
            res = self.st.start("daily", wait=True)
        self.assertTrue(res["ok"])
        engines = [c for c in self.calls if c[:3] == ["-m", "quantum", "live"]]
        self.assertEqual(len(engines), 2)
        for c in engines:
            i = c.index("--broker")
            self.assertEqual(c[i + 1], "paper")
        self.assertIn("--orders", engines[1])

    def test_real_cmd_passes_paper_env_to_the_child(self):
        seen = {}

        def fake_run(cmd, **kw):
            seen.update(kw, cmd=cmd)
            return mock.Mock(returncode=0, stdout="hi", stderr="")

        run = JobRun("daily", "now")
        with mock.patch.dict(os.environ, BROKER_VARS), mock.patch.object(local.subprocess, "run", fake_run):
            code = self.st._cmd(run, ["-m", "quantum", "--version"])
        self.assertEqual(code, 0)
        for k in BROKER_VARS:
            self.assertNotIn(k, seen["env"])
        self.assertEqual(seen["cwd"], ROOT)
        self.assertEqual(run.steps[0]["code"], 0)
        self.assertIn("hi", run.output)


class TestJobs(_StationCase):
    def test_successful_daily_sets_daily_done(self):
        self.st.sched["daily_done"] = "2026-09-29"
        with self.mocked():
            res = self.st.start("daily", wait=True)
        self.assertTrue(res["ok"])
        self.assertEqual(len(self.calls), 4)
        self.assertEqual(self.st.sched["daily_done"], "2026-10-01")
        self.assertNotIn("daily", self.st.sched["retry"])
        saved = json.loads((self.home / "scheduler.json").read_text())
        self.assertEqual(saved["daily_done"], "2026-10-01")
        self.assertTrue((self.home / "logs" / "last_daily.txt").exists())

    def test_failing_step_sets_retry(self):
        self.st.sched["daily_done"] = "2026-09-29"
        self.fail_on = str(self.home / "small" / "prices.csv")  # the $40 bot's fetch fails
        with self.mocked():
            res = self.st.start("daily", wait=True)
        self.assertFalse(res["ok"])
        self.assertEqual(self.st.sched["daily_done"], "2026-09-29")
        want = (self.now + RETRY_AFTER).isoformat(timespec="seconds")
        self.assertEqual(self.st.sched["retry"]["daily"], want)
        saved = json.loads((self.home / "scheduler.json").read_text())
        self.assertEqual(saved["retry"]["daily"], want)
        self.assertEqual(saved["daily_done"], "2026-09-29")
        # Not due again until the retry time passes.
        self.assertNotIn("daily", due_jobs(self.now + timedelta(minutes=19), saved))
        self.assertIn("daily", due_jobs(self.now + RETRY_AFTER, saved))
        # A later success clears the retry.
        self.fail_on = None
        with self.mocked():
            self.assertTrue(self.st.start("daily", wait=True)["ok"])
        self.assertNotIn("daily", self.st.sched["retry"])

    def test_start_refuses_running_and_unknown(self):
        self.st.running["daily"] = JobRun("daily", "x")
        with self.mocked():
            r = self.st.start("daily", wait=True)
            self.assertFalse(r["ok"])
            self.assertIn("already running", r["error"])
            r = self.st.start("rm_rf", wait=True)
            self.assertFalse(r["ok"])
        self.assertEqual(self.calls, [])

    def test_tick_starts_due_jobs(self):
        self.st.sched["daily_done"] = "2026-09-30"
        with self.mocked():
            started = self.st.tick()
            self.wait_idle()
        self.assertEqual(sorted(started), ["daily", "intraday_close"])
        self.assertEqual(self.st.sched["daily_done"], "2026-10-01")
        self.assertEqual(self.st.sched["archived"], "2026-10-01")
        with self.mocked():
            self.assertEqual(self.st.tick(), [])

    def test_tick_does_nothing_when_paused(self):
        self.st.sched["daily_done"] = "2026-09-30"
        self.st.set_paused(True)
        self.assertTrue(json.loads((self.home / "scheduler.json").read_text())["paused"])
        with self.mocked():
            self.assertEqual(self.st.tick(), [])
        self.assertEqual(self.calls, [])

    def test_intraday_records_slot(self):
        self.now = ny(2026, 10, 1, 10, 0, 40)
        self.st.sched["daily_done"] = "2026-09-30"
        with self.mocked():
            self.assertEqual(self.st.tick(), ["intraday"])
            self.wait_idle()
            self.assertEqual(self.st.sched["intraday_slot"], "2026-10-01#6")
            self.assertEqual(self.st.tick(), [])

    def test_reset(self):
        d = self.home / "main"
        (d / "snapshot.json").write_text("{}")
        self.st.sched["daily_done"] = "2026-10-01"
        r = self.st.reset("main")
        self.assertTrue(r["ok"])
        self.assertEqual(sorted(r["moved"]), ["snapshot.json", "state.json"])
        self.assertFalse((d / "state.json").exists())
        self.assertTrue((d / "state.json.20261001-170000.bak").exists())
        self.assertTrue((d / "snapshot.json.20261001-170000.bak").exists())
        self.assertNotIn("daily_done", self.st.sched)
        self.assertNotIn("daily_done", json.loads((self.home / "scheduler.json").read_text()))
        self.assertTrue((self.home / "small" / "state.json").exists())
        self.assertFalse(self.st.reset("../main")["ok"])
        self.assertFalse(self.st.reset("intraday")["ok"])
        self.st.running["daily"] = JobRun("daily", "x")
        self.assertFalse(self.st.reset("small")["ok"])


class TestIntradayClose(_StationCase):
    def setUp(self):
        super().setUp()
        self.idir = self.home / "intraday"
        self.status = {"date": "2026-10-01", "start_cash": 50.0, "equity": 55.0, "trades": [{}, {}, {}]}

    def _write_status(self, args):
        if any(a.endswith("intraday_live.py") for a in args):
            (self.idir / "status.json").write_text(json.dumps(self.status))

    def test_archives_today(self):
        (self.idir / "history" / "summary.json").write_text(json.dumps([
            {"date": "2026-10-01", "start_cash": 50, "equity": 40, "return": -0.2, "trades": 9},
            {"date": "2026-09-30", "start_cash": 50, "equity": 51, "return": 0.02, "trades": 1},
        ]))
        self.on_cmd = self._write_status
        with self.mocked():
            res = self.st.start("intraday_close", wait=True)
        self.assertTrue(res["ok"])
        self.assertEqual(json.loads((self.idir / "history" / "2026-10-01.json").read_text()), self.status)
        summary = json.loads((self.idir / "history" / "summary.json").read_text())
        self.assertEqual([s["date"] for s in summary], ["2026-09-30", "2026-10-01"])
        today = summary[1]
        self.assertAlmostEqual(today["return"], 0.1)
        self.assertEqual(today["trades"], 3)
        self.assertEqual(today["equity"], 55.0)
        self.assertEqual(self.st.sched["archived"], "2026-10-01")
        self.assertNotIn("intraday_close", due_jobs(self.now, self.st.sched))

    def test_no_status_for_today_archives_nothing(self):
        self.status["date"] = "2026-09-30"
        self.on_cmd = self._write_status
        with self.mocked():
            res = self.st.start("intraday_close", wait=True)
        self.assertTrue(res["ok"])
        self.assertFalse((self.idir / "history" / "2026-10-01.json").exists())
        self.assertFalse((self.idir / "history" / "summary.json").exists())
        self.assertEqual(self.st.sched["archived"], "2026-10-01")
        self.assertIn("nothing archived", res["job"]["output"])

    def test_failed_run_does_not_archive(self):
        self.fail_on = "intraday_live.py"
        with self.mocked():
            self.assertFalse(self.st.start("intraday_close", wait=True)["ok"])
        self.assertNotIn("archived", self.st.sched)
        self.assertIn("intraday_close", self.st.sched["retry"])

    # An equity of 0.0 is a real value (a day that lost everything), not a missing one.
    def test_zero_equity_is_a_total_loss(self):
        self.status["equity"] = 0.0
        self.on_cmd = self._write_status
        with self.mocked():
            self.st.start("intraday_close", wait=True)
        summary = json.loads((self.idir / "history" / "summary.json").read_text())
        self.assertAlmostEqual(summary[0]["return"], -1.0)


# --------------------------------------------------------------------------
# Overview
# --------------------------------------------------------------------------


OVERVIEW_KEYS = {"now", "home", "paper", "market", "scheduler", "next", "jobs", "running", "history", "bots",
                 "intraday", "tools", "bars_file", "messages"}


class TestOverview(_StationCase):
    def test_bots_and_snapshots(self):
        snap = {"equity": 101234.5, "date": "2026-10-01"}
        (self.home / "main" / "snapshot.json").write_text(json.dumps(snap))
        ov = self.st.overview()
        self.assertTrue(OVERVIEW_KEYS <= set(ov))
        self.assertTrue(ov["paper"])
        self.assertEqual(set(ov["bots"]), {"main", "small"})
        self.assertEqual(ov["bots"]["main"]["snapshot"], snap)
        self.assertIsNone(ov["bots"]["small"]["snapshot"])
        self.assertEqual(ov["bots"]["main"]["config"]["mode"], "paper")
        self.assertEqual(ov["market"]["last_completed_session"], "2026-10-01")
        self.assertTrue(ov["market"]["trading_day"])
        self.assertFalse(ov["market"]["open"])
        self.assertEqual(ov["home"], str(self.home))
        self.assertFalse(ov["bars_file"]["exists"])
        json.dumps(ov)  # must be serialisable

    def test_running_and_history(self):
        gate = threading.Event()
        self.on_cmd = lambda args: gate.wait(5)
        with self.mocked():
            self.assertTrue(self.st.start("fetch_bars")["ok"])
            for _ in range(200):
                if self.calls:
                    break
                time.sleep(0.01)
            ov = self.st.overview()
            self.assertIn("fetch_bars", ov["running"])
            self.assertIsNone(ov["running"]["fetch_bars"]["ok"])
            gate.set()
            self.wait_idle()
        ov = self.st.overview()
        self.assertEqual(ov["running"], {})
        self.assertEqual(ov["history"][0]["job"], "fetch_bars")
        self.assertTrue(ov["history"][0]["ok"])


# --------------------------------------------------------------------------
# Tool workers on synthetic bars
# --------------------------------------------------------------------------


def _weekdays(start: date, n: int) -> list[date]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _write_bars(path: Path, n_sessions: int, tickers=("AAA", "BBB", "CCC", "DDD"), seed: int = 7) -> None:
    rng = np.random.default_rng(seed)
    lines = ["datetime,ticker,open,high,low,close,volume"]
    price = {t: 5.0 + 3 * i for i, t in enumerate(tickers)}
    for d in _weekdays(date(2025, 1, 6), n_sessions):
        for b in range(78):
            m = 9 * 60 + 30 + 5 * b
            stamp = f"{d.isoformat()} {m // 60:02d}:{m % 60:02d}:00"
            for t in tickers:
                o = price[t]
                c = max(1.0, o * (1 + rng.normal(0.0002, 0.004)))
                hi, lo = max(o, c) * 1.001, min(o, c) * 0.999
                lines.append(f"{stamp},{t},{o:.4f},{hi:.4f},{lo:.4f},{c:.4f},{int(rng.integers(1000, 50000))}")
                price[t] = c
    path.write_text("\n".join(lines) + "\n")


class TestToolWorkers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls._tmp.name)
        cls.bars = cls.dir / "bars_5m.csv"
        _write_bars(cls.bars, WARMUP_SESSIONS + TEST_SESSIONS + 6)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _check_backtest_report(self, out):
        rep = json.loads(out.read_text())
        for k in ("total_return", "n_trades", "beats_random", "random_runs", "sessions", "equity_curve"):
            self.assertIn(k, rep)
        self.assertGreater(rep["n_trades"], 0)
        self.assertEqual(rep["random_runs"], 3)
        self.assertTrue(0.0 <= rep["beats_random"] <= 1.0)

    def test_backtest_intraday(self):
        out = self.dir / "bt.json"
        code = _backtest_intraday(str(self.bars), str(ROOT / "live/intraday/config.json"), str(out), runs=3)
        self.assertEqual(code, 0)
        self._check_backtest_report(out)

    def test_backtest_intraday_needs_sessions(self):
        short = self.dir / "short.csv"
        _write_bars(short, 2)
        out = self.dir / "bt_short.json"
        self.assertEqual(_backtest_intraday(str(short), str(ROOT / "live/intraday/config.json"), str(out), runs=1), 1)
        self.assertFalse(out.exists())

    def test_indicator_test(self):
        broken = self.dir / "broken.py"
        broken.write_text("NAME = 'broken'\nTIMEFRAME = 5\n\ndef signals(bars):\n    raise RuntimeError('boom')\n")
        out = self.dir / "ind.json"
        code = _indicator_test(str(self.bars), str(out), [str(ROOT / "indicators/kama_baseline.py"), str(broken)])
        self.assertEqual(code, 0)
        rep = json.loads(out.read_text())
        self.assertEqual(len(rep["reports"]), 2)
        good, bad = rep["reports"]
        self.assertNotIn("error", good)
        self.assertIn("test", good)
        self.assertIn("passed", good)
        self.assertEqual(good["windows"]["test"][2], TEST_SESSIONS)
        self.assertIn("error", bad)
        self.assertIn("boom", bad["error"])

    def test_indicator_test_needs_sessions(self):
        short = self.dir / "short2.csv"
        _write_bars(short, WARMUP_SESSIONS + TEST_SESSIONS + 4)
        out = self.dir / "ind_short.json"
        self.assertEqual(_indicator_test(str(short), str(out), [str(ROOT / "indicators/kama_baseline.py")]), 1)
        self.assertFalse(out.exists())


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------


class TestStationHTTP(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.now = ny(2026, 10, 1, 17, 0)
        self.st = Station(home=Path(self._tmp.name) / "home", clock=lambda: self.now, copy_state=False)
        self.srv = StationServer(("127.0.0.1", 0), self.st)
        self.port = self.srv.server_address[1]
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self._tmp.cleanup()

    def _request(self, method, path, body=None, headers=None, host=None, raw=False):
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
            return r.status, (payload if raw else json.loads(payload or b"{}"))
        finally:
            conn.close()

    def post(self, path, body):
        status, obj = self._request("POST", path, body, headers={"Origin": f"http://127.0.0.1:{self.port}"})
        self.assertEqual(status, 200)
        return obj

    def test_page(self):
        status, html = self._request("GET", "/", raw=True)
        self.assertEqual(status, 200)
        text = html.decode("utf-8")
        if local.PAGE_FILE.exists():
            self.assertEqual(html, local.PAGE_FILE.read_bytes())
        else:
            self.assertIn("local_page.html is missing", text)
        self.assertIn("Quantum Station", text)

    def test_overview(self):
        status, ov = self._request("GET", "/api/overview")
        self.assertEqual(status, 200)
        self.assertTrue(OVERVIEW_KEYS <= set(ov))
        self.assertIs(ov["paper"], True)
        self.assertEqual(set(ov["jobs"]), set(local.JOBS))

    def test_bad_host(self):
        for host in ("evil.example", f"evil.example:{self.port}", "127.0.0.1", ""):
            status, _ = self._request("GET", "/api/overview", host=host)
            self.assertEqual(status, 403, host)
            status, _ = self._request("POST", "/api/pause", {"paused": True}, host=host)
            self.assertEqual(status, 403, host)
        self.assertFalse(self.st.sched["paused"])
        status, _ = self._request("GET", "/api/overview", host=f"localhost:{self.port}")
        self.assertEqual(status, 200)

    def test_non_json_post(self):
        body = json.dumps({"paused": True}).encode()
        status, _ = self._request("POST", "/api/pause", body, headers={"Content-Type": "text/plain"})
        self.assertEqual(status, 415)
        status, _ = self._request("POST", "/api/pause", body, headers={"Content-Type": None})
        self.assertEqual(status, 415)
        self.assertFalse(self.st.sched["paused"])

    def test_foreign_origin(self):
        for origin in ("http://evil.example", "null", f"http://127.0.0.1:{self.port + 1}"):
            status, _ = self._request("POST", "/api/pause", {"paused": True}, headers={"Origin": origin})
            self.assertEqual(status, 403, origin)
        self.assertFalse(self.st.sched["paused"])

    def test_run_unknown_job(self):
        r = self.post("/api/run", {"job": "../../etc"})
        self.assertFalse(r["ok"])
        self.assertFalse(self.post("/api/run", {})["ok"])
        self.assertEqual(self.st.running, {})

    def test_run_known_job_with_mocked_cmd(self):
        def fake(_self, run, args, timeout=900.0):
            run.steps.append({"cmd": "x", "code": 0, "seconds": 0})
            run.output += "fake output\n"
            return 0
        with mock.patch.object(Station, "_cmd", autospec=True, side_effect=fake):
            self.assertTrue(self.post("/api/run", {"job": "fetch_bars"})["ok"])
            for _ in range(200):
                if not self.st.running:
                    break
                time.sleep(0.01)
        status, log = self._request("GET", "/api/log/fetch_bars")
        self.assertEqual(status, 200)
        self.assertIn("fake output", log["output"])

    def test_pause_toggles(self):
        self.assertTrue(self.post("/api/pause", {"paused": True})["paused"])
        self.assertTrue(self.st.sched["paused"])
        self.assertFalse(self.post("/api/pause", {"paused": False})["paused"])
        self.assertFalse(self.st.sched["paused"])

    def test_reset_unknown_bot(self):
        self.assertFalse(self.post("/api/reset", {"bot": "../main"})["ok"])

    def test_log_unknown_is_404(self):
        status, _ = self._request("GET", "/api/log/nope")
        self.assertEqual(status, 404)
        status, _ = self._request("GET", "/api/log/..%2Fscheduler")
        self.assertEqual(status, 404)
        status, _ = self._request("GET", "/nothing")
        self.assertEqual(status, 404)

    def test_bad_json(self):
        status, _ = self._request("POST", "/api/pause", b"{not json", headers={"Origin": None})
        self.assertEqual(status, 400)
        status, _ = self._request("POST", "/api/pause", [1, 2])
        self.assertEqual(status, 400)

    def test_second_server_on_same_port_fails(self):
        with self.assertRaises(OSError):
            StationServer(("127.0.0.1", self.port), self.st)


if __name__ == "__main__":
    unittest.main()
