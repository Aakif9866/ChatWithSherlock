# All Mix LLMs 🕵️ — v1

**One free AI endpoint built from several free LLM providers — plus a Sherlock Holmes chatbot to test it.**

Instead of wiring every app to Gemini, Groq and OpenRouter separately (each with its own API
format, keys and rate limits), this project runs a **[LiteLLM](https://github.com/BerriAI/litellm)
proxy**. Apps talk to one address with one model name, `free-auto`, and the proxy
picks a provider, translates the request, and fails over when one is rate-limited.

```
 Sherlock app / curl / any OpenAI-compatible tool
                │  model="free-auto"
                ▼
   ┌─────────────────────────────┐
   │  LiteLLM proxy (127.0.0.1)  │  config.yaml + keys from env
   └─────────────────────────────┘
        │           │           │
     Gemini       Groq      OpenRouter
```

> **v1** is this branch (`main`). Planned upgrades — intelligent routing, a live gateway dashboard,
> chaos testing, observability and evaluation — are tracked on the [`v2`](../../tree/v2) branch.

---

## What's inside

| File | Purpose |
|---|---|
| `config.yaml` | LiteLLM config: three models share the name `free-auto`, plus retry / cooldown rules |
| `app.py` | Streamlit chatbot: Sherlock persona, provider labels, navbar with visitor count + contact flow, public-mode limits, stats page |
| `Dockerfile` / `start.sh` | One container: LiteLLM proxy private on `127.0.0.1:4000`, Streamlit public on `$PORT` |
| `render.yaml` | Render Blueprint (free web service, health check, required env vars) |
| `.streamlit/config.toml` | Localhost-only binding for local runs, no usage stats, minimal toolbar |
| `.env` | Your secrets for local runs (**never commit** — it's in `.gitignore`) |
| `info.txt` | Step-by-step local run instructions and troubleshooting |
| `report.md` | Real-world test results: how long you can chat, speed per provider, rate limits |

## Quick start (local)

Requires [uv](https://docs.astral.sh/uv/). First time: `uv sync`.

Create `.env` (one `NAME=value` per line):

```
GROQ_API_KEY=...
GEMINI_API_KEY=...
OPENROUTER_API_KEY=...
CEREBRAS_API_KEY=
LITELLM_MASTER_KEY=sk-<any long random string>

# optional
STATS_KEY=<password for the private stats page>
UPSTASH_REDIS_REST_URL=https://<your-db>.upstash.io
UPSTASH_REDIS_REST_TOKEN=...
```

Then, in **two terminals**:

```bash
# Terminal 1 — the proxy
uv run --env-file .env litellm --config config.yaml --host 127.0.0.1 --port 4000

# Terminal 2 — the chatbot (opens http://localhost:8501)
uv run --env-file .env streamlit run app.py
```

Stop each with `Ctrl + C`. Add `PUBLIC_MODE=1` in front of the second command to try the public version locally.

## Deploy (Render, Docker)

The `Dockerfile` runs both processes in one container via `start.sh`:
a random proxy password is generated at boot, the proxy listens only inside the container,
and Streamlit serves the public port. On Render: **New → Web Service** (or **Blueprint**) → this repo → **Free** plan,
health check path `/_stcore/health`, and these environment variables:

| Variable | Required | Purpose |
|---|---|---|
| `GROQ_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY` | ✅ | Provider keys (only the proxy reads them) |
| `STATS_KEY` | optional | Enables the private stats page |
| `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN` | optional | All-time visitor count (use the **https://** REST URL) |

Every push to `main` redeploys. The free plan sleeps after ~15 idle minutes (first visit then takes ~1 min).

## How it works

1. The app sends a normal **OpenAI-format** request to the proxy with `model: "free-auto"`.
2. LiteLLM finds every entry in `config.yaml` named `free-auto` and treats them as a **pool**. Its default
   `simple-shuffle` strategy does a weighted random pick using each entry's `rpm` (Groq 30, Gemini 10, OpenRouter 5).
3. It **translates** the request into that provider's native format, attaches that provider's real key, and sends it.
4. It translates the answer back to OpenAI format.
5. On failure (429 rate limit, 404, 5xx) it **retries on another provider** (`num_retries: 3`) and **benches** the failing one for 60 s (`cooldown_time: 60`).

The app never sees your provider keys — only the proxy's master key.

## The app (`app.py`)

**Chat**
- Sherlock stays in character and makes playful "deductions" about you from how you write.
- Each reply shows **which provider and model answered** and how long it took (via the proxy's `x-litellm-model-id` header + `/model/info`).
- **Watson fallback:** if the proxy is down, Dr. Watson answers with one of 8 in-character excuses instead of an error.
- **Limits** to make free quotas last: messages up to 1,000 characters, only the last 20 messages sent, replies capped at 2,000 tokens (reasoning models spend hidden "thinking" tokens, so lower caps truncated replies).
- Mobile-friendly layout (tested at phone sizes; 16 px input so iOS doesn't zoom).

**Navbar**
- **👥 N visitors so far** — unique visitors, counted once each by a salted hash of their IP (no raw IPs stored).
  All-time when Upstash Redis is configured (a Redis set: `SADD` + `SCARD`), otherwise since the last restart.
- **✉️ Contact me** — four "are you *really* sure?" dialogs, each at a random spot on screen; after the fourth
  "Yes, really" the email is revealed with balloons. The email is only sent to the browser at that point, so scrapers can't pick it up.

**Public mode** (`PUBLIC_MODE=1`, set in the Dockerfile)
- **10 questions per visitor**, tracked by hashed IP so a page refresh doesn't reset it.
- The sidebar stress test is hidden (it would bypass the limit). Locally it fires 1–30 parallel requests to watch failover.
- A visible note explains that anonymous usage is counted.

**Private stats page** — `https://<app>/?stats=<STATS_KEY>`
- Database status (connected / not configured / the exact connection error), all-time visitors,
  visitors and chatters since restart, questions asked, limit hits, replies per provider.
- Wrong or missing key → just the normal chat page. Logs also get one `[usage]` line per question (hashed visitor, count, provider, seconds — never chat content).

## Test results (short version)

From [`report.md`](report.md) and browser tests during development:

- **60 / 60** chat turns and **60 / 60** burst requests answered — the proxy silently recovered from ~10 rate-limit errors.
- **Groq** was the fastest by far (median **1.1 s**), OpenRouter 3.7 s, Gemini 10.3 s.
- Realistic capacity: **~1,000 messages/day**, mostly from Groq's free tier.
- Playwright smoke tests at desktop and phone sizes: contact flow, navbar, 10-question limit surviving refresh,
  and the visitor count against a real Upstash database (10 simulated visitors → 10, a returning visitor not recounted).

## What I did, step by step

1. **Set up the project** with `uv` and `litellm[proxy]`.
2. **Fixed `.env`** formatting that broke `--env-file`.
3. **Fixed retired models (404s)** by querying each provider's live `/models` endpoint instead of trusting tutorials:
   - Groq: `llama-3.3-70b-versatile` → `openai/gpt-oss-120b`
   - OpenRouter: `meta-llama/llama-3.3-70b-instruct:free` → `nvidia/nemotron-3-super-120b-a12b:free` (Gemma/Qwen free were constantly 429)
   - Gemini: `gemini-3.8-flash` was still live — kept.
4. **Fixed routing:** only one entry was actually named `free-auto`, so everything went to Gemini. Renamed all to `free-auto`.
5. **Parked Cerebras** (commented out until I get a key).
6. **Built the Sherlock chatbot** in Streamlit, with the Watson fallback and provider labels
   (fixing "unknown" labels: OpenRouter responses lack `x-litellm-model-api-base`, so the app maps `x-litellm-model-id` instead).
7. **Load-tested** it and wrote [`report.md`](report.md).
8. **Security hardening** (below).
9. **Made it mobile-friendly** and fixed truncated replies (reply cap 800 → 2,000 tokens).
10. **Containerised and deployed** to Render (Hugging Face Docker Spaces now require PRO).
11. **Public mode** with a 10-question limit per visitor, usage logging and a private stats page.
12. **Navbar** with a persistent visitor count (Upstash Redis) and the playful contact flow.

## Security

| Risk | Fix |
|---|---|
| API keys committed to git / baked into the image | `.env` in `.gitignore` and `.dockerignore` |
| Other macOS users reading keys | `.env` permissions set to `600` (owner only) |
| Anyone on the network using your proxy (LiteLLM binds `0.0.0.0` by default) | Proxy bound to `127.0.0.1`; in Docker it's only reachable inside the container |
| Guessable proxy password (`sk-local-dev`) | Random `LITELLM_MASTER_KEY` (generated per boot in the container) |
| Strangers draining the free quotas | 10 questions per visitor, stress test hidden in public mode, input/history/reply caps |
| Storing personal data | Visitors stored only as salted SHA-256 hashes; no chat content logged or stored |
| Email scraping | Email only rendered after the 4-step contact flow |
| Stats page discovery / timing attacks | Secret key compared with `hmac.compare_digest`; wrong key shows the normal page |
| Container privileges | Runs as a non-root user |

If a key is ever exposed, revoke it in the provider's dashboard and create a new one.

## Known limitations (v1)

- The 10-question limit and "since restart" stats live in memory — a restart resets them. The limit is IP-based,
  so shared networks share it and a VPN bypasses it.
- The container doesn't supervise the proxy: if LiteLLM crashes, the health check (Streamlit only) still passes and users get Watson.
- No automated test suite or CI yet — testing was done with scripted endurance runs, Streamlit AppTest and Playwright.
- Free tiers are the real ceiling (~1,000 requests/day), and the free Render instance has 512 MB RAM (~400 MB used).

These are the starting points for **v2**.

## Lessons learned

- **Model IDs go stale fast.** Tutorials and chatbots (even Claude chat!) may suggest models that were retired months ago. Always check the provider's live `/models` endpoint.
- **Free tiers have two kinds of limits**: requests per day and tokens per minute. Long chat histories hit the token limit first.
- **Models don't know who they are.** Asked "which model are you?", Sherlock confidently claimed GPT-4 — it was actually `gpt-oss-120b` on Groq. Trust the proxy's headers, not the model.
- **Platform facts change too.** Hugging Face Docker Spaces turned out to need PRO; verify pricing before planning a deploy.
- **Env values are literal on hosting dashboards.** Quotes pasted around a URL become part of it — the app now strips them defensively.
- **"Untracked" in VS Code is just git**, not surveillance — `uv init` creates a git repo.

## Credits

- **[LiteLLM](https://github.com/BerriAI/litellm)** by [BerriAI](https://www.litellm.ai/) — the open-source proxy and SDK that makes all of this possible: one OpenAI-compatible API for 100+ LLM providers, with load balancing, retries, fallbacks and cooldowns built in. Huge thanks to the maintainers and contributors.
- Free LLM access from **[Groq](https://groq.com)**, **[Google Gemini](https://ai.google.dev)** and **[OpenRouter](https://openrouter.ai)**.
- Visitor count stored in **[Upstash Redis](https://upstash.com)**; hosted on **[Render](https://render.com)**.
- UI built with **[Streamlit](https://streamlit.io)**; dependencies managed with **[uv](https://docs.astral.sh/uv/)**.
- Sherlock Holmes, Dr. Watson and friends were created by **Sir Arthur Conan Doyle**.
- Built as part of the freeCodeCamp *Agentic AI* course, with help from Claude Code.
