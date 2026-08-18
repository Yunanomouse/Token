# Taxation of Active Trading in Canada (2026)

How Canada taxes high-frequency ("scalp") trading, and the levers that legitimately reduce the bill. Companion to `examples/trader_scenario_comparison.py`, which puts numbers on the scenarios using the dataset in `data/json/`.

> **Not tax advice.** Classification and incorporation questions in particular are fact-specific and worth a session with a Canadian tax accountant (CPA) before acting.

## 1. Classification: business income, not capital gains

CRA decides capital-vs-income treatment from behaviour: transaction frequency, holding periods, time devoted, use of leverage, and speculative intent. High-frequency short-hold trading checks every box, so scalping profits are **100% taxable business income** — the 50% capital gains inclusion rate does not apply.

- Filing scalp profits as capital gains is a common, losing audit position.
- The s.39(4) "Canadian securities" election that locks in capital treatment is explicitly **unavailable** to traders and dealers (s.39(5)).

## 2. Registered accounts

| Account | Active trading inside it |
|---|---|
| **TFSA** | **Do not.** Carrying on a trading business in a TFSA makes the income fully taxable inside the account (s.146.2), and frequent-trading TFSAs are a known CRA audit program. Keep the TFSA for long-term holdings. |
| **RRSP** | Generally sheltered. The Act taxes business income earned by a TFSA, but for RRSPs it carves out the business of trading *qualified investments* (s.146(4)(b)), so gains compound tax-deferred; withdrawals are taxed as ordinary income. Options strategies are restricted in registered accounts — check your broker. |
| **FHSA** | Same "carrying on a business" concern as the TFSA; not a trading vehicle. |

**The RRSP double lever:** trading profits are earned income, so they *create* RRSP room (18% of prior-year earned income, max $33,810 for 2026). The contribution deducts against fully-taxed business income — at trader marginal rates this is the largest easy saving — and money inside the RRSP can itself be traded tax-deferred.

## 3. Deduct like the business you are

Business-income treatment cuts both ways. Deductible against trading profits:

- Market data feeds, charting/platform subscriptions, order-flow tools
- Margin and other interest on money borrowed to trade
- Home-office proportion (workspace used principally for the business)
- Computers, monitors, software (capitalized/CCA where required)
- Accounting and tax-preparation fees
- A **reasonable** salary to a spouse or family member who genuinely does bookkeeping/admin (creates RRSP room for them; keep records of hours and duties)

**Losses:** trading losses are fully deductible against any other income (employment, etc.) — not trapped against capital gains — and carry back 3 years / forward 20 as non-capital losses.

## 4. Incorporation (CCPC): a deferral, not an exemption

A corporation whose business is trading may pay the small-business rate on the first $500,000 of active business income — roughly **11–12% combined** in most provinces for 2026 (see `data/json/corporate_income_tax_2026.json`) versus ~45–53% top personal marginal rates.

- The saving is a **deferral**: you pay the remaining personal tax when profits come out as salary or dividends. The benefit accrues on profits you *retain and compound* inside the corporation.
- Whether trading profits qualify as **active business income** (vs. a specified investment business) is a gray area — get a professional opinion before building the structure.
- Costs: incorporation, annual filings/accounting ($2–5k+/yr), payroll admin. Rule of thumb: interesting once profits are consistently well beyond what you spend personally.
- Income-splitting through a corporation is tightly restricted by the TOSI (tax on split income) rules.

## 5. Housekeeping

- **Instalments:** once CRA requires quarterly instalments, pay them — interest on shortfalls is high and non-deductible.
- **Records:** keep trade-level exports, expense receipts, and a home-office log; business-income audits are won on bookkeeping.
- **CPP:** a sole-proprietor trader pays both halves of CPP (11.9% to the YMPE + 8% CPP2 band) via the T1; no EI is payable (or claimable) on self-employed trading income.
- **Province matters:** combined top rates for 2026 range from ~44% (AB) to ~54.8% (NL); see `data/csv/income_tax_brackets_2026.csv`.

## The honest hierarchy

1. Max the RRSP deduction every year.
2. Deduct every legitimate expense.
3. Keep the TFSA boring (long-term holdings only).
4. Price out incorporation with a CPA once profits are consistently six figures.
