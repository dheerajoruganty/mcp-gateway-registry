# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv (pinned version)
RUN pip install --no-cache-dir uv==0.5.11

# Copy pyproject.toml first for layer caching
COPY pyproject.toml .

# Install dependencies with cache mount
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -e .

# Copy application
COPY app/ app/
COPY create_api_key.py ./

# Create data directory
RUN mkdir -p /var/lib/sqlite

# Expose port
EXPOSE 8890

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8890/health || exit 1

CMD ["python", "-m", "app.main"]