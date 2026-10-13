<!-- /founder:user-interviews · 2026-10-13 · input: Token, a Canadian active-trader tax + market data toolkit. Assumptions I'm least sure about: (1) traders will pay for planning, not just filing; (2) the sole prop vs CCPC question comes up often enough to build around; (3) traders want market data (OpenBB/yfinance) inside a tax tool at all, versus just importing their broker's P&L export; (4) non-coding traders will install Python to use it; (5) trader-focused CPAs would pay for referrals. -->

# User interviews: Token

Assumption: this script is for traders. Assumption 5 (CPAs pay for referrals) needs a different interviewee; test it with experiment 3 in `founder/validate-idea.md`, the CPA email offer.
Assumption: assumptions 1 and 2 are merged, since the CCPC question is the planning moment people would pay for.

## 1. Interview objectives

| # | Hypothesis | Confirmed | Rejected |
|---|---|---|---|
| H1 | Traders over $50K profit have spent time or money planning tax before April, and the incorporation question triggered it. | 6 or more of 15 asked a CPA or forum about incorporating in the last 2 years, and paid for advice or software. | They only deal with tax at filing time, and nobody asked about incorporating. |
| H2 | Traders need price data beyond their broker export to work out tax. | They describe a past case where they pulled outside prices (year-end values, FX rates, crypto) to finish a return or estimate. | Their broker export was the only input, and they never looked elsewhere. |
| H3 | Traders who don't code will install Python to get a tax answer. | Non-coders describe installing a command-line or developer tool in the past year, or finish an install during the commitment test. | They have never used a terminal and stop at the install step. |

## 2. Screening criteria

**Must have:**
- Canadian tax resident who trades in their own account
- 50 or more trades in 2025
- 2025 trading profit of $30K or more (ask for a band, not a number)
- Filed a 2025 return that included trading results

**Nice to have:**
- Has spoken to a CPA about trading in the last 2 years
- Mix of coders and non-coders: aim for 7 who write scripts, 8 who don't
- Alberta or Ontario

**Disqualify:**
- CPAs, tax preparers, advisors (they answer for clients)
- Friends or family (they'll be polite)
- Buy-and-hold investors (no business-income problem)

**Where to find them:** r/CanadianInvestor, r/PersonalFinanceCanada, r/Daytrading (Canadian filter question), r/algotrading and the OpenBB GitHub discussions for coders, Bear Bull Traders forum, LinkedIn search "day trader" + Canada. Paid fallback: Respondent or UserInterviews.com with the screener above.

**Incentive:** $20 gift card. Estimate: $20 × 15 = $300, the top of the product brief's budget.

## 3. Interview script (25 minutes)

### Opening (2 minutes)

"Thanks for making time. I'm researching how Canadian traders handle tax on their trading. I'm not selling anything today. I want to hear how you actually do things now, including the messy parts. There are no right answers. If something doesn't apply to you, just say so. Is it OK if I record this so I don't have to take notes? Only I'll listen to it."

### Warm-up (3 minutes)

1. "How long have you been trading, and what do you trade?"
2. "Walk me through a normal trading day. What do you have open on your screen?"
   Follow-up: "Where does your price data come from? Do you pay for any of it?"
3. "Do you write any code or scripts for your trading, or use spreadsheets?"
   Follow-up: "What's the most technical thing you've set up yourself?"

### Problem exploration (10 minutes)

4. **(H1)** "Tell me about the last time you filed taxes on your trading. What did you do, step by step?"
   Follow-up: "How long did it take? Who helped? What did it cost?"
5. **(H1)** "Before that April, did you do anything during the year to figure out what you'd owe?"
   Follow-up: "What did you use? What happened when the bill came?"
6. **(H1)** "Has incorporating ever come up for you? Tell me about the last time."
   Follow-up: "Who did you ask? What did they say? What did you decide, and what did it cost to find out?"
7. **(H2)** "When you worked out last year's trading profit, what did you start from?"
   Follow-up: "Was there any number you couldn't get from your broker's statement? What did you do to get it?"
8. **(H2)** "Tell me about the last time you pulled prices into a spreadsheet or script yourself, outside your broker's platform."
   Follow-up: "What was it for? Where did you get the data? Did it ever break or give you a wrong number?"
9. **(H3)** "What's the last program you installed on your computer for trading or money? Walk me through installing it."
   Follow-up: "How long did it take? Did you get stuck anywhere? What did you do?"
10. **(H3)** "Have you ever run a script or tool someone else wrote, from GitHub or a forum? What happened?"
    Follow-up: "If you haven't, what did you do the last time a tool needed a technical setup step?"

### Solution exploration (5 minutes)

11. "If you could change one thing about how you handle trading tax, what would it be?"
12. "What have you already tried to fix that? Why did you stop?"
13. "What would a tool need to read from you to give you a useful number: your broker export, prices, something else?"
14. "What would make you stop using a tax tool on the first day?"

Listen for unprompted mentions of market data, incorporation, instalments, or setup friction. Write down their exact words.

### Reaction (5 minutes)

Say exactly: "Token reads your broker's trading export and shows what you'd keep in 2026 as a sole proprietor, with a max RRSP, or through a corporation, for any province. It runs on your own computer with Python, and can optionally pull free market prices through a tool called OpenBB."

15. "What part of that, if any, would you have used last year? What would you have used it for?"
16. "Which part would you skip?" Follow-up for coders and non-coders alike: "What about the market price part?"
17. "Who else would you have to involve to use it, like your accountant?"
18. "What do you pay for tax help or trading tools now?"

Real interest: they ask about their broker or province, or when they can try it. Polite interest: "cool" with no question back.

### Closing (2 minutes)

"Who else do you know who trades seriously and has had to deal with this? Could you introduce me?"

Commitment test, pick one:
- Non-coders: "Would you do a 20-minute screen share this week where you try to install it while I watch, without me helping?"
- Coders: "Would you send me your 2025 broker export with account numbers removed, so I can run it through Token and send you the result?"

"Thank you. I'll send the gift card today and share what I learn in about 3 weeks."

## 4. Analysis framework

**Pattern table** (one row per interview, fill within an hour of each call):

| # | Codes? | Profit band | Planned before April (H1) | Asked about CCPC (H1) | Paid for help, $ | Used outside prices for tax (H2) | Installed dev tool last year (H3) | Commitment kept | Exact quote |
|---|---|---|---|---|---|---|---|---|---|
| 1 | | | Y/N | Y/N | | Y/N | Y/N | Y/N | [Their words] |

**Signal vs. noise:**
- A pattern is 3 or more people describing the same past event unprompted. One loud person is an anecdote.
- Split every count by coder and non-coder. H2 and H3 can be true for coders and false for everyone else.
- A kept commitment outweighs ten "I'd use that".

**Decision criteria (after 8, confirm at 15):**
- **H1:** 6 or more of 15 asked about incorporating: build the incorporation readiness check next. Fewer than 3: drop CCPC as the headline and lead with the TFSA and business-income risk.
- **H2 (OpenBB):** 3 or more of 8 used outside prices to finish their tax: keep OpenBB as a data source for the P&L import. 1 or fewer: remove OpenBB from the core path, keep it as an optional add-on or an OpenBB community extension for distribution, and build the broker CSV import first.
- **H3 (Python):** fewer than half of non-coders finish the install test: ship a browser or Excel version before any non-coder marketing, or target coders only.

## 5. Red flags cheat sheet

**Being polite, not honest:**
- "That sounds cool" with no reason why
- "I would definitely use that" (future tense)
- "You should add live charts" (designing for you, not describing a problem)
- Can't describe the last time they did their trading taxes
- Says "market data would be nice" but can't name a time they needed a price they didn't have

**Real interest:**
- Names a dollar amount: a surprise April bill, an instalment penalty, a CPA fee
- Already built a spreadsheet or script to fix it
- Asks when they can try it, or whether it reads their broker's export
- Offers an introduction to another trader without being asked twice

Saved to `founder/user-interviews.md`. Next: `/founder:pricing-strategy`, `/founder:validate-idea` (rerun with interview results).
