<!-- /founder:pitch-deck · 2026-10-13 · input: Token, Canadian active-trader tax toolkit. Stage: pre-launch. Raise: not decided. Traction: none yet. Team: [not stated]. -->

# Pitch deck: Token

Assumption: the raise amount is not decided, so slide 11 uses placeholders. Nothing here sets a number for you.
Assumption: team is not stated. The saved files assume a solo founder (`founder/product-brief.md`). Slide 10 is placeholders.
Assumption: traction is $0 revenue and 0 users. Launch is January 12, 2027 (`founder/go-to-market.md`).
Assumption: the deck is presented live on a call, so body text stays under 30 words and speaker notes carry the detail. For a sent-ahead version, move each slide's first speaker-note sentence onto the slide.
Assumption: venture is a poor fit. The saved estimates cap the trader side near $71K ARR (`founder/pricing-strategy.md`), and validate-idea scored the idea 19/35. So this deck is built for two audiences first: **trader-focused CPA partners** and **grant or non-dilutive programs**. Slide variants for each are marked "CPA version" and "Grant version". Use the investor wording only if [a reason the market is larger than 8,500 paying traders] turns up.

## Slide 1: Title

**Headline:** Token shows Canadian traders what they keep as a sole proprietor, with an RRSP, or through a corporation.

- Token. [Founder name], [title]
- Party test: "A free tool that tells active traders whether to incorporate."
- "Estimate, not tax advice"

**Visual:** wordmark over the three-scenario result table.

**Speaker notes:** "I built Token because traders find out their real tax in April, when the choices that would have saved money are already gone."

## Slide 2: Problem

**Headline:** A $150,000 Alberta trader leaves $9,720 a year on the table without a max RRSP and misses $31,203 of CCPC deferral.

- CRA taxes frequent trading as 100% business income
- TFSA day trading can make the whole account taxable
- Today: broker export, spreadsheet, Reddit, one CPA visit

**Visual:** one bar pair: tax as sole prop vs through a CCPC, $150K Alberta.

**Speaker notes:** "These numbers are from the worked example in the repo. The two expensive mistakes are filing business income as capital gains, and trading inside a TFSA. The Tax Court's Ahamed decision treated frequent TFSA trading as a business ([Globe and Mail](https://www.theglobeandmail.com/business/article-day-trading-tfsa-income-taxable)). The answers exist, scattered across CRA pages and forums, and nobody joins them to the trader's own trades."

## Slide 3: Solution

**Headline:** Token reads your broker export and shows your 2026 tax three ways in under 5 minutes.

- 2026 tax data, all 14 jurisdictions
- Sole prop vs max RRSP vs CCPC comparison
- Business-income and TFSA warnings

**Visual:** screenshot of the scenario table from a sample Questrade file.

**Speaker notes:** "It runs on the trader's own machine. No broker login leaves the computer. Every result carries the not-tax-advice line."

## Slide 4: Product

**Headline:** Three steps turn a guess into the trader's real number and a CPA-ready page.

1. Import a Questrade or IBKR export
2. See realized profit and warnings
3. Compare three scenarios
4. Export a one-page PDF for a CPA

**Visual:** before and after: a spreadsheet guess vs the PDF summary.

**Speaker notes:** "The surprise moment is step 2: 'your trade count and holding period look like business income.' Most traders have never seen that said about their own account. CPA version: step 4 is your intake form, already filled in."

## Slide 5: Market size

**Headline:** About 8,500 Canadian traders face the incorporation decision each year, and every one needs a CPA to act on it.

- TAM: 3.4M active DIY traders
- SAM: 170K with business income
- SOM: 8,500 netting $30K to $250K

**Visual:** three nested circles, each labeled "Estimate" with source.

**Speaker notes:** "Estimate, from `founder/validate-idea.md`: 32.8M adults ([Statbase](https://statbase.org/data/can-population-age-18-and-above/)) × 27% self-directed ([Investment Executive](https://www.investmentexecutive.com/news/industry/canadians-considering-diy-investing-td-survey-finds/)) × 38% trading 10 to 150 times a quarter ([Wealth Professional, 2026](https://www.wealthprofessional.ca/news/industry-news/canadian-diy-investors-push-for-advanced-tools-wealthsimple-survey-reveals/392353)) = 3.4M. Then 5% business income, then 5% in the profit band. Bottom-up: 8,500 × 20% paying × $42 = $71K ARR. Why now: 2026 rate changes, including Alberta's 8% bracket, and 2.9 million trading accounts opened in the 12 months to June 2025 ([Globe and Mail](https://www.theglobeandmail.com/business/article-questrade-suite-financial-tools-retail-investors-banks-edward)). Grant version: 3.4M people are exposed to the TFSA and classification mistake, which is the public-interest case."

## Slide 6: Traction

**Headline:** $0 revenue and 0 users today; the working tax engine and [N] verified imports are the evidence.

- Built: 14-jurisdiction data, scenario calculator
- Verified imports: [N of 5 testers within 2%]
- Qualified waitlist: [N]
- CPAs agreed: [N of 20]

**Visual:** one chart: verified imports over time, plotted weekly from October 19. No metric is growing yet, so until then show the built-vs-planned feature checklist.

**Speaker notes:** "I count imports with a denominator, never percentages of tiny bases. The North Star is verified imports: a trader's real export matching their own P&L within 2% (`founder/metrics-dashboard.md`)."

## Slide 7: Business model

**Headline:** The calculation stays free; CPAs pay $150 per qualified intro and traders pay $39 a year for the hosted Planner.

- Planner: $39/yr, 71% gross margin (estimate)
- CPA intro: $150, 87% margin (estimate)
- Break-even: 11 Planner customers

**Visual:** two revenue lines stacked: CPA intros and Planner.

**Speaker notes:** "Estimates from `founder/pricing-strategy.md`. CAC from Reddit: estimate $0 to $5. LTV: [Planner renewal rate after first April] needed before I state one. 24-month projection, estimate: launch at $19 for the first 100 buyers = $1,900, plus 3 CPA partners at the $100 launch fee × [intros per partner]. Ceiling at maturity, estimate: $71K trader side plus 200 intros a year at $150 = $30K. Nothing paid launches until the CPA and deposit experiments pass. Each partner confirms their provincial body allows a disclosed referral fee."

## Slide 8: Competition

**Headline:** Filing tools look back at last year; Token is the only tool that plans the incorporation decision for traders.

- X axis: files last year → plans next year
- Y axis: generic → trader-specific
- Token alone, top right

**Visual:** 2x2. Wealthsimple Tax and TurboTax bottom left, TraderSync and Tradervue top left, TaxTips bottom middle, Token top right.

**Speaker notes:** "Wealthsimple Tax is $0 to $80 and files; TraderSync is US$29.95 to $79.95 a month and journals with no Canadian tax ([Wealthsimple](https://www.wealthsimple.com/en-ca/tax), [StockBrokers.com](https://www.stockbrokers.com/review/tools/tradersync)). Defensibility is honest but thin: an open repo CPAs can audit, and 2026 data for all 14 jurisdictions. The threat is Wealthsimple adding an 'incorporate?' screen for its own clients. Our answer is Questrade and IBKR users."

## Slide 9: Go-to-market

**Headline:** Worked-number Reddit posts bring traders for an estimated $0 to $5 each, and CPAs turn them into revenue.

- Reddit tax tables: CAC estimate $0 to $5
- 20 trader-focused CPAs emailed
- Launch January 12, seven weeks before RRSP deadline

**Visual:** timeline: December posts, January 12 launch, March 1 RRSP deadline, March 15 instalment.

**Speaker notes:** "What's working now: [result of first Reddit province-table post]. What money changes: [what the raise or grant pays for, e.g. errors and omissions insurance, parser testing]. CPA version: you get pre-qualified traders over $100K profit who opted in and arrive with the PDF."

## Slide 10: Team

**Headline:** [One sentence on why this founder wins, e.g. tax credential or trader audience].

- [Founder name]: [relevant achievement]
- Built 14-jurisdiction 2026 tax dataset and calculator
- Key hire: [role this round pays for]
- Advisor: [trader-focused CPA name, firm]

**Visual:** founder photo, CPA advisor photo.

**Speaker notes:** "The repo shows I can build it. The gray area, active business income vs specified investment business in a trading CCPC, needs a CPA, which is why the first partner is a CPA."

## Slide 11: The ask

**Headline:** [Amount] gets Token to [milestone, e.g. 25 verified imports and 3 paying CPA partners] by [date].

- Raise or grant: [amount, instrument]
- Use of funds: [% insurance and legal], [% parser testing], [% hosted Planner], [% founder time]
- Next round or renewal: [date]

**Visual:** one bar split into the four buckets.

**Speaker notes:** "CPA version: the ask is not money. It is a written review of the Alberta example and agreement to a disclosed $100 intro fee for 6 months. Grant version: [program name and maximum amount, with link]; milestones tie to verified imports and traders warned about TFSA trading."

## Slide 12: Closing

**Headline:** Every Canadian trader should know what they keep before April, not after.

- $31,203 deferred at $150K in Alberta
- [Email], [repo link]

**Visual:** the $31,203 number alone on the slide.

**Speaker notes:** "If you remember one number, remember $31,203: one trader, one year, one decision that usually happens too late."

## Appendix

1. **Tax engine:** data sources, collected 2026-08-18 and cross-verified; how the three scenarios are computed.
2. **Alberta $150K walkthrough:** the full table behind slides 2 and 12, for CPA review.
3. **Detailed competitor table:** from `founder/competitor-matrix.md`.
4. **Liability and data:** "not tax advice" wording, exports deleted after parsing, [license chosen for the repo], [errors and omissions insurance quote].
5. **Data adapters:** optional OpenBB price history for year-end marks; not part of the core product.

## Numbers to find

- [Founder name], [title], [email], [repo link]
- [N of 5 testers within 2%], [qualified waitlist N], [CPAs agreed N of 20]
- [Result of first Reddit province-table post]
- [Planner renewal rate after first April], [intros per partner]
- [Amount, instrument], [milestone], [date], four use-of-funds percentages, [next round or renewal date]
- [Why this founder wins], [relevant achievement], [key hire], [CPA advisor name, firm]
- [Program name and maximum amount, with link]
- [Each partner CPA's confirmation that their provincial body allows the fee]
- [License chosen], [errors and omissions insurance quote]
- [A reason the market is larger than 8,500 paying traders]

## Checklist

- Every headline states a takeaway: yes
- One idea per slide: yes
- Body under 30 words: yes, numbers in notes
- Story order: problem, solution, proof, opportunity, team, ask: yes

Saved to `/home/user/Token/founder/pitch-deck.md`. Next: `/founder:fundraise-prep`, `/founder:landing-page`.
