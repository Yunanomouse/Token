"""Hardening of the desktop dashboard (quantum/desktop.py).

Client-supplied paths must stay inside the working directory, the HTTP API
must refuse requests a web page could forge (wrong Host, foreign Origin,
non-JSON POST), a resumed replay must reconcile against a re-adjusted CSV,
and the fill count must leave out bookkeeping fills.
"""

import http.client
import json
import math
import tempfile
import time
import unittest
from pathlib import Path

from quantum.desktop import Controller, serve

TICKERS = ["AAA", "BBB"]


def _write_prices(path: Path, n: int, halve: str | None = None) -> None:
    """A smooth two-ticker price file; ``halve`` divides one ticker's history by 2."""
    lines = ["date," + ",".join(TICKERS)]
    for i in range(n):
        day = f"2020-{1 + i // 28:02d}-{1 + i % 28:02d}"
        row = []
        for j, t in enumerate(TICKERS):
            p = (100.0 + 20 * j) * (1.0 + 0.002 * i + 0.01 * math.sin(i / 3 + j))
            if t == halve:
                p /= 2.0
            row.append(f"{p:.4f}")
        lines.append(day + "," + ",".join(row))
    path.write_text("\n".join(lines) + "\n")


class TestDesktopHardening(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.work = base / "work"
        self.outside = base / "outside"
        (self.work / "data" / "prices").mkdir(parents=True)
        self.outside.mkdir()
        self.csv = self.work / "data" / "prices" / "synthetic.csv"
        _write_prices(self.csv, 80)
        self.srv = serve(port=0, open_browser=False, workdir=self.work, block=False)
        self.port = self.srv.server_address[1]

    def tearDown(self):
        self.srv.controller.stop()
        self.srv.shutdown()
        self.srv.server_close()
        self._tmp.cleanup()

    # -- raw HTTP ------------------------------------------------------------
    def _request(self, method, path, body=None, headers=None, host=None):
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
            return r.status, json.loads(r.read() or b"{}")
        finally:
            conn.close()

    def get(self, path):
        status, obj = self._request("GET", path)
        self.assertEqual(status, 200)
        return obj

    def post(self, path, body):
        status, obj = self._request("POST", path, body, headers={"Origin": f"http://127.0.0.1:{self.port}"})
        self.assertEqual(status, 200)
        return obj

    def _form(self, **kw):
        form = {"mode": "replay", "csv": "data/prices/synthetic.csv", "tickers": ",".join(TICKERS),
                "bars_per_second": 0, "fresh": True, "window": 10, "strategy": "equal_weight",
                "max_weight": 1.0, "max_turnover": 1.0, "max_drawdown": 0.9, "rebalance_every": 5}
        form.update(kw)
        return form

    def _wait_idle(self):
        for _ in range(200):
            st = self.get("/api/state")
            if not st["running"]:
                return st
            time.sleep(0.05)
        self.fail("engine did not finish")

    # -- paths ---------------------------------------------------------------
    def test_reset_refuses_paths_outside_the_workdir(self):
        victim = self.outside / "victim.json"
        victim.write_text("keep me")
        for name in ("../outside/victim.json", str(victim), "data/../../outside/victim.json",
                     "data/live_state.json", "notes.txt"):
            r = self.post("/api/reset", {"state_path": name})
            self.assertFalse(r["ok"], name)
        self.assertEqual(victim.read_text(), "keep me")
        self.assertTrue(self.post("/api/reset", {"state_path": "live_state.json"})["ok"])

    def test_start_refuses_outside_csv_and_state_path(self):
        outside_csv = self.outside / "prices.csv"
        _write_prices(outside_csv, 40)
        for csv in ("../outside/prices.csv", str(outside_csv), "../outside/../work/../outside/prices.csv"):
            r = self.post("/api/start", self._form(csv=csv))
            self.assertFalse(r["ok"], csv)
        self.assertFalse(self.post("/api/start", self._form(csv="data/prices/synthetic.txt"))["ok"])
        for state in ("../outside/state.json", str(self.outside / "state.json"), "data/state.json"):
            r = self.post("/api/start", self._form(state_path=state))
            self.assertFalse(r["ok"], state)
            self.assertIn("state file", r["error"])
        self.assertEqual(sorted(p.name for p in self.outside.iterdir()), ["prices.csv"])
        self.assertFalse(self.srv.controller.running)

    def test_resume_refuses_paths_outside_the_workdir(self):
        victim = self.outside / "victim.json"
        victim.write_text('{"halted": true}')
        for name in ("../outside/victim.json", str(victim)):
            self.assertFalse(self.post("/api/resume", {"state_path": name})["ok"])
        self.assertEqual(victim.read_text(), '{"halted": true}')

    # -- request forgery -----------------------------------------------------
    def test_text_plain_post_is_refused(self):
        body = json.dumps({"state_path": "live_state.json"}).encode()
        status, _ = self._request("POST", "/api/reset", body, headers={"Content-Type": "text/plain"})
        self.assertEqual(status, 415)
        status, _ = self._request("POST", "/api/start", json.dumps(self._form()).encode(),
                                  headers={"Content-Type": None})
        self.assertEqual(status, 415)
        self.assertFalse(self.srv.controller.running)

    def test_foreign_origin_is_refused(self):
        for origin in ("http://evil.example", "null", f"http://127.0.0.1:{self.port + 1}"):
            status, _ = self._request("POST", "/api/start", self._form(), headers={"Origin": origin})
            self.assertEqual(status, 403, origin)
        self.assertFalse(self.srv.controller.running)

    def test_bad_host_is_refused(self):
        for host in ("evil.example", f"evil.example:{self.port}", "127.0.0.1", ""):
            status, _ = self._request("GET", "/api/state", host=host)
            self.assertEqual(status, 403, host)
            status, _ = self._request("POST", "/api/reset", {}, host=host)
            self.assertEqual(status, 403, host)
        status, _ = self._request("GET", "/api/state", host=f"localhost:{self.port}")
        self.assertEqual(status, 200)

    def test_page_posts_json_and_a_replay_starts_and_stops(self):
        status_html = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        status_html.request("GET", "/")
        html = status_html.getresponse().read().decode()
        status_html.close()
        self.assertIn("'Content-Type': 'application/json'", html)
        self.assertTrue(self.post("/api/start", self._form(bars_per_second=20))["ok"])
        time.sleep(0.5)
        self.assertTrue(self.get("/api/state")["running"])
        self.assertTrue(self.post("/api/stop", {})["ok"])
        st = self.get("/api/state")
        self.assertFalse(st["running"])
        self.assertGreater(st["bars"], 0)

    # -- resume + reconcile --------------------------------------------------
    def test_resume_rebases_a_readjusted_csv(self):
        self.assertTrue(self.post("/api/start", self._form(end="2020-02-12"))["ok"])
        st = self._wait_idle()
        old_bars, old_equity = st["bars"], st["equity"]
        self.assertEqual(old_bars, 40)
        self.assertTrue(st["positions"])
        # The vendor re-adjusts AAA's whole history (a 2:1 split).
        _write_prices(self.csv, 80, halve="AAA")
        self.assertTrue(self.post("/api/start", self._form(fresh=False, bars_per_second=200))["ok"])
        st = self._wait_idle()
        self.assertEqual(st["bars"], 80)
        self.assertTrue(any("re-based AAA" in m for m in self.srv.controller.messages))
        state = json.loads((self.work / "live_state.json").read_text())
        self.assertTrue(any("re-based AAA" in line for line in state["log"]))
        self.assertFalse(st["halted"])
        # Equity right after the resume is continuous, not ~25-50% down.
        self.assertGreater(st["curve"][old_bars] / old_equity, 0.95)
        self.assertGreater(st["equity"] / old_equity, 0.9)
        # The adjustment is recorded as a noted fill that n_fills leaves out.
        fills = state["fills"]
        noted = [f for f in fills if f.get("note")]
        self.assertTrue(noted)
        self.assertEqual(st["n_fills"], len(fills) - len(noted))

    def test_resume_with_nothing_new_is_refused(self):
        self.assertTrue(self.post("/api/start", self._form())["ok"])
        self._wait_idle()
        r = self.post("/api/start", self._form(fresh=False))
        self.assertFalse(r["ok"])
        self.assertIn("nothing new", r["error"])

    # -- request bodies (B5) ---------------------------------------------------
    def _raw_post(self, length, body=b"", path="/api/stop"):
        import socket
        with socket.create_connection(("127.0.0.1", self.port), timeout=5) as sock:
            head = (f"POST {path} HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n"
                    "Content-Type: application/json\r\n")
            if length is not None:
                head += f"Content-Length: {length}\r\n"
            sock.sendall(head.encode() + b"\r\n" + body)
            data = b""
            try:
                while True:
                    chunk = sock.recv(65536)
                    if not chunk:
                        break
                    data += chunk
            except socket.timeout:
                pass
        return int(data.split(b" ", 2)[1]) if data else None

    def test_bad_content_length_is_refused(self):
        for length in ("abc", "2.5", "-1", "", None, "+2"):
            self.assertEqual(self._raw_post(length, b"{}"), 400, length)
        for length in (str(50 * 1024 * 1024), str(10 ** 12), "1048577"):
            self.assertEqual(self._raw_post(length, b"{}"), 413, length)
        self.assertEqual(self._raw_post("2", b"{}"), 200)

    def test_deeply_nested_json_is_bad_json(self):
        body = b"[" * 100000 + b"]" * 100000
        self.assertEqual(self._raw_post(str(len(body)), body), 400)
        body = b'{"a":' * 50000 + b"1" + b"}" * 50000
        self.assertEqual(self._raw_post(str(len(body)), body), 400)

    # -- start form validation (B6) --------------------------------------------
    def test_non_numeric_speed_or_poll_is_refused(self):
        for kw in ({"bars_per_second": "fast"}, {"mode": "feed", "poll_seconds": "x"},
                   {"bars_per_second": -1}, {"mode": "feed", "poll_seconds": "nan"}):
            r = self.post("/api/start", self._form(**kw))
            self.assertFalse(r["ok"], kw)
        self.assertFalse(self.srv.controller.running)
        self.assertTrue(self.post("/api/start", self._form(bars_per_second="0"))["ok"])
        self._wait_idle()

    def test_fresh_false_as_a_string_keeps_the_state(self):
        self.assertTrue(self.post("/api/start", self._form())["ok"])
        self._wait_idle()
        r = self.post("/api/start", self._form(fresh="false"))
        self.assertFalse(r["ok"])
        self.assertIn("nothing new", r["error"])
        self.assertTrue(self.post("/api/start", self._form(fresh="true"))["ok"])
        self._wait_idle()

    def test_unknown_solver_or_strategy_is_refused_up_front(self):
        r = self.post("/api/start", self._form(strategy="cardinality", solver="bogus", cardinality=1))
        self.assertFalse(r["ok"])
        self.assertIn("solver", r["error"])
        r = self.post("/api/start", self._form(strategy="bogus"))
        self.assertFalse(r["ok"])
        self.assertIn("strategy", r["error"])
        self.assertFalse(self.srv.controller.running)
        for solver in ("simulated_annealing", "simulated_bifurcation", "subspace_qaoa", "exhaustive", "sa"):
            self.assertIsNone(Controller._check_strategy(
                Controller.config_from_form({"tickers": "AAA,BBB", "cardinality": 1, "strategy": "cardinality",
                                            "solver": solver})),
                solver)


class TestDesktopConfigForm(unittest.TestCase):
    def test_optional_engine_rules_round_trip(self):
        cfg = Controller.config_from_form({"tickers": "AAA,BBB", "cardinality": 1, "trade_from": "2020-02-01",
                                           "whole_shares": True, "fill_leftover": "true",
                                           "min_cash_fraction": 0.05, "deploy_from_cash": 1})
        self.assertEqual(cfg.trade_from, "2020-02-01")
        self.assertTrue(cfg.whole_shares)
        self.assertTrue(cfg.fill_leftover)
        self.assertEqual(cfg.limits.min_cash_fraction, 0.05)
        self.assertTrue(cfg.limits.deploy_from_cash)
        default = Controller.config_from_form({"tickers": "AAA,BBB", "cardinality": 1, "trade_from": ""})
        self.assertIsNone(default.trade_from)
        self.assertFalse(default.whole_shares or default.fill_leftover or default.limits.deploy_from_cash)
        self.assertEqual(default.limits.min_cash_fraction, 0.0)


if __name__ == "__main__":
    unittest.main()


class TestDesktopJsonIsStrict(unittest.TestCase):
    """The dashboard's JSON never carries NaN or Infinity, which browsers reject."""

    def test_non_finite_numbers_become_null(self):
        import json
        from quantum.desktop import _finite
        doc = {"a": float("nan"), "b": [1.5, float("inf"), {"c": float("-inf")}], "d": "NaN", "e": 2}
        text = json.dumps(_finite(doc), allow_nan=False)

        def strict(token):
            raise ValueError(token)
        self.assertEqual(json.loads(text, parse_constant=strict),
                         {"a": None, "b": [1.5, None, {"c": None}], "d": "NaN", "e": 2})
