#!/usr/bin/env python3
"""Assemble the single-file app: food-cost/index.html from src/."""
import pathlib
here = pathlib.Path(__file__).parent
src = here / "src"
parts = ["head.html", "body.html", "localdb.js.html", "app.js.html"]
html = "".join((src / p).read_text(encoding="utf-8") for p in parts) + "\n</body>\n</html>\n"
(here / "index.html").write_text(html, encoding="utf-8")
print("wrote", here / "index.html", len(html), "bytes")
