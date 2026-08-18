#!/usr/bin/env python3
"""Compare 2026 tax outcomes for a full-time trader's business income.

Usage:
    python examples/trader_scenario_comparison.py <annual_trading_profit> <province_code>
    python examples/trader_scenario_comparison.py 150000 ON

Scenarios compared:
  A. Sole proprietor, no RRSP contribution
  B. Sole proprietor, maximum RRSP deduction (18% of profit, capped)
  C. CCPC retaining all after-tax profit at the small-business rate
     (deferral — personal tax is still owed when funds are withdrawn)

Trader-specific payroll: self-employed CPP (both halves) + CPP2; no EI.
Rough estimates for comparison only — ignores most credits, the RRSP
room actually available (based on PRIOR-year income), corporate setup
costs, and Ontario/Quebec mid-2026 small-business rate changes.
Not tax advice. See docs/trader_taxation.md.
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
    phase_start = fed["brackets"][2]["up_to"]
    phase_end = fed["brackets"][3]["up_to"]
    if income <= phase_start:
        return bpa["max"]
    if income >= phase_end:
        return bpa["min"]
    frac = (income - phase_start) / (phase_end - phase_start)
    return bpa["max"] - frac * (bpa["max"] - bpa["min"])


def personal_income_tax(income, province, tax_data):
    """Federal + provincial income tax on `income`, excluding payroll."""
    fed = tax_data["federal"]
    prov = tax_data["provinces"][province]

    fed_tax = progressive_tax(income, fed["brackets"]) - federal_bpa(income, fed) * fed["brackets"][0]["rate"]
    fed_tax = max(0.0, fed_tax)
    if province == "QC":
        fed_tax *= 1 - 0.165

    prov_bpa = prov["basic_personal_amount"] or 0
    prov_tax = max(0.0, progressive_tax(income, prov["brackets"]) - prov_bpa * prov["brackets"][0]["rate"])
    if province == "ON":
        basic = prov_tax
        for t in prov["surtax"]["thresholds"]:
            prov_tax += max(0.0, basic - t["tax_over"]) * t["rate"]
        # Ontario health premium (top bands; simplified for trader incomes)
        if income > 200600:
            prov_tax += 900
        elif income > 72600:
            prov_tax += 750 if income <= 200000 else 750 + 0.25 * (income - 200000)
        elif income > 25000:
            prov_tax += min(600.0, 300 + max(0.0, min(income, 72000) - 36000) * 0.06)
        elif income > 20000:
            prov_tax += 0.06 * (income - 20000)
    return fed_tax, prov_tax


def self_employed_cpp(income, pay):
    base = min(max(0.0, min(income, pay["cpp"]["ympe"]) - pay["cpp"]["basic_exemption"])
               * pay["cpp"]["self_employed_rate"], pay["cpp"]["max_self_employed_contribution"])
    band = pay["cpp2"]["earnings_band"]
    cpp2 = min(max(0.0, min(income, band["to"]) - band["from"]) * pay["cpp2"]["self_employed_rate"],
               pay["cpp2"]["max_self_employed_contribution"])
    return base + cpp2


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    profit = float(sys.argv[1])
    province = sys.argv[2].upper()

    tax_data = load("personal_income_tax_2026.json")
    pay = load("payroll_contributions_2026.json")
    corp = load("corporate_income_tax_2026.json")
    limits = load("credits_and_limits_2026.json")
    if province not in tax_data["provinces"]:
        sys.exit(f"Unknown province code {province}. Choose from: {', '.join(tax_data['provinces'])}")
    prov_name = tax_data["provinces"][province]["name"]

    cpp = self_employed_cpp(profit, pay)

    # Scenario A: sole proprietor, no RRSP
    fed_a, prov_a = personal_income_tax(profit, province, tax_data)
    total_a = fed_a + prov_a + cpp

    # Scenario B: sole proprietor with max RRSP deduction
    rrsp = min(0.18 * profit, limits["registered_accounts"]["rrsp"]["annual_limit"])
    fed_b, prov_b = personal_income_tax(profit - rrsp, province, tax_data)
    total_b = fed_b + prov_b + cpp  # CPP is on business profit, unaffected by RRSP

    # Scenario C: CCPC retains everything at the small-business rate
    sb_rate = corp["federal"]["small_business_rate"] + corp["provincial"][province]["small_business_rate"]
    sb_limit = corp["provincial"][province]["small_business_limit"]
    corp_tax = min(profit, sb_limit) * sb_rate + max(0.0, profit - sb_limit) * (
        corp["federal"]["general_rate"] + corp["provincial"][province]["general_rate"])
    retained = profit - corp_tax

    w = 58
    print(f"2026 trader scenarios — ${profit:,.0f} profit, {prov_name}")
    print("=" * w)
    print("A. Sole proprietor, no RRSP")
    print(f"   Income tax ${fed_a + prov_a:,.0f} + self-employed CPP ${cpp:,.0f}")
    print(f"   Total ${total_a:,.0f}  |  keep ${profit - total_a:,.0f}  ({total_a / profit * 100:.1f}% avg)")
    print("-" * w)
    print(f"B. Sole proprietor + max RRSP deduction (${rrsp:,.0f})")
    print(f"   Income tax ${fed_b + prov_b:,.0f} + self-employed CPP ${cpp:,.0f}")
    print(f"   Total ${total_b:,.0f}  |  saves ${total_a - total_b:,.0f} vs A")
    print(f"   (RRSP funds stay yours, taxed only on withdrawal)")
    print("-" * w)
    print(f"C. CCPC, all profit retained (small-business rate {sb_rate * 100:.1f}%)")
    print(f"   Corporate tax ${corp_tax:,.0f}  |  retained in corp ${retained:,.0f}")
    print(f"   Deferral vs A: ${total_a - corp_tax:,.0f} more capital working now (no salary = no CPP);")
    print(f"   personal tax applies later when paid out as salary/dividends.")
    print("=" * w)
    print("Rough estimates only — see docstring and docs/trader_taxation.md.")


if __name__ == "__main__":
    main()
