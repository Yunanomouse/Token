#!/usr/bin/env python3
"""Generate the CSV exports in data/csv/ from the JSON sources in data/json/."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_DIR = ROOT / "data" / "json"
CSV_DIR = ROOT / "data" / "csv"


def load(name):
    with open(JSON_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def write_csv(name, header, rows):
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    path = CSV_DIR / name
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"wrote {path.relative_to(ROOT)} ({len(rows)} rows)")


def brackets_csv():
    data = load("personal_income_tax_2026.json")
    rows = []

    def add(code, name, jur):
        lower = 0
        for i, b in enumerate(jur["brackets"], 1):
            rows.append([code, name, i, lower, b["up_to"] if b["up_to"] is not None else "", b["rate"]])
            lower = b["up_to"]

    add("CA", data["federal"]["name"], data["federal"])
    for code, jur in data["provinces"].items():
        add(code, jur["name"], jur)
    write_csv(
        "income_tax_brackets_2026.csv",
        ["jurisdiction_code", "jurisdiction", "bracket", "income_from", "income_to", "marginal_rate"],
        rows,
    )


def bpa_csv():
    data = load("personal_income_tax_2026.json")
    fed = data["federal"]["basic_personal_amount"]
    rows = [["CA", data["federal"]["name"], fed["max"], fed["min"]]]
    for code, jur in data["provinces"].items():
        bpa = jur["basic_personal_amount"]
        rows.append([code, jur["name"], bpa if bpa is not None else "", ""])
    write_csv(
        "basic_personal_amounts_2026.csv",
        ["jurisdiction_code", "jurisdiction", "bpa_max", "bpa_min_if_phased"],
        rows,
    )


def sales_tax_csv():
    data = load("sales_tax_2026.json")
    rows = []
    for code, j in data["jurisdictions"].items():
        rows.append([
            code, j["name"], j["system"],
            j["gst"] if j["gst"] is not None else "",
            j["pst"] if j["pst"] is not None else "",
            j["hst"] if j["hst"] is not None else "",
            j["total_rate"],
        ])
    write_csv(
        "sales_tax_rates_2026.csv",
        ["jurisdiction_code", "jurisdiction", "system", "gst", "pst_or_qst", "hst", "total_rate"],
        rows,
    )


def corporate_csv():
    data = load("corporate_income_tax_2026.json")
    fed = data["federal"]
    rows = [["CA", "Canada (federal)", fed["general_rate"], fed["small_business_rate"], fed["small_business_limit"]]]
    for code, j in data["provincial"].items():
        rows.append([code, j["name"], j["general_rate"], j["small_business_rate"], j["small_business_limit"]])
    write_csv(
        "corporate_tax_rates_2026.csv",
        ["jurisdiction_code", "jurisdiction", "general_rate", "small_business_rate", "small_business_limit"],
        rows,
    )


def payroll_csv():
    d = load("payroll_contributions_2026.json")
    rows = [
        ["CPP", "employee", d["cpp"]["employee_rate"], d["cpp"]["ympe"], d["cpp"]["basic_exemption"], d["cpp"]["max_employee_contribution"]],
        ["CPP", "self_employed", d["cpp"]["self_employed_rate"], d["cpp"]["ympe"], d["cpp"]["basic_exemption"], d["cpp"]["max_self_employed_contribution"]],
        ["CPP2", "employee", d["cpp2"]["employee_rate"], d["cpp2"]["yampe"], d["cpp2"]["earnings_band"]["from"], d["cpp2"]["max_employee_contribution"]],
        ["CPP2", "self_employed", d["cpp2"]["self_employed_rate"], d["cpp2"]["yampe"], d["cpp2"]["earnings_band"]["from"], d["cpp2"]["max_self_employed_contribution"]],
        ["QPP", "employee", d["qpp"]["employee_rate"], d["qpp"]["ympe"], d["qpp"]["basic_exemption"], d["qpp"]["max_employee_contribution"]],
        ["EI", "employee", d["ei"]["employee_rate"], d["ei"]["maximum_insurable_earnings"], 0, d["ei"]["max_employee_premium"]],
        ["EI", "employer", d["ei"]["employer_rate"], d["ei"]["maximum_insurable_earnings"], 0, d["ei"]["max_employer_premium_per_employee"]],
        ["EI_QC", "employee", d["ei"]["quebec"]["employee_rate"], d["ei"]["maximum_insurable_earnings"], 0, d["ei"]["quebec"]["max_employee_premium"]],
        ["QPIP", "employee", d["qpip"]["employee_rate"], d["qpip"]["maximum_insurable_earnings"], 0, d["qpip"]["max_employee_premium"]],
        ["QPIP", "employer", d["qpip"]["employer_rate"], d["qpip"]["maximum_insurable_earnings"], 0, d["qpip"]["max_employer_premium_per_employee"]],
    ]
    write_csv(
        "payroll_contributions_2026.csv",
        ["program", "payer", "rate", "earnings_ceiling", "exemption_or_band_floor", "max_contribution"],
        rows,
    )


if __name__ == "__main__":
    brackets_csv()
    bpa_csv()
    sales_tax_csv()
    corporate_csv()
    payroll_csv()
