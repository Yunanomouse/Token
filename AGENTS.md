# Working on this repository

Project context for coding agents (Codex reads `AGENTS.md` automatically; other
agent CLIs use it or a configured fallback). Everything here applies to humans
too — it is just the house style written down.

## What this is

A machine-readable dataset of Canada's tax system for the **2026 tax year**,
plus small example programs that read it. `data/json/` is the source of truth;
everything else is generated from it or reads it.

Python 3.9+ with **no third-party packages** for the dataset, the examples and
the tests. Two extras are optional and used by one file each:
`openpyxl` (`scripts/build_tax_workbook.py`) and `openbb`
(`examples/openbb_quickstart.py`).

## Before you finish

```bash
python3 -m unittest discover -s tests     # 62 tests, no network, no extra packages
```

Everything must pass. The suite is fast (~2s); run it after any change, not
just changes to Python.

## Rules that matter here

**Never hardcode a tax rule.** Rates, thresholds, caps and bands live in
`data/json/` and are read at runtime. A tax rule written into a `.py` file is
a bug: it is the exact defect that let the Ontario Health Premium tables in two
scripts silently disagree for months. Shared calculations belong in
`examples/cantax.py`, which both example scripts import.

**Regenerate, don't hand-edit, derived files.** After changing anything in
`data/json/`:

```bash
python3 scripts/generate_csv.py        # rewrites data/csv/
python3 scripts/build_tax_workbook.py  # rewrites examples/personal_tax_outline_2026.xlsx (needs openpyxl)
```

A test fails if the committed CSVs are stale, so this is enforced, not
advisory. `data/csv/*.csv` and the `.xlsx` are build artifacts that happen to
be committed — never edit them directly.

**Know the three shapes a `basic_personal_amount` can take**, because code that
assumes a plain number will crash or silently mis-tax:

- a number — the usual case
- `null` — no 2026 figure published (Prince Edward Island). Warn; do not
  silently treat the credit as `$0`.
- `{max, min}` — phased out by income (federal, and Yukon which adopts the
  federal amount)

**Cite a source for any figure you change.** Every number in `data/json/` was
cross-verified two ways (see "Data provenance" in `README.md`), and anything
that could only be computed rather than confirmed is flagged in that
jurisdiction's `notes`. Keep that discipline: if you cannot confirm a figure,
leave it `null` and say why in `notes` rather than guessing.

**Add a test with any calculation change.** Tests in `tests/test_calculations.py`
check the code against statutory tables written out independently in the test
file — deliberately not against the dataset, so that a wrong figure in the data
cannot make a wrong calculation look correct.

## Secrets

`examples/openrouter_quickstart.py` reads `OPENROUTER_API_KEY` from the
environment. Never write a key into a file, a test, a commit or a log line, and
never add a default. The same goes for any key Codex or another tool needs:
environment only.

## Scope

This dataset is for information and software-development purposes and is **not
tax advice**. Keep the disclaimers in `README.md`, the example docstrings and
`docs/` intact — do not quietly strengthen a claim about what a figure means or
drop a caveat to make output read more confidently.
