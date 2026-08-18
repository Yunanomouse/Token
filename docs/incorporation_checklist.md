# Checklist: Moving Personal Trading into a Corporation (Questrade)

Sequence for moving from a personal cash trading account to a corporate account. A personal account cannot be converted or renamed — the corporation is a separate legal person that must exist first and open its own account.

Companion to `docs/trader_taxation.md` (why/whether to do this) and `examples/trader_scenario_comparison.py` (the numbers).

> **Not legal or tax advice.** Steps 0 and 4 in particular are worth professional help.

## Step 0 — Confirm it's worth it

- [ ] Profits are consistently well beyond personal living costs (the benefit is deferral on *retained* profit)
- [ ] Budgeted ~$2,000–5,000/yr for corporate accounting and filings
- [ ] CPA consult booked — confirm your trading qualifies as **active business income** for the small-business rate (gray area), and whether a s.85 rollover is needed for any in-kind transfers

## Step 1 — Incorporate

- [ ] Choose jurisdiction: federal (Corporations Canada, ~$200 online) or your province (e.g., Ontario ~$300)
- [ ] A numbered company (e.g., `1234567 Ontario Inc.`) is fine for trading — no name search (NUANS) needed
- [ ] Receive articles of incorporation; CRA issues the business number (BN) and corporate income tax account automatically
- [ ] Decide share structure with the CPA before filing if a spouse may ever hold shares (TOSI rules restrict income splitting)
- [ ] Set the corporation's fiscal year-end (CPA input; calendar year is simplest)

## Step 2 — Corporate bank account

- [ ] Open a business account at any bank; bring articles of incorporation + director ID
- [ ] The corporation needs its own bank account before a broker will fund-link it

## Step 3 — Open the Questrade corporate account (new application)

Gather before applying:

- [ ] Articles of incorporation
- [ ] Corporate resolution authorizing the account and naming trading authority
- [ ] Government ID for all directors and all beneficial owners of 25%+
- [ ] Business number / corporate tax info
- [ ] Corporate bank account details for funding

Notes:

- [ ] Expect longer processing than a personal account
- [ ] Re-apply for margin and options approval — nothing carries over from the personal account
- [ ] Check Questrade's current fee schedule for corporate/non-personal accounts

## Step 4 — Fund it (the tax trap)

**Cash — clean:**

- [ ] Flatten positions in the personal account
- [ ] Withdraw to personal bank → transfer to corporate bank → fund the corporate Questrade account
- [ ] Paper the contribution as a **shareholder loan** or **share subscription** (ask the CPA which; keep the record)

**Securities in-kind — not clean:**

- Transferring positions to the corporation is a **disposition at fair market value** — for a trader, immediately taxable business income on any gains
- A s.85 rollover (election form T2057) can defer this but requires professional preparation
- For an active trader mostly in cash, closing positions and moving cash avoids the issue entirely

## Step 5 — Operate like a company

- [ ] All trading in the corporate account from day one; stop trading the strategy personally
- [ ] Bookkeeping from month one (trade exports, expenses, home-office log)
- [ ] Corporate T2 return filed annually; instalments once CRA requires them
- [ ] Pay yourself by salary (creates RRSP room, requires payroll account/remittances) or dividends (simpler, no RRSP room) — mix per CPA
- [ ] Keep or close the personal account; if kept, use it only for long-term personal investing, not the business strategy

## Order matters

Corporation → bank account → Questrade application → funding → trade. Brokers turn away applications without articles of incorporation.
