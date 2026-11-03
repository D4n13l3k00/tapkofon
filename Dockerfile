FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.24 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    TAPKOFON_DATA_DIR=/app/session \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 tapkofon
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY README.md LICENSE ./
COPY tapkofon ./tapkofon
RUN uv sync --locked --no-dev --no-editable \
    && mkdir -p /app/session && chown tapkofon:tapkofon /app/session
USER tapkofon
EXPOSE 8888
CMD ["tapkofon", "serve", "--host", "0.0.0.0", "--port", "8888"]
