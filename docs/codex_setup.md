# Running Codex on Your Own Computer

Codex is OpenAI's coding agent. It runs in your terminal, reads the files in
whatever folder you start it from, and can edit them, run commands and open
pull requests. This guide gets it working against **this** repository in about
10 minutes.

Codex needs a paid ChatGPT plan or an OpenAI API key — see step 3.

## 1. Install Node.js (if you don't have it)

Codex ships as an npm package and needs **Node 16 or newer**.

- **Windows:** download the LTS installer from https://nodejs.org and run it.
- **Mac:** download the LTS installer from https://nodejs.org, or if you use
  Homebrew, `brew install node`.

Check it worked by opening a terminal (Windows: press the Windows key, type
`cmd`, press Enter; Mac: open the Terminal app) and running:

```
node --version
```

Anything from `v16` up is fine.

## 2. Install Codex

```
npm install -g @openai/codex
```

Then confirm:

```
codex --version
```

That should print something like `codex-cli 0.156.0`.

If npm complains about permissions on Mac or Linux, don't use `sudo` — it
causes more problems than it solves. Either use Homebrew's Node (which installs
into a folder you own) or set npm's global prefix to your home directory:

```
npm config set prefix ~/.npm-global
export PATH=~/.npm-global/bin:$PATH
```

Add that `export` line to `~/.zshrc` (Mac) or `~/.bashrc` (Linux) to make it
stick.

## 3. Sign in

Two options. Pick one.

**A. Sign in with ChatGPT** (included with Plus, Pro, Business and Enterprise
plans — no separate billing):

```
codex login
```

That opens a browser window. Sign in, approve, and come back to the terminal.
The credentials are stored under `~/.codex/`.

**B. Use an API key** (billed per token against your OpenAI account):

Create a key at https://platform.openai.com/api-keys, put it in an environment
variable, then hand it to Codex on stdin so it never appears in your shell
history:

```
export OPENAI_API_KEY=sk-...          # Mac/Linux; use setx on Windows
printenv OPENAI_API_KEY | codex login --with-api-key
```

Either way, check the result:

```
codex login status
```

Treat the key like a password. Never paste it into a file in this repository,
a commit, or a chat window — `.gitignore` will not save you from a key pasted
into a tracked file.

## 4. Check everything is healthy

Codex ships a diagnostic that is worth running once before you trust it:

```
codex doctor
```

It reports on auth, network reachability, disk, the git executable and the
install itself. Every line should be a green check. The two that actually
matter are **auth** (step 3) and **reachability** — if reachability fails,
something between you and OpenAI is blocking it: a corporate proxy, a VPN, a
firewall, or a network that inspects TLS with its own certificate.

## 5. Use it on this repository

Start it from the repo folder so it can see the files:

```
cd path/to/Token
codex
```

That opens an interactive session. Describe what you want in plain English;
Codex proposes changes and asks before running commands or writing files.

For one-shot, non-interactive runs (useful in scripts or CI):

```
codex exec "Add the 2027 indexation factors to data/json/personal_income_tax_2026.json"
```

To have it review work rather than write it:

```
codex review
```

### It already knows the house rules

The [`AGENTS.md`](../AGENTS.md) file in the repo root is read automatically at
the start of every session. It tells Codex the things that are easy to get
wrong here — that `data/json/` is the source of truth and tax rules must never
be hardcoded, that `data/csv/` and the `.xlsx` are generated and must be
rebuilt rather than hand-edited, that a `basic_personal_amount` may be a
number, `null` or a `{max, min}` pair, and that
`python3 -m unittest discover -s tests` has to pass before anything is done.

If you find yourself repeating a correction to Codex, add it to `AGENTS.md`
instead — that is what the file is for.

## 6. Good first tasks here

```
codex exec "Run the test suite and summarise what it covers"
codex exec "Add PEI's 2026 basic personal amount once you can cite a source for it, and update the notes"
codex review
```

Always read the diff before accepting it. Codex is capable but not
authoritative, and **a tax figure it cannot cite is a guess** — the repo's
convention is to leave an unverifiable figure `null` with an explanation in
`notes` rather than fill it in.

## Troubleshooting

- **`codex: command not found`** — npm's global `bin` folder is not on your
  PATH. `npm bin -g` prints the folder; add it to PATH (see step 2).
- **`codex doctor` says auth failed** — you are not signed in, or the stored
  credentials expired. Re-run `codex login`, then `codex login status`.
- **`codex doctor` says reachability failed** — Codex cannot reach OpenAI's
  endpoints. On a corporate network this is usually a proxy or TLS-inspecting
  firewall; set `HTTPS_PROXY` and point Node at your organisation's CA bundle
  (`NODE_EXTRA_CA_CERTS`). Never work around it by disabling certificate
  verification.
- **It edits files you didn't expect** — start it in the repo folder, not your
  home folder, and read each proposed diff before approving.
- **Out of credit / 429s** — on an API key, check usage at
  https://platform.openai.com/usage; on a ChatGPT plan, you have hit the plan's
  rate limit and need to wait.

## Note on cloud sessions

Codex needs outbound access to OpenAI's endpoints (`api.openai.com`, and
`chatgpt.com` for the browser sign-in). Sandboxed CI and cloud agent
environments often block these by network policy, in which case `codex doctor`
reports the reachability failure above and no amount of credential fixing will
help. Run Codex from your own machine, where you control the network.
