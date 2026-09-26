# How long can you chat with Sherlock? — Limits Report

Tested on **2026-09-27** against the real proxy (`free-auto` = Gemini + Groq + OpenRouter),
using the app's own settings (last 20 messages sent, replies capped at 800 tokens).

## TL;DR

| Question | Answer |
|---|---|
| How long can **one conversation** be? | **Unlimited length.** The app only sends the last 20 messages, so each request stays ~2,000 tokens no matter how long you chat. (Trade-off: Sherlock forgets things older than ~10 exchanges.) |
| How many **messages per day**? | **~1,000+** in theory, almost all from Groq. OpenRouter adds only 50/day, Gemini a small unpublished amount. |
| How **fast** can you chat? | Normal human speed (1 message every 10–30 s) never hits a limit. At machine speed, Groq's 8,000 tokens/minute kicks in after ~3 messages/minute and the proxy fails over to the others. |
| Did anything **break** in testing? | **No.** 120/120 requests answered. The proxy silently absorbed ~10 rate-limit errors by retrying on another provider. |
| What ran out? | **OpenRouter's free daily quota** — fully used by this test (68 of 50; they let a few extra through). It resets daily. |

---

## 1. The limits on your keys (measured live)

| Provider | Model | Requests / day | Tokens / minute | Where this came from |
|---|---|---|---|---|
| **Groq** | `openai/gpt-oss-120b` | **1,000** | **8,000** | `x-ratelimit-*` response headers |
| **OpenRouter** | `nvidia/nemotron-3-super-120b-a12b:free` | **50** (1,000 if you ever add $10 credit) | — | `GET /api/v1/key` |
| **Gemini** | `gemini-3.8-flash` | not exposed by the API | not exposed | Hit "quota exceeded" after ~6 rapid requests earlier today; see your limits in Google AI Studio |

> Groq may also have a daily *token* cap that its headers don't show — check
> console.groq.com → Settings → Limits.

## 2. Test A — one long conversation at machine speed

60 back-to-back Sherlock questions in a single chat, no pauses (a human could never type this fast).

| Metric | Result |
|---|---|
| Turns answered | **60 / 60** |
| Total time | **284 s** (≈ 4 min 44 s, ~4.7 s per turn) |
| Median reply time | **3.0 s** |
| Answered by | OpenRouter 34 · Groq 21 · Gemini 5 |
| Turns that needed a hidden retry | 19 (25 retries total) — you'd only notice as a slower reply |
| Tokens per request (prompt) | turn 1: 207 → turn 10: 1,909 → turn 20+: **flat at ~2,000** (history cap working) |
| Avg tokens per turn (in + out) | ~2,150 |

**Speed by provider**

| Provider | Median | Fastest | Slowest |
|---|---|---|---|
| Groq | **1.1 s** | 0.75 s | 12.9 s (a retry) |
| OpenRouter | 3.7 s | 1.5 s | 20.6 s |
| Gemini | 10.3 s | 5.7 s | 15.2 s (it "thinks" before answering) |

Groq is the star: custom LPU chips make it ~3× faster than the others.

## 3. Test B — stress bursts (the sidebar button)

Two bursts of **30 parallel requests** each.

| Burst | Answered | Wall time | Median | Slowest | Served by |
|---|---|---|---|---|---|
| 1 | **30 / 30** | 31.1 s | 11.5 s | 31.1 s | OpenRouter 24 · Groq 6 |
| 2 | **30 / 30** | 20.0 s | 8.8 s | 20.0 s | OpenRouter 19 · Groq 11 |

Nothing failed; requests just queued behind retries.

## 4. What the proxy was hiding from you

Errors LiteLLM caught and recovered from (from the proxy log):

- **Groq × 6** — `Rate limit reached ... tokens per minute (TPM): Limit 8000, Used 7804`
- **OpenRouter × 4** — `Rate limit exceeded: free-models-per-day`

Each time, the router retried on a different provider (`num_retries: 3`) and
benched the failing one for 60 s (`cooldown_time: 60`). This is exactly what LiteLLM is for.

## 5. Hypothetically — the math

Using ~2,150 tokens per turn:

- **Groq by tokens:** 8,000 ÷ 2,150 ≈ **3.7 turns/minute** max.
- **Groq by requests:** **1,000 turns/day**, reset on a rolling window.
- **OpenRouter:** **50 turns/day**.
- **Gemini:** a few per minute; daily amount depends on Google's current free tier.
- **Realistic human** (1 message / 20 s, 3/min): within Groq's minute limit alone —
  you could chat for **~5.5 hours straight** before Groq's 1,000/day is gone, then
  Gemini carries you a bit further.

### What if the app did NOT cap history?

Every turn adds ~250 tokens, so request size grows forever:

| Turn | Tokens per request | Effect |
|---|---|---|
| 10 | ~2,500 | fine |
| 30 | ~7,500 | Groq can fit **1 request/minute** |
| ~32 | > 8,000 | **Groq rejects every request** — a single request exceeds its per-minute budget |
| ~500 | ~131,000 | hits the model's context window; every provider rejects |

That's why `MAX_HISTORY = 20` exists in `app.py`.

## 6. How to get more

1. Add the **Cerebras** key when you have it (a whole extra provider's free quota; uncomment it in `config.yaml`).
2. A one-time **$10 OpenRouter credit** raises free-model requests from 50 → 1,000/day.
3. Add more models from the same provider (e.g. a second Groq model) — each model has its own separate limits.

## 7. Caveats

- One test run on one day; free-tier limits change often and without notice.
- The test itself consumed quota: OpenRouter is at 0 for today; Groq had ~930 requests left afterwards.
