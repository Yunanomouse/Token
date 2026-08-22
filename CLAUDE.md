# CLAUDE.md

Machine-readable dataset of Canada's 2026 tax system, plus a Python CLI and a
browser calculator built on it.

## Layout

| Path | What it is |
|---|---|
| `data/json/` | Source of truth. Five files: personal income tax, payroll, sales tax, corporate, credits/limits. |
| `data/csv/` | Generated. Never edit by hand, run `scripts/generate_csv.py`. |
| `examples/` | Runnable demos, including the reference tax calculator. |
| `scripts/` | Generators and checks. |
| `web/` | Zero-dependency browser calculator over `data/json/`. |
| `docs/` | Prose guides, plus vendored Taste Skill reference material. |
| `.claude/skills/` | Vendored Taste Skill design skills. |

## Running things

```bash
python3 examples/income_tax_calculator.py 90000 ON   # CLI estimate
python3 scripts/generate_csv.py                      # regenerate data/csv/
node scripts/verify_web_parity.mjs                   # CLI vs browser parity
python3 -m http.server 8000                          # then open /web/
```

The web app fetches `data/json/` at runtime, so it must be served over HTTP.
Opening `web/index.html` via `file://` fails the fetch and shows a boot error
explaining that.

## The invariant that matters

`web/tax.js` and `examples/income_tax_calculator.py` implement the same tax
math twice, in two languages. **They must agree to the cent.**

If you change either one, run:

```bash
node scripts/verify_web_parity.mjs
```

It compares federal tax, provincial tax, total deductions and take-home across
every jurisdiction at 11 income levels, and fails on any drift above one cent.
A change to bracket logic, the BPA phase-out, the Ontario surtax or health
premium, the Quebec abatement, or any payroll formula needs the same edit in
both files.

`web/tax.js` is written to load both in a browser (as `globalThis.TaxEngine`)
and under Node (`module.exports`), so the code under test is the code that
ships. Keep it free of DOM access.

## Data conventions

- Rates are decimals. `0.14` means 14%.
- Amounts are CAD.
- A bracket's `up_to` is its inclusive upper bound. `null` means no upper bound.
- Per-jurisdiction `notes` flag figures that were computed rather than
  independently confirmed. Preserve them when editing.
- Prince Edward Island's 2026 basic personal amount is deliberately `null`
  rather than guessed. Calculator code must treat a null BPA as zero, not crash.

## Accuracy posture

Everything here is an estimate for software development, not tax advice. The
calculators ignore most credits, deductions and provincial low-income
reductions, and assume employment income. Any user-facing surface must say so
and point at CRA and Revenu Quebec. Do not remove those disclaimers.

Figures were collected 2026-08-18 from tax-reference publishers, not directly
from government sites. See the provenance section of `README.md` before
treating any number as authoritative.

## Design skills

Thirteen Taste Skill design skills are vendored under `.claude/skills/` and
load automatically. See `.claude/skills/README.md` for which to reach for.

`design-taste-frontend` is the default for frontend work here. Note its own
stated boundary: landing pages, portfolios and redesigns, explicitly not
dashboards or dense product UI. `web/` is a tool, not a landing page, so it
applies that skill's typography, colour, motion and accessibility rules but not
its landing-page section grammar.

For anything user-facing that shows tax figures, run the skill at its
trust-first dials (`DESIGN_VARIANCE 3` / `MOTION_INTENSITY 2` /
`VISUAL_DENSITY 6`) rather than the 8/6/4 baseline. Wrong tax numbers presented
playfully is a real harm, and the skill's own dial-inference table routes
regulated and accessibility-critical work to that setting.
