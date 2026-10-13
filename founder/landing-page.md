<!-- /founder:landing-page · 2026-10-13 · input: Token: for Canadian active traders. Drop in your Questrade or IBKR export and see your profit, TFSA/business-income warnings, and what you keep as a sole proprietor, with a max RRSP, or through a corporation. -->

# Landing page copy: Token

Assumption: the page sells the free local tool that `founder/mvp-scope.md` defines (Questrade and IBKR import, two warnings, three-scenario table). Market data is cut from the MVP and does not appear. The year-to-date tracker is planned for week 3, so it is not promised here.
Assumption: the paid Planner (browser upload) is not built yet. The page shows its price as a waitlist with a refundable deposit, matching experiment 1 in `founder/validate-idea.md`.
Assumption: the dollar figures come from the repo's own Alberta worked example ($150,000 profit), as quoted in `founder/product-brief.md`.
Update 2026-10-13: the repo now has an MIT LICENSE, so the page can say "open source". Original assumption: the page says "public on GitHub", not "open source". The repo had no LICENSE file yet (`founder/pricing-strategy.md`). Add one before using the words "open source".

## 1. Hero

**Headline:** See what you keep from trading: sole prop, RRSP, or corporation

Alternates to test:
- Your broker export in, your after-tax trading profit out
- Know your real trading tax before April, not after

**Subheadline:** For Canadian active traders. Drop in your Questrade or IBKR export and see your 2026 profit, TFSA and business-income warnings, and three tax scenarios.

**Button:** Run my 2026 numbers free

**Proof line:** Free, runs on your computer, code public on GitHub. [GitHub star count] · [Waitlist count for the browser version]

## 2. Problem

**Headline:** "I guess what I owe and hope"

1. **"Nobody withholds anything on my trading."** You set money aside from winning trades by feel, and April tells you if you guessed right.
2. **"I can't tell if my TFSA trades count as a business."** If CRA decides they do, gains in that account can be taxed as income, and the forums all say something different.
3. **"I rebuild my P&L from broker exports every spring."** It takes a weekend, and you still don't know if incorporating would have saved you money.

## 3. Solution

**Headline:** Your real profit, your real risks, and three ways to keep more

**Your profit from your trades**
Token reads your Questrade or IBKR export, pairs buys with sells, and totals your realized 2026 profit. You start from your own trades, not a number you typed from memory. Detail: one file in, one profit figure out, every trade counted.

**Warnings before CRA sees it**
Any trade in a TFSA or FHSA gets flagged. If your trading frequency and holding periods look like business income, Token tells you before you file it as capital gains. Detail: these are the two costliest mistakes in the repo's trader tax guide.

**Three scenarios, side by side**
See what you keep as a sole proprietor, with a max RRSP contribution, or through a corporation (CCPC), with the $2,000 to $5,000 a year corporate upkeep shown next to the savings. Detail: in the Alberta worked example at $150,000 profit, a max RRSP saves $9,720 a year and a corporation defers $31,203.

## 4. How it works

1. **Get Token.** Clone the repo. It needs Python 3.10 or later and one package, openpyxl.
2. **Export your trades.** Download your Questrade transaction history or an IBKR Flex Query CSV for 2026.
3. **Run one command.** Point Token at the file and pick your province.
4. **Read your numbers.** See your profit, any warnings, and the three-scenario table in dollars.

## 5. Social proof

Stage: pre-launch. Use the waitlist count, the public repo's activity, and the founder's track record. Add beta quotes once the first 10 importers confirm their profit matches their own records.

- [Quote from a full-time trader weighing incorporation: what the three-scenario table showed and what they decided, compared with their CPA's answer]
- [Quote from a Questrade swing trader: how long their year-end P&L used to take, and what the TFSA warning told them]
- [Founder line: years trading in Canada and why Token was built]

## 6. Pricing preview

**Open: $0.** Every calculation, unlimited trades, runs on your computer.

**Planner (browser version, waitlist): $39 a year, or $5 a month ($60 billed monthly).** No install: upload your export in the browser. Founding price: $19 a year for the first 100 buyers, kept for as long as you renew. [Confirm deposit amount and refund terms before launch]

Is it worth it? A CPA charges $200 to $500 for one self-employed return. $39 is less than 20% of that.

## 7. FAQ

**Is this tax advice?**
No. Every result is labeled an estimate, not tax advice. Use it to walk into your CPA meeting with your real numbers and a clear question, which makes that meeting shorter.

**Is my trading data safe?**
The free version runs on your computer. Your export never leaves your machine, and Token never asks for your broker login. You can read every line of the code on GitHub.

**Do I need to know how to code?**
For now, you need to run one Python command. If you would rather upload in a browser, join the Planner waitlist and you will hear when it opens.

**What does it support today?**
Stocks and ETFs from Questrade and IBKR exports, for all 14 Canadian jurisdictions. Options and crypto rows are skipped and labeled, and Alberta and Ontario are the most tested. Tell us what you trade and we will prioritize it.

**Why not use Wealthsimple Tax or TurboTax?**
Keep them for filing. They file last year's return. Token answers this year's question: what you keep and whether a corporation is worth its upkeep.

## 8. Final call to action

**Headline:** Find out what incorporating is worth before April, not after

**Button:** Run my 2026 numbers free

**Risk reversal:** Free, no account, no credit card. Runs on your computer.

## 9. SEO metadata

- **Title tag:** Canadian trader tax: sole prop vs RRSP vs corporation
- **Meta description:** Drop in your Questrade or IBKR export and see your 2026 trading profit, TFSA warnings, and what you keep as a sole prop, with an RRSP, or as a corporation.
- **Keywords:** day trading tax Canada, should I incorporate my trading, TFSA day trading CRA

Saved to `/home/user/Token/founder/landing-page.md`. Next: `/founder:go-to-market`, `/founder:validate-idea`.
