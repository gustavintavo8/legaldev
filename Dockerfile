FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen --no-cache

# Add the project venv to PATH so subsequent RUN steps and the CMD use it
ENV PATH="/app/.venv/bin:$PATH"

# HF cache must live in /tmp — only writable path in HF Spaces at runtime.
# These vars must be set BEFORE the model download RUN step below.
ENV HF_HOME=/tmp/huggingface \
    TRANSFORMERS_CACHE=/tmp/huggingface/hub \
    SENTENCE_TRANSFORMERS_HOME=/tmp/huggingface/sentence_transformers

# Pre-download embedding model into the image so startup makes zero HF Hub requests.
# HF_HUB_OFFLINE=1 at runtime prevents any validation calls to huggingface.co.
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2'); CrossEncoder('BAAI/bge-reranker-base')" && \
    find /tmp/huggingface -name "*.lock" -delete && \
    find /tmp/huggingface -name "*.incomplete" -delete

ENV HF_HUB_OFFLINE=1

COPY chroma_db/ ./chroma_db/
COPY app/ ./app/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
