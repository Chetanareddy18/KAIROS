# ── 1. build the dashboard ─────────────────────────────────────────────────────
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── 2. API + agents, serving the built dashboard on the same port ──────────────
FROM python:3.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/ backend/
COPY edge_agent/ edge_agent/
COPY scripts/ scripts/
COPY benchmark/ benchmark/
COPY sources.example.yaml ./
COPY --from=web /web/dist frontend/dist

RUN useradd --create-home kairos && mkdir -p /app/data && chown -R kairos /app
USER kairos

ENV KAIROS_DB_PATH=/app/data/kairos.duckdb KAIROS_DATA_DIR=/app/data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
