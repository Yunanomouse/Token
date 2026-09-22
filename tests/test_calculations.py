#!/usr/bin/env python3
"""Behaviour checks for examples/cantax.py and the two example scripts.

Run with:  python3 -m unittest discover -s tests
"""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "examples"))

import cantax  # noqa: E402  (needs the sys.path line above)

TAX = cantax.load("personal_income_tax_2026.json")
PAY = cantax.load("payroll_contributions_2026.json")
LIMITS = cantax.load("credits_and_limits_2026.json")


def statutory_ontario_health_premium(income):
    """The legislated table, written out independently of the dataset."""
    if income <= 20000:
        return 0.0
    if income <= 36000:
        return min(300.0, 0.06 * (income - 20000))
    if income <= 48000:
        return min(450.0, 300 + 0.06 * (income - 36000))
    if income <= 72000:
        return min(600.0, 450 + 0.25 * (income - 48000))
    if income <= 200000:
        return min(750.0, 600 + 0.25 * (income - 72000))
    return min(900.0, 750 + 0.25 * (income - 200000))


class TestProgressiveTax(unittest.TestCase):
    BRACKETS = [{"up_to": 100, "rate": 0.1}, {"up_to": 200, "rate": 0.2}, {"up_to": None, "rate": 0.3}]

    def test_zero_and_negative_income_pay_nothing(self):
        self.assertEqual(cantax.progressive_tax(0, self.BRACKETS), 0.0)
        self.assertEqual(cantax.progressive_tax(-50, self.BRACKETS), 0.0)

    def test_tax_within_and_across_brackets(self):
        self.assertAlmostEqual(cantax.progressive_tax(50, self.BRACKETS), 5.0)
        self.assertAlmostEqual(cantax.progressive_tax(100, self.BRACKETS), 10.0)
        self.assertAlmostEqual(cantax.progressive_tax(150, self.BRACKETS), 20.0)
        self.assertAlmostEqual(cantax.progressive_tax(200, self.BRACKETS), 30.0)
        self.assertAlmostEqual(cantax.progressive_tax(300, self.BRACKETS), 60.0)

    def test_tax_is_monotonic_in_income(self):
        previous = -1.0
        for income in range(0, 400, 7):
            tax = cantax.progressive_tax(income, self.BRACKETS)
            self.assertGreaterEqual(tax, previous)
            previous = tax

    def test_real_federal_brackets(self):
        fed = TAX["federal"]["brackets"]
        first = fed[0]["up_to"]
        self.assertAlmostEqual(cantax.progressive_tax(first, fed), first * fed[0]["rate"], places=6)
        expected = first * fed[0]["rate"] + (fed[1]["up_to"] - first) * fed[1]["rate"]
        self.assertAlmostEqual(cantax.progressive_tax(fed[1]["up_to"], fed), expected, places=6)


class TestBasicPersonalAmount(unittest.TestCase):
    def test_federal_bpa_phase_out_endpoints_and_midpoint(self):
        fed = TAX["federal"]
        bpa = fed["basic_personal_amount"]
        start, end = fed["brackets"][2]["up_to"], fed["brackets"][3]["up_to"]
        self.assertEqual(cantax.federal_bpa(0, fed), bpa["max"])
        self.assertEqual(cantax.federal_bpa(start, fed), bpa["max"])
        self.assertEqual(cantax.federal_bpa(end, fed), bpa["min"])
        self.assertEqual(cantax.federal_bpa(end + 100000, fed), bpa["min"])
        self.assertAlmostEqual(cantax.federal_bpa((start + end) / 2, fed),
                               (bpa["max"] + bpa["min"]) / 2, places=6)

    def test_yukon_bpa_is_phased_like_the_federal_one(self):
        fed, yt = TAX["federal"], TAX["provinces"]["YT"]
        end = fed["brackets"][3]["up_to"]
        low, missing_low = cantax.provincial_bpa(50000, yt, fed)
        high, missing_high = cantax.provincial_bpa(end + 1, yt, fed)
        self.assertFalse(missing_low or missing_high)
        self.assertEqual(low, yt["basic_personal_amount"]["max"])
        self.assertEqual(high, yt["basic_personal_amount"]["min"])
        self.assertLess(high, low)

    def test_flat_provincial_bpa_does_not_vary_with_income(self):
        fed, ab = TAX["federal"], TAX["provinces"]["AB"]
        self.assertEqual(cantax.provincial_bpa(30000, ab, fed),
                         cantax.provincial_bpa(400000, ab, fed))

    def test_missing_bpa_is_reported_rather_than_silently_zero(self):
        fed, pe = TAX["federal"], TAX["provinces"]["PE"]
        amount, missing = cantax.provincial_bpa(60000, pe, fed)
        self.assertEqual(amount, 0.0)
        self.assertTrue(missing)


class TestOntarioExtras(unittest.TestCase):
    def test_health_premium_matches_the_statutory_table(self):
        on = TAX["provinces"]["ON"]
        incomes = [0, 20000, 20001, 22000, 25000, 30000, 36000, 38500, 40000, 45000,
                   48000, 48600, 50000, 72000, 72300, 72600, 150000, 200000, 200600,
                   300000, 1000000]
        for income in incomes:
            with self.subTest(income=income):
                self.assertAlmostEqual(cantax.ontario_health_premium(income, on),
                                       statutory_ontario_health_premium(income), places=6)

    def test_health_premium_is_capped_and_never_negative(self):
        on = TAX["provinces"]["ON"]
        for income in range(0, 300000, 977):
            premium = cantax.ontario_health_premium(income, on)
            self.assertGreaterEqual(premium, 0.0)
            self.assertLessEqual(premium, 900.0)

    def test_surtax_applies_only_above_the_thresholds(self):
        on = TAX["provinces"]["ON"]
        first, second = (t["tax_over"] for t in on["surtax"]["thresholds"])
        self.assertEqual(cantax.ontario_surtax(first, on), 0.0)
        self.assertAlmostEqual(cantax.ontario_surtax(second, on), (second - first) * 0.2, places=6)
        self.assertAlmostEqual(cantax.ontario_surtax(second + 1000, on),
                               (second + 1000 - first) * 0.2 + 1000 * 0.36, places=6)


class TestIncomeTax(unittest.TestCase):
    def test_no_tax_on_zero_income_anywhere(self):
        for code in TAX["provinces"]:
            with self.subTest(jurisdiction=code):
                fed, prov, _, _, _ = cantax.income_tax(0, code, TAX, LIMITS)
                self.assertEqual(fed, 0.0)
                self.assertEqual(prov, 0.0)

    def test_quebec_federal_tax_is_reduced_by_the_abatement(self):
        income = 120000
        qc_fed, _, _, _, _ = cantax.income_tax(income, "QC", TAX, LIMITS)
        on_fed, _, _, _, _ = cantax.income_tax(income, "ON", TAX, LIMITS)
        rate = LIMITS["other"]["quebec_abatement_rate"]
        self.assertAlmostEqual(qc_fed, on_fed * (1 - rate), places=6)

    def test_ontario_provincial_tax_includes_surtax_and_premium(self):
        income = 250000
        _, prov, surtax, premium, _ = cantax.income_tax(income, "ON", TAX, LIMITS)
        self.assertGreater(surtax, 0)
        self.assertEqual(premium, 900.0)
        on = TAX["provinces"]["ON"]
        bpa, _ = cantax.provincial_bpa(income, on, TAX["federal"])
        basic = cantax.progressive_tax(income, on["brackets"]) - bpa * on["brackets"][0]["rate"]
        self.assertAlmostEqual(prov, basic + surtax + premium, places=6)

    def test_total_tax_is_monotonic_in_income(self):
        for code in ("ON", "QC", "AB"):
            previous = -1.0
            for income in range(0, 400000, 9999):
                fed, prov, _, _, _ = cantax.income_tax(income, code, TAX, LIMITS)
                with self.subTest(jurisdiction=code, income=income):
                    self.assertGreaterEqual(fed + prov, previous)
                previous = fed + prov


class TestPayroll(unittest.TestCase):
    def test_contributions_cap_at_the_published_maximums(self):
        pension, pension2, ei, qpip = cantax.employee_payroll(500000, "ON", PAY)
        self.assertAlmostEqual(pension, PAY["cpp"]["max_employee_contribution"])
        self.assertAlmostEqual(pension2, PAY["cpp2"]["max_employee_contribution"])
        self.assertAlmostEqual(ei, PAY["ei"]["max_employee_premium"])
        self.assertEqual(qpip, 0.0)

    def test_quebec_uses_qpp_qpp2_and_qpip_not_the_federal_plans(self):
        pension, pension2, ei, qpip = cantax.employee_payroll(500000, "QC", PAY)
        self.assertAlmostEqual(pension, PAY["qpp"]["max_employee_contribution"])
        self.assertNotAlmostEqual(pension, PAY["cpp"]["max_employee_contribution"])
        self.assertAlmostEqual(pension2, PAY["qpp2"]["max_employee_contribution"])
        self.assertAlmostEqual(ei, PAY["ei"]["quebec"]["max_employee_premium"])
        self.assertAlmostEqual(qpip, PAY["qpip"]["max_employee_premium"])

    def test_no_contributions_below_the_basic_exemption(self):
        pension, pension2, _, _ = cantax.employee_payroll(PAY["cpp"]["basic_exemption"], "ON", PAY)
        self.assertEqual(pension, 0.0)
        self.assertEqual(pension2, 0.0)

    def test_second_tier_starts_only_above_the_ympe(self):
        ympe = PAY["cpp"]["ympe"]
        _, at_ympe, _, _ = cantax.employee_payroll(ympe, "ON", PAY)
        _, above, _, _ = cantax.employee_payroll(ympe + 1000, "ON", PAY)
        self.assertEqual(at_ympe, 0.0)
        self.assertAlmostEqual(above, 1000 * PAY["cpp2"]["employee_rate"])

    def test_self_employed_pays_both_halves(self):
        high = 500000
        employee_side = sum(cantax.employee_payroll(high, "ON", PAY)[:2])
        self.assertAlmostEqual(cantax.self_employed_pension(high, "ON", PAY), employee_side * 2)

    def test_self_employed_quebec_uses_the_qpp_rate(self):
        qc = cantax.self_employed_pension(500000, "QC", PAY)
        ca = cantax.self_employed_pension(500000, "ON", PAY)
        self.assertAlmostEqual(qc, PAY["qpp"]["max_self_employed_contribution"]
                               + PAY["qpp2"]["max_self_employed_contribution"])
        self.assertGreater(qc, ca, "QPP's 12.6% rate exceeds CPP's 11.9%")


class TestExampleScripts(unittest.TestCase):
    """The scripts must run, and must not crash on edge-case input."""

    def run_script(self, name, *args):
        return subprocess.run([sys.executable, str(ROOT / "examples" / name), *args],
                              capture_output=True, text=True)

    def test_calculator_runs_for_every_jurisdiction(self):
        for code in TAX["provinces"]:
            with self.subTest(jurisdiction=code):
                result = self.run_script("income_tax_calculator.py", "90000", code)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Total deductions", result.stdout)

    def test_calculator_handles_zero_income_without_dividing_by_zero(self):
        result = self.run_script("income_tax_calculator.py", "0", "ON")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_calculator_rejects_bad_input_with_a_message_not_a_traceback(self):
        for args in (("abc", "ON"), ("-100", "ON"), ("90000", "ZZ"), ("90000",)):
            with self.subTest(args=args):
                result = self.run_script("income_tax_calculator.py", *args)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Traceback", result.stderr)

    def test_calculator_warns_when_a_province_has_no_bpa(self):
        result = self.run_script("income_tax_calculator.py", "90000", "PE")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("warning", result.stderr.lower())

    def test_trader_comparison_runs(self):
        result = self.run_script("trader_scenario_comparison.py", "150000", "ON")
        self.assertEqual(result.returncode, 0, result.stderr)
        for marker in ("A. Sole proprietor", "B. Sole proprietor", "C. CCPC"):
            self.assertIn(marker, result.stdout)

    def test_trader_comparison_labels_quebec_contributions_qpp(self):
        result = self.run_script("trader_scenario_comparison.py", "150000", "QC")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("QPP", result.stdout)
        self.assertNotIn("CPP", result.stdout)

    def test_trader_comparison_rejects_zero_profit(self):
        result = self.run_script("trader_scenario_comparison.py", "0", "ON")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
