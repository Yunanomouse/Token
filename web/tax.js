/* Canada Tax 2026 - pure calculation engine.
   Mirrors examples/income_tax_calculator.py exactly. No DOM access, so this file
   is loaded by the browser and by scripts/verify_web_parity.mjs alike. */

'use strict';

(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.TaxEngine = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {

  const QUEBEC_ABATEMENT = 0.165;

  /* ---------------- tax math ---------------- */

  /** Progressive tax over a bracket list. `up_to` is the inclusive upper bound;
   *  null means no upper bound. Mirrors progressive_tax() in the Python. */
  function progressiveTax(income, brackets) {
    let tax = 0;
    let lower = 0;
    for (const b of brackets) {
      const upper = b.up_to === null ? Infinity : b.up_to;
      if (income > lower) {
        tax += (Math.min(income, upper) - lower) * b.rate;
        lower = upper;
      } else {
        break;
      }
    }
    return tax;
  }

  /** Marginal rate: the rate of the bracket the income falls in. */
  function marginalRate(income, brackets) {
    let lower = 0;
    for (const b of brackets) {
      const upper = b.up_to === null ? Infinity : b.up_to;
      if (income <= upper) return b.rate;
      lower = upper;
    }
    return brackets[brackets.length - 1].rate;
  }

  /** Federal basic personal amount, linearly phased down between the 4th and 5th
   *  bracket thresholds. Mirrors federal_bpa() in the Python. */
  function federalBPA(income, fed) {
    const bpa = fed.basic_personal_amount;
    const phaseStart = fed.brackets[2].up_to;
    const phaseEnd = fed.brackets[3].up_to;
    if (income <= phaseStart) return bpa.max;
    if (income >= phaseEnd) return bpa.min;
    const frac = (income - phaseStart) / (phaseEnd - phaseStart);
    return bpa.max - frac * (bpa.max - bpa.min);
  }

  /** Ontario surtax on basic tax payable, plus the Ontario Health Premium.
   *  Mirrors ontario_extras() in the Python. */
  function ontarioExtras(income, basicTax, on) {
    let surtax = 0;
    for (const t of on.surtax.thresholds) {
      surtax += Math.max(0, basicTax - t.tax_over) * t.rate;
    }

    let premium;
    if (income <= 20000) premium = 0;
    else if (income <= 36000) premium = Math.min(300, 0.06 * (income - 20000));
    else if (income <= 48000) premium = Math.min(450, 300 + 0.06 * Math.max(0, income - 36000));
    else if (income <= 72000) premium = Math.min(600, 450 + 0.25 * Math.max(0, income - 48000));
    else if (income <= 200000) premium = Math.min(750, 600 + 0.25 * Math.max(0, income - 72000));
    else premium = Math.min(900, 750 + 0.25 * (income - 200000));

    return { surtax, premium };
  }

  /** Employee-side pension, EI and QPIP. Mirrors payroll_deductions() in the Python. */
  function payrollDeductions(income, code, pay) {
    let pension, ei, qpip;

    if (code === 'QC') {
      const q = pay.qpp;
      pension = Math.min(
        Math.max(0, Math.min(income, q.ympe) - q.basic_exemption) * q.employee_rate,
        q.max_employee_contribution
      );
      ei = Math.min(income * pay.ei.quebec.employee_rate, pay.ei.quebec.max_employee_premium);
      qpip = Math.min(income * pay.qpip.employee_rate, pay.qpip.max_employee_premium);
    } else {
      const c = pay.cpp;
      pension = Math.min(
        Math.max(0, Math.min(income, c.ympe) - c.basic_exemption) * c.employee_rate,
        c.max_employee_contribution
      );
      ei = Math.min(income * pay.ei.employee_rate, pay.ei.max_employee_premium);
      qpip = 0;
    }

    const band = pay.cpp2.earnings_band;
    const pension2 = Math.min(
      Math.max(0, Math.min(income, band.to) - band.from) * pay.cpp2.employee_rate,
      pay.cpp2.max_employee_contribution
    );

    return { pension, pension2, ei, qpip };
  }

  /** Full estimate for one income and one jurisdiction. */
  function estimate(income, code, data) {
    const fed = data.income.federal;
    const prov = data.income.provinces[code];

    let fedTax = Math.max(
      0,
      progressiveTax(income, fed.brackets) - federalBPA(income, fed) * fed.brackets[0].rate
    );
    if (code === 'QC') fedTax *= 1 - QUEBEC_ABATEMENT;

    const provBPA = prov.basic_personal_amount || 0;
    let provTax = Math.max(
      0,
      progressiveTax(income, prov.brackets) - provBPA * prov.brackets[0].rate
    );

    let surtax = 0;
    let premium = 0;
    if (code === 'ON') {
      ({ surtax, premium } = ontarioExtras(income, provTax, prov));
      provTax += surtax + premium;
    }

    const { pension, pension2, ei, qpip } = payrollDeductions(income, code, data.payroll);
    const payroll = pension + pension2 + ei + qpip;
    const total = fedTax + provTax + payroll;

    let fedMarginal = marginalRate(income, fed.brackets);
    if (code === 'QC') fedMarginal *= 1 - QUEBEC_ABATEMENT;

    return {
      code,
      name: prov.name,
      income,
      fedTax,
      provTax,
      surtax,
      premium,
      pension,
      pension2,
      ei,
      qpip,
      payroll,
      total,
      keep: income - total,
      avgRate: income > 0 ? total / income : 0,
      marginal: fedMarginal + marginalRate(income, prov.brackets),
      isQuebec: code === 'QC',
    };
  }

  return { progressiveTax, marginalRate, federalBPA, ontarioExtras, payrollDeductions, estimate };
});
