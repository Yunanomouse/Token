#!/usr/bin/env python3
"""Estimate 2026 Canadian income tax from the dataset in data/json/.

Usage:
    python3 examples/income_tax_calculator.py <taxable_income> <province_code>
    python3 examples/income_tax_calculator.py 90000 ON

Covers: progressive federal + provincial brackets, basic personal amount
credits (including the federal enhanced-BPA phase-out, which Yukon mirrors),
the Ontario surtax and health premium, and the Quebec abatement. Employee
CPP/CPP2 (QPP/QPP2 in Quebec) and EI are estimated for employment income.
This is an estimate for illustration, not tax advice — it ignores most
credits, deductions, and provincial low-income reductions.
"""
import sys

import cantax


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)

    tax_data = cantax.load("personal_income_tax_2026.json")
    pay = cantax.load("payroll_contributions_2026.json")
    limits = cantax.load("credits_and_limits_2026.json")

    income = cantax.parse_income(sys.argv[1], "taxable income")
    province = cantax.resolve_province(sys.argv[2], tax_data)
    prov = tax_data["provinces"][province]

    fed_tax, prov_tax, surtax, premium, bpa_missing = cantax.income_tax(
        income, province, tax_data, limits)
    if bpa_missing:
        cantax.warn_missing_bpa(province, tax_data)

    pension, pension2, ei, qpip = cantax.employee_payroll(income, province, pay)
    total = fed_tax + prov_tax + pension + pension2 + ei + qpip
    label = cantax.pension_label(province)

    print(f"2026 estimate for ${income:,.0f} taxable income in {prov['name']}")
    print(f"  Federal income tax:    ${fed_tax:>12,.2f}")
    print(f"  Provincial income tax: ${prov_tax:>12,.2f}" +
          (f"  (incl. surtax ${surtax:,.2f}, health premium ${premium:,.2f})"
           if province == cantax.ONTARIO else ""))
    print(f"  {label} + {label}2:            ${pension + pension2:>12,.2f}")
    print(f"  EI:                    ${ei:>12,.2f}")
    if qpip:
        print(f"  QPIP:                  ${qpip:>12,.2f}")
    print(f"  Total deductions:      ${total:>12,.2f}")
    print(f"  After-tax income:      ${income - total:>12,.2f}")
    if income > 0:
        print(f"  Average rate: {total / income * 100:.1f}%")


if __name__ == "__main__":
    main()
