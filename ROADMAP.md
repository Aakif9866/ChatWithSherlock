# v2 Roadmap — Sherlock for Incidents 🕵️🔥

**v1** was a chatbot on top of a multi-provider LLM gateway.
**v2** gives Sherlock real cases: **production incidents.**

> *An agentic on-call investigator. When an alert fires on a (deliberately breakable) demo system,
> Sherlock gathers evidence from logs, metrics and recent deploys, forms and tests hypotheses, and
> reports the most likely root cause with the evidence behind it. Because incidents are injected by a
> chaos lab, the true root cause is known — so the agent's diagnosis accuracy can be measured.*

Why this use case:
- **Implementation-heavy:** microservices, webhooks, queues, durable workflows, tool-using agents, RAG, a gateway, evaluation.
- **Measurable:** ground truth for every incident → accuracy, time-to-diagnosis, cost per investigation.
- **Great to discuss:** agent safety (read-only tools), idempotency, retries, cost-aware model routing,
  hallucination control, evaluation methodology, failure modes of the investigator itself.
- **Keeps the fun:** Sherlock deduces, Watson writes the postmortem.

Resume bullet this should earn:
> "Built an agentic incident investigator that diagnoses injected production failures from logs, metrics and
> deploy history; routed LLM calls through a cost/latency-aware multi-provider gateway; evaluated root-cause
> accuracy against ground truth across N chaos scenarios."

---

## Architecture

```
 ┌─────────── Chaos Lab ───────────┐        ┌──────── Demo system ("Baker Street Shop") ────────┐
 │ inject: kill svc, latency, bad  │──────▶ │ frontend → orders-api → payments-api → Postgres    │
 │ deploy, DB pool exhaustion, 429 │        │ emits structured logs, Prometheus metrics, deploys │
 │ records ground-truth root cause │        └───────────────┬───────────────────────────────────┘
 └─────────────────────────────────┘                        │ alert rule fires
                                                            ▼
                                             Alert webhook → queue (idempotent by alert id)
                                                            ▼
                               ┌──────────── Investigation workflow (durable) ────────────┐
                               │ 1. Triage (cheap model): severity, affected service       │
                               │ 2. Gather evidence via READ-ONLY tools:                   │
                               │    query_logs · query_metrics · recent_deploys ·          │
                               │    service_topology · search_runbooks (RAG)               │
                               │ 3. Hypothesise → test → rank (strong model)               │
                               │ 4. Report: root cause + evidence + confidence + next steps│
                               └───────────────┬──────────────────────────────────────────┘
                                               │ every LLM call
                                               ▼
                                 LLM Gateway (from v1, upgraded)
                             routing by cost / latency / capability,
                             fallbacks, budgets, per-call tracing
                                               ▼
                                  Gemini · Groq · OpenRouter · …

 Sherlock UI: live case file (timeline of evidence & reasoning) · Watson postmortem · eval dashboard
```

---

## Milestones

### 0. Foundations from v1
- [ ] Fix v1 issues: `model_for()` errors treated as proxy-down; model map cache; proxy supervision + health check; friendly errors.
- [ ] Split services with docker-compose; pytest + CI (GitHub Actions).

### 1. The demo system to investigate
- [ ] 2–3 tiny services (e.g. FastAPI `orders-api`, `payments-api`) + Postgres, with a load generator.
- [ ] Structured JSON logs with request IDs; Prometheus metrics (RPS, error rate, p95 latency, DB pool usage).
- [ ] A deploy log (who deployed what, when, config diff).
- [ ] Alert rules (error rate, latency, saturation) → webhook.

### 2. Chaos lab (incident generator with ground truth)
- [ ] Scenarios: service crash, injected latency, bad config deploy, DB connection-pool exhaustion,
      upstream 429s, memory leak, dependency timeout.
- [ ] Each run records the **true root cause** and timestamps.
- [ ] UI buttons + a CLI to run a scenario or a random one.

### 3. The investigator agent
- [ ] Tool layer (**read-only**, allow-listed, time-bounded queries, result size limits).
- [ ] Runbook RAG: embed runbooks/past postmortems in a vector store; retrieve with citations.
- [ ] Hypothesis loop with a step budget (max tool calls, max tokens, max wall time).
- [ ] Structured output: root cause, affected component, evidence links, confidence, suggested remediation
      (suggest only — never execute).
- [ ] Guardrails: prompt-injection resistance for log content, "insufficient evidence" as a valid answer.

### 4. Reliability of the investigator itself
- [ ] Queue + idempotent processing (duplicate alerts don't start duplicate investigations).
- [ ] Durable workflow steps (resume after crash; retries with backoff per step).
- [ ] Incident de-duplication / grouping of related alerts.
- [ ] Timeouts and graceful degradation when LLM providers fail (via the gateway).

### 5. LLM gateway upgrades
- [ ] Route by task: cheap/fast model for triage & summarisation, strongest for reasoning.
- [ ] Track latency, failures, rate-limit state per provider; fallbacks; per-investigation budget.
- [ ] Per-call tracing: which model, tokens, cost, latency, retries — attached to the case file.

### 6. Evaluation (the headline)
- [ ] Benchmark of N chaos scenarios × repeats.
- [ ] Metrics: **root-cause accuracy**, component accuracy, time-to-diagnosis, tool calls, tokens, cost, "insufficient evidence" rate.
- [ ] Compare configurations: single model vs routed; with vs without RAG; different step budgets.
- [ ] Report with confidence intervals — only numbers that were actually measured.

### 7. Observability & dashboard
- [ ] Prometheus + Grafana for the demo system **and** for the investigator/gateway.
- [ ] Sherlock UI: live case file (evidence timeline, hypotheses, final verdict), Watson's postmortem draft,
      evaluation dashboard.

### 8. Fun layer
- [ ] Sherlock narrates deductions ("The p95 rose four minutes after deploy #42 — elementary.").
- [ ] Watson writes the postmortem; Moriarty = the chaos lab.

---

## Interview talking points this creates

- How do you stop an agent from taking dangerous actions? (read-only tools, allow-lists, budgets, human approval)
- How do you evaluate an agent? (ground truth from injected faults, repeated runs, confidence intervals)
- Idempotency and at-least-once delivery for alert webhooks.
- Durable workflows vs a simple loop; what happens if the worker crashes mid-investigation.
- Cost-aware model routing; per-investigation budgets.
- Prompt injection via log lines.
- Why the agent must be allowed to say "insufficient evidence".

## Possible stack (to decide during implementation)

FastAPI services · Postgres · Prometheus/Grafana · LiteLLM gateway · a queue + durable workflow
(e.g. Upstash QStash/Workflow, or Redis + a worker) · a vector store for runbooks (e.g. Upstash Vector or pgvector) ·
Streamlit UI · docker-compose · pytest + GitHub Actions.

## Suggested order

1 → 2 (you need incidents before an investigator) → 3 (single-model agent) → 6 (baseline eval early!) →
5 (routing, measured against the baseline) → 4 → 7 → 8.
