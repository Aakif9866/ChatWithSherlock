# Docker image (used by Render): LiteLLM proxy (private) + Streamlit app (public on $PORT, default 7860)
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Run as a non-root user
RUN useradd -m -u 1000 user
USER user
WORKDIR /home/user/app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH=/home/user/app/.venv/bin:$PATH \
    PUBLIC_MODE=1

COPY --chown=user pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-install-project

COPY --chown=user app.py config.yaml start.sh ./
COPY --chown=user .streamlit .streamlit

EXPOSE 7860
CMD ["bash", "start.sh"]
