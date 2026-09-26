# All Mix LLMs 🕵️

**One free AI endpoint built from several free LLM providers — plus a Sherlock Holmes chatbot to test it.**

Instead of wiring every app to Gemini, Groq and OpenRouter separately (each with its own API
format, keys and rate limits), this project runs a local **[LiteLLM](https://github.com/BerriAI/litellm)
proxy**. Apps talk to one address with one model name, `free-auto`, and the proxy
picks a provider, translates the request, and fails over when one is rate-limited.

```
 Sherlock app / curl / any OpenAI-compatible tool
                │  model="free-auto"
                ▼
   ┌─────────────────────────────┐
   │  LiteLLM proxy (127.0.0.1)  │  config.yaml + keys from .env
   └─────────────────────────────┘
        │           │           │
     Gemini       Groq      OpenRouter
```

---

## What's inside

| File | Purpose |
|---|---|
| `config.yaml` | LiteLLM config: three models share the name `free-auto`, plus retry / cooldown rules |
| `.env` | API keys + the proxy's master key (**never commit** — it's in `.gitignore`) |
| `app.py` | Streamlit chatbot: Sherlock Holmes, with provider labels, a stress-test button and a Watson fallback |
| `.streamlit/config.toml` | Keeps the app on localhost and turns off Streamlit usage stats |
| `info.txt` | Step-by-step run instructions and troubleshooting |
| `report.md` | Real-world test results: how long you can chat, speed per provider, rate limits |

## Quick start

Requires [uv](https://docs.astral.sh/uv/). First time: `uv sync`.

Create `.env` (format is strictly `NAME=value` — no spaces, no quotes):

```
GROQ_API_KEY=...
GEMINI_API_KEY=...
OPENROUTER_API_KEY=...
CEREBRAS_API_KEY=
LITELLM_MASTER_KEY=sk-<any long random string>
```

Then, in **two terminals**:

```bash
# Terminal 1 — the proxy
uv run --env-file .env litellm --config config.yaml --host 127.0.0.1 --port 4000

# Terminal 2 — the chatbot (opens http://localhost:8501)
uv run --env-file .env streamlit run app.py
```

Stop each with `Ctrl + C`. More detail in [`info.txt`](info.txt).

## How it works

1. The app sends a normal **OpenAI-format** request to `localhost:4000` with `model: "free-auto"`.
2. LiteLLM finds every entry in `config.yaml` named `free-auto` and treats them as a **pool**, choosing one while respecting each one's `rpm` limit.
3. It **translates** the request into that provider's native format (Gemini's API is very different from OpenAI's), attaches that provider's real key, and sends it.
4. It translates the answer back to OpenAI format.
5. On failure (429 rate limit, 404, 5xx) it **retries on another provider** (`num_retries: 3`) and **benches** the failing one for 60 s (`cooldown_time: 60`).

The app never sees your provider keys — only the proxy's master key.

## The Sherlock Holmes chatbot (`app.py`)

- Stays in character and makes playful "deductions" about you from how you write.
- Each reply shows **which provider and model answered** and how long it took (looked up via the proxy's `x-litellm-model-id` header + `/model/info`).
- **Sidebar stress test:** fire 1–30 parallel requests to watch load balancing and failover.
- **Watson fallback:** if the proxy is down, Dr. Watson answers with one of 8 in-character excuses instead of an error.
- **Limits** to make free quotas last: messages up to 1,000 characters, only the last 20 messages sent, replies capped at 800 tokens.

## Test results (short version)

From [`report.md`](report.md):

- **60 / 60** chat turns and **60 / 60** burst requests answered — the proxy silently recovered from ~10 rate-limit errors.
- **Groq** was the fastest by far (median **1.1 s**), OpenRouter 3.7 s, Gemini 10.3 s.
- Realistic capacity: **~1,000 messages/day**, mostly from Groq's free tier.

## What I did, step by step

1. **Set up the project** with `uv` and `litellm[proxy]`.
2. **Fixed `.env`**: removed a space before `=` and quotes around an empty value — both break `--env-file`.
3. **Fixed retired models (404s)** by querying each provider's live `/models` endpoint instead of trusting tutorials:
   - Groq: `llama-3.3-70b-versatile` → `openai/gpt-oss-120b`
   - OpenRouter: `meta-llama/llama-3.3-70b-instruct:free` → `nvidia/nemotron-3-super-120b-a12b:free` (Gemma/Qwen free were constantly 429)
   - Gemini: `gemini-3.8-flash` was still live — kept.
4. **Fixed routing:** only one entry was actually named `free-auto`, so everything went to Gemini. Renamed all to `free-auto`.
5. **Parked Cerebras** (commented out until I get a key).
6. **Built the Sherlock chatbot** in Streamlit.
7. **Fixed "unknown" provider labels:** OpenRouter responses don't include `x-litellm-model-api-base`, so the app now maps `x-litellm-model-id` via `/model/info`.
8. **Added the Watson fallback** for when the proxy is down.
9. **Load-tested** it and wrote [`report.md`](report.md).
10. **Security hardening** (below).

## Security

| Risk | Fix |
|---|---|
| API keys committed to git | `.env` added to `.gitignore` |
| Other macOS users reading keys | `.env` permissions set to `600` (owner only) |
| Anyone on the same Wi-Fi using your proxy (LiteLLM binds `0.0.0.0` by default) | Proxy started with `--host 127.0.0.1` |
| Guessable proxy password (`sk-local-dev`) | Random `LITELLM_MASTER_KEY` in `.env`, read via `os.environ/` in `config.yaml` |
| Streamlit reachable from the network / usage stats | `.streamlit/config.toml`: `address = "localhost"`, `gatherUsageStats = false` |
| Huge inputs burning quota | Input length, history and reply length caps in `app.py` |

If a key is ever exposed, revoke it in the provider's dashboard and create a new one.

## Lessons learned

- **Model IDs go stale fast.** Tutorials and chatbots (even Claude chat!) may suggest models that were retired months ago. Always check the provider's live `/models` endpoint.
- **Free tiers have two kinds of limits**: requests per day and tokens per minute. Long chat histories hit the token limit first.
- **Models don't know who they are.** Asked "which model are you?", Sherlock confidently claimed GPT-4 — it was actually `gpt-oss-120b` on Groq. Trust the proxy's headers, not the model.
- **"Untracked" in VS Code is just git**, not surveillance — `uv init` creates a git repo.

## Credits

- **[LiteLLM](https://github.com/BerriAI/litellm)** by [BerriAI](https://www.litellm.ai/) — the open-source proxy and SDK that makes all of this possible: one OpenAI-compatible API for 100+ LLM providers, with load balancing, retries, fallbacks and cooldowns built in. Huge thanks to the maintainers and contributors.
- Free LLM access from **[Groq](https://groq.com)**, **[Google Gemini](https://ai.google.dev)** and **[OpenRouter](https://openrouter.ai)**.
- UI built with **[Streamlit](https://streamlit.io)**; dependencies managed with **[uv](https://docs.astral.sh/uv/)**.
- Sherlock Holmes, Dr. Watson and friends were created by **Sir Arthur Conan Doyle**.
- Built as part of the freeCodeCamp *Agentic AI* course, with help from Claude Code.
