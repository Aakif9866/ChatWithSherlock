# so basically found out Openrouter does this
# but it has a specific limit

# but LLM Lite does the same for free
# an opensource model

# ---------------------------------------------------------------
# Sherlock Holmes chatbot — talks to the LiteLLM proxy (free-auto)
# Run the proxy first, then:  uv run --env-file .env streamlit run app.py
# ---------------------------------------------------------------
import json
import os
import random
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
MAX_REPLY_TOKENS = 800   # cap on each reply's length

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
[data-testid="stChatInput"] textarea { font-family: 'EB Garamond', Georgia, serif; }
</style>
""", unsafe_allow_html=True)

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
    st.write(counts or "No replies yet")

    st.header("Stress test")
    st.caption("Fire N parallel requests to see load balancing, rate limits and failover.")
    n = st.slider("Parallel requests", 1, 30, 10)
    if st.button("Run burst"):
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

if prompt := st.chat_input("Present your case to Mr. Holmes...", max_chars=MAX_INPUT_CHARS):
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
        except (APIConnectionError, OSError):  # proxy is down / port 4000 closed
            st.session_state.history.append(
                {"role": "watson", "content": random.choice(WATSON_REPLIES)})
        except Exception as e:  # proxy is up but every provider failed
            st.error(f"The proxy answered with an error: {e}")
            st.stop()
    st.rerun()
