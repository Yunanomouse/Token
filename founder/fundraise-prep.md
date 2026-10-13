<!-- /founder:fundraise-prep · 2026-10-13 · input: Token. Stage: pre-launch, no users, no revenue. Country: Canada. Raise amount: not decided. -->

# Fundraise prep: Token

Assumption: the founder is solo and part-time. [Confirm team size and hours per week]
Assumption: Token is not incorporated yet. Nothing in `founder/facts.md` says it is. [Confirm: incorporated or not, and in which province]
Assumption: launch is January 12, 2027 and no raise is planned in the next 6 months, as in `founder/metrics-dashboard.md`.
Assumption: the founder is Canadian and based in Alberta, because the repo's worked examples use Alberta. [Confirm province and age, which matter for Futurpreneur]

**Short answer: do not raise equity now, and probably not from venture funds at all.** The saved estimates put the trader-side ceiling at $71K to $83K ARR (`founder/pricing-strategy.md`, `founder/validate-idea.md`). Adding 200 CPA intros a year at $150 ($30K) gives Estimate: about $100K to $113K ARR. Reaching $1M ARR at $49 would need 20,400 payers, more than twice the estimated 8,500-person segment. That is a good bootstrapped business if the experiments pass. It is not a venture-scale outcome, and an investor will do this same arithmetic in the first meeting.

## 1. Readiness assessment

| Dimension | Score | What investors want to see | The gap |
|---|---|---|---|
| Traction | 1 | Pre-seed: idea and team, plus signs of demand | 0 users, 0 revenue, 0 verified imports. The three experiments in `founder/validate-idea.md` have not run. |
| Team | 2 | Full-time, technical, domain experience | Repo shows build skill. Solo, hours unknown, no stated tax credential or trader audience. |
| Market | 1 | Big enough for venture returns | Estimate: about 8,500 paying-segment traders. Ceiling about $71K to $83K ARR on the trader side. |
| Product | 2 | Working MVP, feedback, retention | Calculator and tax data exist. Broker import, YTD tracker and hosted Planner do not. OpenBB quickstart broke once. |
| Unit economics | 2 | CAC, LTV, margin, even rough | Margin estimates exist (71% to 87%, `founder/pricing-strategy.md`). CAC and conversion are guesses. |
| Story | 3 | 30 seconds that makes someone care | "A $150K Alberta trader defers $31,203 through a CCPC" is sharp. The market-size answer undercuts it. |

**Verdict: too early, and the market may never fit venture capital.** Not "1 to 3 more months." What to do first:

1. Run experiment 3 (20 CPAs, referral fee) this month. If 3 or more agree in writing, the CPA line is real.
2. Run experiment 1 (landing page, $19 vs $49 deposits). Pass line: 10 paid deposits.
3. Get 5 of 5 verified imports before January 12.
4. Then decide: bootstrap, or a small angel round only if the market looks bigger than estimated.

## 2. Round size and terms

**Recommended now: $0 of equity.** Fund the next 6 months with founder time, revenue from the Planner and CPA intros, and non-dilutive money.

### Non-dilutive options in Canada

| Program | What it offers | Fit for Token today |
|---|---|---|
| NRC IRAP | Advice and funding for R&D of technology-driven products. Must be incorporated, for-profit, in Canada, up to 500 FTE. Sole proprietorships are not eligible. Does not fund day-to-day operating costs or purely commercial activity ([NRC](https://nrc.canada.ca/en/support-technology-innovation/financial-support-technology-innovation)). Cost-share rates: not shown on the official page; third-party guides disagree ([Avinova](https://www.avinova.ca/en/blog/nrc-irap-program-guide)) | Weak now. Needs a corporation and a technical R&D project. A reliable multi-broker parser with FX and options could be framed as one. Ask an IRAP advisor before spending on incorporation. |
| SR&ED | 35% refundable credit on qualified current expenditures for most CCPCs, up to an expenditure limit; 15% above it ([CRA](https://www.canada.ca/en/revenue-agency/services/scientific-research-experimental-development-tax-incentive-program/sred-claim/investment-tax-credit.html)). Budget 2025 proposes raising the limit to $6M for years starting on or after December 16, 2024 ([Budget 2025](https://budget.canada.ca/2025/report-rapport/tm-mf-en.html)). Routine data collection and routine testing are excluded ([CRA](https://www.canada.ca/en/revenue-agency/services/scientific-research-experimental-development-tax-incentive-program/sred-eligibility.html)) | Likely small. Applying published tax rates and parsing CSVs is mostly routine engineering. Only work with real technical uncertainty counts. Also needs a CCPC. Estimate: on $20,000 of eligible salary, 35% = $7,000 back. |
| Futurpreneur startup loan | Up to $75,000 collateral-free financing with mentorship, announced September 2024 ([Futurpreneur](https://futurpreneur.ca/en/?p=10931)). Third-party guide: ages 18 to 39, business operating 24 months or less, Futurpreneur up to $25,000 plus BDC up to $50,000 ([GrantCompass](https://grantcompass.ca/grants/futurpreneur-canada-startup-program)) | Possible, but it is debt. Do not borrow before experiments 1 and 3 pass. |

### If triggers hit later: a small angel round

Raise only if, by about April 30, 2027: 10+ paid deposits, 3+ CPAs paying, 5 of 5 verified imports, and evidence the market is bigger than 8,500 (for example, experiment 2 shows far more traders over $30K, or a wider product such as the TFSA-risk hook converts).

- **Amount:** [Raise amount, not decided]. Estimate: size it to 12 to 18 months of one founder's salary plus about $300/yr fixed costs and an E&O insurance quote [E&O quote]. Example only: $100K to $150K.
- **Instrument:** post-money SAFE with a valuation cap, no discount, and an MFN clause. Carta reports 93% of pre-seed rounds used SAFEs in Q2 2026 and about 91% of SAFEs were post-money ([Carta, Q2 2026](https://carta.com/data/safe-valuation-caps-q2-2026/)).
- **Valuation range:** Carta's Q2 2025 median cap for SAFE rounds under $250K was $7.5M ([Carta, Q2 2025](https://carta.com/data/state-of-pre-seed-q2-2025/)). Average pre-seed instrument size was $276,000 in Q2 2026 ([Carta, Q2 2026](https://carta.com/data/state-of-pre-seed-q2-2026/)). Canada-specific, fintech-specific caps for the last 12 months: Not found. Carta data skews to US venture-backed companies, and those caps assume a venture-scale market Token does not have. Expect angels to offer well below the median.
- **Runway:** 12 to 18 months.
- **Dilution:** Estimate: $150K on a $5M post-money cap = 3%. $150K on $3M = 5%.

## 3. Investor targeting

Venture funds are the wrong buyer at a $71K to $113K ceiling. If you raise, target people who value a profitable niche.

**Investor profile**
- Fund stage: angels and pre-seed only. No seed funds.
- Check size: $10K to $50K each.
- Sector: Canadian fintech, wealth, tax and accounting.
- Geography: Alberta and Ontario first.
- Hands-on: yes. You need CPA intros and liability advice more than money.

**Target list framework (only after the triggers above)**
- Tier 1 (10): trader-focused CPAs, accountants and tax lawyers who write about trader tax, and fintech operators from Canadian brokers. They understand the problem and can refer users.
- Tier 2 (20): Canadian fintech angels and angel groups with a record of small cheques.
- Tier 3 (20): pre-seed funds with Canadian fintech deals. Use as practice and for feedback, expect "too small."

Example fund with a linkable recent Canadian fintech deal: **Conexus Venture Capital** led Cyder's C$3M seed in January 2026, a loyalty platform for credit unions ([Fasken](https://www.fasken.com/en/experience/2026/01/cyder-raises-c$3-million-in-seed-financing-to-grow-loyalty-platform)). That is seed, not pre-seed, so it is a Tier 3 fit at best. I could not link a 2026 Canadian pre-seed fintech lead investor, so no other funds are named.

**Where to find investors**
- Databases: OpenVC and Signal by NFX (free), Crunchbase. Filter for Canada, fintech, pre-seed.
- Warm intros that work for this product:
  1. The 20 CPAs in experiment 3. Ask each paying CPA: "Which clients of yours angel invest?"
  2. Reddit and GitHub users who run a verified import and reply. Some traders netting $150K+ are angels. Ask once, after they have used it.
  3. Publish the yearly province table and send it to Canadian fintech newsletters. Reply threads produce intros.

## 4. Materials checklist

| Material | Status needed | Priority | Today |
|---|---|---|---|
| Pitch deck (10 to 12 slides) | Polished | Must have | In progress (`founder/pitch-deck.md`) |
| One-pager | Polished | Must have | [Not started] |
| Financial model (24 months) | Draft | Should have | [Not started]. Show the $71K to $113K ceiling honestly. |
| Data room | Organized | Should have | [Not started] |
| Product demo | Working | Must have | Calculator works; import missing |
| Customer references | 2 to 3 ready | Nice to have | [Beta user quote about the verified import] |
| Cap table | Clean | Must have | [Incorporation status and share structure] |
| LICENSE file in the repo | Chosen | Must have | Done 2026-10-13: MIT |
| IRAP advisor call notes | Done | Should have | [Not started] |

## 5. Timeline

The 12 weeks below replace the raise timeline. A raise only starts after week 12 if the triggers in section 2 are met.

- **Weeks 1 to 2:** email 20 CPAs (experiment 3). Launch the $19 vs $49 deposit page (experiment 1). Request an IRAP advisor call to ask whether a broker-import parser is fundable and whether to incorporate first.
- **Weeks 3 to 4:** first export testers. Log what is technically uncertain in the parser (FX, options, corporate actions) with dates and hours, in case SR&ED applies later.
- **Weeks 5 to 6:** survey (experiment 2). Decide on a LICENSE.
- **Weeks 7 to 8:** decide on incorporation with a CPA, based on experiment 3 and the IRAP answer.
- **Weeks 9 to 10:** 5 of 5 verified imports. Draft the 24-month model with real deposit and CPA numbers.
- **Weeks 11 to 12:** go or no-go. Bootstrap, apply for Futurpreneur or IRAP, or start the angel raise using the skill's 12-week plan (Tier 3 first as practice, then Tier 2, then Tier 1).

## 6. Mistakes to avoid

1. **Raising venture money for a niche market.**
   - Why: a seed round feels like proof.
   - Instead: a $100K-ARR business with no investors is a good outcome. With a VC on the cap table, it is a failure.
2. **Incorporating just to qualify for IRAP or SR&ED.**
   - Why: the credit looks like free money.
   - Instead: ask an IRAP advisor first. Upkeep is $2,000 to $5,000 a year (repo estimate), more than a small SR&ED refund.
3. **Pitching the 3.4M active-trader number as the market.**
   - Why: it is in your own files.
   - Instead: lead with the 8,500 paying segment and how you would widen it. Investors will find the gap anyway.
4. **Skipping the liability question.**
   - Why: it is not a product feature.
   - Instead: get an E&O insurance quote before any paid launch. One wrong incorporation number costs a user thousands.
5. **Counting stars and waitlist size as traction.**
   - Why: they grow fast after Show HN.
   - Instead: show counts with denominators: verified imports, paid deposits, CPAs paying.

Saved to `/home/user/Token/founder/fundraise-prep.md`. Next: `/founder:pitch-deck` (match the market slide to this ceiling), `/founder:metrics-dashboard` (add the raise triggers).
