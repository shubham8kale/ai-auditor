FROM node:24-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS application
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY auditor/ ./auditor/
COPY --from=frontend /build/dist ./frontend/dist
RUN useradd --create-home --uid 10001 auditor && mkdir -p /app/data && chown auditor:auditor /app/data
USER auditor
EXPOSE 10000
# A single worker owns the lightweight background queue; jobs remain persisted in PostgreSQL.
CMD ["sh", "-c", "exec python -m uvicorn auditor.main:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1 --no-access-log"]
