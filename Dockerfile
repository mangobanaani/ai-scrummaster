FROM python:3.12-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .

# Production stage — no dev dependencies
FROM base AS production
COPY src/ ./src/
COPY policies/ ./policies/
RUN pip install --no-cache-dir .
ENV PYTHONPATH=/app/src
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Dev stage — includes test dependencies
FROM base AS dev
COPY src/ ./src/
COPY policies/ ./policies/
COPY tests/ ./tests/
RUN pip install --no-cache-dir ".[dev]"
ENV PYTHONPATH=/app/src
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
