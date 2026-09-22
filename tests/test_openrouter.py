#!/usr/bin/env python3
"""Checks for examples/openrouter_quickstart.py against a local stub server.

No API key and no internet access are needed: the script's OPENROUTER_BASE_URL
override points it at a throwaway HTTP server started here, which records what
the script sent and replies with canned OpenRouter-shaped JSON.

Run with:  python3 -m unittest discover -s tests
"""
import json
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "examples" / "openrouter_quickstart.py"

MODELS_RESPONSE = {"data": [{"id": "anthropic/claude-opus-5"},
                            {"id": "anthropic/claude-haiku-4.5"},
                            {"id": "google/gemini-2.5-pro"}]}


def completion(content, finish_reason="stop"):
    return {
        "model": "anthropic/claude-opus-5",
        "choices": [{"message": {"role": "assistant", "content": content},
                     "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 34},
    }


class StubHandler(BaseHTTPRequestHandler):
    """Replies as OpenRouter would; the reply is chosen by the model slug."""

    requests = []

    def _send(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.requests.append({"method": "GET", "path": self.path, "headers": dict(self.headers)})
        if self.path.endswith("/models"):
            self._send(200, MODELS_RESPONSE)
        else:
            self._send(404, {"error": {"message": "not found"}})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        self.requests.append({"method": "POST", "path": self.path,
                              "headers": dict(self.headers), "body": payload})
        model = payload.get("model", "")
        if model == "vendor/unauthorized":
            self._send(401, {"error": {"message": "No auth credentials found"}})
        elif model == "vendor/nonexistent":
            self._send(404, {"error": {"message": "vendor/nonexistent is not a valid model ID"}})
        elif model == "vendor/truncating":
            self._send(200, completion("A very long answer that runs out of", "length"))
        else:
            self._send(200, completion("Ontario's combined HST is 13%."))

    def log_message(self, *args):  # keep the test output quiet
        pass


class TestOpenRouterQuickstart(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), StubHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        host, port = cls.server.server_address
        cls.base_url = f"http://{host}:{port}/api/v1"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        StubHandler.requests.clear()

    def run_script(self, *args, key="sk-or-test-key"):
        env = {"PATH": "/usr/bin:/bin", "OPENROUTER_BASE_URL": self.base_url,
               "no_proxy": "127.0.0.1,localhost", "NO_PROXY": "127.0.0.1,localhost"}
        if key is not None:
            env["OPENROUTER_API_KEY"] = key
        return subprocess.run([sys.executable, str(SCRIPT), *args],
                              capture_output=True, text=True, env=env, timeout=60)

    def test_prompt_returns_the_models_reply(self):
        result = self.run_script("What is Ontario's HST?")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "Ontario's combined HST is 13%.")
        self.assertIn("12 prompt + 34 completion tokens", result.stderr)

    def test_request_carries_the_key_and_an_openai_shaped_body(self):
        self.run_script("hello")
        self.assertEqual(len(StubHandler.requests), 1)
        sent = StubHandler.requests[0]
        self.assertEqual(sent["method"], "POST")
        self.assertTrue(sent["path"].endswith("/chat/completions"), sent["path"])
        self.assertEqual(sent["headers"]["Authorization"], "Bearer sk-or-test-key")
        self.assertEqual(sent["headers"]["Content-Type"], "application/json")
        self.assertEqual(sent["body"]["messages"], [{"role": "user", "content": "hello"}])
        self.assertEqual(sent["body"]["model"], "anthropic/claude-opus-5")
        self.assertEqual(sent["body"]["max_tokens"], 1024)

    def test_model_and_max_tokens_flags_reach_the_request(self):
        self.run_script("--model", "google/gemini-2.5-pro", "--max-tokens", "77", "hi")
        body = StubHandler.requests[0]["body"]
        self.assertEqual(body["model"], "google/gemini-2.5-pro")
        self.assertEqual(body["max_tokens"], 77)

    def test_file_option_attaches_the_dataset_as_context(self):
        dataset = ROOT / "data" / "json" / "sales_tax_2026.json"
        result = self.run_script("--file", str(dataset), "Summarise this")
        self.assertEqual(result.returncode, 0, result.stderr)
        prompt = StubHandler.requests[0]["body"]["messages"][0]["content"]
        self.assertTrue(prompt.startswith("Summarise this"))
        self.assertIn("sales_tax_2026.json", prompt)
        self.assertIn("federal_gst_rate", prompt, "the file contents should be included")

    def test_models_flag_lists_matching_slugs_only(self):
        result = self.run_script("--models", "anthropic")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("anthropic/claude-opus-5", result.stdout)
        self.assertNotIn("google/gemini", result.stdout)
        self.assertEqual(StubHandler.requests[0]["method"], "GET")

    def test_models_flag_reports_when_nothing_matches(self):
        result = self.run_script("--models", "no-such-vendor")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)

    def test_api_errors_are_explained_not_raised(self):
        for model, expected in (("vendor/unauthorized", "No auth credentials found"),
                                ("vendor/nonexistent", "not a valid model ID")):
            with self.subTest(model=model):
                result = self.run_script("--model", model, "hi")
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Traceback", result.stderr)
                self.assertIn(expected, result.stderr)

    def test_truncated_reply_is_flagged(self):
        result = self.run_script("--model", "vendor/truncating", "hi")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--max-tokens", result.stderr)

    def test_missing_key_is_caught_before_any_request(self):
        result = self.run_script("hi", key=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("OPENROUTER_API_KEY", result.stderr)
        self.assertEqual(StubHandler.requests, [], "no request should be sent without a key")

    def test_key_is_never_echoed_to_stdout(self):
        result = self.run_script("hi")
        self.assertNotIn("sk-or-test-key", result.stdout)
        self.assertNotIn("sk-or-test-key", result.stderr)


if __name__ == "__main__":
    unittest.main()
