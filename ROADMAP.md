# v2 Roadmap — from "Sherlock chatbot" to an LLM Gateway / Control Plane

**Goal:** turn v1 (a chatbot on top of a LiteLLM proxy) into a small but serious systems project:

> *An intelligent LLM gateway that routes across multiple providers using latency, reliability, cost and
> capability — with a live dashboard, chaos testing, observability and an evaluation harness.*

Not 20 random features: **one engineering direction, done well.** Sherlock stays as the fun demo
interface; the gateway underneath is the real project.

```
            Fun layer                         Engineering layer
  🕵️ Sherlock · 🧠 deductions          ⚙️ gateway · 🚦 routing · 🔄 failover
  🎩 Watson · 😂 provider personalities 📊 observability · 🔥 chaos · 📈 evaluation
                     │                         🐳 Docker · 🧪 load testing
                     ▼
          OpenAI-compatible API
                     ▼
     ┌──────────── LLM Gateway ────────────┐
     │  Router (strategy per request)       │
     │  health · rate-limit state · costs   │
     └───────┬──────────┬──────────┬────────┘
          Gemini       Groq     OpenRouter   (+ Cerebras, …)
```

Resume bullet this should earn:
> "Built and evaluated an LLM routing layer across multiple providers, using latency, reliability and
> response-quality metrics, with a live dashboard, chaos testing and Prometheus/Grafana observability."

---

## 0. Fix v1 foundations first

Known issues from v1 that v2 features would otherwise build on top of:

- [ ] `model_for()` errors are caught as "proxy down" → a good reply can be discarded. Handle lookup errors separately.
- [ ] Cache the model-id map in `st.cache_resource` (module globals reset on every Streamlit rerun).
- [ ] Supervise the proxy in the container (or split proxy/app); make the health check cover the proxy.
- [ ] Fail fast in `start.sh` if the proxy never becomes healthy.
- [ ] Show friendly errors to users; keep raw provider errors in logs only.
- [ ] Move rate-limit counters to Redis (`INCR` + `EXPIRE`) so limits survive restarts and allow replicas.
- [ ] Trust only the platform-appended `X-Forwarded-For` hop.
- [ ] Declare `openai` as a direct dependency; pin the `uv` image.

## 1. Intelligent routing

Replace the static weighted shuffle with a router that picks a provider **per request**:

```
Question → Router
             ├── cheapest  → Provider A
             ├── fastest   → Provider B
             ├── strongest → Provider C
             └── fallback  → Provider D
```

- [ ] Track live signals per provider: rolling latency (p50/p95), failure rate, current rate-limit state
      (e.g. Groq's `x-ratelimit-remaining-*` headers), cooldowns.
- [ ] Static metadata per model: estimated cost, capability tags (coding, reasoning, long context), context length.
- [ ] Routing strategies selectable per request: `fastest`, `cheapest`, `strongest`, `balanced`.
- [ ] Context-length aware: skip models that can't fit the prompt.
- [ ] Explicit fallback chains (LiteLLM `fallbacks`) instead of an even pool.
- [ ] Expose the decision: "routed to Groq because: fastest healthy, 1.1 s p50, 0 recent failures".

## 2. Real-time gateway dashboard

```
┌─────────────────────────────────────┐
│         LLM GATEWAY DASHBOARD       │
├─────────────────────────────────────┤
│ Requests       12,842               │
│ Success        99.2%                │
│ Avg latency    1.84s                │
│ Failovers      183                  │
├─────────────────────────────────────┤
│ Provider     Requests  Latency  OK  │
│ Groq           5,421    1.1s   99%  │
│ Gemini         4,122    3.2s   98%  │
│ OpenRouter     3,299    2.4s   99%  │
└─────────────────────────────────────┘
```

- [ ] Persist per-request events (Redis or Postgres): provider, latency, status, retries, tokens, cost.
- [ ] Streamlit dashboard page: totals, success rate, latency, failovers, per-provider table, time-series charts.
- [ ] Live refresh (auto-updating fragment).

## 3. Chaos testing

Buttons that break things on purpose, then watch the system recover:

- [ ] **Kill Groq** (mark provider down)
- [ ] **Make Gemini slow** (inject latency)
- [ ] **Force OpenRouter 429**
- [ ] **Kill the entire proxy** (Watson should take over; health check should notice)
- [ ] **Simulate 100 concurrent users**
- [ ] Record each experiment: time to detect, time to recover, user-visible errors.

(Implementation idea: a fault-injection layer in the gateway, or LiteLLM mock responses / a fake provider endpoint.)

## 4. Observability

- [ ] Structured JSON logs with **request IDs** propagated app → gateway → provider.
- [ ] **Prometheus** metrics: requests, success rate per provider, **p50/p95/p99 latency**, retry counts,
      failover counts, error rates, tokens, cost.
- [ ] **Grafana** dashboards (docker-compose for local: app, gateway, Prometheus, Grafana).
- [ ] Tracing via OpenTelemetry (LiteLLM supports OTel callbacks).
- [ ] Alerts: all providers in cooldown, error rate spike, proxy down.

## 5. Evaluation (highest resume value)

Small labelled dataset, same prompts through every provider:

```
Question                Expected property
------------------------------------------------
"What is TCP?"          technical
"Write Python code"     coding
"Summarize this..."     summarization
"Translate..."          translation
```

- [ ] Build the dataset (start ~30–50 prompts across categories).
- [ ] Runner that sends each prompt to each provider and records latency, failures, tokens, cost.
- [ ] Quality scoring (LLM-as-judge with a rubric, plus simple checks like code that runs).
- [ ] Results table and chart:

```
Provider       Quality   Latency   Failures
---------------------------------------------
Groq           ?/10      ?s        ?%
Gemini         ?/10      ?s        ?%
OpenRouter     ?/10      ?s        ?%
```

- [ ] Feed results back into routing (`strongest` per category).
- [ ] Only publish numbers that were actually measured.

## 6. Keep the fun layer

- [ ] Sherlock remains the demo UI.
- [ ] Provider personalities (e.g. Watson narrates when a failover happens).
- [ ] "Behind the scenes" panel per message: which provider, why, retries, latency, cost.

## Engineering hygiene (throughout)

- [ ] pytest + Streamlit AppTest + Playwright tests; GitHub Actions CI on every PR.
- [ ] Load testing (k6/Locust against the gateway).
- [ ] Separate services (app / gateway / Redis / Prometheus / Grafana) with docker-compose.
- [ ] Architecture diagram + design-decision notes in the README.

## Suggested order

1. Foundations (section 0) + tests/CI
2. Request event storage + dashboard (2) — makes everything after it visible
3. Observability (4)
4. Chaos testing (3)
5. Intelligent routing (1), informed by the data from 2–4
6. Evaluation (5), then feed it into routing
