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

# ------------------------------------------------- Full CRA system sheets ----
with open(ROOT / "data/json/sales_tax_2026.json", encoding="utf-8") as f:
    SALES = json.load(f)
with open(ROOT / "data/json/corporate_income_tax_2026.json", encoding="utf-8") as f:
    CORP = json.load(f)
with open(ROOT / "data/json/credits_and_limits_2026.json", encoding="utf-8") as f:
    LIM = json.load(f)


def header_row(ws_, r, headers, widths=None):
    for i, h in enumerate(headers):
        c = ws_.cell(r, 1 + i, h)
        c.font = F_HW
        c.fill = FILL_HDR
    if widths:
        for col, w in widths.items():
            ws_.column_dimensions[col].width = w


def sheet_title(ws_, text, sub=""):
    ws_["A1"] = text
    ws_["A1"].font = F_TITLE
    if sub:
        ws_["A2"] = sub
        ws_["A2"].font = F_NOTE


# --- all personal income tax brackets, every jurisdiction
wa = wb.create_sheet("All Income Brackets")
sheet_title(wa, "Personal Income Tax Brackets 2026 — All of Canada",
            "Federal + every province/territory. Source: data/json/personal_income_tax_2026.json (CRA figures; see README.md).")
header_row(wa, 4, ["Jurisdiction", "Bracket", "From", "To", "Marginal rate"],
           {"A": 28, "B": 9, "C": 14, "D": 14, "E": 14})
r = 5
all_jur = [("CA", TAX["federal"])] + list(TAX["provinces"].items())
for code, jur in all_jur:
    lower = 0
    for i, b in enumerate(jur["brackets"], 1):
        wa.cell(r, 1, jur["name"]).font = F_B
        wa.cell(r, 2, i).font = F_B
        wa.cell(r, 3, lower).number_format = MONEY
        wa.cell(r, 3).font = F_B
        c = wa.cell(r, 4, b["up_to"] if b["up_to"] is not None else "no limit")
        c.number_format = MONEY
        c.font = F_B
        c5 = wa.cell(r, 5, b["rate"])
        c5.number_format = "0.00%"
        c5.font = F_B
        lower = b["up_to"]
        r += 1
r += 1
wa.cell(r, 1, "Basic personal amounts").font = F_H
header_row(wa, r + 1, ["Jurisdiction", "BPA"])
r += 2
fed_bpa = TAX["federal"]["basic_personal_amount"]
wa.cell(r, 1, "Canada (federal)").font = F_B
wa.cell(r, 2, fed_bpa["max"]).number_format = MONEY
wa.cell(r, 2).font = F_B
wa.cell(r, 3, f"Phases down to ${fed_bpa['min']:,} for income above $181,440").font = F_NOTE
r += 1
for code, jur in TAX["provinces"].items():
    wa.cell(r, 1, jur["name"]).font = F_B
    bpa = jur["basic_personal_amount"]
    c = wa.cell(r, 2, bpa if bpa is not None else "n/a")
    c.number_format = MONEY
    c.font = F_B
    r += 1

# --- sales tax
wst = wb.create_sheet("Sales Tax")
sheet_title(wst, "Sales Tax Rates 2026 — GST / HST / PST / QST",
            "Source: data/json/sales_tax_2026.json.")
header_row(wst, 4, ["Province/Territory", "System", "GST", "PST/QST", "HST", "Total"],
           {"A": 28, "B": 12, "C": 10, "D": 10, "E": 10, "F": 10})
r = 5
for code, j in SALES["jurisdictions"].items():
    wst.cell(r, 1, j["name"]).font = F_B
    wst.cell(r, 2, j["system"]).font = F_B
    for col, key in ((3, "gst"), (4, "pst"), (5, "hst"), (6, "total_rate")):
        v = j.get(key)
        c = wst.cell(r, col, v if v is not None else "-")
        c.number_format = "0.00%"
        c.font = F_B
    if "note" in j:
        wst.cell(r, 7, j["note"]).font = F_NOTE
    r += 1

# --- payroll programs
wp = wb.create_sheet("Payroll CPP EI")
sheet_title(wp, "Payroll Contributions 2026 — CPP, CPP2, QPP, EI, QPIP",
            "Source: data/json/payroll_contributions_2026.json.")
wp.column_dimensions["A"].width = 40
wp.column_dimensions["B"].width = 16
wp.column_dimensions["C"].width = 70
r = 4
for prog_key in ("cpp", "cpp2", "qpp", "ei", "qpip"):
    prog = PAY[prog_key]
    wp.cell(r, 1, prog["name"]).font = F_H
    wp.cell(r, 1).fill = FILL_SUB
    wp.cell(r, 2).fill = FILL_SUB
    r += 1
    for k, v in prog.items():
        if k in ("name", "note", "quebec") or isinstance(v, dict):
            continue
        wp.cell(r, 1, k.replace("_", " ")).font = F_B
        c = wp.cell(r, 2, v)
        c.font = F_B
        c.number_format = "0.000%" if ("rate" in k or "multiplier" in k) and v < 1 else MONEY2
        r += 1
    if "quebec" in prog:
        for k, v in prog["quebec"].items():
            if k == "note":
                continue
            wp.cell(r, 1, f"Quebec {k.replace('_', ' ')}").font = F_B
            c = wp.cell(r, 2, v)
            c.font = F_B
            c.number_format = "0.000%" if "rate" in k else MONEY2
            r += 1
    if "note" in prog:
        wp.cell(r, 1, prog["note"]).font = F_NOTE
        wp.cell(r, 1).alignment = WRAP
        r += 1
    r += 1

# --- corporate tax
wco = wb.create_sheet("Corporate Tax")
sheet_title(wco, "Corporate Income Tax Rates 2026",
            "Source: data/json/corporate_income_tax_2026.json.")
header_row(wco, 4, ["Jurisdiction", "General rate", "Small business rate", "SB limit", "Notes"],
           {"A": 28, "B": 13, "C": 17, "D": 12, "E": 70})
r = 5
fed = CORP["federal"]
wco.cell(r, 1, "Canada (federal)").font = F_B
wco.cell(r, 2, fed["general_rate"]).number_format = "0.0%"
wco.cell(r, 3, fed["small_business_rate"]).number_format = "0.0%"
wco.cell(r, 4, fed["small_business_limit"]).number_format = MONEY
for col in range(2, 5):
    wco.cell(r, col).font = F_B
r += 1
for code, j in CORP["provincial"].items():
    wco.cell(r, 1, j["name"]).font = F_B
    wco.cell(r, 2, j["general_rate"]).number_format = "0.0%"
    wco.cell(r, 3, j["small_business_rate"]).number_format = "0.0%"
    wco.cell(r, 4, j["small_business_limit"]).number_format = MONEY
    for col in range(2, 5):
        wco.cell(r, col).font = F_B
    if "note" in j:
        wco.cell(r, 5, j["note"]).font = F_NOTE
        wco.cell(r, 5).alignment = WRAP
    r += 1

# --- credits & limits
wl = wb.create_sheet("Credits & Limits")
sheet_title(wl, "Key Credits, Registered Accounts & System Parameters 2026",
            "Source: data/json/credits_and_limits_2026.json.")
wl.column_dimensions["A"].width = 44
wl.column_dimensions["B"].width = 16
wl.column_dimensions["C"].width = 70
lim_rows = [
    ("TFSA annual limit", LIM["registered_accounts"]["tfsa"]["annual_limit"], MONEY, LIM["registered_accounts"]["tfsa"]["note"]),
    ("TFSA cumulative room since 2009", LIM["registered_accounts"]["tfsa"]["cumulative_room_since_2009"], MONEY, ""),
    ("RRSP annual limit", LIM["registered_accounts"]["rrsp"]["annual_limit"], MONEY, LIM["registered_accounts"]["rrsp"]["formula"]),
    ("FHSA annual limit", LIM["registered_accounts"]["fhsa"]["annual_limit"], MONEY, LIM["registered_accounts"]["fhsa"]["note"]),
    ("FHSA lifetime limit", LIM["registered_accounts"]["fhsa"]["lifetime_limit"], MONEY, ""),
    ("Federal BPA (max)", LIM["credits"]["federal_basic_personal_amount"]["max"], MONEY, ""),
    ("Federal BPA (min, high income)", LIM["credits"]["federal_basic_personal_amount"]["min"], MONEY, ""),
    ("Federal credit rate", LIM["credits"]["credit_rate_federal"], "0.0%", LIM["credits"]["note"]),
    ("OAS clawback threshold", LIM["oas"]["clawback_threshold"], MONEY, LIM["oas"]["note"]),
    ("OAS recovery rate", LIM["oas"]["recovery_rate"], "0.0%", ""),
    ("Capital gains inclusion rate", LIM["capital_gains"]["inclusion_rate"], "0.0%", LIM["capital_gains"]["note"]),
    ("Lifetime capital gains exemption", LIM["capital_gains"]["lifetime_capital_gains_exemption"], MONEY, ""),
    ("Quebec abatement rate", LIM["other"]["quebec_abatement_rate"], "0.0%", ""),
]
r = 4
for label, val, fmt, note_txt in lim_rows:
    wl.cell(r, 1, label).font = F_B
    c = wl.cell(r, 2, val)
    c.font = F_B
    c.number_format = fmt
    if note_txt:
        wl.cell(r, 3, note_txt).font = F_NOTE
        wl.cell(r, 3).alignment = WRAP
    r += 1
r += 1
wl.cell(r, 1, "Trading note: for an active/scalp trader, profits are business income — the capital gains inclusion rate does not apply. See docs/trader_taxation.md.").font = F_NOTE
wl.cell(r, 1).alignment = WRAP

wb.save(OUT)
print(f"wrote {OUT.relative_to(ROOT)}")
