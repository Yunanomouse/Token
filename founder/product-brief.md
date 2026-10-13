<!-- /founder:product-brief · 2026-10-13 · input: Token, a Canadian active-trader toolkit that pairs free OpenBB market data with 2026 tax calculators showing what a trader keeps as a sole proprietor, with an RRSP, or through a CCPC -->

# Product brief: Token

Assumption: Token is being treated as a product for other Canadian traders. Today it is a personal toolkit in a public repo, with no users and no revenue.
Assumption: The founder is solo. [Confirm team size and time committed per week]
Assumption: The first version stays free and open source. Pricing is decided later in `/founder:pricing-strategy`.
Assumption: "Active trader" means a self-directed Canadian who trades often enough that CRA treats profits as business income.

## Problem statement

Canadian active traders find out their real after-tax result too late, usually in April.

- **The pain:** CRA taxes frequent short-hold trading as 100% business income, not 50%-included capital gains. A trader who files it as capital gains loses the audit position. One who trades in a TFSA can have the whole account's gains taxed (s.146.2). The levers that help (RRSP room created by trading profit, deductible data feeds, the CCPC deferral) are scattered across CRA pages, accountant blogs and forums.
- **Who feels it most:** traders with $30K to $250K a year in trading profit. They are big enough that the sole proprietor vs CCPC choice is worth tens of thousands of dollars, and too small to keep a CPA on retainer. The repo's own Alberta example puts the gap at $9,720 a year from a max RRSP deduction and $31,203 of deferral through a CCPC on $150,000 of profit.
- **Today they use:** a broker P&L export, a spreadsheet, TaxTips.ca tables, Reddit threads (r/PersonalFinanceCanada, r/CanadianInvestor), and a once-a-year CPA visit. Market data and tax planning live in separate tools, and none of them is Canadian-trader specific.

## Target audience

Self-directed Canadian day and swing traders, mostly in Alberta and Ontario, earning $30K to $250K a year in trading profit through Questrade, IBKR or Wealthsimple. They run their own scripts or spreadsheets and are weighing whether to incorporate in the next 12 months.

Run `/founder:persona-gen` for full personas.

## Value proposition

Token helps Canadian active traders keep more of each year's profit by putting 2026 tax data for all 14 jurisdictions, a sole proprietor vs RRSP vs CCPC calculator, and free OpenBB market data in one local, open toolkit, unlike TurboTax or Wealthsimple Tax, which only file last year's return and never model whether to incorporate.

## Core features (MVP)

1. **Tax data for all 14 jurisdictions (exists).** 2026 brackets, BPAs, CPP/QPP/EI, GST/HST/PST and corporate rates in JSON and CSV. Every calculation stands on it.
2. **Trader scenario calculator (exists).** Profit and province in, sole prop vs max RRSP vs CCPC out. This is the reason a trader shows up at all.
3. **Trading P&L import (missing).** Read a Questrade or IBKR activity export, or OpenBB price history, and compute realized profit for the year. Without it, users type a guess and the calculator answers a guess.
4. **Year-to-date tax tracker (missing).** Running estimate of tax owed and the next quarterly instalment. Instalment interest is high and non-deductible, so this is the feature people return to monthly.
5. **OpenBB market data layer (exists, thin).** One script pulls yfinance prices to CSV. It needs to feed features 3 and 4, or it is a tutorial, not a feature.
6. **Classification and account guardrails (docs only).** A checklist that flags TFSA trading and capital-gains filing of business income. These are the two most expensive mistakes.
7. **Incorporation readiness check (docs only).** Turn `docs/incorporation_checklist.md` into a scored check: profit level, retained profit, setup cost of $2,000 to $5,000 a year. This is the high-value moment that justifies paying later.

## Success metrics (first 90 days)

| KPI | Target by day 90 | Type |
|---|---|---|
| GitHub stars | 150 | Leading, awareness |
| People who ran the scenario calculator (opt-in counter or survey) | 100 | Leading, activation |
| Traders who imported a real P&L export | 25 | Activation |
| Repeat use in a second month (YTD tracker) | 10 | Retention |
| Interviews completed with active traders | 15 | Learning |

## Risks and assumptions

1. **Traders will pay for planning, not just filing.** Test: a one-page landing page with a $19/year "planner" preorder button, posted to two Canadian trading subreddits. Pass if 3% of visitors click. Cost under $100 in ads, 1 week.
2. **The CCPC question is common enough to build around.** Test: 15 interviews with traders over $50K profit (see `/founder:user-interviews`). Pass if 6 or more have asked a CPA or forum about incorporating. Cost: $0 to $300 in gift cards, 2 weeks.
3. **Free data (yfinance through OpenBB) is reliable enough.** yfinance is an unofficial Yahoo scraper and breaks without warning. Test: run the quickstart daily for 14 days on 20 TSX and US tickers and log failures. Pass if under 5% of runs fail. Cost: $0.

Liability risk underlies all three. Output is estimates, not tax advice, and the disclaimers already in the repo must ship with every result.

## Go-to-market snapshot

| Channel | Estimated CAC | Why |
|---|---|---|
| Reddit (r/CanadianInvestor, r/PersonalFinanceCanada, r/Daytrading) posts with real worked numbers | Estimate: $0 to $5. Time only, about 3 hours per post that reaches 50 or more users | The TFSA-trading and "is trading income taxed as capital gains" threads repeat every month |
| GitHub and Hacker News "Show HN" | Estimate: $0. Reaches technical traders who already run Python | The repo is already public, and OpenBB users are this crowd |
| Partnerships with Canadian trader-focused CPAs (referral both ways) | Estimate: $20 to $60 per user (one lunch or $50 referral per 1 to 3 users) | CPAs get pre-qualified incorporation leads, Token gets credibility |

**Growth tactic:** publish a yearly "What a $50K, $150K and $300K trader keeps in each province, 2026" table generated straight from the repo's JSON. It is shareable, comes back every budget season, and every row links to the calculator.

Saved to `founder/product-brief.md`. Next: `/founder:validate-idea`, `/founder:competitor-matrix`.
