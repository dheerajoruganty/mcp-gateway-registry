# Lightweight Docker image for AOSS CLI management tasks
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy only the necessary files for AOSS management
COPY scripts/manage-aoss-indexes.py /app/scripts/manage-aoss-indexes.py
COPY pyproject.toml /app/pyproject.toml

# Install uv for fast Python package management
RUN pip install --no-cache-dir uv

# Install only the required dependencies for AOSS management
RUN uv pip install --system \
    'boto3>=1.28.0' \
    'opensearch-py[async]>=2.4.0'

# Set up environment
ENV PYTHONUNBUFFERED=1

# Default command (can be overridden)
CMD ["python", "scripts/manage-aoss-indexes.py", "list"]
