#!/usr/bin/env python3
"""Compare 2026 tax outcomes for a full-time trader's business income.

Usage:
    python3 examples/trader_scenario_comparison.py <annual_trading_profit> <province_code>
    python3 examples/trader_scenario_comparison.py 150000 ON

Scenarios compared:
  A. Sole proprietor, no RRSP contribution
  B. Sole proprietor, maximum RRSP deduction (18% of profit, capped)
  C. CCPC retaining all after-tax profit at the small-business rate
     (deferral — personal tax is still owed when funds are withdrawn)

Trader-specific payroll: self-employed CPP/CPP2 — QPP/QPP2 in Quebec —
paying both halves; no EI.
Rough estimates for comparison only — ignores most credits, the RRSP
room actually available (based on PRIOR-year income), corporate setup
costs, and Ontario/Quebec mid-2026 small-business rate changes.
Not tax advice. See docs/trader_taxation.md.
"""
import sys

import cantax


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)

    tax_data = cantax.load("personal_income_tax_2026.json")
    pay = cantax.load("payroll_contributions_2026.json")
    corp = cantax.load("corporate_income_tax_2026.json")
    limits = cantax.load("credits_and_limits_2026.json")

    profit = cantax.parse_income(sys.argv[1], "trading profit")
    province = cantax.resolve_province(sys.argv[2], tax_data)
    prov_name = tax_data["provinces"][province]["name"]
    if profit <= 0:
        sys.exit("Trading profit must be greater than zero to compare scenarios.")

    pension = cantax.self_employed_pension(profit, province, pay)
    label = cantax.pension_label(province)

    # Scenario A: sole proprietor, no RRSP
    fed_a, prov_a, _, _, bpa_missing = cantax.income_tax(profit, province, tax_data, limits)
    if bpa_missing:
        cantax.warn_missing_bpa(province, tax_data)
    total_a = fed_a + prov_a + pension

    # Scenario B: sole proprietor with max RRSP deduction
    rrsp = min(0.18 * profit, limits["registered_accounts"]["rrsp"]["annual_limit"])
    fed_b, prov_b, _, _, _ = cantax.income_tax(profit - rrsp, province, tax_data, limits)
    total_b = fed_b + prov_b + pension  # pension is on business profit, unaffected by RRSP

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
    print(f"   Income tax ${fed_a + prov_a:,.0f} + self-employed {label} ${pension:,.0f}")
    print(f"   Total ${total_a:,.0f}  |  keep ${profit - total_a:,.0f}  ({total_a / profit * 100:.1f}% avg)")
    print("-" * w)
    print(f"B. Sole proprietor + max RRSP deduction (${rrsp:,.0f})")
    print(f"   Income tax ${fed_b + prov_b:,.0f} + self-employed {label} ${pension:,.0f}")
    print(f"   Total ${total_b:,.0f}  |  saves ${total_a - total_b:,.0f} vs A")
    print("   (RRSP funds stay yours, taxed only on withdrawal)")
    print("-" * w)
    print(f"C. CCPC, all profit retained (small-business rate {sb_rate * 100:.1f}%)")
    print(f"   Corporate tax ${corp_tax:,.0f}  |  retained in corp ${retained:,.0f}")
    print(f"   Deferral vs A: ${total_a - corp_tax:,.0f} more capital working now (no salary = no {label});")
    print("   personal tax applies later when paid out as salary/dividends.")
    print("=" * w)
    print("Rough estimates only — see docstring and docs/trader_taxation.md.")


if __name__ == "__main__":
    main()
