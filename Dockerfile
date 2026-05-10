FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download embedding model into the image so startup makes zero HF Hub requests.
# HF_HUB_OFFLINE=1 at runtime prevents any validation calls to huggingface.co.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

ENV HF_HUB_OFFLINE=1

COPY app/ ./app/
COPY chroma_db/ ./chroma_db/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
