# syntax=docker/dockerfile:1
FROM python:3.11-slim

LABEL maintainer="Voice Agent Studio"
LABEL description="Voice Agent Studio — FastAPI backend"

# System deps for PDF parsing (pdfminer.six needs no native libs; PyMuPDF does)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY server.py guardrail.py google_integration.py ./
COPY qpo/ ./qpo/
COPY static/ ./static/

# DB stored in a volume mount at runtime; create placeholder dir
RUN mkdir -p /app/data
ENV DB_PATH=/app/data/agents.db

# Non-root user for security
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# Bind to 0.0.0.0; PORT env var overrides default 8000
CMD ["sh", "-c", "python -m uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]
