# ── Stage 1: dependency install ───────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /install

# Install build deps only in this stage
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/deps -r requirements.txt


# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Non-root user for security
RUN useradd --create-home --shell /bin/bash botuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /deps /usr/local

# Copy source code
COPY src/ ./src/

# Persistent volume for the SQLite database
RUN mkdir -p /app/data && chown botuser:botuser /app/data
VOLUME ["/app/data"]

USER botuser

# Health check – just verifies the process is alive
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import os; open('/app/data/.healthcheck', 'w').close()" || exit 1

CMD ["python", "src/bot.py"]
