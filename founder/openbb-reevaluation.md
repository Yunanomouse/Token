<!-- openbb re-evaluation · 2026-10-13 · input: re-evaluate OpenBB in Token using the founder skills -->

# OpenBB re-evaluation

What each founder skill concluded about OpenBB, what was tested, what is done, and what is left. Sources for outside claims are in the skill files linked here.

## Verdict

Keep OpenBB as an optional extra for price history, repaired and pinned. Drop it as a product feature or headline. The tax decision (sole prop vs RRSP vs CCPC) and the broker import are the product. OpenBB is a supplier, not the reason anyone adopts Token.

## What was tested (2026-10-13, clean Python 3.13 virtualenvs)

| Check | Result |
|---|---|
| `pip install openbb` (5.0.0), then the repo's quickstart | Broken. 5.0 no longer bundles the equity commands or the yfinance provider. Every ticker failed with `'App' object has no attribute 'equity'` and the script still printed "Done". Step 3 of the guide failed the same way. |
| `pip install openbb-core openbb-equity openbb-yfinance` (2.0.x) | Works. AAPL 251 rows, SHOP.TO 250, BTC-USD 365. About 730MB installed vs 1.2GB for the full bundle. |
| `openbb-cli` 2.0 with the guide's old `/equity/price/historical` syntax | Changed. The new form `openbb equity.price.historical --symbol AAPL --provider yfinance` works and prints JSON. |
| Licenses (installed package metadata) | `openbb-core` and `openbb-equity` Apache-2.0. `openbb-yfinance` AGPL-3.0-only. |
| OpenBB the company | On 2026-08-25 it said it could not find product-market fit and is releasing its suite as open source. On 2026-10-01 a non-profit, OpenBQ, took over stewardship and Workspace went to FINOS ([announcement](https://openbb.co/blog/openbb-belongs-to-everyone)). No package maintenance plan published. |

## What each skill said

| Skill | OpenBB finding |
|---|---|
| [validate-idea](validate-idea.md) | Does not set Token apart: price history computes no profit or tax. Keep it optional for non-coders. |
| [competitor-matrix](competitor-matrix.md) | A supplier with a weakening owner, not a competitor. OpenBB raised $8.5M and could not turn free market data into a business, which says the tax decision is the paid part. |
| [persona-gen](persona-gen.md) | None of the 3 personas adopts Token for OpenBB. The primary (a coder) would only use it to feed the import. The secondary gives up at the Python install. The third never uses a laptop for money. |
| [user-interviews](user-interviews.md) | Two hypotheses to test: do traders need outside prices to finish their tax (H2), and will non-coders install Python (H3). Each has a keep or drop rule. |
| [mvp-scope](mvp-scope.md) | Won't have as a feature. Half a day of repair in the MVP. Keep it out of core requirements so the AGPL provider is never a calculator dependency. |
| [pricing-strategy](pricing-strategy.md) | No tier includes market data. A hosted Planner must never bundle `openbb-yfinance` (AGPL), and yfinance data is personal use only, so no hosted price data. |
| [go-to-market](go-to-market.md) | Don't build an OpenBB extension for distribution: no listing exists, the audience is global quants, and the steward has no extension plan. Only add the `openbb` GitHub topic. |
| [metrics-dashboard](metrics-dashboard.md) | Not a metric. A weekly yes/no check that the pinned guide still runs, because it already broke once without warning. |
| [landing-page](landing-page.md), [email-sequence](email-sequence.md) | Not mentioned. |

## Done in this branch

- [x] `docs/openbb_setup.md`: pinned install line (`openbb-core`, `openbb-equity`, `openbb-yfinance`, all `>=2,<3`), a warning against plain `pip install openbb`, an "optional extra" and stewardship note, the new CLI syntax, a troubleshooting entry for the `equity` error, and a license note.
- [x] `examples/openbb_quickstart.py`: same pinned install line; exits with the install command when the equity commands are missing; exits non-zero when no ticker succeeds instead of printing "Done". Retested: works on the pinned install, gives the correct error on the 5.0 bundle.
- [x] `.github/workflows/openbb-check.yml`: weekly (Mondays) and on PRs touching OpenBB files, installs the pinned packages, runs the quickstart, fails if any ticker returns 100 rows or fewer.
- [x] `examples/market_data/` added to `.gitignore`.
- [x] README lists the OpenBB files as optional.

## Still to do (needs the founder)

1. ~~**Add a LICENSE file.**~~ Done 2026-10-13: MIT, plus Terms, Privacy, Cookie and Code of Conduct pages. The repo has none, so it is not legally open source yet. Pricing, landing page and go-to-market all depend on this. Note the split: whatever license Token picks, the optional OpenBB yfinance provider stays AGPL.
2. **Add the `openbb` GitHub topic** to the repo (Settings, About). Zero cost; it is the only OpenBB channel go-to-market recommends.
3. **Watch the weekly check.** GitHub turns off scheduled workflows in public repos after 60 days without activity. If it fails twice in a row, mark the guide "currently broken" in the README.
4. **Ask interview questions Q7 to Q10 and Q16** (see [user-interviews](user-interviews.md)). If 3 or more of 8 coders used outside prices to finish their tax, OpenBB earns a role in the import, valuing open positions at December 31. If 1 or fewer did, leave it as is.

## Revisit when

- 10 users ask to value open positions at December 31, or
- OpenBQ publishes a maintenance plan or an extension listing process, or
- the weekly check fails and the pinned packages can't be fixed, in which case remove the guide rather than ship a broken one.
