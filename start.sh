#!/bin/bash
# Container entrypoint: start the LiteLLM proxy privately, then the public Streamlit app.
set -e

# The proxy is only reachable inside the container, so a random per-boot password is enough
export LITELLM_MASTER_KEY="${LITELLM_MASTER_KEY:-sk-$(python -c 'import secrets; print(secrets.token_urlsafe(32))')}"

litellm --config config.yaml --host 127.0.0.1 --port 4000 &

# Wait for the proxy (up to ~2 min) before opening the app
python - <<'EOF'
import time, urllib.request
for _ in range(120):
    try:
        urllib.request.urlopen("http://127.0.0.1:4000/health/liveliness", timeout=2)
        break
    except Exception:
        time.sleep(1)
EOF

exec streamlit run app.py --server.address 0.0.0.0 --server.port 7860 --server.headless true
