# Running OpenRouter on Your Own Computer

OpenRouter is a single API that reaches hundreds of AI models — Anthropic's
Claude, Google's Gemini, Meta's Llama, Mistral, and more — through one key and
one endpoint. Instead of opening an account with every vendor, you top up one
balance and switch models by changing a name. This guide gets it running
locally in about 10 minutes.

Unlike the OpenBB setup, **there is no software to install** — the script in
this repo uses only what comes with Python. You do need an API key, and calls
cost money (usually a fraction of a cent each).

## 1. Install Python (if you don't have it)

- **Windows:** Download Python from https://www.python.org/downloads/ and run
  the installer. **Important:** on the first installer screen, tick the
  checkbox "Add python.exe to PATH" before clicking Install.
- **Mac:** Python 3 is usually already installed. Open the **Terminal** app
  (Cmd+Space, type "terminal") and run `python3 --version`. If that prints a
  version like `3.11`, you're set.

Python 3.9 or newer works.

## 2. Create an OpenRouter account and key

1. Sign up at https://openrouter.ai.
2. Add credit at https://openrouter.ai/credits — $5 goes a long way, and
   there is no subscription. Some models are free but heavily rate-limited.
3. Create a key at https://openrouter.ai/keys and copy it. It starts with
   `sk-or-`. **This is the only time the full key is shown.**

Treat the key like a password: anyone who has it can spend your balance. Never
paste it into a file you commit to git, and never share it in a screenshot.

## 3. Put the key in your environment

The script reads the key from an environment variable, so it never has to be
written into any file.

**Mac / Linux** — in Terminal:

```
export OPENROUTER_API_KEY=sk-or-your-key-here
```

That lasts until you close the window. To make it permanent, add the same line
to the end of `~/.zshrc` (Mac) or `~/.bashrc` (Linux), then open a new window.

**Windows** — in Command Prompt:

```
setx OPENROUTER_API_KEY sk-or-your-key-here
```

Then **close and reopen** the terminal — `setx` only affects new windows.

To confirm it worked, run `echo $OPENROUTER_API_KEY` (Mac/Linux) or
`echo %OPENROUTER_API_KEY%` (Windows) and check that your key prints.

## 4. Try it

From the repo folder:

```
python3 examples/openrouter_quickstart.py "Explain a TFSA in one paragraph"
```

You should get a few sentences back, and a line on the end reporting which
model answered and how many tokens it used.

## 5. Choosing a model

Models are named `vendor/model`. The script defaults to
`anthropic/claude-opus-5`. To use a different one:

```
python3 examples/openrouter_quickstart.py --model google/gemini-2.5-pro "Same question"
```

To find a slug without leaving the terminal, search the live catalogue:

```
python3 examples/openrouter_quickstart.py --models claude
python3 examples/openrouter_quickstart.py --models free
```

The full catalogue with per-model pricing is at https://openrouter.ai/models.
Prices are quoted per million tokens, charged separately for what you send
(prompt) and what you get back (completion), so a long document costs more to
ask about than a short question.

## 6. Asking about the tax data in this repo

The `--file` option attaches one of the dataset files as context, which is the
most useful thing this script does here:

```
python3 examples/openrouter_quickstart.py --file data/json/sales_tax_2026.json \
  "Which provinces charge more than 13% combined sales tax?"
```

```
python3 examples/openrouter_quickstart.py --file data/csv/income_tax_brackets_2026.csv \
  "Compare Alberta and Ontario marginal rates at $120,000"
```

A word of warning that applies to every model: **check the arithmetic**. The
figures in `data/json/` are the source of truth (and carry the provenance
notes in [README.md](../README.md)); a model summarising them can still get a
number wrong. The same disclaimer as the rest of this repo applies — none of
it is tax advice.

## 7. Using it from your own code

The endpoint is OpenAI-compatible, so most existing libraries work by pointing
them at OpenRouter's base URL:

```python
# pip install openai
from openai import OpenAI

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)
reply = client.chat.completions.create(
    model="anthropic/claude-opus-5",
    messages=[{"role": "user", "content": "Hello"}],
)
print(reply.choices[0].message.content)
```

If you only ever plan to use Claude, Anthropic's own API and the `anthropic`
package give you first-party features (extended thinking, prompt caching,
tool use) that a compatibility layer may not expose. OpenRouter's advantage is
breadth and one bill — pick based on whether you value that over depth.

## Troubleshooting

- **"OPENROUTER_API_KEY is not set"** — the variable didn't reach this
  terminal. On Windows, `setx` needs a *new* window; on Mac/Linux, `export`
  only affects the window you typed it in.
- **401** — the key was rejected. It may have been revoked or copied with a
  missing character; make a fresh one at https://openrouter.ai/keys.
- **402** — the account is out of credit. Top up at
  https://openrouter.ai/credits.
- **404 on a model** — the slug is wrong or that model was retired. Run
  `--models <part of the name>` to see current slugs.
- **429** — too many requests, or a free model's daily limit. Wait, or switch
  to a paid model.
- **The reply stops mid-sentence** — raise the cap, e.g. `--max-tokens 4000`.
