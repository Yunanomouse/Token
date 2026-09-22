#!/usr/bin/env python3
"""Send a prompt to any model on OpenRouter from the command line.

Setup (one time):  set OPENROUTER_API_KEY in your environment
Run:               python3 examples/openrouter_quickstart.py "Explain the TFSA in one paragraph"

Options:
    --model SLUG   Which model to use (default: anthropic/claude-opus-5)
    --file PATH    Attach a file as context — handy for the datasets in
                   data/json/, e.g. --file data/json/sales_tax_2026.json
    --models TEXT  List matching model slugs instead of sending a prompt
    --max-tokens N Cap the reply length (default: 1024)

OpenRouter exposes one OpenAI-compatible endpoint in front of many vendors'
models, so the same code reaches Anthropic, Google, Meta, Mistral and others
by changing the model slug. Uses only the Python standard library — no
`pip install` needed. See docs/openrouter_setup.md for a full walkthrough.

Your API key is read from the environment and is never written to disk or
printed. Do not paste it into this file.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Override to route through a gateway, a proxy, or a local stub (see tests/).
API_ROOT = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
DEFAULT_MODEL = "anthropic/claude-opus-5"
TIMEOUT_SECONDS = 120

# Sent so usage shows up under a recognisable name on openrouter.ai; optional.
APP_TITLE = "canada-tax-system-data"


def api_key():
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        sys.exit("OPENROUTER_API_KEY is not set. Create a key at "
                 "https://openrouter.ai/keys, then:\n"
                 "  macOS/Linux:  export OPENROUTER_API_KEY=sk-or-...\n"
                 "  Windows:      setx OPENROUTER_API_KEY sk-or-...   (then reopen the terminal)")
    return key


def request(path, payload=None):
    """Call the OpenRouter API and return the decoded JSON response."""
    headers = {
        "Authorization": f"Bearer {api_key()}",
        "Content-Type": "application/json",
        "X-Title": APP_TITLE,
    }
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(f"{API_ROOT}{path}", data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        sys.exit(f"OpenRouter returned {exc.code} {exc.reason}: {explain(exc)}")
    except urllib.error.URLError as exc:
        sys.exit(f"Could not reach OpenRouter ({exc.reason}). Check your connection.")


def explain(exc):
    """Turn an HTTP error into something worth reading."""
    hints = {
        401: "the API key was rejected — check OPENROUTER_API_KEY",
        402: "the account is out of credit — top up at https://openrouter.ai/credits",
        404: "no such model slug — run with --models to list what is available",
        429: "rate limited — wait a moment and try again",
    }
    try:
        detail = json.loads(exc.read().decode("utf-8"))["error"]["message"]
    except Exception:  # noqa: BLE001 - the body is best-effort context
        detail = hints.get(exc.code, "see https://openrouter.ai/docs")
    return detail


def list_models(needle):
    models = request("/models")["data"]
    matches = sorted(m["id"] for m in models if needle.lower() in m["id"].lower())
    if not matches:
        sys.exit(f"No model slug contains {needle!r}. Browse https://openrouter.ai/models")
    print(f"{len(matches)} model(s) matching {needle!r}:")
    for slug in matches:
        print(f"  {slug}")


def ask(prompt, model, max_tokens):
    body = request("/chat/completions", {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    })
    choice = body["choices"][0]
    print(choice["message"]["content"].strip())

    usage = body.get("usage") or {}
    if usage:
        print(f"\n[{body.get('model', model)} — {usage.get('prompt_tokens', '?')} prompt + "
              f"{usage.get('completion_tokens', '?')} completion tokens]", file=sys.stderr)
    if choice.get("finish_reason") == "length":
        print("[reply was cut off; raise --max-tokens for a longer answer]", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Send a prompt to a model on OpenRouter.",
        epilog="See docs/openrouter_setup.md for setup help.")
    parser.add_argument("prompt", nargs="*", help="the question to ask")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"model slug (default: {DEFAULT_MODEL})")
    parser.add_argument("--file", type=Path, help="attach a file as context")
    parser.add_argument("--models", metavar="TEXT", help="list matching model slugs and exit")
    parser.add_argument("--max-tokens", type=int, default=1024, help="cap the reply length")
    args = parser.parse_args()

    if args.models:
        list_models(args.models)
        return

    prompt = " ".join(args.prompt).strip()
    if not prompt:
        parser.error("give a prompt, e.g. \"Explain the TFSA in one paragraph\"")

    if args.file:
        if not args.file.is_file():
            sys.exit(f"No such file: {args.file}")
        prompt = (f"{prompt}\n\n--- contents of {args.file.name} ---\n"
                  f"{args.file.read_text(encoding='utf-8')}")

    ask(prompt, args.model, args.max_tokens)


if __name__ == "__main__":
    main()
