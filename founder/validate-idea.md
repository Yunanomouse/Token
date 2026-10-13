<!-- /founder:validate-idea · 2026-10-13 · input: Token: a local, open-source toolkit for self-directed Canadian active traders that combines 2026 tax data and a sole-prop vs RRSP vs CCPC calculator with free OpenBB market data. For Canadian day/swing traders with $30K to $250K trading profit. -->

# Validate idea: Token

Assumption: Founder is solo and has no paying users yet (from `founder/product-brief.md`). [Confirm team size, hours per week, and any tax or accounting credential]
Assumption: "Active trader" means trading frequent enough that CRA treats profit as business income.

## The 30-second assessment

The problem is real: a $150,000 Alberta trader leaves $9,720 a year on the table without a max RRSP deduction and can defer $31,203 through a CCPC (the repo's own worked example). But the buyer you named is tiny, and the two halves of the product do not touch: OpenBB price history does not tell anyone what they owe. As pitched, this is a strong open-source side project, not a business.

## The five fatal questions

**Q1: Who is the customer, and would they pay today?**
A self-directed Alberta or Ontario day or swing trader on Questrade or IBKR, netting $30K to $250K, deciding whether to incorporate in the next 12 months. They would pay once, at the moment of the incorporation decision, and then hand the work to a CPA. Estimate: willingness to pay $20 to $50 a year for a planner, because the alternatives are free: Wealthsimple Tax files self-employment at $0 with optional donation ([wealthsimplebonus.ca](https://wealthsimplebonus.ca/blog/wealthsimple-tax-review-2025)) and TurboTax Self-Employed is about $50 ([wealthnorth.ca](https://wealthnorth.ca/taxes/tax-software/turbotax-canada-review/)). Recurring payment is a "maybe", so it is a no until tested.

**Q2: Why hasn't someone built this already?**
- [sum.money incorporation calculator](https://sum.money/ca/incorporation-calculator/): sole prop vs incorporation for all 13 provinces and territories, no registration, but on 2025 rates and aimed at consultants, not traders.
- [Canadian Money Help salary vs dividend tool](https://canadianmoneyhelp.ca/tools/tax/salary-vs-dividend/) and [Wealthnorth](https://wealthnorth.ca/taxes/corporate-tax/dividend-vs-salary-calculator/): free, generic.
- [AdjustedCostBase.ca](https://adjustedcostbase.ca/): free ACB and capital gains tracker. Built for capital-account investors, the opposite of business-income traders.
- [TraderSync](https://www.moneycrashers.com/tradersync-review/): trade journal at $29.95 to $79.95 USD a month. Proves traders pay for P&L tooling. No Canadian tax.
- [Tradecovex](https://tradecovex.com/guides/canadian-prop-firm-tax-guide): Ontario-built NinjaTrader copier and journal that uses a Canadian tax guide as content marketing. No incorporation calculator.
- Failed Canadian trader-tax products: Not found.

Why the gap exists: the segment is too small for Intuit or Wealthsimple to build for, and generic incorporation calculators already cover 80% of the math. What is new: 2026 rate changes (Alberta 8% bracket, ON and QC small-business rate cuts) and record retail activity, with 2.9 million trading accounts opened in the 12 months to June 2025 ([Globe and Mail, citing Investor Economics](https://www.theglobeandmail.com/business/article-questrade-suite-financial-tools-retail-investors-banks-edward)).

**Q3: What's the distribution advantage?**
First 100 users: Reddit threads on TFSA day trading and "is trading income capital gains" (the brief's plan), plus GitHub and Show HN. That reaches users, not buyers. There is no built-in loop: one trader's tax result does not pull in another trader. The yearly "what a trader keeps in each province" table is the closest thing to a loop, and it is content marketing. Red flag.

**Q4: Big business or feature?**
A feature. Market size:
- Estimate: 32.8M adults ([Statbase, UN projection 2025](https://statbase.org/data/can-population-age-18-and-above/)) × 27% with self-directed accounts ([TD survey via Investment Executive](https://www.investmentexecutive.com/news/industry/canadians-considering-diy-investing-td-survey-finds/), year not shown) = 8.9M DIY investors.
- × 38% who trade 10 to 150 times a quarter ([Wealthsimple and Angus Reid, 2026](https://www.wealthprofessional.ca/news/industry-news/canadian-diy-investors-push-for-advanced-tools-wealthsimple-survey-reveals/392353)) = 3.4M active traders.
- Estimate: 5% trade often enough to be business income = 170K. 5% of those net $30K to $250K = about 8,500 people. The 5% is generous: only 0.4% of persistent Brazilian day traders earned more than a bank teller ([Chague, De-Losso, Giovannetti](https://ideas.repec.org/p/fgv/eesptd/525.html)).
- Ceiling. Estimate: 8,500 × 20% paying × $49 = $83K ARR. $1M ARR at $49 needs 20,400 payers, more than twice the whole segment. Wealthsimple (about 4 million customers, [Investment Executive](https://www.investmentexecutive.com/news/industry/what-four-trading-apps-in-canada-are-focusing-on-right-now/)) could ship an "incorporate?" screen in Wealthsimple Tax in a quarter.

**Q5: Can the founder build it?**
The repo shows the founder can assemble 14 jurisdictions of tax data and a working scenario calculator. The hard parts are not code: (1) parsing Questrade and IBKR activity exports correctly, including FX and options; (2) liability, since one wrong number on an incorporation decision costs a user thousands; (3) the "active business income vs specified investment business" question for a trading CCPC is a gray area the repo itself says needs a CPA. That makes a trader-focused CPA a first-partner problem.

## Idea scorecard

| Dimension | Score | Notes |
|-----------|-------|-------|
| Problem severity | 4 | $9,720 to $31,203 a year at $150K profit (repo example). Painful, but felt once a year. |
| Market size | 1 | Estimate: about 8,500 people. |
| Willingness to pay | 2 | Free filing and free incorporation calculators anchor the price near $0. |
| Competition gap | 3 | No one combines trader classification, TFSA risk, and CCPC math on 2026 data. Generic calculators cover most of it. |
| Distribution | 3 | Reddit and GitHub are cheap. No loop. |
| Timing | 3 | 2026 rate changes and high retail volume help. Nothing forces a purchase now. |
| Founder fit | 3 | Repo proves build skill. No stated tax credential or trader audience. |
| **Total** | **19/35** | Significant concerns. |

## What OpenBB adds, and what it costs

- It is not a differentiator. Free yfinance prices are one `pip install` away for anyone, and price history does not compute realized P&L or tax.
- yfinance is not affiliated with Yahoo, and its README says the Yahoo Finance API is "intended for personal use only" ([yfinance](https://github.com/ranaroussi/yfinance)). Fine for a local tool the user runs; not a data source you can resell or host.
- Licenses are split. Checked in the installed 2.0 packages on 2026-10-13: `openbb-core` and `openbb-equity` are Apache-2.0, but the `openbb-yfinance` provider Token uses is AGPL-3.0-only (an earlier [AGPL change post](https://www.openbb.co/blog/license-change-openbb-platform-goes-agpl) is out of date for core). Local use is fine. A paid hosted Token that bundles the yfinance provider would have to release its source.
- Its real value is distribution: about 69.5K GitHub stars ([gittrend.io](https://gittrend.io/repo/OpenBB-finance/OpenBB)) of technical traders. A "Canadian trader tax" OpenBB extension listed in that community is a cheaper channel than Reddit.
- The install is a few hundred MB (repo's `docs/openbb_setup.md`). For non-coding traders, it is a barrier, not a feature. Keep it optional.

## Validation experiments

**1. Will traders pay for a plan, not a calculator?**
- How: Landing page with the repo's Alberta $150K example and a "Get my 2026 trader tax plan" button, split between $19 and $49 a year. Collect a refundable $5 deposit through Stripe. Post the province table to r/CanadianInvestor and r/PersonalFinanceCanada. Spend $100 on Reddit ads targeted to Canada.
- Success: 500 or more visitors, 3% or more click a price, 10 or more paid deposits.
- Time and cost: 7 days, $100.

**2. Is the segment as small as estimated?**
- How: A 4-question Google Form posted to the same subreddits plus r/Daytrading and the Bear Bull Traders forum: province, 2025 trading profit band, filed as business income or capital gains, considered incorporating.
- Success: 150 or more Canadian responses, 15% or more report over $30K profit. Also count how many filed business-like trading as capital gains: that is the bigger, more frightened market.
- Time and cost: 10 days, $0 to $50 in a gift card draw.

**3. Will CPAs pay for incorporation-ready traders?**
- How: Find 20 Canadian CPAs who write about trader or day-trader tax. Email each a one-page sample "incorporation readiness report" generated from the repo and offer $150 per qualified referral (trader over $100K profit who has run the calculator).
- Success: 3 or more agree in writing to the referral fee.
- Time and cost: 2 weeks, $0.

## The honest verdict

**Pivot it.** Keep Token free and open; it is the credibility engine. Change who you sell to and what you sell:

1. Widen the user from "$30K to $250K profit" to the estimated 3.4M active DIY traders, with one hook they all fear: "Is my trading business income, and is my TFSA at risk?" CRA audits TFSAs it sees as carrying on a trading business ([Globe and Mail](https://www.theglobeandmail.com/business/article-day-trading-tfsa-income-taxable)). That is the free top of the funnel.
2. Make the paying customer the trader-focused CPA, who buys qualified incorporation leads. One CCPC client is worth $2,000 to $5,000 a year in accounting fees (repo's `docs/incorporation_checklist.md`), so a $150 referral fee is easy to justify.
3. Treat OpenBB as a distribution channel (an extension in its community), not a core feature, until Token computes P&L from broker exports.

This week: run experiment 3. If no CPA will pay for a lead, the remaining path is a free open-source project with a donation button, and you should decide that before building the P&L importer.

Founder fit question: do you hold a CPA or tax credential, or have an audience of Canadian traders? Either one moves founder fit to 4 or 5.

Saved to `founder/validate-idea.md`. Next: `/founder:competitor-matrix`, `/founder:pricing-strategy`.
