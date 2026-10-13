<!-- /founder:mvp-scope · 2026-10-13 · input: Token. Features I want: 1) 2026 tax data for 14 jurisdictions (exists), 2) trader scenario calculator sole prop vs RRSP vs CCPC (exists), 3) broker P&L import from Questrade/IBKR exports, 4) year-to-date tax and instalment tracker, 5) OpenBB market data layer (exists as a quickstart script), 6) TFSA / business-income classification guardrails, 7) incorporation readiness check, 8) Excel workbook output (exists). -->

# MVP scope: Token

Assumption: the founder is solo and the MVP stays a free, local, open-source Python tool (from `founder/product-brief.md`).
Assumption: the first user is Daniel, the full-time IBKR or Questrade trader weighing a CCPC (`founder/persona-gen.md`).
Assumption: stocks and ETFs only.

Correction to a saved fact: `founder/facts.md` says the OpenBB script pulls prices to CSV. As of today it does not. Current `pip install openbb` is 5.0.0 and no longer includes the equity router or the yfinance provider, so `examples/openbb_quickstart.py` and step 3 of `docs/openbb_setup.md` both fail with `'App' object has no attribute 'equity'`, and the script still prints "Done" (tested 2026-10-13).

## 1. Feature triage

| # | Feature | Category | Reasoning |
|---|---|---|---|
| 1 | 2026 tax data, 14 jurisdictions (exists) | Must have | Every number depends on it; zero build cost. |
| 2 | Sole prop vs RRSP vs CCPC calculator (exists) | Must have | It is the one answer no filing tool gives (`founder/competitor-matrix.md`, Gap 1). |
| 3 | Questrade and IBKR P&L import | Must have | Without it the calculator answers a typed guess; it is also the input features 4 and 6 need. |
| 6 | TFSA and business-income guardrails (lite) | Must have | Filing trading profit as capital gains and trading in a TFSA are the two costliest mistakes in `docs/trader_taxation.md`, and the import already holds the data to flag them. |
| 4 | YTD tax and instalment tracker | Should have | Brings users back monthly, but a trader gets the core decision without it. Week 3. |
| 8 | Excel workbook output (exists) | Should have | Keep the existing outline untouched; add one sheet fed by the import in week 4 for spreadsheet users. |
| 7 | Incorporation readiness check | Won't have | The calculator already shows the CCPC deferral; a scored check only pays off if CPAs buy referrals, which is untested. |
| 5 | OpenBB market data layer (exists, broken) | Won't have | Price history computes no profit or tax, none of the three personas adopts Token for it, and today it is broken. See the verdict below. |

Feature 6 in the MVP is two rules, not a scoring engine: (a) any trade in an account labeled TFSA or FHSA gets a warning, (b) a frequency and holding-period check prints "this looks like business income, not capital gains".

### OpenBB verdict

**Cut from the MVP feature list. Do one half-day repair so the public repo stops shipping a broken guide.**

Why cut:
- Realized P&L comes from broker exports, not price history.
- It adds 730MB to 1.2GB of install (tested 2026-10-13) to a tool whose core needs only Python and `openpyxl`.
- `openbb-yfinance` is AGPL-3.0-only, while `openbb-core` and `openbb-equity` are Apache-2.0 (tested 2026-10-13). Fine locally, a problem if Token is ever hosted and paid.
- Its steward is in transition. OpenBB said on 2026-08-25 it could not find product-market fit; stewardship moved to the non-profit OpenBQ on 2026-10-01 and Workspace to FINOS ([OpenBB blog](https://openbb.co/blog/openbb-belongs-to-everyone)). Package maintenance plans: Not found.

The minimal OpenBB work in the MVP (0.5 day):
1. Change the install line in `docs/openbb_setup.md` and the script docstring to `pip install openbb-core openbb-equity openbb-yfinance`, pinned to the 2.0.x versions that fetched AAPL (251 rows), SHOP.TO (250) and BTC-USD (365) (tested 2026-10-13).
2. Make `examples/openbb_quickstart.py` exit non-zero and skip "Done" when every ticker fails.
3. Label the guide "optional extra, not required for tax features" and keep OpenBB out of the core requirements, so the AGPL provider is never a dependency of the calculator.

## 2. MVP definition

A Canadian trader can drop in a Questrade or IBKR export and see their 2026 trading profit, any classification warnings, and what they keep as a sole proprietor, with a max RRSP, or through a CCPC in under 5 minutes.

Features that make this possible:
1. 2026 tax data (exists)
2. Scenario calculator, taking profit from the import and showing CCPC setup cost of $2,000 to $5,000 a year next to the deferral (from `docs/incorporation_checklist.md`)
3. Questrade transaction-history export and IBKR Flex Query CSV import
4. Two guardrail rules (TFSA/FHSA trading, business-income pattern)

## 3. User flow

```
Step 1: User arrives at the GitHub README from a Reddit post showing the Alberta $150K table
Step 2: User clones the repo and runs pip install -r requirements.txt (stdlib + openpyxl only)
Step 3: User runs: python token_cli.py import activity.xlsx --province AB
Step 4: User sees realized 2026 profit, any warnings, and the three-scenario table in dollars
Step 5: User stars the repo or fills a 4-question form ("would you want a CPA to review this?")
```

Questrade exports transaction history to Excel from Reports ([Questrade](https://www.questrade.com/learning/using-questrade/checking-your-account-activity)). The export lists individual transaction rows, not round trips, so Token must pair buys and sells itself ([JournalPlus](https://journalplus.co/integrations/questrade)). IBKR Flex Queries export trades to CSV and may cap one export at a year ([Navexa](https://help.navexa.com/en/articles/16061811-import-interactive-brokers-ibkr-trades-using-csv)), which fits a single tax year.

## 4. Technical scope

**Build vs. buy**
- Build: two parsers, a profit calculator, two rules, a CLI wrapper.
- Buy or skip: no auth, payments or email. It runs locally, so no broker credentials leave the machine. Feedback through a free Google Form.

**Stack:** Python 3.10+, standard library, `openpyxl` (already used by `scripts/build_tax_workbook.py`). One CLI entry point. No OpenBB, no pandas.

**Build time (Estimate, one developer)**

| Work | Days |
|---|---|
| Regression tests against the Alberta worked profiles | 0.5 |
| Calculator refactor: accept imported profit, prior-year RRSP room, setup-cost line | 1 |
| Questrade parser, buy/sell pairing, USD to CAD | 3 |
| IBKR Flex parser (uses IBKR's own FX column) | 2 |
| Guardrail rules and warning text | 1 |
| CLI and README quickstart with disclaimer | 1 |
| OpenBB repair (above) | 0.5 |
| Buffer for real-export edge cases | 2 |
| **Total** | **11 days, about 2.5 weeks** |

Settle before coding the parsers: [CPA confirmation of the cost method for a business-income trader: average cost or inventory valuation] and [CPA confirmation of the FX rate to use for Questrade USD trades].

**Hosting:** none for the tool. For the province table landing page, GitHub Pages: sites up to 1 GB, soft limit of 100 GB bandwidth a month ([GitHub Docs](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)). Cost $0.

## 5. What you're not building, and why

| Feature | Why it feels important | Why it doesn't matter before PMF | Revisit when |
|---|---|---|---|
| OpenBB market data layer | It is already in the repo and OpenBB has a large technical audience | Prices don't produce a tax number, and the install and license weight the core | 10 users ask to mark open positions at Dec 31, or OpenBQ publishes a maintenance plan for the packages |
| Incorporation readiness score | It is the high-value moment a CPA might pay for | The calculator already answers "is CCPC worth it"; the score only matters with a buyer | 3 CPAs agree in writing to a referral fee (experiment 3 in `founder/validate-idea.md`) |
| YTD tracker with instalment dates | Instalment interest is non-deductible and it drives monthly return visits | Retention only matters once people trust the first number | 25 users have imported a real export (product brief KPI). Planned for week 3 |
| Options, futures and crypto parsing | Daniel and Tyler trade options | Each asset class doubles the parser edge cases | 5 of the first 25 importers send option-heavy exports |
| Web upload or Wealthsimple import | Jenna and Tyler will never run Python | A hosted version brings data custody, liability and the AGPL question at once | The $19 to $49 preorder test passes (3% click, 10 deposits) |

## 6. Launch criteria

**Must work**
- [ ] A real Questrade export and a real IBKR Flex CSV each import without manual edits
- [ ] Imported profit matches a hand-checked total within $1 on 3 test files
- [ ] Scenario table matches the Alberta worked profiles in `docs/trader_taxation.md`
- [ ] TFSA trades always trigger the warning
- [ ] Fresh clone to first result in under 5 minutes on Mac and Windows
- [ ] Every result prints "estimate, not tax advice"
- [ ] OpenBB guide either works with the pinned packages or says clearly that it is optional

**Can be broken or ugly**
- Output is terminal text only
- Quebec and territory results are less tested than Alberta and Ontario
- Unsupported rows (options, crypto) just say "skipped"

**The one thing to test with the first 10 users:** does the imported profit match what the trader believes they made? If not within 2%, nobody trusts the CCPC answer. [Count of first 10 users whose imported profit matched their own records within 2%]

Saved to `/home/user/Token/founder/mvp-scope.md`. Next: `/founder:user-interviews`, `/founder:landing-page`.
