# Keeping API keys secret with Bitwarden Secrets Manager

Token needs no API keys today: the optional OpenBB script uses the free Yahoo
provider. This guide sets things up so that the day you add a paid data
provider, a payment processor, or a hosted service, every key lives in
Bitwarden Secrets Manager and never in this repository, a file you might
share, or a terminal history.

Checked 2026-10-13 with `bws` 2.1.0 and OpenBB 2.x.

## How it works

1. Each key is stored once, encrypted, in a Bitwarden **project**.
2. A **machine account** gets read access to that project. Its **access
   token** is the only thing your computer (or CI) holds.
3. `bws run -- <command>` fetches the project's secrets and starts the
   command with each secret set as an environment variable named after the
   secret (for example `FRED_API_KEY`).
4. OpenBB reads provider keys from environment variables named
   `<PROVIDER>_API_KEY` automatically. Tested: with `FRED_API_KEY` set,
   `obb.user.credentials.fred_api_key` picks it up with no code changes.

The key exists only in memory for that one command. Nothing is written to
disk.

## 1. Create the account (you, once)

1. Sign up at <https://bitwarden.com/products/secrets-manager/>. The free
   plan covers unlimited secrets, 2 users, 3 projects and 3 machine accounts
   ([plans](https://bitwarden.com/help/secrets-manager-plans/)).
2. Choose the **US** or **EU** cloud when you sign up. Bitwarden has no
   Canadian region. API keys aren't personal information, but write down
   which one you picked: EU users need an extra setting in step 3.
3. Turn on two-step login (Settings, then Security, then Two-step login).
   This account guards every key you'll ever have.
4. Open **Secrets Manager** from the product switcher and create a project
   named `token-local`. Later, make separate ones such as `token-ci` and
   `token-planner`, so one leaked token can't reach every key.
5. Create a **machine account** named `my-laptop`. Give it **Can read**
   access to `token-local` only.
6. In that machine account, create an **access token**, set an expiry (90
   days is a good habit), and copy it. Bitwarden shows it only once.

## 2. Install the `bws` command-line tool

- **Mac or Linux:** `curl https://bws.bitwarden.com/install | sh`
- **Windows (PowerShell):** `iwr https://bws.bitwarden.com/install | iex`
- **Or** download the zip for your system from the
  [releases page](https://github.com/bitwarden/sdk-sm/releases), check it
  against the published `bws-sha256-checksums-<version>.txt`, and put `bws`
  on your PATH.

Check it with `bws --version`.

## 3. Give `bws` your access token

Set it for the current terminal session only, so it isn't saved to disk:

```
# Mac / Linux (a leading space keeps it out of shell history in most setups)
 export BWS_ACCESS_TOKEN=<paste token>

# Windows PowerShell
$env:BWS_ACCESS_TOKEN = "<paste token>"
```

If you chose the **EU** cloud, also run this once:

```
bws config server-base https://vault.bitwarden.eu
```

Never put the access token in this repository, a `.env` file you commit, a
screenshot, or a chat.

## 4. Store a key

In the web app, open the `token-local` project, click **New secret**, and
name it exactly as the program expects it. For an OpenBB provider that's
`<PROVIDER>_API_KEY` in capitals, for example `FRED_API_KEY`. Or from the
command line:

```
bws project list                        # copy the token-local project ID
bws secret create FRED_API_KEY <value> <project-id> --note "FRED data for OpenBB"
```

`.env.example` in the repo root lists the names Token will use.

## 5. Run Token with the key injected

```
bws run -- python examples/openbb_quickstart.py
```

Any command works the same way. Use `--project-id <id>` to load only one
project's secrets. Use `--no-inherit-env` to start the command with *only*
the Bitwarden secrets (note that this hides PATH too, so give full paths).

## 6. CI (only if a workflow ever needs a key)

Don't add keys to CI unless a workflow really needs one. If one does:

1. Create a separate project and machine account (for example `token-ci`)
   holding only that key.
2. Save its access token as a GitHub Actions secret named `BWS_ACCESS_TOKEN`
   (repo Settings, then Secrets and variables, then Actions).
3. Fetch the key in the workflow with Bitwarden's action, pinned to a commit
   SHA like the other actions in `.github/workflows/`:

   ```yaml
   - uses: bitwarden/sm-action@v3   # pin to a commit SHA before use
     with:
       access_token: ${{ secrets.BWS_ACCESS_TOKEN }}
       # cloud_region: eu           # only if your account is in the EU cloud
       secrets: |
         <secret-uuid> > FRED_API_KEY
   ```

4. Only do this in workflows triggered by `push`, `schedule` or
   `workflow_dispatch`. **Never** in `pull_request` workflows, which run code
   from outside contributors. GitHub doesn't pass secrets to fork pull
   requests, but don't rely on that alone.

## Rules that keep keys safe

- One project and machine account per place a key is used (laptop, CI,
  hosted service), each with read access to only what it needs.
- Set expiry dates on access tokens and rotate them. Revoke a token
  immediately if a device is lost.
- Keys stay server-side. A future website or hosted planner must call paid
  APIs from its own server, never from the user's browser, where any key
  would be visible.
- `.env`, `.env.*` (except `.env.example`), `*.pem`, `*.key` and
  `.openbb_platform/` are in `.gitignore`. If a key is ever committed,
  revoke it at the provider first. Deleting the commit isn't enough.
- Session replay and analytics stay off everywhere ([Privacy Policy](../PRIVACY.md)),
  so keys typed into a future web page can't be recorded.
