#!/usr/bin/env python3
"""Fail if any text in data/json/ could be read as a spreadsheet formula.

The JSON datasets feed the CSV exports (scripts/generate_csv.py) and the
Excel workbook (scripts/build_tax_workbook.py). A string that starts with
= + - @ tab or CR can be evaluated as a formula by spreadsheet apps. Both
scripts already neutralise such text; this check keeps it out of the source
data in the first place. Every string value and every object key is checked;
numbers (including negatives) are not strings and are fine.

Usage:  python scripts/check_data.py [repo_root]
"""
import json
import sys
from pathlib import Path

FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def walk(node, path: str, hits: list[str]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            child = f"{path}.{k}"
            if k.startswith(FORMULA_TRIGGERS):
                hits.append(f"{child} (key)")
            walk(v, child, hits)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            walk(v, f"{path}[{i}]", hits)
    elif isinstance(node, str) and node.startswith(FORMULA_TRIGGERS):
        hits.append(f"{path}: {node[:40]!r}")


def scan(root: Path) -> list[str]:
    hits = []
    for path in sorted((root / "data" / "json").glob("*.json")):
        rel = path.relative_to(root).as_posix()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        found = []
        walk(data, "$", found)
        hits.extend(f"{rel}: {h}" for h in found)
    return hits


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    hits = scan(root)
    if hits:
        print("Text in data/json/ must not start with = + - @ tab or CR:")
        print("\n".join(f"  {h}" for h in hits))
        sys.exit(1)
    print("No formula-like text found in data/json/.")


if __name__ == "__main__":
    main()
