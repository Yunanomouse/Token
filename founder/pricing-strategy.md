<!-- /founder:pricing-strategy · 2026-10-13 · input: Token. Who pays: Canadian active traders ($30K to $250K profit) and possibly trader-focused CPAs via referral fees. Pricing idea: core stays free and open source; maybe a paid planner tier around $19 to $49 a year. -->

# Pricing strategy: Token

Assumption: prices are in CAD, because the Canadian tax tools in `founder/competitor-matrix.md` quote CAD.
Assumption: nothing paid launches until experiment 1 (10 paid deposits) and experiment 3 (3 CPAs agree in writing) in `founder/validate-idea.md` pass. Until then Token is free with a donation link.
Assumption: no market data in any tier. OpenBB is cut from the MVP (`founder/mvp-scope.md`).

**Your pricing idea is half right.** $19 to $49 a year is the right range, because the anchors next to it are Wealthsimple Tax Plus at $40 and AdjustedCostBase.ca Premium at $49. What is wrong: a paid tier on top of an open repo sells nothing if it gates code anyone can clone. Daniel, your primary persona, will run the free CLI and never pay. The planner buyer is Jenna, who will not install Python, so the paid tier must be the hosted, no-install version plus reminders. And the trader side tops out near $83K ARR (`founder/validate-idea.md`), so CPA referral fees are the second revenue line, not an afterthought.

## 1. Pricing model analysis

| Model | Fit score | Pros | Cons |
|-------|-----------|------|------|
| Flat subscription | 3 | Simple, predictable | Tax decision is yearly; monthly churn after April |
| Usage-based | 1 | Ties to uploads | Users upload 4 to 12 times a year; too small to meter |
| Per-seat | 1 | Fits CPA firms later | Traders are one person |
| Freemium (open core plus hosted paid) | 5 | Free repo is the credibility and Reddit funnel; paid is convenience the repo cannot give | Most users never pay; needs a clear gate |
| Credits | 1 | None for this use | Confusing for a once-a-year task |
| One-time purchase | 3 | Matches the single incorporation moment | No revenue in year 2; no reason to return monthly |

**Recommend freemium (open core):** free local CLI with every calculation, a hosted Planner sold annually, and a CPA referral fee. Because the open repo is the trust signal for a tax tool, and hosting plus reminders is the only thing a non-coder cannot get by cloning it.

## 2. Tier design

### Open (free, local CLI): $0

- 2026 tax data, all 14 jurisdictions, JSON and CSV
- Sole prop vs max RRSP vs CCPC calculator
- Questrade and IBKR import, unlimited trades, runs on your machine
- TFSA/FHSA and business-income warnings (2 rules)
- Excel workbook output
- YTD tax and instalment estimate in the terminal (week 3 of the MVP)

**Hook:** your real profit and the three-scenario table in under 5 minutes. **Upgrade trigger:** you cannot or will not run Python, or you want the instalment number without rerunning a script each quarter.

### Planner: $5/mo or $39/yr (35% annual discount)

- Browser upload of a Questrade or IBKR export, no install
- Raw export deleted after parsing; only yearly totals stored
- YTD tax and instalment estimate, unlimited uploads, 1 person, up to 3 accounts
- Email reminder 14 days before each quarterly instalment date
- One-page CPA-ready PDF: profit, warnings, three scenarios, "estimate, not tax advice"
- 2 tax years of history stored

**Why the jump:** it replaces the install and the "guess and hope" set-aside (Jenna's pain). **Gated here:** hosting, reminders, PDF. No calculation is gated. **Upgrade trigger:** profit passes $100K and the calculator shows CCPC deferral larger than the $2,000 to $5,000 setup cost.

### CPA Partner (paid by CPAs, sales-led): $150 per qualified intro, or 10 intros prepaid for $1,200/yr (20% discount)

- Listed for one province in the "talk to a CPA" step
- Intro only when the trader opts in, with profit over $100K
- Receives the trader's PDF summary with consent
- Maximum 10 intros a month per CPA
- $0 to join, no monthly fee until volume exists

**Why sales-led:** 20 named CPAs emailed one by one (experiment 3). **Upgrade trigger for the CPA:** more than 5 intros a month, then a prepaid block. Check the rules first: CPA codes restrict commissions; CPA Ontario's guidance on Rule 216 ([CPA Ontario](https://assets.cpaontario.ca/members/regulations-guidance/pdfs/pas-commission-similar-compensation.pdf)) and CPABC's equivalent ([CPABC](https://www.bccpa.ca/kbase/kbase-search/practice-management/cpabc-code-of-conduct/guidance/payment-or-receipt-of-commissions)) describe written disclosure to and consent from the client. Disclose the fee to every trader on the intro screen. [Each partner CPA's confirmation that their provincial body allows the fee]

## 3. Competitive pricing context

Prices reused from `founder/competitor-matrix.md`, checked 2026-10-13.

| Competitor | Price | Included | Token Planner sits |
|---|---|---|---|
| [Wealthsimple Tax](https://www.wealthsimple.com/en-ca/tax) | $0 / $40 / $80 | Filing; Pro adds expert help | At Plus ($39 vs $40), because Token plans and WS files. Complements, not replaces |
| [TurboTax Self-Employed](https://wealthnorth.ca/taxes/tax-software/turbotax-canada-review/) | About $49.99 (third-party) | T2125 filing | Below, because Token does not file |
| [AdjustedCostBase.ca](https://www.adjustedcostbase.ca/) | $0 / $49/yr | ACB, broker import | Below, because ACB.ca has years of trust |
| [TraderSync](https://www.stockbrokers.com/review/tools/tradersync) | US$29.95 to $79.95/mo | Journal, analytics | Far below, because Token is not a journal |
| [CPA return](https://wealthnorth.ca/taxes/filing/when-to-hire-accountant-vs-diy-taxes/) | $200 to $500 | Human filing | Far below; the PDF makes that visit shorter |

## 4. Unit economics check

**Free tier:** $0. Runs on the user's machine; landing page on GitHub Pages at $0 (`founder/mvp-scope.md`).

**Planner fixed cost per month:**
- Hosting: one Fly.io shared-cpu-1x 1GB machine at US$6.70 plus a 1GB volume at US$0.15 = US$6.85 ([Fly.io](https://docs.fly.io/about/pricing)). Estimate: × 1.38 CAD = $9.45.
- Estimate: email sending $0 to $15. Not confirmed.
- Estimate: fixed total about $25/mo, $300/yr.
- [Errors and omissions insurance quote for a tax-estimate tool]. This could be the largest cost.

**Planner variable cost per user per year:**
- Stripe: 2.9% + $0.30 per payment ([Stripe](https://stripe.com/en-ca/pricing)). Annual: $39 × 2.9% + $0.30 = $1.43. Monthly: ($5 × 2.9% + $0.30) × 12 = $5.34.
- Estimate: support 15 minutes a year at $40/hr = $10.

| Tier | Revenue/yr | Variable cost | Gross margin | Break-even on $300 fixed |
|---|---|---|---|---|
| Open | $0 | $0 | n/a | n/a |
| Planner annual | $39 | $11.43 | 71% | 300 / 27.57 = 11 customers |
| Planner monthly | $60 | $15.34 | 74% | 300 / 44.66 = 7 customers |
| CPA intro | $150 | Estimate: $20 (30 min handling) | 87% | 300 / 130 = 3 intros |

**Target blended ARPU (trader side):** Estimate 85% annual, 15% monthly: 0.85 × $39 + 0.15 × $60 = $42 a year per paying trader.

**The ceiling, stated plainly:** 8,500 segment × 20% paying × $42 = $71K ARR (estimate from `founder/validate-idea.md`). Each CPA intro equals about 4 Planner subscriptions, so 200 intros a year ($30K) matters as much as 700 subscribers.

**AGPL and data:** the hosted Planner must not include `openbb-yfinance` (AGPL-3.0-only), or the hosted source must be released. Add a build check that fails if it appears. yfinance is "for personal use only" ([yfinance](https://github.com/ranaroussi/yfinance)), so no hosted price data, ever. Also: the repo has no LICENSE file (checked 2026-10-13), so it is not legally open source yet. Pick one before charging, because it decides whether a competitor may host your code.

## 5. Pricing psychology

1. **Anchoring:** the anchor is the CPA, not a tier. Put "$200 to $500 per return" and "$31,203 CCPC deferral at $150K in Alberta" next to $39, because both make $39 look small.
2. **Decoy:** the $5/mo option exists to sell $39/yr. Show "$60 billed monthly" beside it, because a once-a-year decision rarely justifies monthly billing and the 35% gap pushes buyers to annual.
3. **Annual framing:** "$39 a year, less than 20% of one self-employed return at a CPA ($39 / $200)."

## 6. Launch pricing vs. scale pricing

- **Launch (first 90 days after the experiments pass):** Founding Planner at $19/yr for the first 100 buyers, because the hosted version will be rough and you need 25 real imports (product brief KPI) more than revenue. Run experiment 1's $19 vs $49 split first: if $49 converts at two thirds or more of $19's rate, set the scale price at $49 instead of $39.
- **CPA launch:** first 3 partners pay $100 per intro for 6 months, because they are testing your lead quality.
- **Grandfathering:** founding buyers keep $19 for as long as they renew without a gap. Everyone else gets 60 days' email notice before any increase.
- **Raise the Planner price when:** free-to-Planner conversion among browser uploaders stays above 5% for 2 months, or renewal after the first April is above 75%.
- **Raise the CPA fee to $250 when:** partners report 30% or more of intros became CCPC clients, or 3 or more CPAs are waiting for one province.
- **Stop selling the Planner if:** fewer than 11 paying customers by 2027-04-30, the fixed-cost break-even. Keep Open free either way.

Saved to `/home/user/Token/founder/pricing-strategy.md`. Next: `/founder:landing-page`, `/founder:go-to-market`.
