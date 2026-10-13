<!-- /founder:email-sequence · 2026-10-13 · input: Token. Goal: onboarding. Audience: Canadian active traders who signed up on the waitlist or downloaded the open-source tool, aiming to get them to import their first broker export and later to try the Planner tier. -->

# Email sequence: Token onboarding

Assumption: the sequence starts once the import command from `founder/mvp-scope.md` ships (`requirements.txt` and `python token_cli.py import`). The repo has neither today.
Assumption: email 6 and the P.S. in email 7 go out only after the hosted Planner is live. `founder/pricing-strategy.md` holds all paid tiers until the experiments pass. Until then, point those calls to action at a Planner waitlist and drop the prices.
Assumption: people who only cloned the repo are not on any list. GitHub does not share their emails, and CASL needs their consent. They join through a README sign-up form.
Assumption: the CLI has no telemetry, so "imported" is measured by replies, the feedback form and clicks.

## 1. Sequence strategy

- **Goal:** activate. First real Questrade or IBKR import, then a Planner trial.
- **Trigger:** confirmed sign-up (waitlist or README form).
- **Length:** 7 emails over 14 days.
- **Success metric:** 25 traders who imported a real export within 90 days (product brief KPI), measured by reply or form.

## 2. The emails

Every email ends with: "Estimates, not tax advice."

**Email 1: Welcome and first import**
- **Send timing:** immediately
- **Subject:** Your 2026 trading profit in 5 minutes
- **A/B:** Drop in one broker export
- **Preview:** Questrade or IBKR export in, three tax scenarios out.

Hi [first name],

Thanks for joining Token. [One sentence, in your words, on why you built it.]

One thing to do first: run a real broker export through it. It takes about 5 minutes and nothing leaves your machine.

1. Clone the repo and run `pip install -r requirements.txt`
2. Run `python token_cli.py import activity.xlsx --province AB` with your own file and province

You'll see your realized 2026 trading profit, any warnings, and what you keep as a sole proprietor, with a max RRSP, or through a CCPC.

**Button:** Open the quickstart (README quickstart section)

P.S. Reply with your broker if it isn't Questrade or IBKR. That decides what I parse next.

Estimates, not tax advice.

**Email 2: Find the export**
- **Send timing:** day 1
- **Subject:** Getting your Questrade or IBKR export
- **A/B:** The file most traders can't find
- **Preview:** Two minutes in your broker's reports menu.

Hi [first name],

Most people stall on step one: finding the file.

**Questrade:** open Reports and export your account activity to Excel for 2026. It lists each buy and sell. Token pairs them for you.

**IBKR:** create a Flex Query for trades, set the period to 2026, output CSV. One query covers one year, which is one tax year.

Stocks and ETFs only for now. Option and crypto rows show as "skipped".

Keep that file even if you never run Token. Trade-level exports are the first record CRA asks for in a business-income audit.

**Button:** Run my first import (README quickstart)

Estimates, not tax advice.

**Email 3: The three-scenario table**
- **Send timing:** day 3
- **Subject:** What $150K of trading profit keeps
- **A/B:** Sole prop, RRSP or CCPC?
- **Preview:** The Alberta numbers, and the two catches.

Hi [first name],

Here is where the import ends, for $150,000 of 2026 trading profit in Alberta:

- Sole proprietor: $47,703 in income tax and CPP
- Max RRSP deduction ($27,000): saves $9,720
- CCPC keeping all profit inside: $31,203 more capital working now

Two catches. RRSP room is 18% of last year's earned income, capped at $33,810 for 2026. Trading profit counts as earned income, but you need the room. And the CCPC figure is a deferral, not a saving: personal tax comes due when you pay yourself, and a corporation costs $2,000 to $5,000 or more a year to run.

**Button:** See my own numbers (README quickstart)

Estimates, not tax advice. Talk to a CPA before you incorporate.

**Email 4: Two warnings**
- **Send timing:** day 5
- **Subject:** The two costliest trading tax mistakes
- **A/B:** Is your TFSA a trading account?
- **Preview:** Token checks both on every import.

Hi [first name],

The import runs two checks, because these mistakes cost the most.

1. **Filing trading profit as capital gains.** Frequent, short-hold trading is usually 100% taxable business income, not 50%-included capital gains. The election that locks in capital treatment is not available to traders.
2. **Trading in a TFSA or FHSA.** Carrying on a trading business in a TFSA makes the income taxable inside the account. Keep the TFSA for long-term holdings.

If either warning shows up for you, book an hour with a CPA now, not in April.

**Button:** Run the checks on my export (README quickstart)

P.S. [Quote from an early user about a warning the import caught]

Estimates, not tax advice.

**Email 5: Did it match?**
- **Send timing:** day 7
- **Subject:** Did Token's profit match yours?
- **A/B:** One question about your number
- **Preview:** A one-line reply helps more than you think.

Hi [first name],

One question. Your reply is the most useful thing you can send me this month.

When you imported your export, did Token's 2026 profit land within 2% of what you believe you made?

If not, I want to know why. Common causes: option or crypto rows, USD trades, or a short date range.

If you haven't run it yet, what stopped you: Python, the export, or time?

**Button:** Reply with your answer (mailto reply)

I read every reply, and they decide what I fix next.

Estimates, not tax advice.

**Email 6: Set-aside and instalments**
- **Send timing:** day 10
- **Subject:** How much to set aside from each win
- **A/B:** Nobody withholds tax on your trades
- **Preview:** About 34 cents per dollar in one Alberta example.

Hi [first name],

Nothing is withheld on trading profit. In the repo's Alberta example, $10,000 of trading profit on top of a $45,760 salary costs about 34% at the margin: income tax plus both halves of CPP. Your rate depends on income and province. The balance is due April 30.

Once you owe more than $3,000 two years running, expect CRA to ask for quarterly instalments. Interest on short payments is high and not deductible.

If you'd rather not rerun a script each quarter, the Planner does it in the browser: upload your export, no install, a year-to-date estimate, and an email 14 days before each instalment date. $5/mo or $39/yr.

**Button:** See the Planner (Planner page)

Estimates, not tax advice.

**Email 7: Recap and feedback**
- **Send timing:** day 14
- **Subject:** Your trading tax picture in 4 lines
- **A/B:** Two weeks in: what to keep
- **Preview:** Plus 4 questions, 2 minutes.

Hi [first name],

A recap, in case one email got buried:

- Frequent trading profit is usually business income, taxed in full.
- Keep the TFSA for long-term holdings.
- Max your RRSP deduction. Trading profit creates the room.
- A CCPC defers tax, it doesn't erase it. Price it with a CPA once profits are consistently six figures.

Rerun the import whenever you add a month of trades.

Could you give me 2 minutes? Four questions on what worked and what didn't.

**Button:** Answer 4 questions (Google Form)

P.S. The first 100 Planner buyers get the Founding price of $19/yr, kept as long as you renew without a gap.

Estimates, not tax advice.

## 3. Technical setup

- **Tool:** MailerLite Comfort, from $12/month ([MailerLite pricing](https://www.mailerlite.com/pricing), checked 2026-10-13). The free plan covers 250 subscribers but caps automations at 5 steps, too short for 7 emails. Comfort allows 100 steps.
- **Segmentation:** source (waitlist or README form), broker (Questrade, IBKR, other), province, imported yes or no (from replies and the form), profit band, and "won't install Python". That last group gets email 6 first, since the Planner is built for them.
- **Unsubscribes:** your list is Canadian, so CASL applies, not just CAN-SPAM or GDPR. Get express consent on every form: say who is asking and that people can withdraw. Every email names you, gives a mailing address and contact, and has an unsubscribe link that works for 60 days and is honoured within 10 business days ([fightspam.gc.ca](https://www.fightspam.gc.ca/eic/site/030.nsf/eng/00008.html); [ISED](https://ised-isde.canada.ca/site/canada-anti-spam-legislation/en/node/7)).
- **From name:** "[Founder first name] from Token". Email 5 depends on replies, and traders reply to a person, not a brand.

## 4. Targets

Source for the first three rows: PostHog's onboarding flow write-up ([PostHog](https://posthog.com/blog/how-we-built-email-onboarding), 2024, updated 2025). It covers a developer tool, not a tax tool. Apple Mail Privacy Protection (2021) inflates opens, so trust clicks and replies more.

| Metric | Target | Source | Action if below |
|--------|--------|--------|----------------|
| Open rate | 40% minimum, 50% goal | PostHog, 2024 | Test subject lines, check send time |
| Click rate | 4% minimum, 6% goal | PostHog, 2024 | Simplify the call to action, shorten the email |
| Unsubscribe rate | Under 1% per email | PostHog, 2024 | Check frequency, add value |
| Sequence completion | Estimate: 90% still subscribed at email 7 (7 emails × under 1% unsubscribes, plus bounces) | Estimate | Remove or rewrite weak emails |
| Replies to email 5 | Estimate: 5% of recipients | Estimate | Ask one narrower question |
