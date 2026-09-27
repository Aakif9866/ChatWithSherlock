# so basically found out Openrouter does this
# but it has a specific limit

# but LLM Lite does the same for free
# an opensource model

# ---------------------------------------------------------------
# Sherlock Holmes chatbot — talks to the LiteLLM proxy (free-auto)
# Run the proxy first, then:  uv run --env-file .env streamlit run app.py
# ---------------------------------------------------------------
import hashlib
import hmac
import json
import os
import random
import secrets
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import streamlit as st
from openai import APIConnectionError, OpenAI

PROXY_URL = "http://localhost:4000/v1"
PROXY_KEY = os.environ.get("LITELLM_MASTER_KEY", "")  # the proxy's master_key, from .env
MODEL = "free-auto"

# Limits: keep each request small so free-tier token quotas last longer
MAX_INPUT_CHARS = 1000   # longest message a user may send
MAX_HISTORY = 20         # only the last 20 messages are sent to the model
MAX_REPLY_TOKENS = 2000  # cap per reply; includes hidden "thinking" tokens, so not too low

# Public deployment (PUBLIC_MODE=1): each visitor gets MAX_QUESTIONS, stress test is hidden
PUBLIC_MODE = os.environ.get("PUBLIC_MODE") == "1"
MAX_QUESTIONS = 10
STATS_KEY = os.environ.get("STATS_KEY", "")  # open ?stats=<STATS_KEY> to see usage; unset = disabled

# Optional database for the all-time visitor count: Upstash Redis (free tier), over its REST API.
# Unset = counts live in memory only and reset when the app restarts.
REDIS_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "").rstrip("/")
REDIS_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
DB_ENABLED = bool(REDIS_URL and REDIS_TOKEN)
CONTACT_EMAIL = "aakif9866@gmail.com"

SYSTEM_PROMPT = """You are Sherlock Holmes, the consulting detective of 221B Baker Street.
Stay in character at all times. You are brilliant, precise, a little arrogant, and easily
bored by the obvious. From small details in what the user writes (word choice, typos,
time of day they mention, what they ask about) make bold, playful deductions about them,
and explain your reasoning step by step, as you do with Watson. Refer now and then to
Watson, Mrs. Hudson, Lestrade, Moriarty, your violin, or your pipe. Keep answers under
150 words unless the user asks you to solve a proper case."""

WATSON_REPLIES = [
    "Dr. Watson here. I'm afraid Holmes is not at home — he left at dawn in the "
    "disguise of an elderly clergyman and would not say where he was going.",
    "Watson speaking. Holmes has locked himself in with his chemistry set and a "
    "most unpleasant smell. He has asked, rather rudely, not to be disturbed.",
    "Mrs. Hudson tells me Holmes dashed off in a hansom cab after reading a "
    "telegram. Something about Lestrade and a missing emerald. Do try again shortly.",
    "Holmes is in one of his black moods, lying on the sofa, scraping at his "
    "violin. He answers no one. Give him a moment — it usually passes.",
    "I regret to say Holmes is out. The Baker Street Irregulars came running with "
    "news and he was gone before I could finish my breakfast.",
    "Watson here. Holmes is at the British Museum researching a 17th-century "
    "cipher. He will return when he has cracked it, or when he gets hungry.",
    "The line to Baker Street appears to be down — or, if you ask Holmes, cut. "
    "He suspects Moriarty. I suspect the proxy on port 4000 is not running.",
    "Holmes is asleep, which happens roughly once every three days. I shall not "
    "be the one to wake him. Please call again presently.",
]

client = OpenAI(base_url=PROXY_URL, api_key=PROXY_KEY or "missing")  # checked below
_model_map = {}  # proxy model id -> "gemini/gemini-3.8-flash", etc.


def model_for(model_id: str) -> str:
    """Look up which configured model a response came from (via /model/info)."""
    if model_id not in _model_map:
        req = urllib.request.Request(f"{PROXY_URL}/model/info",
                                     headers={"Authorization": f"Bearer {PROXY_KEY}"})
        with urllib.request.urlopen(req, timeout=5) as r:
            for m in json.load(r)["data"]:
                _model_map[m["model_info"]["id"]] = m["litellm_params"]["model"]
    return _model_map.get(model_id, "unknown")


def provider_from(model: str) -> str:
    """'openrouter/nvidia/nemotron...' -> 'OpenRouter (nvidia/nemotron...)'."""
    names = {"gemini": "Gemini", "groq": "Groq", "openrouter": "OpenRouter", "cerebras": "Cerebras"}
    prefix, _, rest = model.partition("/")
    return f"{names.get(prefix, prefix)} ({rest})" if rest else model


def ask(messages):
    """One non-streaming call. Returns (text, provider, seconds) or raises."""
    start = time.time()
    raw = client.chat.completions.with_raw_response.create(
        model=MODEL, messages=messages, max_tokens=MAX_REPLY_TOKENS)
    resp = raw.parse()
    provider = provider_from(model_for(raw.headers.get("x-litellm-model-id", "")))
    return resp.choices[0].message.content or "", provider, time.time() - start


st.set_page_config(page_title="221B Baker Street", page_icon="🕵️")

# Victorian serif fonts (colors stay Streamlit's default)
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;1,500&family=EB+Garamond:wght@400;500&display=swap');

html, body, .stApp, .stMarkdown, p, li { font-family: 'EB Garamond', Georgia, serif; font-size: 1.08rem; }
h1, h2, h3 { font-family: 'Playfair Display', Georgia, serif !important; letter-spacing: .5px; }
[data-testid="stChatInput"] textarea { font-family: 'EB Garamond', Georgia, serif; font-size: 16px; }
[data-testid="stTable"] { overflow-x: auto; }

/* Navbar: brand on the left, user count + contact button on the right */
.st-key-navbar { border-bottom: 1px solid rgba(128, 128, 128, .25); padding-bottom: .6rem; margin-bottom: .25rem; }
.st-key-brand p { font-family: 'Playfair Display', Georgia, serif; font-weight: 700; font-size: 1.15rem; margin: 0; }

/* The grand email reveal */
.contact-reveal { text-align: center; padding: .5rem 0 1rem; }
.contact-reveal .email {
  display: inline-block; margin-top: .75rem; font-family: 'Playfair Display', Georgia, serif;
  font-size: 1.7rem; font-weight: 700; word-break: break-all;
  background: linear-gradient(90deg, #b8860b, #e8c872, #b8860b); background-size: 200% auto;
  -webkit-background-clip: text; background-clip: text; color: transparent;
  animation: shimmer 2.5s linear infinite, pop .6s ease-out;
}
@keyframes shimmer { to { background-position: 200% center; } }
@keyframes pop { 0% { transform: scale(.4); opacity: 0; } 70% { transform: scale(1.12); } 100% { transform: scale(1); opacity: 1; } }

/* Phones: tighter spacing, smaller title, wider chat bubbles */
@media (max-width: 640px) {
  .block-container, [data-testid="stMainBlockContainer"] { padding: 3.5rem 0.75rem 6rem !important; }
  h1 { font-size: 1.6rem !important; line-height: 1.25 !important; }
  html, body, .stApp, .stMarkdown, p, li { font-size: 1rem; }
  [data-testid="stChatMessage"] { padding: 0.6rem 0.5rem; gap: 0.5rem; }
  [data-testid="stChatMessage"] [data-testid^="stChatMessageAvatar"] { width: 1.8rem; height: 1.8rem; }
  [data-testid="stBottom"] > div { padding-left: 0.75rem; padding-right: 0.75rem; }
  .contact-reveal .email { font-size: 1.3rem; }
}
</style>
""", unsafe_allow_html=True)

def redis(*command):
    """Run one Redis command through Upstash's REST API. Returns the result, or None if the
    database isn't configured or the call fails (the app then falls back to memory)."""
    if not DB_ENABLED:
        return None
    req = urllib.request.Request(REDIS_URL, data=json.dumps(command).encode(),
                                 headers={"Authorization": f"Bearer {REDIS_TOKEN}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return json.load(r).get("result")
    except Exception as e:
        print(f"[db] {command[0]} failed: {e}", flush=True)
        return None


@st.cache_resource
def usage():
    """Usage shared across all sessions, in memory (resets when the app restarts).
    Visitors are stored as salted hashes, never raw IPs; chat content is never stored.
    With the database on, the salt is kept there so a visitor's hash stays the same across
    restarts - otherwise returning visitors would be counted again."""
    salt = secrets.token_hex(16)
    redis("SET", "sherlock:salt", salt, "NX")  # only the first boot ever sets it
    salt = redis("GET", "sherlock:salt") or salt
    return {"questions": {}, "providers": {}, "visitors": set(), "started": time.time(),
            "salt": salt}, threading.Lock()


def visitor_id() -> str:
    """Anonymous visitor id: hash of the IP (first X-Forwarded-For hop behind a proxy),
    so a page refresh doesn't reset the limit."""
    forwarded = st.context.headers.get("X-Forwarded-For", "")
    ip = str(forwarded.split(",")[0].strip() or st.context.ip_address or "unknown")
    return hashlib.sha256((usage()[0]["salt"] + ip).encode()).hexdigest()[:10]


def questions_used() -> int:
    data, lock = usage()
    with lock:
        return data["questions"].get(visitor_id(), 0)


def use_question() -> int:
    data, lock = usage()
    with lock:
        n = data["questions"][visitor_id()] = data["questions"].get(visitor_id(), 0) + 1
    return n


def log_usage(n: int, provider: str, secs: float) -> None:
    """One line per question in the server log (Render → Logs). No chat content."""
    data, lock = usage()
    with lock:
        data["providers"][provider] = data["providers"].get(provider, 0) + 1
    print(f"[usage] visitor={visitor_id()} question={n}/{MAX_QUESTIONS} "
          f"provider={provider} secs={secs:.1f}", flush=True)


def record_visit() -> int:
    """Remember this visitor (hashed) and return the unique-visitor count:
    all-time from the database if configured, otherwise since the last restart."""
    vid = visitor_id()
    data, lock = usage()
    with lock:
        data["visitors"].add(vid)
        since_restart = len(data["visitors"])
    if "visitor_total" not in st.session_state:  # hit the database once per browser session
        redis("SADD", "sherlock:visitors", vid)  # a set stores each visitor only once
        st.session_state.visitor_total = redis("SCARD", "sherlock:visitors")
    return st.session_state.visitor_total or since_restart


# ---- Private stats page: ?stats=<STATS_KEY> -------------------------------
if STATS_KEY and hmac.compare_digest(st.query_params.get("stats", ""), STATS_KEY):
    data, lock = usage()
    with lock:
        counts = dict(data["questions"])
        providers = dict(data["providers"])
        visitors = len(data["visitors"])
    all_time = redis("SCARD", "sherlock:visitors")
    st.title("📊 Usage stats")
    if all_time is not None:
        st.metric("All-time unique visitors (database)", all_time)
    else:
        st.caption("Database not configured - only counts since the last restart are available.")
    st.caption(f"Since last restart: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(data['started']))}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Visitors", visitors)
    c2.metric("Chatted", len(counts))
    c3.metric("Questions asked", sum(counts.values()))
    c4.metric("Hit the limit", sum(1 for n in counts.values() if n >= MAX_QUESTIONS))
    if providers:
        st.subheader("Replies by provider")
        st.markdown("\n".join(f"- **{n}** · {p}" for p, n in sorted(providers.items(), key=lambda x: -x[1])))
    st.stop()

# ---- Contact: 4 "are you sure?" dialogs at random spots, then the email is revealed ----
# The email is only sent to the browser after the 4th "Yes, really".
CONTACT_QUESTIONS = [
    "Do you really want to contact me?",
    "Do you really want to meet me?",
    "Are you absolutely certain? Mrs. Hudson will have to put the kettle on.",
    "Final answer? Holmes deduces you will write a rather splendid email.",
]


def contact_reset():
    st.session_state.contact_step = 0


def contact_open(step: int):
    """Open question `step` (1-based) at a new random offset from the centre."""
    st.session_state.contact_step = step
    # fractions of the free space around the dialog: sideways either way, downward only
    # (Streamlit pins dialogs near the top), so it always stays on screen
    st.session_state.contact_pos = (random.uniform(-0.45, 0.45), random.uniform(0, 0.8))


def contact_dialog(step: int):
    dx, dy = st.session_state.contact_pos

    @st.dialog(f"✉️ Question {step} of {len(CONTACT_QUESTIONS)}", on_dismiss=contact_reset)
    def ask_again():
        st.markdown(f"""<style>[data-testid="stDialog"] > div {{ transform: translate(
            calc((100vw - 100%) * {dx:.2f}), calc((100vh - 100% - 7rem) * {dy:.2f})); }}</style>""",
                    unsafe_allow_html=True)
        st.markdown(f"#### {CONTACT_QUESTIONS[step - 1]}")
        yes, no = st.columns(2)
        if yes.button("Yes, really", type="primary", width="stretch"):
            if step < len(CONTACT_QUESTIONS):
                contact_open(step + 1)
            else:
                contact_reset()
                st.session_state.contact_reveal = True
            st.rerun()
        if no.button("Not really", width="stretch"):
            contact_reset()
            st.rerun()

    ask_again()


@st.dialog("🎩 Elementary! The case is closed.", width="medium")
def contact_reveal():
    st.markdown(f"""<div class="contact-reveal">
        <div>Your persistence is remarkable. You may write to me at</div>
        <div class="email">{CONTACT_EMAIL}</div>
        </div>""", unsafe_allow_html=True)
    st.link_button("✉️ Write the email", f"mailto:{CONTACT_EMAIL}?subject=Chat%20with%20Sherlock",
                   type="primary", width="stretch")


# ---- Navbar ------------------------------------------------------------------
users = record_visit()
with st.container(key="navbar", horizontal=True, vertical_alignment="center",
                  horizontal_alignment="distribute"):
    with st.container(key="brand", width="content"):
        st.markdown("🕵️ 221B Baker Street")
    with st.container(horizontal=True, vertical_alignment="center", width="content"):
        st.badge(f"{users} {'user' if users == 1 else 'users'}", icon="👥", color="gray",
                 help=("Unique visitors of all time" if DB_ENABLED else
                       "Unique visitors since the app last restarted") + " (anonymous: hashed IP).")
        st.button("Contact me", icon="✉️", key="contact_btn", on_click=contact_open, args=(1,))

st.title("🕵️ Chat with Sherlock Holmes")
st.caption("Every reply goes through your LiteLLM proxy → Gemini / Groq / OpenRouter")

if not PROXY_KEY:
    st.error("LITELLM_MASTER_KEY is not set. Start the app with: "
             "`uv run --env-file .env streamlit run app.py`")
    st.stop()

if "history" not in st.session_state:
    st.session_state.history = []  # list of dicts: role, content, provider, secs


# ---- Sidebar: stats + stress test ----------------------------------------
with st.sidebar:
    st.header("Proxy stats")
    counts = {}
    for m in st.session_state.history:
        if m["role"] == "assistant":
            counts[m["provider"]] = counts.get(m["provider"], 0) + 1
    if counts:
        st.markdown("\n".join(f"- **{n}** · {p}" for p, n in counts.items()))
    else:
        st.caption("No replies yet")

    if not PUBLIC_MODE:
        st.header("Stress test")
        st.caption("Fire N parallel requests to see load balancing, rate limits and failover.")
        n = st.slider("Parallel requests", 1, 30, 10)
    if not PUBLIC_MODE and st.button("Run burst"):
        msgs = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "In one sentence, deduce something about me."}]

        def one(_):
            try:
                _, provider, secs = ask(msgs)
                return provider, f"{secs:.1f}s"
            except Exception as e:  # show failures instead of crashing
                return "ERROR", str(e)[:80]

        with st.spinner(f"Sending {n} requests..."):
            with ThreadPoolExecutor(max_workers=n) as pool:
                results = list(pool.map(one, range(n)))
        st.table([{"provider": p, "time / error": t} for p, t in results])

    if st.button("Clear chat"):
        st.session_state.history = []
        st.rerun()

# ---- Chat ------------------------------------------------------------------
AVATARS = {"assistant": "🕵️", "watson": "🩺", "user": None}
for m in st.session_state.history:
    with st.chat_message("user" if m["role"] == "user" else "assistant", avatar=AVATARS[m["role"]]):
        st.markdown(m["content"])
        if m["role"] == "assistant":
            st.caption(f"via {m['provider']} · {m['secs']:.1f}s")
        elif m["role"] == "watson":
            st.caption("Sherlock unavailable — proxy on port 4000 is not reachable")

out_of_questions = PUBLIC_MODE and questions_used() >= MAX_QUESTIONS
if PUBLIC_MODE:
    if out_of_questions:
        st.info("🎻 Holmes has taken up his violin and will see you no further. "
                f"(Each visitor may ask {MAX_QUESTIONS} questions on this public demo.)")
    else:
        st.caption(f"Questions left: {MAX_QUESTIONS - questions_used()} of {MAX_QUESTIONS} · "
                   "Anonymous usage is counted (hashed IP, no chat content stored) "
                   "to keep this free demo fair.")

if st.session_state.get("contact_step", 0):
    contact_dialog(st.session_state.contact_step)
elif st.session_state.pop("contact_reveal", False):
    st.balloons()
    contact_reveal()

if prompt := st.chat_input("Present your case to Mr. Holmes...", max_chars=MAX_INPUT_CHARS,
                           disabled=out_of_questions):
    n = use_question() if PUBLIC_MODE else 0
    st.session_state.history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Watson's messages are not part of Sherlock's conversation, so don't send them.
    # Only the most recent MAX_HISTORY messages go out, so requests don't grow forever.
    chat = [{"role": m["role"], "content": m["content"]}
            for m in st.session_state.history if m["role"] != "watson"]
    recent = chat[-MAX_HISTORY:]
    if recent[0]["role"] == "assistant":  # conversation must start with a user turn
        recent = recent[1:]
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + recent
    with st.chat_message("assistant", avatar="🕵️"):
        try:
            with st.spinner("Holmes is thinking..."):
                text, provider, secs = ask(messages)
            st.session_state.history.append(
                {"role": "assistant", "content": text, "provider": provider, "secs": secs})
            log_usage(n, provider, secs)
        except (APIConnectionError, OSError):  # proxy is down / port 4000 closed
            st.session_state.history.append(
                {"role": "watson", "content": random.choice(WATSON_REPLIES)})
            log_usage(n, "Watson (proxy down)", 0)
        except Exception as e:  # proxy is up but every provider failed
            log_usage(n, "ERROR", 0)
            st.error(f"The proxy answered with an error: {e}")
            st.stop()
    st.rerun()
