"""Rebuild web/quantum-trading.html from the template, engine and bundled prices.

    python3 web/build.py

The page is a browser port of quantum/live.py.  tests/test_quantum.py checks
the port against the Python engine to the cent when Node is available.
"""
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TICKERS = ["GOOG", "AAPL", "AMZN", "GE", "AMD", "WMT", "BAC", "T", "UAA", "SHLD",
           "XOM", "RRC", "BBY", "MA", "PFE", "JPM", "SBUX"]


def dataset() -> dict:
    rows = list(csv.DictReader((ROOT / "data/prices/us_equities_1989_2018.csv").open()))
    rows = [r for r in rows if r["date"] >= "2006-05-25" and all(r[t] for t in TICKERS)]
    return {"dates": [r["date"] for r in rows], "tickers": TICKERS,
            "prices": {t: [float(r[t]) for r in rows] for t in TICKERS}}


def main() -> None:
    template = (HERE / "template.html").read_text()
    engine = (HERE / "engine.js").read_text().replace(
        'if (typeof module !== "undefined") module.exports = QT;', "")
    data = json.dumps(dataset(), separators=(",", ":"))
    out = template.replace("/*__ENGINE__*/", engine).replace("/*__DATA__*/", data)
    (HERE / "quantum-trading.html").write_text(out)
    print(f"wrote {HERE / 'quantum-trading.html'} ({len(out):,} bytes)")


if __name__ == "__main__":
    main()
