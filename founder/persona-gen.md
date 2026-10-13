<!-- /founder:persona-gen · 2026-10-13 · input: Token: a local, open-source toolkit for self-directed Canadian active traders: 2026 tax data, a sole-prop vs RRSP vs CCPC calculator, and free OpenBB market data. Market: Canadian day/swing traders, $30K to $250K trading profit, Questrade/IBKR/Wealthsimple users. -->

# User personas: Token

These are archetypes, not real people. They are hypotheses until the 15 interviews in the product brief confirm or kill them. Every quote below is illustrative, written for interview testing, not said by a user.

Assumption: provinces follow the product brief (mostly Alberta and Ontario).
Assumption: names, ages and incomes are invented to make each archetype concrete.

## Persona 1: Daniel Okafor, the full-time trader weighing a CCPC (archetype)

**Identity:** 36, Calgary AB. Former backend developer, full-time day trader for 3 years. Sole proprietor. Trading profit $110K to $160K a year, no other income.

**Day in the life:** At 7:00 he runs his own Python scripts against the IBKR API to build a watchlist. He trades the US open until 11:00 in TWS, then journals in a Google Sheet. Evenings he reads r/CanadianInvestor and CPA blogs about incorporating. His frustration: he can model a strategy to the cent but not his own tax bill.

**Goals:**
- Primary: decide before 2027 whether to incorporate.
- Secondary: automate his year-end P&L instead of rebuilding it every April.
- Motivation: financial pressure. He has no employer RRSP or pension, so every dollar deferred matters.

**Pain points:**
1. "Two CPAs gave me two answers on whether my trading is active business income."
2. "I rebuild my realized P&L from IBKR Flex reports every spring. It takes a weekend."
3. "I don't know what my instalments should be until CRA sends the reminder."

**Current workarounds:**
- IBKR Flex Query exports plus a Python script: works, but breaks when IBKR changes columns.
- Google Sheet with TaxTips.ca brackets typed in by hand: has to be redone each year.
- One CPA consult a year. Estimate: about 2 hours a week on tax bookkeeping, valued at his roughly $75/hour trading rate ($150K / 2,000 hours), so about $150 a week.

**Decision-making:** Finds tools on GitHub, Hacker News and r/algotrading. Tries anything he can `pip install` in 5 minutes. Pays when a tool replaces a CPA hour or saves the April weekend.

**OpenBB and Python:** Fully comfortable. He would install OpenBB in 10 minutes, but he already pulls clean prices from IBKR, so yfinance through OpenBB adds nothing for him. yfinance rate limits are a known pain ([yfinance issue #2422](https://github.com/ranaroussi/yfinance/issues/2422), 2025). He would use OpenBB only as a pipe into a P&L import or YTD tracker, never as the reason to adopt Token.

**Fit:** Urgency 5, Willingness to pay 4, Reachability 3. **Primary.**

## Persona 2: Jenna Morrison, the employed swing trader (archetype)

**Identity:** 41, Mississauga ON. Registered nurse, 3 twelve-hour shifts a week, salary about $98K. Swing trades TSX and US stocks on Questrade on days off. Trading profit $35K to $60K.

**Day in the life:** On off days she reviews charts on TradingView Essential at the kitchen table and places 5 to 15 trades a week. She keeps a paper notebook of trades. Last year she learned from a Reddit thread that some of her trades sat in a TFSA, and she has not slept well since.

**Goals:**
- Primary: know how much to set aside from each winning trade.
- Secondary: find out if her TFSA trading is a problem before CRA does.
- Motivation: fear of an audit, and a family to protect.

**Pain points:**
1. "Nobody withholds anything on my trading. I just guess and hope."
2. "I can't tell if my TFSA trades count as a business."
3. "My accountant charges more every year because my Questrade statements are a mess."

**Current workarounds:**
- Questrade year-end statements handed to an accountant: expensive and late.
- Reddit threads: contradictory. CRA has reassessed more than $75 million from TFSA audits, about 10% of it from accounts seen as carrying on a business ([Investment Executive, 2017](https://www.investmentexecutive.com/news/industry/cra-raises-more-than-75-million-from-audited-tfsas/); [Globe and Mail](https://www.theglobeandmail.com/business/article-day-trading-tfsa-income-taxable)).
- Estimate: 1 hour a week of worry and record keeping, plus [her actual accountant fee].

**Decision-making:** Finds tools through r/PersonalFinanceCanada and coworkers. Tries a tool if it runs in a browser or Excel. Pays after a scare: a CRA letter or a large April balance.

**OpenBB and Python:** She has never opened a terminal and will not install Python. The 10-minute OpenBB guide is where she quits. She needs a Questrade CSV upload and a set-aside number, not market data.

**Fit:** Urgency 4, Willingness to pay 3, Reachability 4. **Secondary.**

## Persona 3: Tyler Brandt, the mobile-first Wealthsimple trader (archetype)

**Identity:** 27, Edmonton AB. Electrician, salary about $85K. Trades options and crypto on Wealthsimple from his phone between jobs. Trading profit swings from a loss to $40K.

**Day in the life:** Checks Wealthsimple and X on breaks, trades 20 or more times a week, mostly short-dated options. Charts on the TradingView free plan on his phone. Never touches a laptop for money.

**Goals:**
- Primary: not get crushed by a tax bill after his best year.
- Secondary: grow the account to quit electrical work.
- Motivation: independence.

**Pain points:**
1. "Wealthsimple Tax files it, but I don't know if it's filed right."
2. "I paid $9K in April and had no idea it was coming."
3. "Every thread says something different about capital gains vs business income."

**Current workarounds:**
- Wealthsimple Tax: files last year, plans nothing.
- Estimate: 30 minutes a week reading threads. His real loss is one surprise bill a year.

**Decision-making:** Finds tools on X, TikTok and Reddit. Tries a tool if it works on his phone in 2 minutes. Low willingness to pay until his profit stays above $40K two years in a row.

**OpenBB and Python:** None. No desktop habit, so OpenBB is irrelevant to him. Wealthsimple reports 3.6 million clients ([Wealthsimple Q2 2026](https://www.newsfilecorp.com/release/307150/Wealthsimple-Reports-17B-Net-Flows-in-Q2-Driven-by-High-Demand-for-Chequing-and-Spending-Products)), so this group is large but hard to serve with a local toolkit.

**Fit:** Urgency 3, Willingness to pay 2, Reachability 4. **Tertiary.**

## Persona priority matrix

| Persona | Urgency | Willingness to pay | Reachability | Total | Would install OpenBB? |
|---|---|---|---|---|---|
| Daniel (full-time, CCPC question) | 5 | 4 | 3 | 12 | Yes, but does not need it |
| Jenna (employed swing trader) | 4 | 3 | 4 | 11 | No |
| Tyler (mobile Wealthsimple) | 3 | 2 | 4 | 9 | No |

**Build for Daniel first.** His CCPC question is the one Token's calculator answers and nobody else models, and he can run a local Python repo today. Note what all three share: none of them adopts Token for OpenBB. Daniel has better data from his broker, and Jenna and Tyler will never install it. The broker CSV import is what serves all three. Use the interviews to test whether OpenBB should stay as an optional data source for the P&L import rather than a headline feature.

Saved to `founder/persona-gen.md`. Next: `/founder:user-interviews`, `/founder:validate-idea`.
