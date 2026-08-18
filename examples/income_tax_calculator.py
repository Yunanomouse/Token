#!/usr/bin/env python3
"""Estimate 2026 Canadian income tax from the dataset in data/json/.

Usage:
    python examples/income_tax_calculator.py <taxable_income> <province_code>
    python examples/income_tax_calculator.py 90000 ON

Covers: progressive federal + provincial brackets, basic personal amount
credits (including the federal enhanced-BPA phase-out), the Ontario surtax
and health premium, and the Quebec abatement. Employee CPP/CPP2 and EI are
estimated for employment income. This is an estimate for illustration, not
tax advice — it ignores most credits, deductions, and provincial low-income
reductions.
"""
import json
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "json"


def load(name):
    with open(DATA / name, encoding="utf-8") as f:
        return json.load(f)


def progressive_tax(income, brackets):
    tax, lower = 0.0, 0.0
    for b in brackets:
        upper = b["up_to"] if b["up_to"] is not None else float("inf")
        if income > lower:
            tax += (min(income, upper) - lower) * b["rate"]
            lower = upper
        else:
            break
    return tax


def federal_bpa(income, fed):
    bpa = fed["basic_personal_amount"]
    phase_start = fed["brackets"][2]["up_to"]  # 4th bracket threshold
    phase_end = fed["brackets"][3]["up_to"]    # 5th bracket threshold
    if income <= phase_start:
        return bpa["max"]
    if income >= phase_end:
        return bpa["min"]
    frac = (income - phase_start) / (phase_end - phase_start)
    return bpa["max"] - frac * (bpa["max"] - bpa["min"])


def ontario_extras(income, basic_tax, on):
    surtax = 0.0
    for t in on["surtax"]["thresholds"]:
        surtax += max(0.0, basic_tax - t["tax_over"]) * t["rate"]
    if income <= 20000:
        premium = 0.0
    elif income <= 36000:
        premium = min(300.0, 0.06 * (income - 20000))
    elif income <= 48000:
        premium = min(450.0, 300 + 0.06 * max(0.0, income - 36000))
    elif income <= 72000:
        premium = min(600.0, 450 + 0.25 * max(0.0, income - 48000))
    elif income <= 200000:
        premium = min(750.0, 600 + 0.25 * max(0.0, income - 72000))
    else:
        premium = min(900.0, 750 + 0.25 * (income - 200000))
    return surtax, premium


def payroll_deductions(income, province, pay):
    if province == "QC":
        pension = min(max(0.0, min(income, pay["qpp"]["ympe"]) - pay["qpp"]["basic_exemption"])
                      * pay["qpp"]["employee_rate"], pay["qpp"]["max_employee_contribution"])
        ei = min(income * pay["ei"]["quebec"]["employee_rate"], pay["ei"]["quebec"]["max_employee_premium"])
        qpip = min(income * pay["qpip"]["employee_rate"], pay["qpip"]["max_employee_premium"])
    else:
        pension = min(max(0.0, min(income, pay["cpp"]["ympe"]) - pay["cpp"]["basic_exemption"])
                      * pay["cpp"]["employee_rate"], pay["cpp"]["max_employee_contribution"])
        ei = min(income * pay["ei"]["employee_rate"], pay["ei"]["max_employee_premium"])
        qpip = 0.0
    band = pay["cpp2"]["earnings_band"]
    pension2 = min(max(0.0, min(income, band["to"]) - band["from"]) * pay["cpp2"]["employee_rate"],
                   pay["cpp2"]["max_employee_contribution"])
    return pension, pension2, ei, qpip


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    income = float(sys.argv[1])
    province = sys.argv[2].upper()

    tax_data = load("personal_income_tax_2026.json")
    pay = load("payroll_contributions_2026.json")
    fed = tax_data["federal"]
    if province not in tax_data["provinces"]:
        sys.exit(f"Unknown province code {province}. Choose from: {', '.join(tax_data['provinces'])}")
    prov = tax_data["provinces"][province]

    fed_rate0 = fed["brackets"][0]["rate"]
    fed_tax = progressive_tax(income, fed["brackets"]) - federal_bpa(income, fed) * fed_rate0
    fed_tax = max(0.0, fed_tax)
    if province == "QC":
        fed_tax *= 1 - 0.165  # Quebec abatement

    prov_rate0 = prov["brackets"][0]["rate"]
    prov_bpa = prov["basic_personal_amount"] or 0
    prov_tax = max(0.0, progressive_tax(income, prov["brackets"]) - prov_bpa * prov_rate0)
    surtax = premium = 0.0
    if province == "ON":
        surtax, premium = ontario_extras(income, prov_tax, prov)
        prov_tax += surtax + premium

    pension, pension2, ei, qpip = payroll_deductions(income, province, pay)
    total = fed_tax + prov_tax + pension + pension2 + ei + qpip

    print(f"2026 estimate for ${income:,.0f} taxable income in {prov['name']}")
    print(f"  Federal income tax:    ${fed_tax:>12,.2f}")
    print(f"  Provincial income tax: ${prov_tax:>12,.2f}" +
          (f"  (incl. surtax ${surtax:,.2f}, health premium ${premium:,.2f})" if province == "ON" else ""))
    label = "QPP" if province == "QC" else "CPP"
    print(f"  {label} + {label}2:            ${pension + pension2:>12,.2f}")
    print(f"  EI:                    ${ei:>12,.2f}")
    if qpip:
        print(f"  QPIP:                  ${qpip:>12,.2f}")
    print(f"  Total deductions:      ${total:>12,.2f}")
    print(f"  After-tax income:      ${income - total:>12,.2f}")
    print(f"  Average rate: {total / income * 100:.1f}%")


if __name__ == "__main__":
    main()
