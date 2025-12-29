FROM public.ecr.aws/docker/library/python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the initialization scripts and schemas
COPY init-opensearch-aws.py .
COPY import-scopes-to-opensearch-aws.py .
COPY init-and-import.sh .
COPY opensearch-schemas/ ./opensearch-schemas/
COPY auth_server/ ./auth_server/

# Make scripts executable
RUN chmod +x init-opensearch-aws.py import-scopes-to-opensearch-aws.py init-and-import.sh

# Run the combined initialization and import script
ENTRYPOINT ["./init-and-import.sh"]
