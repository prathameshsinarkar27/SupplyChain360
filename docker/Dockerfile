# =============================================================================
# SupplyChain360 - Application Dockerfile
# =============================================================================
# This container runs Python-based pipeline code (ingestion, validation, ETL).
# PySpark, Airflow, and PostgreSQL run as separate services (see docker-compose.yml).
# =============================================================================

FROM python:3.11-slim

LABEL maintainer="SupplyChain360 Team"
LABEL description="Application container for SupplyChain360 data pipelines"

# Prevent Python from writing .pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System dependencies needed by psycopg2 and general build tooling
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (better Docker layer caching)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the rest of the project
COPY . .

# Default command: drop into a shell. Later phases will override this
# with actual pipeline entrypoints (e.g., python -m src.ingestion.run_ingestion).
CMD ["bash"]
