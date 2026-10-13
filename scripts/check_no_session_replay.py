#!/usr/bin/env python3
"""Fail if session replay or session recording code appears in the repo.

Token's policy (PRIVACY.md, COOKIES.md) is that session replay is off for
every user, on every page or tool Token ever ships. This check enforces it
in CI by scanning code and config files for known replay vendors and SDK
switches. Markdown is skipped so the policy documents can name the vendors.

Usage:  python scripts/check_no_session_replay.py [repo_root]
"""
import re
import sys
from pathlib import Path

PATTERNS = {
    "Hotjar": r"hotjar",
    "FullStory": r"fullstory|\bFS\.identify\b",
    "LogRocket": r"logrocket",
    "Microsoft Clarity": r"clarity\.ms|\bclarity\(",
    "Smartlook": r"smartlook",
    "Mouseflow": r"mouseflow",
    "Lucky Orange": r"luckyorange",
    "Inspectlet": r"inspectlet",
    "Crazy Egg": r"crazyegg",
    "Contentsquare": r"contentsquare",
    "Quantum Metric": r"quantummetric",
    "Glassbox": r"glassbox",
    "OpenReplay": r"openreplay",
    "Highlight": r"highlight\.run",
    "rrweb": r"\brrweb\b",
    "PostHog session recording": r"session_recording|sessionRecording|enable_recording_console_log",
    "Sentry Replay": r"replayIntegration|Sentry\.Replay|replaysSessionSampleRate|replaysOnErrorSampleRate",
    "Datadog RUM replay": r"sessionReplaySampleRate|startSessionReplayRecording",
    "Generic session replay": r"session[_\- ]?replay",
}

SKIP_DIRS = {".git", "__pycache__", "node_modules", "market_data"}
SKIP_SUFFIXES = {".md", ".xlsx", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".csv"}
SELF = Path(__file__).resolve()
# The workflow that runs this check names the policy in its title.
SKIP_FILES = {".github/workflows/no-session-replay.yml"}


def scan(root: Path) -> list[str]:
    compiled = {name: re.compile(p, re.IGNORECASE) for name, p in PATTERNS.items()}
    hits = []
    for path in root.rglob("*"):
        if not path.is_file() or path.resolve() == SELF:
            continue
        rel = path.relative_to(root)
        if SKIP_DIRS.intersection(rel.parts) or rel.as_posix() in SKIP_FILES:
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for name, rx in compiled.items():
                if rx.search(line):
                    hits.append(f"{rel}:{lineno}: {name}")
    return hits


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    hits = scan(root)
    if hits:
        print("Session replay is not allowed in Token (see PRIVACY.md):")
        print("\n".join(f"  {h}" for h in hits))
        sys.exit(1)
    print("No session replay code found.")


if __name__ == "__main__":
    main()
