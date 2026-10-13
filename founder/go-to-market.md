<!-- /founder:go-to-market · 2026-10-13 · input: Token, Canadian active-trader tax toolkit. Stage: pre-launch, public GitHub repo, no users yet. Launch target: before the 2027 tax season (RRSP deadline early March 2027, filing April 30 2027). -->

# Go-to-market: Token

Assumption: the MVP in `founder/mvp-scope.md` (Questrade and IBKR import, two guardrails, scenario table, no OpenBB) ships in about 2.5 weeks, so launch day is Tuesday, January 12, 2027.
Assumption: Token stays free with a donation link until the experiments in `founder/validate-idea.md` pass (`founder/pricing-strategy.md`).
Assumption: the founder is solo with $0 to $500 a month.

**The dates that drive this plan.** The RRSP deadline for the 2026 tax year is March 1, 2027, the 60th day of the year ([WealthNorth](https://wealthnorth.ca/taxes/filing/rrsp-season-2027/)). Tax owed is due April 30, but self-employed filers, which business-income traders are, file by June 15 ([CRA, 2025 tax year dates](https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/important-dates-individuals.html)). A January launch gives traders 7 weeks to act on the RRSP number, which is the most actionable result Token shows.

## 1. Launch readiness check

**Minimum to launch:** the "Must work" list in `founder/mvp-scope.md`, plus a LICENSE file (the repo has none, per `founder/pricing-strategy.md`) and the OpenBB guide either fixed or marked optional. Launching with a broken guide in a public repo costs trust on Hacker News.

**Enough people to reach?** Yes for awareness, thin for buyers. r/PersonalFinanceCanada has about 1.9M members and r/CanadianInvestor about 668K ([GummySearch](https://gummysearch.com/r/PersonalFinanceCanada/), [GummySearch](https://gummysearch.com/r/CanadianInvestor/); counts from before GummySearch closed in November 2025). The paying segment is an estimated 8,500 people (`founder/validate-idea.md`).

**Biggest risk:** a wrong number. If the imported profit is off by more than 2%, nobody trusts the CCPC answer, and one bad screenshot on Reddit ends the launch. Get 5 real exports checked before January (see budget).

## 2. Pre-launch (December 2026)

**Where the audience gathers** (sizes from [GummySearch](https://gummysearch.com/r/algotrading/), pre-November 2025):

| Community | Size | Who | Use |
|---|---|---|---|
| [r/PersonalFinanceCanada](https://www.reddit.com/r/PersonalFinanceCanada/) | ~1.9M | Jenna | TFSA and "is this business income" questions |
| [r/CanadianInvestor](https://www.reddit.com/r/CanadianInvestor/) | ~668K | Daniel, Jenna | Canadian tax implications are on topic ([Finder](https://www.finder.com/ca/stock-trading/what-are-the-top-stock-discussion-forums)) |
| [r/algotrading](https://www.reddit.com/r/algotrading/) | ~1.9M | Daniel | Open-source tools welcome; proprietary links and referral posts are not ([wiki mirror](https://r.datuan.dev/r/algotrading/wiki/index)) |
| [r/Daytrading](https://www.reddit.com/r/Daytrading/) | ~5.2M | Daniel, Tyler | Mostly US; use only for the Canadian survey |

Reddit blocked rule checks from this session. Read each sidebar before posting. [Each subreddit's current self-promotion rule, checked the day you post]

**Posts before launch:**
1. r/PersonalFinanceCanada, early December: "What a $50K, $150K and $300K trader keeps in each province, 2026" table as a text post, numbers in the body, no link in the title.
2. r/CanadianInvestor: the TFSA day-trading explainer, citing the Tax Court's *Ahamed* decision that frequent TFSA trading was a business ([Globe and Mail](https://www.theglobeandmail.com/business/article-day-trading-tfsa-income-taxable)).
3. r/PersonalFinanceCanada and r/Daytrading: experiment 2's 4-question survey. Promise to publish results; that post is your launch-week content.
4. r/algotrading: "How I parse Questrade exports into round-trip trades" with the code. Engineering, not pitch.
5. Founder's LinkedIn: the province table, tagged for CPAs (see launch day).

**Waitlist: yes, one field.** Reason to join: "Get your sole prop vs RRSP vs CCPC result on January 12, seven weeks before the March 1 RRSP deadline." Use a GitHub Pages form or a pinned GitHub Discussion.

**Assets**
- Landing page: run `/founder:landing-page`. Must have the Alberta $150K table ($9,720 RRSP gap, $31,203 CCPC deferral), "runs on your machine, no broker login", and "estimate, not tax advice" above the fold.
- Demo: a 60-second terminal recording (asciinema or GIF in the README): clone, import a sample Questrade file, see the three-scenario table. Use a fake sample file only.
- Social proof without customers: the 5 paid export testers. Ask each for one line. [Quote from an export tester on whether Token matched their own P&L]. A CPA review line once experiment 3 lands. [Name and firm of a CPA who reviewed the Alberta example]

## 3. Launch day: Tuesday, January 12, 2027

Three platforms fit. Product Hunt and X do not: Product Hunt reaches a global startup audience, not Canadian traders, and X mainly reaches Tyler, the lowest-paying persona.

**Hacker News (Show HN).** It qualifies: users can try it without signups, and you built it ([Show HN rules](https://news.ycombinator.com/showhn.html)). The repo is the link, never a landing page.
- Title: "Show HN: Token, a local Canadian trader tax calculator (sole prop vs RRSP vs corp)"
- First comment: why you built it, what it reads, what it does not do (file returns, options), the disclaimer.
- Comments: answer every one for 6 hours. Thank critics of the tax logic and open a GitHub issue for each. Don't ask friends to upvote; the rules forbid it.

**Reddit.** r/CanadianInvestor and r/PersonalFinanceCanada, two days apart, never cross-posted the same hour.
- Format: "I built a free tool that reads your Questrade/IBKR export and shows your 2026 tax as sole prop, max RRSP, or corp. Here's what it says for $50K, $150K, $300K." Table in the body, disclose you built it, GitHub link at the end or in a comment if the sidebar requires.
- Reply to every comment in the first 3 hours.

**LinkedIn (B2B, for CPAs).** Post Tuesday morning Eastern: the Alberta table, one paragraph on the incorporation question, "I'm looking for 3 trader-focused CPAs to review it." Message the 20 CPAs from experiment 3 with the post link the same day.

## 4. Post-launch growth (January to April 2027)

**Channel ranking**

| # | Channel | CAC | Time to results | First action this week |
|---|---|---|---|---|
| 1 | Reddit worked-number posts | Estimate: $0 to $5 (3 hours per post, 50+ users) | Same day | Draft the province table from the repo JSON |
| 2 | Trader-focused CPA referrals | Estimate: $20 to $60 per user (`founder/product-brief.md`) | 4 to 8 weeks | Send experiment 3's 20 emails |
| 3 | Search content (below) | Estimate: $0, 4 to 6 hours per article | 2 to 4 months, so start now | Publish "Is day trading income taxable in Canada?" |
| 4 | Show HN and GitHub | Estimate: $0 | One day, then a long tail | Add the README demo GIF |
| 5 | Deadline emails to the waitlist | Estimate: $0 | Per deadline | Write the February RRSP reminder |

**Content** (each one ends with a link to the calculator):
1. "Is day trading income taxable in Canada? Business income vs capital gains." Publish on GitHub Pages, cut into a Reddit answer each time the question comes up.
2. "Day trading in a TFSA: what the Ahamed case means." Pages, then r/PersonalFinanceCanada.
3. "Should I incorporate my trading? The $150K Alberta math." Pages, LinkedIn, and the CPA emails.
4. "How much RRSP room does trading profit create?" Publish early February for the March 1 deadline.
5. "CRA instalments for traders: what to pay March 15." Instalment dates are March 15, June 15, September 15, December 15 ([Questrade](https://www.questrade.com/learning/accounts-taxes/cra-tax-installments)). Republish before each date.

**Communities to join:** [r/CanadianInvestor](https://www.reddit.com/r/CanadianInvestor/), [r/PersonalFinanceCanada](https://www.reddit.com/r/PersonalFinanceCanada/), [r/algotrading](https://www.reddit.com/r/algotrading/). Answer 3 tax questions a week without links for 2 weeks before your first post.

**Partnerships:**
1. Trader-focused CPAs: free review of the Alberta example in exchange for a credit line, then the referral fee in `founder/pricing-strategy.md`.
2. AdjustedCostBase.ca: it serves capital-gains investors, Token serves business-income traders. Offer a mutual "wrong tool? try this one" link. [Reply from AdjustedCostBase.ca]

**Product-specific tactic:** a "classification check" command that prints, from the user's own export, "your trade count and holding period look like business income". Every Reddit thread asking "am I a day trader?" gets a reply with the one-line command.

### The OpenBB channel: verdict

**Don't build an OpenBB extension. Spend 5 minutes, not 5 days.** `founder/validate-idea.md` called it cheaper than Reddit. It is not, for four reasons:

1. **No listing exists to get into.** The ODP extensions page says anyone can publish an extension to PyPI and lists only OpenBB's own packages, with no community table ([OpenBB docs](https://docs.openbb.co/odp/python/extensions), updated 2026-09-29). The curated list, [awesome-openbb](https://github.com/openbq-org/awesome-openbb), has 25 Workspace apps and agents, no Python extension category, and no contributing guide.
2. **It rebuilds what you cut.** An extension depends on `openbb-core`, the 730MB to 1.2GB install and split licensing that `founder/mvp-scope.md` removed.
3. **The steward's plans are silent on this.** Since 2026-10-01 the non-profit OpenBQ holds the code, but the announcement gives no plan for extensions, Discord or package maintenance ([OpenBB blog](https://openbb.co/blog/openbb-belongs-to-everyone)). The code is not abandoned: commits landed on 2026-10-12 and V5 shipped 2026-09-29 ([GitHub](https://github.com/OpenBB-finance/OpenBB/commits/develop)).
4. **Wrong audience share.** 74K stars ([openbq-org](https://github.com/openbq-org)) are global quants and analysts. Canadian business-income traders are an unknown slice, and none of the three personas adopts Token for OpenBB (`founder/persona-gen.md`).

**Do:** add the `openbb` GitHub topic, which OpenBB's community page names as the way to be featured ([OpenBB](https://my.openbb.co/app/sdk/community-projects); whether anyone still curates it is unknown), and keep the fixed optional guide. **Revisit when** OpenBQ publishes an extension listing process, or 10 users ask to mark open positions at December 31.

## 5. Launch metrics (day 30 = Feb 11, day 60 = Mar 13, day 90 = Apr 12)

| Metric | Day 30 / 60 / 90 | Tool | If below target |
|---|---|---|---|
| GitHub stars | 60 / 110 / 150 | GitHub Insights | Post the repo in a technical channel (r/algotrading, Show HN follow-up) |
| Unique repo cloners | 80 / 150 / 250 | GitHub Traffic tab (14-day window, log it weekly) | Shorten the README to one command above the fold |
| Opt-in feedback forms completed | 15 / 35 / 60 | Google Form | Move the form link into the CLI output |
| Imports matching user's own P&L within 2% | 8 of 10 / 20 of 25 / 25 of 30 | Feedback form question | Stop marketing, fix parsers |
| CPAs agreeing to review or refer | 1 / 3 / 5 | Spreadsheet | Switch the paying-customer bet back to traders, per `founder/validate-idea.md` |

These are estimates scaled from the product brief's 90-day KPIs. For a full setup, run `/founder:metrics-dashboard`.

## 6. Budget ($0 to $500 a month)

| Item | Monthly | Free or paid |
|---|---|---|
| Reddit, HN, LinkedIn, GitHub Pages, Google Form | $0 | Free; your time is the cost |
| Export testers | $100 once (December) | Paid |
| Experiment 1 Reddit ads | $100 once | Paid, only after launch |
| Interview gift cards | $300 over 2 months (`founder/user-interviews.md`) | Paid |
| Domain | Estimate: $15 to $25 a year | Optional |

Don't pay for Product Hunt promotion, X ads or newsletter sponsorships.

**Best spend under $200: $100 for 5 export testers at $20 each.** Recruit coders through r/algotrading who send a real 2025 Questrade or IBKR export with account numbers removed. It tests the biggest risk (a wrong number), produces the only honest social proof you can have before launch, and gives you real files for regression tests. A wrong import found in December costs $20; found on launch day, it costs the launch.
