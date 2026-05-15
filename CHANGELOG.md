# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Cross-encoder reranker (`BAAI/bge-reranker-base`) between overfetch and top-k slice, improving multi-normativa query precision
- Article-boundary legal splitter (`app/legal_splitter.py`) — regex splits on `Artículo`/`Considerando`/`Art.` boundaries, falls back to `RecursiveCharacterTextSplitter`
- `GET /health/deep` endpoint — pings Chroma and Groq, TTL-cached 60 s
- `POST /v1/feedback` endpoint — persists `{request_id, rating, comment}` to `feedback.jsonl`
- TTL in-memory response cache for `/v1/analyze` with `X-Cache: HIT/MISS` header
- `X-Request-ID` header on every response; `request_id` injected into all structured logs via `contextvars`
- Corpus version hash (`chroma_db/.corpus_version`) exposed in `/health` and `RAGResponse`
- Prometheus custom metrics: `legaldev_chunks_retrieved`, `legaldev_top_score`, `legaldev_retrieval_duration_seconds`, `legaldev_llm_duration_seconds`, `legaldev_404_no_coverage_total`, `legaldev_aux_search_triggered_total{type}`
- `POST /v1/analyze` threshold sweep tool (`python tools/eval_retrieval.py --sweep`) with results in `tools/eval_results.md`
- E2E test against real ChromaDB (`tests/test_e2e.py`, `@pytest.mark.slow`), runs only on push to `main`
- `TRUST_PROXY_HEADERS` env var (default `false`) — only trusts `X-Forwarded-For` when explicitly enabled
- `ALLOWED_ORIGINS` validator — rejects `*,https://...` mixed configurations
- Retrieval timeout via `ThreadPoolExecutor` — returns 503 instead of hanging on ChromaDB I/O
- `app/store.py` wrapper for Chroma private API (`_collection.count`, `_collection.get`) — isolates breakage to one file
- `indexed_normativas` populated from ChromaDB at startup, not from `REQUIRED_DOCS` list
- Dockerfile layer order optimized: deps → model download → `chroma_db/` → `app/`
- PII policy in logs: `descripcion_breve` logged as length + SHA-256 prefix, never raw
- `X-API-Key` header authentication for `/v1/analyze`; open by default when `API_KEYS` env var is unset
- Prompt injection detection: `descripcion_breve` scanned for suspicious patterns; logs `suspected_injection: true` without rejecting

### Changed
- "Cobertura del análisis" section rendered in code (`_render_coverage_section`) rather than by LLM — deterministic, frees prompt tokens
- `app/ingest.py` uses `split_document` from `legal_splitter` instead of inline `RecursiveCharacterTextSplitter`

## [0.1.0] - 2026-05-09

### Added
- RAG pipeline over 22 Spanish/EU legal documents: 10 EU normativas (RGPD, EU AI Act, NIS2, DSA, CRA, DORA, ePrivacy, Data Act, DGA, Responsabilidad IA), 4 Spanish (LOPDGDD, ENS, LSSI, LPI), Código Ético CCII, and 7 AEPD guides
- `POST /analyze` endpoint: structured questionnaire → applicable regulations with technical implications
- `GET /health` endpoint with live document count from ChromaDB
- Score-based overfetch retrieval: fetch `OVERFETCH_K` candidates, filter by `MIN_RELEVANCE_SCORE`, keep top `TOP_K_CHUNKS`
- Page-level citations in retrieved chunks
- Rate limiting on `/analyze` (configurable, default 10 req/min)
- Configurable CORS origins via `ALLOWED_ORIGINS` env var
- Groq API timeout via `GROQ_TIMEOUT` env var
- Standalone `ingest.py` script to build the vector store from PDFs
- Docker + docker-compose support
- Railway deployment via pre-built `chroma_db/` baked into the Docker image
- Mandatory legal disclaimer on every response
