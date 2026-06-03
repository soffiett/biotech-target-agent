# ── Base image ────────────────────────────────────────────────────────────────
# python:3.11-slim on linux/arm64 matches AWS Graviton2 Fargate instances
FROM python:3.11-slim

WORKDIR /app

# ── System dependencies ───────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ───────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Pre-download embedding model ──────────────────────────────────────────────
# Baking the model into the image avoids a slow download on every container start.
# The model (~440MB) is cached in /root/.cache/huggingface inside the image.
RUN python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-base-en-v1.5')"

# ── Application code ──────────────────────────────────────────────────────────
COPY . .

# ── Runtime config ────────────────────────────────────────────────────────────
EXPOSE 8501

# Streamlit health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl --fail http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
