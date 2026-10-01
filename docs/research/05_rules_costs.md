# 05 — Rules and real costs a tiny real account would face (checking the paper-sim assumptions)

Researched 2026-09-30. **This is general information, not tax, legal or investment advice.** Rules change, and how a specific dealer applies them varies. A person placing real orders should check their own dealer's account agreement and, for tax, a qualified Canadian tax professional.

Simulation assumptions under review: **0.1% slippage per side, zero commission, T+1 settlement, whole shares** (a $40 daily whole-share bot on cheap US stocks, a $50 intraday long-only cash-account bot on 5-minute bars that does several round trips a day, and a $100k daily paper bot).

Scope note: at the user's request, this document recommends no broker and no automation. Broker fee pages are cited only as evidence of what fees look like in the market.

---

## 1. US settlement (T+1) and cash-account violations (good faith / free-riding)

### Facts
| Rule / fact | Source (checked) | Date |
|---|---|---|
| The SEC amended Exchange Act Rule 15c6-1 to shorten the standard settlement cycle from T+2 to T+1. Compliance date: **May 28, 2024**. | SEC press release 2023-29, https://www.sec.gov/newsroom/press-releases/2023-29 | Adopted Feb 15, 2023 |
| Canada moved to T+1 on **May 27, 2024** (amendments to NI 24-101 came into force the same day). | CSA, https://www.securities-administrators.ca/news/csa-announces-adoption-of-amendments-to-national-instrument-24-101-institutional-trade-matching-and-settlement/ | 2024 |
| "When you buy securities in a cash account, you must pay for securities in full before selling them." "Buying and selling the same security in a cash account before paying for it is known as 'free-riding,' a violation of the Federal Reserve's Regulation T." "The current settlement time for most equity trades is T+1." | FINRA Investor Insights, *Frequent Intraday Trading*, https://www.finra.org/investors/insights/frequent-intraday-trading | Jun 4, 2026 |
| Reg T 12 CFR 220.8(c): if a security in a cash account "is sold ... without having been previously paid for in full by the customer, the privilege of delaying payment beyond the trade date shall be withdrawn for **90 calendar days**" (the 90-day freeze). | https://www.law.cornell.edu/cfr/text/12/220.8 | current CFR |
| **Good-faith violation (GFV)**, as dealers define it: buying with **unsettled** sale proceeds, then selling that new position **before those proceeds settle**, even if the money settles later. Typical dealer policy: **3 GFVs (or 1 free-riding violation) in 12 months → 90 days of settled-cash-only trading.** GFV is a dealer policy built on Reg T, so the details vary by firm. | Example of a dealer help page: https://www.fidelity.com/webxpress/help/topics/learn_cash_account_trading_freeride_restrictions.shtml (its worked example still uses older settlement timing, but the definition is unchanged) | accessed 2026-09 |

### What this means for a cash account trading intraday (the $50 bot)
- With $50 of **settled** cash you can buy at 10:00 and sell at 11:00 with no problem. The $50 from that sale is **unsettled until T+1**.
- If you buy again at 12:00 with that unsettled $50, you may be allowed to, but **selling that second position the same day is a GFV**. The 2nd, 3rd and later round trips of the day all run on unsettled proceeds.
- So in a US-style cash account, **each settled dollar can complete only one round trip per day**. With $50 split into N slices you get at most N same-day round trips of $50/N each, and whole-share limits make small slices hard to fill (see section 5). If the bot does several full-size round trips a day, it would pile up GFVs within days and reach the 90-day restriction.
- **Canadian dealer caveat:** Reg T is a US Federal Reserve rule for US broker-dealers. A Canadian resident trading through a Canadian (CIRO) dealer falls under that dealer's own cash-account and settlement policies, not Reg T GFV counting as such. Some dealers may let you reuse unsettled proceeds; others restrict it. I could not find a CIRO rule that copies Reg T's GFV regime (the CIRO rulebook PDF would not download). **For simulation purposes, model settled-cash-only buying (the conservative case)** unless the user has confirmed their dealer's policy.

**Sim implication:** "T+1 settlement" is the right cycle. What matters is whether the $50 intraday sim **stops buying with unsettled proceeds on the same day**. If it recycles the same $50 through several round trips a day, it is simulating something a US cash account cannot do without violations. Add a `settled_cash` ledger in which sale proceeds become available at the next business day's open.

---

## 2. FINRA pattern day trader (PDT) rule: replaced in 2026

| Rule / fact | Source (checked) | Date |
|---|---|---|
| The SEC approved **SR-FINRA-2025-017** on **April 14, 2026**. It replaces the day-trading margin rules in FINRA Rule 4210 "in their entirety", including the day-trade count behind the "pattern day trader" label and the **$25,000 PDT minimum equity**. | FINRA weekly update, https://www.finra.org/compliance-tools/weekly-archive/04152026 ; SEC filing page https://www.sec.gov/rules-regulations/self-regulatory-organization-rulemaking/sr-finra-2025-017 | Apr 14–15, 2026 |
| **Effective June 4, 2026.** Member firms may phase implementation in over 18 months, **until October 20, 2027**. That means some firms may still run PDT-style logic until then. | FINRA Regulatory Notice 26-10, https://www.finra.org/rules-guidance/notices/26-10 | Apr 2026 |
| The new regime works through an **intraday margin deficit** in *margin* accounts, which must be met promptly. A 90-day freeze applies to customers who "make a practice" of not meeting deficits. It applies to margin accounts and excludes good-faith (cash) accounts. | Orrick summary, https://infobytes.orrick.com/2026-05-01/finra-replaces-day-trading-margin-requirements-with-new-intraday-margin-standards/ ; FINRA Rule 4210 text (d)(2), https://www.finra.org/rules-guidance/rulebooks/finra-rules/4210 | May 2026 |
| Rule 4210(b)(4) still requires **"equity of at least $2,000"** to buy on margin (cash need not exceed the cost of the security). | FINRA Rule 4210, same URL | current |
| FINRA: margin rules are a *minimum*, and firms set their own "house" requirements. | FINRA Unscripted podcast, https://www.finra.org/media-center/finra-unscripted/finras-intraday-margin-standard-what-investors-and-members-need-to-know | 2026 |

**Did PDT ever apply to cash accounts?** No. PDT was a margin-account rule. Cash accounts were, and still are, limited by Reg T payment and free-riding rules (section 1), not by a day-trade count.

**Sim implication:** PDT is **not** a constraint for the $50 cash bot, before or after June 2026. The binding constraint is **settled cash** (section 1). A $50 account is far below the $2,000 margin minimum, so it would be a cash account in practice. Do not model a $25k rule. Do model settled cash.

---

## 3. Canadian context

### 3a. CIRO: no PDT equivalent
- Canada has no $25k PDT-style rule. PDT was a **FINRA** rule that bound FINRA-member US broker-dealers. CIRO sets margin minimums, and dealers may set stricter "house" rules. (Secondary sources, e.g. https://www.daytrading.com/ca/rules. I could not retrieve CIRO's rulebook PDF to confirm the absence directly.) CIRO dealer-member rules index: https://www.ciro.ca/rules-and-enforcement/dealer-member-rules
- The point is moot anyway, because the US PDT rule itself ended on June 4, 2026 (section 2).

### 3b. Currency conversion (CAD↔USD)
| Fact | Source (checked) | Date |
|---|---|---|
| A published fee schedule for a zero-commission Canadian trading account: "**1.5% currency conversion fee** on CAD and USD conversions (and vice versa)". Commission on listed US and Canadian securities: $0. | https://www.wealthsimple.com/en-ca/legal/fees/trade | accessed 2026-09 |
| A bank-owned discount brokerage's published FX pricing: spread of 1.07% for $0–$9,999, plus a surcharge of one-third of that spread. Its worked example for a **$1,000 cash conversion totals 199 bps (~2.0%)**. | https://www.td.com/ca/en/investing/direct-investing/pricing/fx-pricing | page uses the 2025 BoC average rate (1.3978) |
| Industry roundups put bank-brokerage FX markups at about **1.5%–2.5%** per conversion. | e.g. https://www.brokerguide.ca/blog/hidden-brokerage-fees-canada (secondary) | 2026 |

**Sim implication:** a CAD-funded account pays about **1.5%–2% each way** to get into USD and again to come back. That is **3%–4% round trip on capital**, a one-time cost if the money stays in USD. On a $40 account that is **$0.60–$0.80 each way**, likely more than months of the bot's expected edge. The paper P&L is in USD and ignores both this cost and USD/CAD exchange-rate moves. **Report results in CAD with a one-time 1.5%–2% haircut on entry and exit**, or state clearly that the sim assumes the capital is already in USD.

### 3c. TFSA / RRSP and day trading
| Fact | Source (checked) | Date |
|---|---|---|
| "If a TFSA holds a non-qualified investment or **carries on a business**, the TFSA trust is **taxable** on any income earned on, and any capital gains derived from ... [the] business." Reported on a T3 return. | CRA, TFSA issuers: Taxes, https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/tax-free-savings-account-tfsa-issuers/taxes.html | modified 2026-02-02 |
| Since Budget 2019 (2019 and later tax years), the **TFSA holder is jointly liable** for that tax. The issuer's liability is limited to the TFSA's assets. | Investment Executive report on Budget 2019, https://www.investmentexecutive.com/news/industry/tfsa-holders-ultimately-liable-for-any-tax-on-day-trading-in-an-account/ | Mar 21, 2019 |
| **Ahamed v. The King, 2023 TCC 17**, affirmed in **Canadian Western Trust Co. v. The King, 2024 FCA 108** (June 11, 2024). A TFSA that traded actively was taxable on its business income. The FCA held that the RRSP exemption for business income from qualified investments (ITA **146(4)(b)**) does **not** carry over to TFSAs under 146.2(6). My search found no Supreme Court of Canada appeal. | https://taxinterpretations.com/content/820171 (FCA summary); CanLII history https://www.canlii.org/judgmentTabs/history/?judgmentId=37545280&lang=en | 2023–2024 |
| CRA factors for "trader" status (archived IT-479R para 11): frequent buying and selling or quick turnover, short holding periods, knowledge of markets, trading as part of ordinary business, substantial time spent, margin/debt financing, speculative non-dividend stocks. No single factor decides it. | https://www.canada.ca/en/revenue-agency/services/forms-publications/publications/it479r/archived-transactions-securities.html | archived, still cited |
| Superficial loss (taxable accounts, capital property): a loss is denied if the same or identical property is bought within 30 days before or after the sale and still held 30 days after. | CRA, https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/about-your-tax-return/tax-return/completing-a-tax-return/personal-income/line-12700-capital-gains/capital-losses-deductions.html | 2025–26 |

**Sim implication:** a bot doing several intraday round trips a day in cheap speculative stocks matches most IT-479R factors. In a **TFSA**, gains could be taxed as **business income** (fully taxable, with the holder jointly liable). In a **non-registered** account, gains could be business income rather than 50%-inclusion capital gains. If they are capital gains instead, frequent re-entry into the same tickers can trigger **superficial-loss** denials. For honest comparisons, report the $50 bot's results **pre-tax and at an assumed full marginal rate**, not as tax-free.

### 3d. US withholding tax on dividends
| Fact | Source (checked) | Date |
|---|---|---|
| Canada–US treaty Art. X(2): portfolio dividends are withheld at a maximum of **15%** (5% for ≥10% corporate holders). | Treaty consolidated text, https://www.canada.ca/en/department-finance/programs/tax-policy/tax-treaties/country/united-states-america-convention-consolidated-1980-1983-1984-1995-1997-2007.html | treaty as amended to 2007 |
| Art. XXI(2): dividends and interest received by an arrangement "operated exclusively to administer or provide pension, retirement or employee benefits" are **exempt**. In practice this covers RRSP/RRIF/LIRA, **not TFSA/FHSA/RESP**. In a TFSA the 15% cannot be recovered because there is no Canadian tax to credit it against. | same; e.g. https://mywealthwise.ca/en/blog/us-dividend-withholding-tax-tfsa-rrsp (secondary, for the TFSA point) | |
| Form **W-8BEN** establishes foreign status and claims treaty rates. Without it the default withholding is **30%**. | IRS, https://www.irs.gov/forms-pubs/about-form-w-8-ben | page updated Jan 2025 |

**Sim implication:** the intraday bot almost never holds over an ex-date, so this barely matters there. For the $100k daily bot's dividend income, **net 15% off US dividends** in taxable or TFSA accounts (0% in an RRSP; a foreign tax credit is available only in a taxable account).

---

## 4. Realistic execution costs for small orders in cheap or volatile US stocks

### 4a. Hard floor: the one-cent tick
For stocks at $1 and up, quotes move in $0.01 steps (Rule 612; see 4e for the delayed half-penny change). A stock can never quote tighter than 1 cent, so the **minimum** cost of crossing half the spread is:

| Price | Min 1-tick spread | Min half-spread (cost per side for a marketable order at NBBO) |
|---|---|---|
| $1 | 1.00% | **0.50%** |
| $2 | 0.50% | **0.25%** |
| $3 | 0.33% | **0.17%** |
| $5 | 0.20% | **0.10%** |
| $10 | 0.10% | 0.05% |
| $20 | 0.05% | 0.025% |

So **0.1% per side is the best-case cost at $5 and is too low below about $5**, even for a perfectly liquid, tick-constrained stock. Most sub-$5 small caps quote several cents wide, not one.

### 4b. Measured spreads on small retail orders
- **Schwarz, Barber, Huang, Jorion & Odean, "The 'Actual Retail Price' of Equity Trades", *Journal of Finance* 80 (2025) 2507–2541.** The authors placed about 75–85k real **$100–$5,000** market orders across six retail accounts, in a sample stratified across CRSP stocks. Working paper: https://microstructure.exchange/papers/Schwartz_et_al_,_2022_WP,_The_'Actual_Retail_Price'_of_Equity_Trades.pdf ; press release https://merage.uci.edu/press-releases/2022/10/Uncovering-the-Hidden-Retail-Prices-of-Zero-Commission-Stock-Trades.html
  - NBBO quoted spread (Table IV, all stocks): **median 0.28%, mean 0.64%, 75th percentile 0.68%, 90th percentile 1.66%**. Non-S&P 500 mean **0.77%**, S&P 500 mean 0.08%. The 10th-percentile price in the sample was $2.36, so cheap stocks were included.
  - Average price improvement was about **33% of the spread**, so the effective cost is roughly 2/3 of the half-spread per side.
  - Average **round-trip cost ranged from 0.07% to 0.46%** across broker accounts. Differences between brokers were large, partly driven by payment for order flow (PFOF) and routing.
- Implied **per-side** cost for non-S&P stocks: about 0.77%/2 × 0.67 ≈ **0.26%**. For the widest decile it is about 0.55% or more. Sub-$5 names cluster in the wide end.
- Academic literature confirms that spreads as a **percent of price** are much larger for low-priced stocks, partly because of the fixed tick (e.g. Hagströmer, "Bias in the effective bid-ask spread", *JFE* 2021, https://www.sciencedirect.com/science/article/pii/S0304405X21001458, which covers low-priced S&P 500 names).
- Honest gap: I did **not** find an authoritative 2024–2026 public table of percentage spreads by price bucket (<$1, $1–5, $5–10). The amended Rule 605 reports (4d) will start giving broker-level effective-spread statistics by order size from the August 2026 data onward.

### 4c. Market orders at the open and in volatile names
- Spreads follow an **intraday reverse-J / U shape: widest right after the open**, narrowing through the morning, rising slightly at the close (McInish & Wood, *J. Finance* 47(2), 1992, https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.1992.tb04408.x ; Chung, Van Ness & Van Ness, *JFE* 1999).
- FINRA: market orders "must be executed fully and promptly without regard to price", and in fast markets you may not get the quoted price. FINRA urges caution with unpriced orders near the open (https://www.finra.org/investors/investing/investment-products/stocks/order-types ; https://www.finra.org/investors/insights/market-liquidity-risk, Aug 4, 2026).
- **Limit Up–Limit Down (LULD)** bands: Tier 2 (non-S&P 500/Russell 1000) stocks above $3 have 10% bands, and **$0.75–$3 stocks have 20%** bands. A 5-minute trading **pause** follows if the stock stays at a band for 15 seconds (https://www.finra.org/investors/insights/guardrails-market-volatility, Nov 26, 2024). A 5-minute-bar sim that ignores halts will fill orders that could not have been filled.

### 4d. PFOF, Rule 605/606, and withdrawn proposals
- **Rule 605 amendments** (adopted **March 6, 2024**, https://www.sec.gov/newsroom/press-releases/2024-32) extend reporting to broker-dealers with **≥100,000 customer accounts**. They add **odd-lot and fractional-share orders** and group orders by **notional dollar size**, add realized-spread and "effective over quoted spread" metrics, and require human-readable summary reports. The compliance date moved from Dec 14, 2025 to **August 1, 2026** (https://www.federalregister.gov/documents/2025/10/02/2025-19316/extension-of-compliance-date-for-disclosure-of-order-execution-information). The first reports (for August 2026) were due **before the end of September 2026** (FINRA Information Notice, Jun 17, 2026, https://www.finra.org/rules-guidance/notices/information-notice-20260617). These reports are now the best public source for checking a broker's real effective spread on small orders.
- Rule 606 (routing and PFOF disclosure) is unchanged in substance since the 2018 amendments.
- The SEC **withdrew** the Order Competition Rule and Regulation Best Execution proposals on **June 12, 2025** (https://www.regulatoryandcompliance.com/2025/06/sec-formally-withdraws-fourteen-rule-proposals/). PFOF-based wholesaler routing therefore continues. Per the JF 2025 study above, price improvement for identical small orders differs by several basis points or more across brokers.
- **Regulatory sell-side fees, still charged under $0 commission:** SEC Section 31 fee of **$20.60 per $1M** of sales from **April 4, 2026** (it was $0.00 before that date; https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2). FINRA TAF of **$0.000195/share (max $9.79) in 2026**, rising to $0.000232 in 2027 (https://www.finra.org/rules-guidance/rule-filings/sr-finra-2024-019/fee-adjustment-schedule). On a $50 sale these come to about $0.001 + $0.002. Many firms **round each fee up to $0.01**, which would make it about 0.02%–0.04% of a $50 sale. That is dealer-specific; check the fee schedule.

### 4e. Tick size and access fees (SEC Nov 2024 rule), now delayed to November 2027
- The SEC adopted amendments on **Sept 18, 2024** (Release 34-101070, https://www.sec.gov/files/rules/final/2024/34-101070.pdf):
  - **Rule 612:** a **$0.005 tick** for stocks ≥$1 whose time-weighted average quoted spread is ≤$0.015 ("tick-constrained").
  - **Rule 610(c):** access-fee caps cut from 30 to **10 mils ($0.001/share)** for stocks ≥$1, and to **0.1% of price** for stocks <$1 (from 0.3%).
  - Faster rollout of the round-lot and odd-lot information definitions.
- Original compliance date: Nov 3, 2025. **Delayed:** the SEC order of Oct 31, 2025 moved it to Nov 2026 (https://www.sec.gov/newsroom/press-releases/2025-130-sec-issues-exemptive-order-regarding-compliance-certain-rules-under-regulation-nms). Release 34-105656, dated **June 11, 2026**, extended relief for Rules 600(b)(89)(i)(F), 610(c) and 612 to the **first business day of November 2027** (https://www.sec.gov/files/rules/exorders/2026/34-105656.pdf). The Chairman also asked staff to review 610(c) and 612 by year-end 2026, so they may change again (https://www.sec.gov/newsroom/speeches-statements/atkins-statement-minimum-pricing-increments-access-fee-caps-061126). The same day the SEC **proposed rescinding Rule 611 (the trade-through rule)** (https://www.mofo.com/resources/insights/260612-sec-proposes-landmark-rollback-of-core-regulation). The D.C. Circuit denied the industry challenge on Oct 14, 2025.
- The **round-lot** tiers **did** take effect Nov 3, 2025: 100 shares up to $250, 40 shares for $250.01–$1,000, 10 shares for $1,000.01–$10,000, and 1 share above that, reset each May and November (https://www.schwab.com/learn/story/round-lots-regulatory-changes ; CTA FAQ https://www.ctaplan.com/publicdocs/ctaplan/CTA_Round_Lot_Changes_FAQ.pdf). For cheap stocks the round lot is still 100 shares, so **every order from these bots is an odd lot**.

**Sim implication:** today the 1-cent tick still applies to every stock ≥$1, and half-penny ticks are **not** expected before Nov 2027 at the earliest. The tick floor in 4a is the current reality. A sim should use **price-dependent slippage**, for example `max(0.1%, k × 0.5 × tick / price)` plus a liquidity term, not a flat 0.1%.

---

## 5. Whole shares, a $40 account, and minimum-price issues

- **Diversification is arithmetic-limited.** With $40, a single $7 stock allows 5 shares ($35, with 12.5% left as cash). Two positions of about $20 each only work for stocks under about $20, and even then rounding leaves 5%–30% cash. The **investable universe shrinks toward sub-$10 names, where spreads are widest** (section 4). Every order is an odd lot (4e).
- **Rounding error on target weights** is large. On a $20 target in a $6 stock you get 3 shares ($18), a 10% miss. The sim should round down to whole shares and **carry the leftover cash** (it may already do this; it is worth checking against the whole-share assumption).
- **Penny-stock rules.** SEC Rule 3a51-1 defines a "penny stock" as under $5, but **exchange-listed** stocks that meet exchange standards are excluded (https://www.law.cornell.edu/cfr/text/17/240.3a51-1). OTC sub-$5 stocks bring extra broker paperwork (Rule 15g-9), and many dealers restrict them. **Keep the universe to exchange-listed stocks.**
- **Delisting risk at very low prices.** Nasdaq requires a $1.00 minimum bid (a deficiency follows 30 consecutive business days below $1). The SEC approved a rule on Dec 5, 2025, **effective Jan 19, 2026**, under which a closing bid **≤$0.10 for 10 consecutive trading days triggers immediate delisting determination and suspension**, with no automatic stay (https://natlawreview.com/article/nasdaq-implements-accelerated-delisting-securities-trading-below-010-ten). Sub-$1 names also carry reverse-split and gap risk that a daily bar sim will understate.
- **Fractional shares** would remove the diversification limit. Some dealers support them for US stocks, but availability, order types (often market-only, sometimes only during market hours) and execution quality vary. The amended Rule 605 now covers fractional orders. No dealer is recommended here.
- For **stocks under $1**, sub-penny quotes ($0.0001) are allowed, and the access-fee cap is currently 0.3% of price (0.1% after Nov 2027 if unchanged). Taker fees alone can be about 0.3% per side on such names.

---

## Summary: sim assumptions vs. reality

| Assumption | Verdict | Suggested replacement |
|---|---|---|
| 0.1% slippage per side | **Too low** under about $10, and far too low under $5 or at the open | Price-dependent cost: `half_spread = max(0.5 × $0.01/price, observed or assumed spread/2)` plus about 0.05%–0.1% impact/volatility. Rough per-side figures: **≥$20 liquid: 0.05%–0.10%; $5–20: 0.15%–0.30%; $1–5: 0.3%–1.0%; <$1: 1%–3%**. At the first 5-minute bar after the open, use **1.5×–2×**. |
| Zero commission | Close, but not zero in total | Add sell-side regulatory fees (Sec 31 $20.60/M plus TAF $0.000195/share), possibly rounded up to $0.01 per fee. For a CAD-funded account, add **1.5%–2% FX per conversion**. |
| T+1 settlement | Right cycle; **enforcement matters** | For the $50 cash bot: **sale proceeds usable only for buys that are not sold until the next business day**. Effectively one round trip per settled dollar per day. |
| Whole shares | Correct for the $40 bot | Round down, carry the cash residual, restrict to exchange-listed stocks, exclude <$1 (Nasdaq $0.10 rule, fees) |
| PDT | Not applicable | Cash accounts were never subject to it, and PDT was eliminated June 4, 2026 (firms have until Oct 20, 2027 to implement) |
| Taxes | Not modelled | Frequent intraday trading can be treated as business income (TFSA taxable: *Ahamed*, 2024 FCA 108). Report results pre-tax and at a full marginal rate. Apply 15% US withholding on dividends outside an RRSP. |
