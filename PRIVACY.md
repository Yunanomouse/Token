# Privacy Policy

Last updated: 2026-10-13

Token is a set of files and scripts you run on your own computer. This policy explains what happens to your information when you use it. In short: **the author collects nothing.**

## 1. What Token collects

Nothing. Token has no accounts, no sign-up, no analytics, no telemetry and no tracking.

- The calculators, tax data, spreadsheets and documents run or open entirely on your computer.
- Any income figures, broker exports or results you use stay on your computer. Token never sends them to the author or to anyone else.
- Files Token creates, such as CSVs in `examples/market_data/` or Excel outputs, are saved locally. You control them and can delete them at any time.

## 2. Session replay is off for everyone

Session replay (recording a user's clicks, scrolling, typing or screen so it can be played back later) is turned off for every user of Token. That covers anyone who uses the tools, and any future website, waitlist, hosted planner or email page.

- Token contains no session replay or session recording code. This includes Hotjar, FullStory, LogRocket, Microsoft Clarity, Smartlook, Mouseflow, and the replay features of PostHog, Sentry and Datadog.
- A CI check (`scripts/check_no_session_replay.py`, run on every push and pull request) fails if any such code is added.
- No user can be opted in to session replay, and no future Token service will turn it on.

GitHub and other third-party sites run their own tools under their own policies, outside Token's control (see section 3).

## 3. Third parties you may connect to

Some actions involve other services. Each has its own privacy policy, and the author does not control or receive their data.

| Action | Who receives data | What they may receive |
|---|---|---|
| Visiting or cloning the repository | GitHub | Your IP address, browser details, and your account if signed in. See the [GitHub Privacy Statement](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement). |
| Installing Python packages with `pip` | The Python Package Index (PyPI) | Your IP address and the packages you download. |
| Running the optional OpenBB script or guide | Yahoo Finance, through the `openbb-yfinance` package | Your IP address and the tickers you request. |
| Opening an issue or pull request | GitHub, and anyone who can view the repository | Whatever you write, plus your GitHub username. Don't post broker exports, account numbers, SINs or tax figures. |

## 4. Your broker exports and tax information

Treat broker exports and tax documents as sensitive. Before you share any of them, for example in an issue or with a tester, remove account numbers, names, addresses and Social Insurance Numbers. The author will never ask you to send these.

## 5. Cookies

Token itself sets no cookies. See the [Cookie Policy](COOKIES.md).

## 6. Future services

There is no website sign-up, email list or hosted service today. If one launches, this policy will be updated before it collects anything. The update will say what is collected, why, where it is stored, how long it is kept, and how to have it deleted. It will follow Canada's Personal Information Protection and Electronic Documents Act (PIPEDA), any provincial privacy law that applies, and Canada's Anti-Spam Legislation (CASL) for email.

## 7. Children

Token is meant for adults managing their own taxes and trading. It is not directed at children.

## 8. Changes

Updates are dated at the top. The repository's git history keeps every earlier version.

## 9. Contact

Privacy questions: open an issue at https://github.com/Yunanomouse/Token/issues. Don't include personal or financial details in the issue.
