"""Shared 2026 Canadian tax calculations, driven entirely by data/json/.

Both example scripts import this module so the two of them can never drift
apart on a rule (they previously carried separate, disagreeing copies of the
Ontario Health Premium table).

Nothing here is tax advice: it implements the statutory arithmetic for the
figures in the dataset and deliberately ignores most credits, deductions,
and provincial low-income reductions.
"""
import json
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "json"

# Rate applied to non-refundable credits is each jurisdiction's lowest rate.
QUEBEC = "QC"
ONTARIO = "ON"


def load(name):
    """Load one dataset file from data/json/."""
    with open(DATA / name, encoding="utf-8") as f:
        return json.load(f)


def parse_income(raw, label="income"):
    """Parse a command-line dollar amount, exiting with a clear message."""
    try:
        value = float(raw.replace(",", "").replace("$", ""))
    except ValueError:
        sys.exit(f"Could not read {label} {raw!r} — pass a number, e.g. 90000")
    if value < 0:
        sys.exit(f"{label.capitalize()} cannot be negative (got {value:,.2f})")
    return value


def resolve_province(code, tax_data):
    """Validate a province/territory code against the dataset."""
    code = code.upper()
    if code not in tax_data["provinces"]:
        sys.exit(f"Unknown province code {code}. Choose from: "
                 f"{', '.join(tax_data['provinces'])}")
    return code


def progressive_tax(income, brackets):
    """Tax on `income` under a list of {up_to, rate} marginal brackets."""
    tax, lower = 0.0, 0.0
    for b in brackets:
        if income <= lower:
            break
        upper = b["up_to"] if b["up_to"] is not None else float("inf")
        tax += (min(income, upper) - lower) * b["rate"]
        lower = upper
    return tax


def phased_bpa(income, bpa, phase_start, phase_end):
    """Basic personal amount reduced linearly between two income thresholds."""
    if income <= phase_start:
        return bpa["max"]
    if income >= phase_end:
        return bpa["min"]
    frac = (income - phase_start) / (phase_end - phase_start)
    return bpa["max"] - frac * (bpa["max"] - bpa["min"])


def federal_bpa(income, fed):
    """Federal enhanced BPA, phased down across the top two bracket thresholds."""
    return phased_bpa(income, fed["basic_personal_amount"],
                      fed["brackets"][2]["up_to"], fed["brackets"][3]["up_to"])


def provincial_bpa(income, prov, fed):
    """Provincial BPA: a flat figure, a phased {max, min} pair, or None.

    Returns (amount, missing). `missing` is True when the dataset has no
    figure for the jurisdiction (PEI), so callers can warn instead of
    silently treating the credit as zero.
    """
    bpa = prov["basic_personal_amount"]
    if bpa is None:
        return 0.0, True
    if isinstance(bpa, dict):
        # Yukon adopts the federal enhanced BPA and its phase-out range.
        return phased_bpa(income, bpa, fed["brackets"][2]["up_to"],
                          fed["brackets"][3]["up_to"]), False
    return float(bpa), False


def ontario_surtax(basic_tax, on):
    """Ontario surtax on basic provincial tax payable (after the BPA credit)."""
    return sum(max(0.0, basic_tax - t["tax_over"]) * t["rate"]
               for t in on["surtax"]["thresholds"])


def ontario_health_premium(income, on):
    """Ontario Health Premium from the legislated band table in the dataset."""
    for band in on["health_premium"]["bands"]:
        upper = band["income_up_to"]
        if upper is None or income <= upper:
            return min(band["cap"], band["base"] + band["rate"] * (income - band["income_over"]))
    return 0.0


def quebec_abatement_rate(limits):
    """Quebec's refundable abatement of basic federal tax."""
    return limits["other"]["quebec_abatement_rate"]


def income_tax(income, province, tax_data, limits):
    """Federal and provincial income tax on `income`, excluding payroll.

    Returns (federal_tax, provincial_tax, surtax, health_premium, bpa_missing);
    `provincial_tax` already includes the Ontario surtax and health premium.
    """
    fed = tax_data["federal"]
    prov = tax_data["provinces"][province]

    fed_tax = progressive_tax(income, fed["brackets"])
    fed_tax -= federal_bpa(income, fed) * fed["brackets"][0]["rate"]
    fed_tax = max(0.0, fed_tax)
    if province == QUEBEC:
        fed_tax *= 1 - quebec_abatement_rate(limits)

    bpa, bpa_missing = provincial_bpa(income, prov, fed)
    prov_tax = max(0.0, progressive_tax(income, prov["brackets"])
                   - bpa * prov["brackets"][0]["rate"])

    surtax = premium = 0.0
    if province == ONTARIO:
        surtax = ontario_surtax(prov_tax, prov)
        premium = ontario_health_premium(income, prov)
        prov_tax += surtax + premium

    return fed_tax, prov_tax, surtax, premium, bpa_missing


def _capped(earnings, floor, ceiling, rate, maximum):
    """Contribution on the earnings between floor and ceiling, capped."""
    return min(max(0.0, min(earnings, ceiling) - floor) * rate, maximum)


def pension_plan(province, pay):
    """The (base, second-tier) pension plan blocks that apply in a province."""
    return (pay["qpp"], pay["qpp2"]) if province == QUEBEC else (pay["cpp"], pay["cpp2"])


def employee_payroll(income, province, pay):
    """Employee-side CPP/QPP, CPP2/QPP2, EI, and QPIP on employment income.

    Returns (pension, pension2, ei, qpip).
    """
    base, second = pension_plan(province, pay)
    pension = _capped(income, base["basic_exemption"], base["ympe"],
                      base["employee_rate"], base["max_employee_contribution"])
    pension2 = _capped(income, second["earnings_band"]["from"], second["earnings_band"]["to"],
                       second["employee_rate"], second["max_employee_contribution"])
    if province == QUEBEC:
        ei = min(income * pay["ei"]["quebec"]["employee_rate"],
                 pay["ei"]["quebec"]["max_employee_premium"])
        qpip = min(income * pay["qpip"]["employee_rate"], pay["qpip"]["max_employee_premium"])
    else:
        ei = min(income * pay["ei"]["employee_rate"], pay["ei"]["max_employee_premium"])
        qpip = 0.0
    return pension, pension2, ei, qpip


def self_employed_pension(income, province, pay):
    """Self-employed pension contributions (both halves), including the 2nd tier."""
    base, second = pension_plan(province, pay)
    return (_capped(income, base["basic_exemption"], base["ympe"],
                    base["self_employed_rate"], base["max_self_employed_contribution"])
            + _capped(income, second["earnings_band"]["from"], second["earnings_band"]["to"],
                      second["self_employed_rate"], second["max_self_employed_contribution"]))


def pension_label(province):
    """'QPP' in Quebec, 'CPP' everywhere else."""
    return "QPP" if province == QUEBEC else "CPP"


def warn_missing_bpa(province, tax_data):
    """Print a stderr warning when a jurisdiction has no BPA in the dataset."""
    print(f"warning: no 2026 basic personal amount on file for "
          f"{tax_data['provinces'][province]['name']}; its provincial tax is "
          f"overstated because the credit is treated as $0. See the notes in "
          f"data/json/personal_income_tax_2026.json.", file=sys.stderr)
