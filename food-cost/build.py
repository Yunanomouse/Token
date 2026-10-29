#!/usr/bin/env python3
"""Assemble the single-file app from src/.

  python3 build.py                                   -> index.html (Kitchen Manager, every feature)
  python3 build.py --edition essentials --out X.html -> one edition (essentials, professional or manager)
"""
import argparse, pathlib
here = pathlib.Path(__file__).parent
src = here / "src"
ap = argparse.ArgumentParser()
ap.add_argument("--edition", default="manager", choices=["essentials", "professional", "manager"])
ap.add_argument("--out", default=str(here / "index.html"))
ap.add_argument("--tools", help="comma list: only include tool files whose name contains one of these (for testing one tool)")
a = ap.parse_args()
# Kitchen Manager tools go inside the app's closure, so they can use its helpers
want = [t.strip() for t in a.tools.split(",")] if a.tools else None
tools = "".join(p.read_text(encoding="utf-8") for p in sorted((src / "tools").glob("*.js")) if not want or any(w in p.name for w in want)) if a.edition == "manager" else ""
app = (src / "app.js.html").read_text(encoding="utf-8").replace("{{EDITION}}", a.edition).replace("  /*TOOLS*/\n", tools)
parts = [(src / p).read_text(encoding="utf-8") for p in ["head.html", "body.html", "localdb.js.html"]] + [app]
html = "".join(parts) + "\n</body>\n</html>\n"
pathlib.Path(a.out).write_text(html, encoding="utf-8")
print("wrote", a.out, a.edition, len(html), "bytes")
