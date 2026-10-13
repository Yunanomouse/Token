# Compliance checklist

Last updated: 2026-10-13 · Owner: Matthew Marinier, Calgary, Alberta

The legal steps for running Token as an online business from Calgary, grouped by when they start to apply. This is general research, not legal advice. Items marked **Verify** could not be confirmed against a primary source. Have an Alberta lawyer and an accountant review this list before charging money.

## Stage 1: now (free, local, public repo)

- [x] **License and terms.** MIT [LICENSE](LICENSE) in the author's legal name, plus [Terms](TERMS.md), [Privacy](PRIVACY.md), [Cookies](COOKIES.md) and [Code of Conduct](CODE_OF_CONDUCT.md).
- [x] **Not-advice wording** on the README, terms, OpenBB guide and script, and incorporation checklist. A disclaimer alone does not avoid securities registration (see "Never" below), so the product itself must stay non-advisory ([CSA/CIRO Staff Notice 31-369](https://www.bcsc.bc.ca/-/media/PWS/New-Resources/Securities-Law/Instruments-and-Policies/Policy-3/31369-CSA-and-CIRO-Staff-Notice-December-11-2025.pdf)).
- [x] **No protected titles.** Don't call yourself a CPA, chartered professional accountant, accountant, lawyer or registered adviser. Fines start at $2,000 under the [Alberta CPA Act s.7 and s.149](https://kings-printer.alberta.ca/documents/Acts/C10P2.pdf), and at $4,000 under the [Legal Profession Act s.106 to s.109](https://kings-printer.alberta.ca/documents/Acts/L08.pdf).
- [x] **Market data stays personal.**
  - Downloaded CSVs are gitignored and carry a `SOURCE.txt` record.
  - The OpenBB guide explains [Yahoo's terms](https://legal.yahoo.com/ca/en/yahoo/terms/otos/index.html): no commercial use and no redistribution.
  - No affiliation with OpenBB, Yahoo, exchanges or brokers is claimed or held.
- [x] **Open-source licenses respected.**
  - Token only tells users to install the AGPL `openbb-yfinance` package; it doesn't bundle it.
  - The guide lists the licenses and the conditions that would trigger AGPL duties.
- [x] **No tracking.** No analytics, cookies or session replay. Enforced by CI (`scripts/check_no_session_replay.py`).
- [ ] **Check the name "Token"** in the [Canadian Trademarks Database](https://ised-isde.canada.ca/cipo/trademark-search/srch) before spending on branding. It is a common word, and software and finance classes are crowded.
- [ ] **Accurate, sourced claims** in the README, the `founder/` docs and any post.
  - Under the Competition Act, a claim is judged by its general impression.
  - "Save $X" claims need adequate testing before they are made.
  - Comparisons with Wealthsimple, TurboTax and others must be true and current, and use names only, no logos. ([Competition Bureau guide](https://competition-bureau.canada.ca/en/how-we-foster-competition/education-and-outreach/guide-june-2024-amendments-competition-act))
- [ ] **Keep business records from day one.** Keep receipts for any expenses for 6 years, since they become deductible later ([CRA record keeping](https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/keeping-records.html)).

## Stage 2: before a waitlist or email list

- [ ] **Register the trade name.**
  - Operating publicly under any name other than "Matthew Marinier" (for example "Token") requires a Declaration of Trade Name with Alberta Corporate Registry, through a registry agent ([Alberta](https://www.alberta.ca/register-business-name)).
  - The registration fee is about $60. **Verify.**
- [ ] **CASL consent.** ([CRTC](https://crtc.gc.ca/eng/internet/anti.htm), [fightspam.gc.ca](https://fightspam.gc.ca))
  - Use an unticked checkbox and double opt-in.
  - Log the time, the source and the exact wording each person agreed to, and keep proof of consent.
  - Every email names you, gives a mailing address and has a working unsubscribe link, honoured within 10 business days.
  - Penalties go up to $1M per violation for an individual.
- [ ] **Update the privacy policy before collecting anything.**
  - Alberta PIPA governs an Alberta business. PIPEDA covers data that crosses provincial borders. Quebec Law 25 applies if Quebec residents sign up.
  - Name yourself as the privacy contact.
  - Collect email only.
  - Sources: [OIPC Alberta](https://oipc.ab.ca/), [OPC](https://www.priv.gc.ca/en/privacy-topics/privacy-laws-in-canada/the-personal-information-protection-and-electronic-documents-act-pipeda/), [CAI Quebec](https://www.cai.gouv.qc.ca).
- [ ] **Breach plan.** If a breach creates a real risk of significant harm:
  - Notify the Alberta OIPC without unreasonable delay ([guidance](https://oipc.ab.ca/wp-content/uploads/2024/04/Guidance-for-Notifying-the-OIPC-about-a-Privacy-Breach-Under-PIPA-April-2024.pdf)).
  - Notify the people affected.
  - Keep a log of every breach for 24 months.
- [ ] **Session replay stays off,** and no analytics cookies without opt-in consent ([COOKIES.md](COOKIES.md)).
- [ ] **Market to Canada only.** Price in CAD and state that the service is for Canadian residents. This avoids [GDPR Article 3(2)](https://gdpr-info.eu/art-3-gdpr/) obligations.

## Stage 3: before charging money (Planner subscription or referral fees)

- [ ] **City of Calgary.**
  - Get a Business ID and home occupation approval (Class 1).
  - Call 403-268-5311 to confirm whether an online software business needs a licence. **Verify.**
  - Sources: [not-required list](https://www.calgary.ca/for-business/licences/not-required.html), [Home Occupation Class 1](https://www.calgary.ca/PDA/pd/Documents/carls/development-permit/home-occupation-class-1.pdf).
- [ ] **Internet sales contract rules** (Alberta Consumer Protection Act and Internet Sales Contract Regulation, purchases over $50).
  - Before purchase, disclose: legal name and address, a product description, the itemized price in CAD, and the cancellation and refund policy.
  - Let the buyer accept, decline or correct the order.
  - Email a copy of the agreement within 15 days.
  - Honour the statutory cancellation rights. Already written into [TERMS.md section 8](TERMS.md#8-paid-services-and-payment-terms). ([Alberta guide](https://open.alberta.ca/dataset/07cdf766-de64-473f-b57a-dda11c63f05e/resource/f7874d1f-3a63-41dc-8978-ed78f7cb0879/download/internet-shopping.pdf))
- [ ] **All-in pricing.**
  - The advertised price must include every mandatory fee; only sales tax may be added.
  - Drip pricing is a Competition Act violation.
  - Send renewal reminders and allow easy cancellation.
- [ ] **GST/HST.**
  - Register once taxable revenue, including referral fees, passes $30,000 in a calendar quarter or over the last four quarters ([CRA](https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/gst-hst-businesses/gst-hst-register/register-small-supplier.html)).
  - Charge the rate of the customer's province.
  - Register for QST if sales to Quebec consumers pass $30,000 in 12 months ([Revenu Québec](https://www.revenuquebec.ca/en/)).
- [ ] **Income tax.**
  - Report the business on form T2125 with the T1 return.
  - The balance owing is due April 30; self-employed filers have until June 15 to file ([CRA T2125](https://www.canada.ca/en/revenue-agency/services/forms-publications/forms/t2125.html)).
- [ ] **Payment processor.** Card details are handled by the processor, never stored by Token. The processor's own terms apply.
- [ ] **CPA referral fees.**
  - Have a written agreement with each firm, confirming they comply with CPA Alberta Rule 216 ([rules](https://www.cpaalberta.ca/-/media/Files/Protecting-the-Public/Governing-Documents/CPAAlbertaRulesofProfessionalConductwithGuidance_070115.pdf); **Verify** the current wording).
  - Before any introduction, tell the user the fee and get their written consent.
  - Never refer the firm's assurance clients.
  - Consider a flat listing fee instead of a per-client commission.
- [ ] **No broker affiliate pay** without a written referral arrangement and disclosure next to the link (Notice 31-369).
- [ ] **Hosted Planner data.**
  - Use licensed market data only, never Yahoo/yfinance.
  - Never bundle `openbb-yfinance`.
  - Exchange data redistribution needs a licence ([TMX](https://www.m-x.ca/en/trading/data/market-data-services)).
- [ ] **Insurance.** Get errors and omissions (professional liability) and cyber cover. Roughly $500 to $1,500 a year. **Verify.**
- [ ] **Liability limits.**
  - Disclaimers protect a paid service only partly. Courts can refuse exclusion clauses ([Tercon, 2010 SCC 4](https://scc-csc.lexum.com/scc-csc/scc-csc/en/item/7837/index.do)).
  - Consumer Protection Act rights can't be waived.
  - Keep output accurate, dated and sourced. That is the real protection.
- [ ] **Consider incorporating** to separate personal assets from business debts (NUANS name search plus Articles).
- [ ] **Lawyer review** of TERMS.md, PRIVACY.md and the checkout flow.

## Never (these would require a licence or break the law)

- **No investment advice.** Never give buy or sell signals, stock picks, model portfolios, watchlists presented as picks, copy trading, or advice tailored to a person about securities.
  - Doing that as a business requires registration as an adviser under the [Alberta Securities Act s.75](https://kings-printer.alberta.ca/documents/Acts/S04.pdf). The exemption for general advice is NI 31-103 s.8.25, and it is lost once advice is tailored.
  - Penalties go up to $5M and 5 years in jail (s.194), or $1M per contravention administratively (s.199). A "not advice" disclaimer does not change this.
- **No undisclosed interest.** Never mention a security you hold, or are paid about, without a specific, prominent disclosure at the start.
- **No returns or legal documents for others.**
  - Never prepare or file tax returns for other people. More than 5 paid returns a year also requires CRA EFILE registration ([CRA](https://www.canada.ca/en/revenue-agency/services/e-services/digital-services-tax-preparers/mandatory-electronic-filing-tax-preparers.html)).
  - Never prepare articles, bylaws or share structures for other people.
- **No aggressive tax positions.** Never promote a position you know is wrong, such as filing active trading gains as capital gains. Third-party penalties under ITA s.163.2 run up to $100,000 plus fees ([CRA IC01-1R2](https://www.canada.ca/en/revenue-agency/services/forms-publications/publications/ic01-1/third-party-civil-penalties.html)).
- **No data redistribution.** Never publish, sell or host Yahoo or exchange data.
- **No marketing without consent.** Never send marketing emails without CASL consent.
- **No fake proof.** Never invent testimonials, user counts or results. That is deceptive marketing under the Competition Act, and since June 2025 consumers and competitors can bring these cases to the Competition Tribunal themselves.

## To confirm with a lawyer or accountant

- The current text of NI 31-103 s.8.25, and of CPA Alberta Rule 216.
- Whether Calgary requires a licence for an online software business.
- The Alberta trade name fee, and the Internet Sales Contract Regulation refund deadline.
- Whether CASL's private right of action is still suspended in 2026.
