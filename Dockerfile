FROM ghcr.io/astral-sh/uv:python3.15-trixie-slim AS build
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.15-slim-trixie
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH HOST=0.0.0.0
USER nobody
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/health', timeout=4)"]
CMD ["kizaru-mcp"]
