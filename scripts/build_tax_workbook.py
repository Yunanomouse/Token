#!/usr/bin/env python3
"""Build examples/personal_tax_outline_2026.xlsx — a live-formula outline of
2026 taxes for an Alberta employee with self-employed trading income on the
side. Inputs (wage, trading profit, rent) are editable; everything else is
formulas fed by the 2026 dataset in data/json/."""
import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "examples" / "personal_tax_outline_2026.xlsx"

with open(ROOT / "data/json/personal_income_tax_2026.json", encoding="utf-8") as f:
    TAX = json.load(f)
with open(ROOT / "data/json/payroll_contributions_2026.json", encoding="utf-8") as f:
    PAY = json.load(f)

ARIAL = "Arial"
F_TITLE = Font(name=ARIAL, size=14, bold=True)
F_H = Font(name=ARIAL, size=10, bold=True)
F_HW = Font(name=ARIAL, size=10, bold=True, color="FFFFFF")
F_B = Font(name=ARIAL, size=10)
F_IN = Font(name=ARIAL, size=10, color="0000FF")          # blue = input
F_LINK = Font(name=ARIAL, size=10, color="008000")        # green = cross-sheet
F_NOTE = Font(name=ARIAL, size=9, italic=True, color="595959")
F_TOTAL = Font(name=ARIAL, size=10, bold=True)
FILL_IN = PatternFill("solid", start_color="FFFF00")      # yellow = edit me
FILL_HDR = PatternFill("solid", start_color="1F4E79")
FILL_SUB = PatternFill("solid", start_color="DDEBF7")
TOP = Border(top=Side(style="thin"))
MONEY = "$#,##0;($#,##0);\"-\""
MONEY2 = "$#,##0.00;($#,##0.00);\"-\""
PCT = "0.0%"
WRAP = Alignment(wrap_text=True, vertical="top")

wb = Workbook()

# ---------------------------------------------------------------- Inputs ----
ws = wb.active
ws.title = "Inputs"
ws.column_dimensions["A"].width = 34
ws.column_dimensions["B"].width = 14
ws.column_dimensions["C"].width = 62

ws["A1"] = "2026 Tax Outline — Inputs"
ws["A1"].font = F_TITLE
ws["A2"] = "Alberta resident · employee salary + self-employed trading (business income)"
ws["A2"].font = F_NOTE

rows = [
    ("Hourly wage ($/hr)", 22, "Your full-time job wage. Value provided by you."),
    ("Hours per week", 40, "Assumed full-time. Edit if different."),
    ("Weeks paid per year", 52, "Assumed paid 52 weeks. Edit if different."),
    ("Monthly rent ($)", 1375, "Value provided by you. Used only for the home-office deduction."),
    ("Home office share of rent", 0.15, "Assumption: 15% of the home used principally for trading. Set to your actual workspace %; CRA expects a reasonable, documented figure."),
    ("Other annual trading expenses ($)", 0, "Data feeds, platform fees, hardware, etc. Deductible against trading profit."),
]
r = 4
ws["A3"] = "Edit the yellow cells:"
ws["A3"].font = F_H
for label, val, note in rows:
    ws.cell(r, 1, label).font = F_B
    c = ws.cell(r, 2, val)
    c.font = F_IN
    c.fill = FILL_IN
    c.number_format = PCT if "share" in label else "#,##0"
    ws.cell(r, 3, note).font = F_NOTE
    ws.cell(r, 3).alignment = WRAP
    r += 1

r += 1
ws.cell(r, 1, "Legend").font = F_H
legend = [
    ("Blue text on yellow", "Input — edit these (here and the trading-profit row on 'Tax Calc')."),
    ("Black text", "Formula — leave alone; recalculates from inputs."),
    ("Green text", "Value pulled from another sheet."),
]
for name, desc in legend:
    r += 1
    ws.cell(r, 1, name).font = F_B
    ws.cell(r, 3, desc).font = F_NOTE
r += 2
ws.cell(r, 1, "Example: at $22/hr, 40 hrs, 52 weeks, the salary computes to $45,760 on the Tax Calc sheet.").font = F_NOTE

# ---------------------------------------------------------- Tax Data 2026 ----
wd = wb.create_sheet("Tax Data 2026")
wd.column_dimensions["A"].width = 30
for col in "BCD":
    wd.column_dimensions[col].width = 14
wd.column_dimensions["E"].width = 66

wd["A1"] = "2026 Tax Parameters (Canada + Alberta)"
wd["A1"].font = F_TITLE
wd["A2"] = "Source: data/json/*.json in this repository (CRA/provincial figures, collected 2026-08-18 — see README.md for provenance)."
wd["A2"].font = F_NOTE

def bracket_table(start_row, title, brackets):
    wd.cell(start_row, 1, title).font = F_H
    for i, h in enumerate(["From", "To", "Rate"]):
        c = wd.cell(start_row + 1, 1 + i, h)
        c.font = F_HW
        c.fill = FILL_HDR
    lower = 0
    r = start_row + 2
    for b in brackets:
        wd.cell(r, 1, lower).number_format = MONEY
        wd.cell(r, 1).font = F_B
        up = b["up_to"]
        c = wd.cell(r, 2, up if up is not None else 10**9)
        c.number_format = MONEY
        c.font = F_B
        if up is None:
            c.comment = Comment("No upper bound; 1,000,000,000 used so MIN() formulas work.", "Claude")
        c3 = wd.cell(r, 3, b["rate"])
        c3.number_format = PCT
        c3.font = F_B
        lower = up
        r += 1
    return r

r = bracket_table(4, "Federal brackets", TAX["federal"]["brackets"])
r = bracket_table(r + 1, "Alberta brackets", TAX["provinces"]["AB"]["brackets"])

params = [
    ("Federal basic personal amount", TAX["federal"]["basic_personal_amount"]["max"], MONEY,
     "Maximum BPA; the phase-out starts at $181,440 net income — far above this model's incomes, so not modelled."),
    ("Alberta basic personal amount", TAX["provinces"]["AB"]["basic_personal_amount"], MONEY, ""),
    ("Canada employment amount", 1500, MONEY,
     "Estimate: 2025 amount $1,471 x 1.02 federal indexation, rounded. Federal credit base for employees."),
    ("CPP YMPE", PAY["cpp"]["ympe"], MONEY, ""),
    ("CPP basic exemption", PAY["cpp"]["basic_exemption"], MONEY, ""),
    ("CPP employee rate", PAY["cpp"]["employee_rate"], PCT, ""),
    ("CPP self-employed rate", PAY["cpp"]["self_employed_rate"], PCT, ""),
    ("CPP2 YAMPE", PAY["cpp2"]["yampe"], MONEY, ""),
    ("CPP2 self-employed rate", PAY["cpp2"]["self_employed_rate"], PCT, ""),
    ("EI max insurable earnings", PAY["ei"]["maximum_insurable_earnings"], MONEY, ""),
    ("EI employee rate", PAY["ei"]["employee_rate"], PCT,
     "No EI is payable (or claimable) on self-employment income unless you opt in."),
]
r += 1
wd.cell(r, 1, "Other parameters").font = F_H
P = {}  # name -> cell ref on this sheet
for name, val, fmt, note in params:
    r += 1
    wd.cell(r, 1, name).font = F_B
    c = wd.cell(r, 2, val)
    c.number_format = fmt
    c.font = F_B
    if note:
        wd.cell(r, 5, note).font = F_NOTE
        wd.cell(r, 5).alignment = WRAP
    P[name] = f"'Tax Data 2026'!$B${r}"

FED_BR_FIRST_ROW = 6    # federal bracket data occupies A6:C10
AB_BR_FIRST_ROW = 14    # Alberta bracket data occupies A14:C19

# --------------------------------------------------------------- Tax Calc ----
wc = wb.create_sheet("Tax Calc")
wc.column_dimensions["A"].width = 40
for col in "BCDE":
    wc.column_dimensions[col].width = 15
wc.column_dimensions["G"].width = 60

wc["A1"] = "2026 Tax Calculation — Salary + Scalp Trading (Alberta)"
wc["A1"].font = F_TITLE
wc["A2"] = "Column B is your salary with no trading (reference). C is your situation; D and E are what-if profit levels — all three yellow cells are editable."
wc["A2"].font = F_NOTE

hdrs = ["", "Salary only", "Your case", "What-if", "What-if"]
for i, h in enumerate(hdrs):
    c = wc.cell(4, 1 + i, h)
    c.font = F_HW
    c.fill = FILL_HDR

def note(cell, text):
    wc[cell].comment = Comment(text, "Claude")

def row(r, label, formulas, fmt=MONEY, font=None, fill=None, sub=False):
    c = wc.cell(r, 1, label)
    c.font = font or F_B
    if sub:
        c.font = F_H
        c.fill = FILL_SUB
        for col in range(2, 6):
            wc.cell(r, col).fill = FILL_SUB
        return
    for i, fx in enumerate(formulas):
        cc = wc.cell(r, 2 + i, fx)
        cc.number_format = fmt
        cc.font = font or F_B
        if fill:
            cc.fill = fill

# --- income section
row(6, "INCOME", [], sub=True)
row(7, "Trading profit (gross)", [0, 10000, 25000, 50000], font=F_IN, fill=FILL_IN)
note("C7", "Value provided by you (under $10,000; modelled at $10,000). Edit C7/D7/E7 freely; B7 stays 0 as the salary-only reference.")
wc["B7"].font = F_B
wc["B7"].fill = PatternFill()
row(8, "Home office deduction", [f'=-MIN(Inputs!$B$7*12*Inputs!$B$8,{c}7)' for c in "BCDE"], font=F_LINK)
note("B8", "Rent x 12 x office share, capped at trading profit — business-use-of-home expenses cannot create a loss (unused amounts carry forward; carryforward not modelled).")
row(9, "Other trading expenses", [f'=-MIN(Inputs!$B$9,{c}7+{c}8)' for c in "BCDE"], font=F_LINK)
row(10, "Net trading income", [f'={c}7+{c}8+{c}9' for c in "BCDE"], font=F_TOTAL)
row(11, "Employment income", ['=Inputs!$B$4*Inputs!$B$5*Inputs!$B$6'] + [f'=$B$11' for _ in "CDE"], font=F_LINK)
row(12, "Total income", [f'={c}10+{c}11' for c in "BCDE"], font=F_TOTAL)

# --- payroll section
row(14, "PAYROLL CONTRIBUTIONS", [], sub=True)
ympe, exemp = P["CPP YMPE"], P["CPP basic exemption"]
cpp_ee, cpp_se = P["CPP employee rate"], P["CPP self-employed rate"]
yampe, cpp2_se = P["CPP2 YAMPE"], P["CPP2 self-employed rate"]
mie, ei_rate = P["EI max insurable earnings"], P["EI employee rate"]
row(15, "Employee CPP (withheld from pay)",
    [f'=(MIN({c}11,{ympe})-{exemp})*{cpp_ee}' for c in "BCDE"], MONEY2, font=F_LINK)
row(16, "EI premiums (withheld from pay)",
    [f'=MIN({c}11,{mie})*{ei_rate}' for c in "BCDE"], MONEY2, font=F_LINK)
row(17, "Self-employed CPP on trading",
    [f'=(MIN({c}11+{c}10,{ympe})-MIN({c}11,{ympe}))*{cpp_se}' for c in "BCDE"], MONEY2, font=F_LINK)
note("C17", "11.9% (both halves) on trading income. Applies from dollar one: the $3,500 exemption is already used against your salary.")
row(18, "Self-employed CPP2 on trading",
    [f'=MAX(0,MIN({c}11+{c}10,{yampe})-MAX({c}11,{ympe}))*{cpp2_se}' for c in "BCDE"], MONEY2, font=F_LINK)
note("E18", "8% on earnings between the YMPE ($74,600) and YAMPE ($85,000). Only the $50k what-if reaches this band.")

# --- taxable income
row(20, "TAXABLE INCOME", [], sub=True)
row(21, "Deduction: half of self-employed CPP",
    [f'=-0.5*({c}17+{c}18)' for c in "BCDE"], MONEY2)
note("B21", "Simplification: the T1 deducts the employer half plus enhanced portions of self-employed CPP; 50% of the total is within ~$50 of the exact figure at these incomes.")
row(22, "Taxable income", [f'={c}12+{c}21' for c in "BCDE"], font=F_TOTAL)

# --- federal tax: per-bracket rows
row(24, "FEDERAL TAX", [], sub=True)
fed_first = 25
for i in range(5):
    dr = FED_BR_FIRST_ROW + i
    lo, up, rt = (f"'Tax Data 2026'!$A${dr}", f"'Tax Data 2026'!$B${dr}", f"'Tax Data 2026'!$C${dr}")
    row(fed_first + i, f"  Bracket {i+1}",
        [f'=MAX(0,MIN({c}$22,{up})-{lo})*{rt}' for c in "BCDE"], MONEY2)
row(30, "Federal tax before credits", [f'=SUM({c}{fed_first}:{c}29)' for c in "BCDE"], MONEY2)
cea, bpa_f = P["Canada employment amount"], P["Federal basic personal amount"]
row(31, "Non-refundable credits (14%)",
    [f'=-0.14*({bpa_f}+{cea}+{c}15+{c}16+0.5*{c}17)' for c in "BCDE"], MONEY2)
note("B31", "14% x (BPA + Canada employment amount + employee CPP + EI + employee half of self-employed CPP). Simplification: the enhanced-CPP slice is deductible rather than creditable on a real T1 — difference under $30 here. Federal BPA phase-out not modelled (starts at $181,440).")
row(32, "Federal tax payable", [f'=MAX(0,{c}30+{c}31)' for c in "BCDE"], MONEY2, font=F_TOTAL)
for col in "BCDE":
    wc[f"{col}32"].border = TOP

# --- alberta tax
row(34, "ALBERTA TAX", [], sub=True)
ab_first = 35
for i in range(6):
    dr = AB_BR_FIRST_ROW + i
    lo, up, rt = (f"'Tax Data 2026'!$A${dr}", f"'Tax Data 2026'!$B${dr}", f"'Tax Data 2026'!$C${dr}")
    row(ab_first + i, f"  Bracket {i+1}",
        [f'=MAX(0,MIN({c}$22,{up})-{lo})*{rt}' for c in "BCDE"], MONEY2)
row(41, "Alberta tax before credits", [f'=SUM({c}{ab_first}:{c}40)' for c in "BCDE"], MONEY2)
bpa_a = P["Alberta basic personal amount"]
row(42, "Non-refundable credits (8%)",
    [f'=-0.08*({bpa_a}+{c}15+{c}16+0.5*{c}17)' for c in "BCDE"], MONEY2)
row(43, "Alberta tax payable", [f'=MAX(0,{c}41+{c}42)' for c in "BCDE"], MONEY2, font=F_TOTAL)
for col in "BCDE":
    wc[f"{col}43"].border = TOP

# --- results
row(45, "RESULTS", [], sub=True)
row(46, "Total income tax", [f'={c}32+{c}43' for c in "BCDE"], MONEY2, font=F_TOTAL)
row(47, "Total tax + all CPP/EI", [f'={c}46+{c}15+{c}16+{c}17+{c}18' for c in "BCDE"], MONEY2, font=F_TOTAL)
row(48, "After-tax income", [f'={c}12-{c}47' for c in "BCDE"], MONEY, font=F_TOTAL)
row(49, "Average rate (on total income)", [f'=IF({c}12=0,0,{c}47/{c}12)' for c in "BCDE"], PCT)
row(51, "Cost of trading vs salary-only", ['', '=C47-$B$47', '=D47-$B$47', '=E47-$B$47'], MONEY2)
note("C51", "Extra tax + CPP caused by the trading income — this is roughly your balance due at filing, since employer withholding covers the salary-only column.")
row(52, "Effective rate on trading profit", ['', '=IF(C7=0,0,C51/C7)', '=IF(D7=0,0,D51/D7)', '=IF(E7=0,0,E51/E7)'], PCT, font=F_TOTAL)
row(53, "Set aside per $100 of trading profit", ['', '=C52*100', '=D52*100', '=E52*100'], MONEY)

wc["A55"] = ("Notes: 2026 rules, Alberta resident, single filer, no other income/deductions. Employer withholding assumed to cover the salary-only "
             "liability. No EI on self-employment income (opt-in not assumed). Estimates for planning, not filing — see docs/trader_taxation.md.")
wc["A55"].font = F_NOTE
wc["A55"].alignment = WRAP
wc.merge_cells("A55:E57")

wb.save(OUT)
print(f"wrote {OUT.relative_to(ROOT)}")
