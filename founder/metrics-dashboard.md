<!-- /founder:metrics-dashboard · 2026-10-13 · input: Token. Stage: pre-launch, no users, no revenue. Current numbers: none yet. -->

# Metrics dashboard: Token

Assumption: launch is Tuesday, January 12, 2027 (`founder/go-to-market.md`). Day 30, 60 and 90 here are Nov 12, Dec 12 and Jan 11, so this whole window is pre-launch.
Assumption: the CLI has no telemetry (`founder/email-sequence.md`). Everything is counted from GitHub, the waitlist, replies, an opt-in form, and later Planner and Stripe data.
Assumption: no raise is planned in the next 6 months.

## 1. Stage

**Pre-launch, validation.** No users, no revenue. The 90-day job is three answers before January: do traders trust the imported number, do enough have the problem, and will CPAs pay for leads.

**North Star: verified imports.** Count of traders who ran a real Questrade or IBKR export through Token and confirmed, by reply or form, that the profit matched their own records within 2%. It holds before and after launch: if it is low, nobody trusts the CCPC answer (`founder/mvp-scope.md`).

## 2. The five metrics

All current values: [none yet, first entry on Monday, October 19].

**1. Verified imports (North Star)**
- Definition: traders whose imported 2026 profit matched their own P&L within 2%, confirmed in writing, divided by traders who sent a real export.
- Target: 1 of 1 / 3 of 3 / 5 of 5 (the 5 paid export testers, $20 each, from `founder/go-to-market.md`).
- Why: decides launch or delay.
- If below: stop all posting, get the failing file, add it as a regression test, fix the parser before recruiting the next tester.

**2. Qualified waitlist signups**
- Definition: waitlist sign-ups that answered "Canadian, trades at least 10 times a quarter" on the one-field-plus-one-question form.
- Target: 25 / 100 / 250. Estimate: one December Reddit post reaching about 1,000 readers at 8% to 15% sign-up, the medium-intent range [LaunchList](https://app.getlaunchlist.com/tools/waitlist-benchmark) cites (year not shown, vendor source).
- Why: decides how big launch day can be and whether the January email list is worth writing for.
- If below: post the "What a $50K, $150K and $300K trader keeps" province table as a text post, with the waitlist link in a comment.

**3. Trader interviews completed, and how many raised incorporating**
- Definition: 25-minute interviews with traders over $50K profit (`founder/user-interviews.md`). Second number: how many have asked a CPA or forum about a CCPC.
- Target: 6 / 15 / 15 completed, with 6 or more of 15 raising incorporation (product brief pass line).
- Why: decides whether the CCPC calculator is the lead feature or the TFSA warning is.
- If below: switch to the paid fallback (Respondent or UserInterviews.com) and screen on profit band only.

**4. Segment survey responses (experiment 2)**
- Definition: Canadian responses to the 4-question form; second number: share reporting over $30K profit.
- Target: 0 / 150 / 150, with 15% or more over $30K (`founder/validate-idea.md`). It runs in December.
- Why: confirms or shrinks the 8,500-person paying segment.
- If below: add the $50 gift card draw and repost to r/Daytrading with a Canada filter question in the title.

**5. CPAs agreeing in writing to review or refer (experiment 3)**
- Definition: of the 20 CPAs emailed, the number who agree in writing to the $150 referral fee or to review the Alberta example.
- Target: 1 / 3 / 3.
- Why: decides whether the paying customer is the CPA or nobody (`founder/validate-idea.md`).
- If below by day 60: email 20 more CPAs with a 2-minute screen recording of the readiness report instead of a PDF, and drop the fee to the $100 launch rate.

**After January 12,** replace metrics 3 and 4 with unique repo cloners and opt-in forms completed, using the day 30/60/90 targets in `founder/go-to-market.md`. Once the Planner ships, add Planner paid conversions from Stripe and drop whichever metric has stopped changing decisions.

### OpenBB health: a weekly check, not a metric

It earns a single yes/no line in the weekly review, not one of the five. Reasons it is in: the guide is public, it already broke silently once (printed "Done" after every ticker failed, `founder/mvp-scope.md`), the launch criteria require it to work or say it is optional, and a broken guide on Show HN costs trust. Reasons it is not a metric: no persona adopts Token for it, and its result drives no business decision. Setup: a weekly scheduled GitHub Action that installs the pinned `openbb-core openbb-equity openbb-yfinance` 2.0.x and runs the quickstart, failing if any ticker returns 0 rows. Cost $0: Actions are free on public repos with standard runners ([GitHub Docs](https://docs.github.com/en/billing/concepts/product-billing/github-actions)). Scheduled workflows in public repos switch off after 60 days without repo activity ([GitHub Docs](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)), so the review asks "did it run?" as well as "did it pass?". If it fails twice in a row, mark the guide "currently broken" in the README the same day.

## 3. Metrics to ignore

| Metric | Why it feels important | Why it misleads | Track instead |
|---|---|---|---|
| GitHub stars | Public, rises fast after HN | Global quants star and leave; stars run no import | Verified imports |
| Reddit upvotes and post views | Instant feedback | A tax table gets upvoted by people who will never trade $30K | Qualified waitlist signups from that post |
| Total waitlist size | Looks good on the landing page | Unqualified emails inflate it and CASL limits what you can send | Qualified signups |
| Repo page views | Easy to see in Insights | Views count bots and you | Unique cloners, logged weekly |
| OpenBB ecosystem attention | 74K-star project | None of the personas comes for it | The yes/no health check |

## 4. Tracking setup

| Need | Tool | Cost | Setup time |
|------|------|------|------------|
| Product analytics (no telemetry) | GitHub Insights Traffic tab: views and clones, last 14 days only ([GitHub Docs](https://docs.github.com/en/rest/metrics/traffic)) | $0 | 10 min |
| Waitlist and feedback forms | [Tally](https://tally.so/pricing): unlimited forms and submissions on free, fair use applies | $0 | 30 min |
| Waitlist email | [MailerLite](https://www.mailerlite.com/pricing): free up to 250 subscribers, 2,500 emails a month | $0 until 250 | 1 hour |
| Revenue (later) | [Stripe](https://stripe.com/en-ca/pricing): 2.9% + $0.30 per payment | Per payment | 1 hour, after experiments pass |
| OpenBB check | GitHub Actions, scheduled | $0 | 1 hour |
| Dashboard | Google Sheet, one tab per metric | $0 | 30 min |

MailerLite's 250 cap equals your day 90 target: budget for its paid plan by December.

**Events to log** (by hand or from form exports, Monday mornings):

| Event | When it fires | What it tells you |
|---|---|---|
| `waitlist_joined` | Tally form submitted | Raw interest |
| `waitlist_qualified` | Trading-frequency answer is yes | Real target user |
| `repo_cloned` | Unique cloners, GitHub Traffic | Top of funnel, lost after 14 days unless logged |
| `export_received` | Tester sends a real export | Supply of test files |
| `import_verified` | Tester confirms match within 2% | North Star |
| `import_mismatch` | Tester reports a gap over 2% | Parser bug to fix |
| `interview_done` | Call ends, pattern table filled | Learning pace |
| `ccpc_raised` | Interviewee has asked about incorporating | Lead feature choice |
| `survey_response` | Experiment 2 form submitted | Segment size |
| `cpa_reply` | Any CPA response | Channel interest |
| `cpa_agreed` | Written yes to fee or review | Paying customer exists |
| `email_reply` | Waitlist subscriber replies | Engagement without telemetry |
| `openbb_check` | Weekly Action finishes | Guide works or not |

## 5. Weekly review template

Every Monday, 15 minutes.

```
Week of: ___
Verified imports: ___ of ___ exports (last week: ___) (target: ___)
Qualified waitlist signups: ___ (target: ___)
Interviews done: ___, raised CCPC: ___ (target: ___)
Survey responses: ___, over $30K: ___% (target: ___)
CPAs agreed: ___ of ___ emailed (target: ___)
Unique cloners, last 14 days (log it): ___
OpenBB check ran: yes / no   Passed: yes / no

What worked: ___
What didn't: ___
One thing to try this week: ___
```

## 6. Investor-ready metrics

Not needed now. If you raise later, investors at this stage ask for verified imports, waitlist-to-active conversion, and, once the Planner ships, free-to-paid conversion. The best-sourced benchmark found: a median of 8% free-to-paid across 200 software products, with 3% to 5% counted as "good" for freemium ([ChartMogul, 2026](https://chartmogul.com/reports/saas-conversion-report/)). Present early numbers as counts with denominators ("5 of 5 testers matched within 2%"), never as percentages of tiny bases, and show what each one decided.

Saved to `/home/user/Token/founder/metrics-dashboard.md`. Next: `/founder:landing-page` (add the qualifying question to the waitlist form), `/founder:email-sequence` (route replies into the `email_reply` log).
