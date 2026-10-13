<!-- /founder:competitor-matrix · 2026-10-13 · input: Token: a local, open-source toolkit for self-directed Canadian active traders that combines 2026 tax data and a sole-prop vs RRSP vs CCPC calculator with free OpenBB market data. Target: Canadian day/swing traders with $30K to $250K trading profit. -->

# Competitor matrix: Token

Assumption: Token stays free and open source for now, as in `founder/product-brief.md`. Nothing here replaces a saved fact.
Assumption: Prices are as shown on each page, checked 2026-10-13. Canadian tax tools appear to quote CAD, US journals and OpenBB quote USD.

## 1. Market landscape

| # | Competitor | Founded and funding | Pricing (checked 2026-10-13) | Segment | Key differentiator |
|---|---|---|---|---|---|
| 1 | **OpenBB** (Open Data Platform + Workspace), [openbb.co](https://openbb.co) | $8.5M seed from OSS Capital and angels ([TechCrunch](https://techcrunch.com/2024/10/07/fintech-openbb-aims-to-be-more-than-an-open-source-bloomberg-terminal/)). No later round found ([CB Insights](https://www.cbinsights.com/company/openbb)). On 2026-08-25 it said it could not find product-market fit and is open-sourcing the whole suite; on 2026-10-01 stewardship moved to the OpenBQ non-profit, with Workspace going to FINOS ([blog](https://openbb.co/blog/openbb-belongs-to-everyone)) | ODP: free, Apache 2.0 ([GitHub](https://github.com/OpenBB-finance/OpenBB)). Workspace Community: free, 20 Copilot queries/day. Lite: $2,400/yr. Pro: custom ([pricing](https://openbb.co/pricing)) | Prosumer to institutional research teams | Open financial data platform and AI workspace |
| 2 | **Wealthsimple Tax**, [wealthsimple.com/en-ca/tax](https://www.wealthsimple.com/en-ca/tax) | Parent raised up to C$750M at C$10B valuation, Oct 2025 ([CP24](https://www.cp24.com/news/canada/2025/10/27/wealthsimple-announces-its-raising-up-to-750m-in-new-capital-to-accelerate-growth/)) | Basic: pay what you want, $0 OK. Plus: $40. Pro: $80, expert help ([page](https://www.wealthsimple.com/en-ca/tax)) | Consumer | File your return free, owned by the broker many targets already use |
| 3 | **TurboTax Canada**, [turbotax.intuit.ca](https://turbotax.intuit.ca) | Intuit product. Funding: not applicable | Self-Employed online about $49.99, per third-party review; official page returned 404 ([WealthNorth](https://wealthnorth.ca/taxes/tax-software/turbotax-canada-review/)) | Consumer, sole props | Best-known filing brand, T2125 support |
| 4 | **TaxTips.ca calculators**, [taxtips.ca](https://www.taxtips.ca/calculators/canadian-tax/canadian-tax-calculator.htm) | Not found | No fee shown on the calculator page | Prosumer, CPAs | Detailed 2025/2026 calculator with self-employment, CPP, RRSP/FHSA savings; covers 12 jurisdictions, Quebec not listed |
| 5 | **AdjustedCostBase.ca**, [adjustedcostbase.ca](https://www.adjustedcostbase.ca/) | Established 2010 (own site). Funding: Not found | Basic $0/yr. Premium $49/yr adds broker import, T1135, CDA tools ([site](https://www.adjustedcostbase.ca/)) | Prosumer investors | ACB and superficial-loss tracking for capital gains |
| 6 | **TraderSync**, [tradersync.com](https://tradersync.com) | Founded 2014 ([CB Insights](https://www.cbinsights.com/company/tradersync)). Funding: Not found | Pro $29.95/mo, Premium $49.95/mo, Elite $79.95/mo ([StockBrokers.com](https://www.stockbrokers.com/review/tools/tradersync)); own pricing page blocked | Prosumer day traders | AI-coached trading journal, 900+ broker imports |
| 7 | **Tradervue**, [tradervue.com](https://www.tradervue.com) | Founded 2011, acquired by SureSwift Capital 2021 ([NexusFi](https://nexusfi.com/d/journals/tradervue/)) | Free: 30 trades/month ([help](https://help.tradervue.com/article/3420-trade-import-quota)). Silver $29.95/mo, Gold $49.95/mo ([StockBrokers.com](https://www.stockbrokers.com/review/tools/tradervue)) | Prosumer day traders | Long-running journal with a free tier |
| 8 | **Status quo: CPA + spreadsheet + broker export** | Not applicable | Self-employed personal return $200 to $500, wider range $150 to $1,500 ([WealthNorth](https://wealthnorth.ca/taxes/filing/when-to-hire-accountant-vs-diy-taxes/)). CCPC upkeep $2,000 to $5,000+/yr (repo's own estimate, `docs/trader_taxation.md`) | Everyone | Human judgment and filing, once a year |

## 2. Feature comparison matrix

"No" means the feature is absent from the pages checked. "Unknown" means I could not confirm either way.

| Feature | Token | OpenBB | WS Tax | TurboTax | TaxTips | ACB.ca | TraderSync | Tradervue | CPA + sheet |
|---|---|---|---|---|---|---|---|---|---|
| Free market data in Python | Building (thin) | Yes | No | No | No | No | Partial (charts) | Partial (charts) | No |
| 2026 tax rates, all 14 jurisdictions, machine-readable | Building | No | No | No | No | No | No | No | No |
| Sole prop vs max RRSP vs CCPC comparison | Building | No | No | No | Unknown | No | No | No | Yes |
| Business-income (T2125) tax estimate | Building | No | Yes | Yes | Yes | No | No | No | Yes |
| Files the return with CRA | No | No | Yes | Yes | No | No | No | No | Yes |
| Broker trade import | Planned | Partial (SnapTrade in Workspace) | Unknown | Unknown | No | Yes (Premium) | Yes | Yes (paid sync) | Partial (manual) |
| Questrade support | Planned | Partial ([SnapTrade lists it](https://snaptrade.com/brokerage-integrations)) | Unknown | Unknown | No | Unknown | Unknown | Unknown | Yes |
| ACB and superficial-loss tracking | No | No | Partial | Unknown | No | Yes | No | No | Partial |
| Business vs capital classification and TFSA trading flag | Planned | No | No | Unknown | No | No | No | No | Yes |
| Year-to-date tax and instalment estimate | Planned | No | No | No | Partial (manual inputs) | No | No | No | Partial |
| Trade performance analytics | No | Partial | No | No | No | No | Yes | Yes | No |
| Runs locally, open source | Yes | Yes (ODP, Apache 2.0) | No | No | No | No | No | No | Partial (spreadsheet) |

## 3. Positioning gaps

**Gap 1: A forward-looking "should I incorporate" answer for traders.**
- Missing: no software tool checked compares sole prop, max RRSP and CCPC for trading profit. Filing tools look back at last year. TaxTips models one person, not the corporate route (Unknown if a separate tool exists).
- Why it matters: the repo's Alberta example shows $9,720/yr from a max RRSP and $31,203 of deferral through a CCPC on $150,000 profit. Today that answer costs a CPA meeting.
- Difficulty: low. The calculator already exists.
- Head start: Estimate: 12 to 24 months. Filing vendors ship once a year around tax season and their product is a T1 filer, not a planner. A CCPC model needs corporate tables they do not expose to consumers.

**Gap 2: Classification and account guardrails tied to real trades.**
- Missing: no tool flags "this activity looks like business income" or "you are day trading in a TFSA". ACB.ca and filing tools assume capital gains. Journals ignore tax.
- Why it matters: filing business income as capital gains, or trading in a TFSA, are the two most expensive mistakes in `docs/trader_taxation.md`.
- Difficulty: medium. Needs trade import plus simple rules (frequency, holding period, account type), with careful "not tax advice" language.
- Head start: Estimate: 12 months. A journal could add it, but none shows Canadian tax features today, and the liability makes US-first vendors cautious.

**Gap 3: Year-to-date tax and instalments from a local broker export.**
- Missing: journals have the P&L, tax tools have the rates, nobody joins them during the year. Running it locally means no broker credentials leave the machine.
- Why it matters: instalment interest is non-deductible. A monthly number is what brings users back.
- Difficulty: medium. Questrade and IBKR CSV parsers plus the existing JSON tables.
- Head start: Estimate: 6 to 12 months. Wealthsimple could build this for its own clients faster than anyone, but only for Wealthsimple accounts.

## 4. Threat assessment

| Rank | Competitor | Threat | Resources | Overlap | Iteration speed |
|---|---|---|---|---|---|
| 1 | Wealthsimple Tax | High | C$10B parent, C$550M primary in Oct 2025 ([CP24](https://www.cp24.com/news/canada/2025/10/27/wealthsimple-announces-its-raising-up-to-750m-in-new-capital-to-accelerate-growth/)) | Medium: tax estimate and filing, free entry tier, already holds many target users' trades | Changelog: Not found |
| 2 | CPA + spreadsheet | Medium | One human per client, $200 to $500 per return | High on the CCPC decision, low on tooling | Once a year |
| 3 | TraderSync | Low | Funding: Not found | Low: owns the active-trader journal habit, no Canadian tax features seen | Release history: Not found |

**OpenBB is not a threat. It is a supplier with a weakening owner.** The company said it could not reach product-market fit and handed its code to OpenBQ and FINOS ([blog](https://openbb.co/blog/openbb-belongs-to-everyone)). It shipped about 30 blog-announced features in 2026 ([blog index](https://openbb.co/blog/)), all aimed at institutional Workspace users, none at tax. The ODP code stays Apache 2.0, so Token can keep using or vendoring it, but maintenance pace after the handover is unknown.

## 5. Strategic recommendations

- **Position to own:** "The incorporation and RRSP decision for Canadian traders making $30K to $250K." Not a data terminal, not a filer, not a journal. Start in Alberta and Ontario, where the worked examples already exist.
- **Feature to ship first:** Questrade and IBKR activity-export import feeding the existing sole prop vs RRSP vs CCPC calculator. It turns a typed guess into the trader's real number, and it is the input Gaps 2 and 3 also need.
- **Competitor to watch:** Wealthsimple. It has the trades, the tax product and the brand. If it adds an "incorporate?" or YTD-tax view for active traders, the planner wedge narrows to non-Wealthsimple brokers (Questrade, IBKR).

**What this means for OpenBB's role in Token:**
- Treat OpenBB as one optional data adapter behind Token's own interface, not the headline. "Powered by OpenBB" now signals a project in transition.
- Make broker CSV import the main data path. OpenBB price history is useful for marking open positions to market at year end, not for realized P&L.
- Keep the yfinance reliability test from the product brief, and add a fallback provider. Both yfinance breakage and slower ODP maintenance are now real risks.
- OpenBB's own result is a warning: free market data alone did not become a business even with $8.5M and 74k GitHub stars ([GitHub](https://github.com/OpenBB-finance/OpenBB)). The tax decision is what Token can charge for.
- There is an upside: OpenBB's open users are technical traders who may follow the project to Token. [Count of Token users who arrived from OpenBB channels]

Saved to `/home/user/Token/founder/competitor-matrix.md`. Next: `/founder:pricing-strategy`, `/founder:go-to-market`.
