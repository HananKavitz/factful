# ---- frontend build ----
FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- runtime ----
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY --from=frontend /app/frontend/dist ./frontend/dist
RUN pip install --no-cache-dir .
ENV FRONTEND_DIST_DIR=/app/frontend/dist
EXPOSE 8000
CMD ["uvicorn", "factful.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
