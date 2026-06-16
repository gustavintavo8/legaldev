# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.1] - 2026-06-16

### Security
- Cerrada vía de inyección de prompt en el campo `ccaa` (ahora enum cerrado de comunidades autónomas, validado por Pydantic).

### Fixed
- Eliminados chunks duplicados en `pre_rerank` en proyectos de baja señal.
- El reranker y la llamada a Groq ya no bloquean el event loop; el servidor responde a otras peticiones (incl. `/health`) durante un análisis.

## [0.3.0] - 2026-05-25

### Added
- INJECTIONS: garantía determinista de normativa aplicable post-reranker (RGPD, EU AI Act, LSSI, IA Agéntica) según campos del cuestionario.
- EXCLUSIONS condicionales para documentos de IA (Adecuación RGPD+IA, IA Agéntica) y LOPDGDD en proyectos sin datos ni usuarios.
- Gold standard de evaluación con precision (`negative_expected`) además de recall.
- Caso de evaluación `lssi-web-publica`.

### Changed
- El evaluador (`eval_retrieval.py`) ahora replica el pipeline completo de producción (recorte `reranker_top_k`, CrossEncoder, exclusiones), corrigiendo una fidelidad optimista que ocultaba misses de recall.

### Fixed
- Recall de normativa fundamental (RGPD, EU AI Act, LSSI): de 2/10 a 11/11.
- Falsos positivos de documentos de IA en proyectos sin IA: de 16 a 2 (2 residuales de DSA, documentados).

## [0.2.0] - 2026-05-15

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
- Retrieval timeout via `asyncio.wait_for` + `asyncio.to_thread` — returns 503 instead of hanging on ChromaDB I/O; `run_pipeline` is fully async
- `app/store.py` wrapper for Chroma private API (`_collection.count`, `_collection.get`) — isolates breakage to one file
- `indexed_normativas` populated from ChromaDB at startup, not from `REQUIRED_DOCS` list
- Dockerfile layer order optimized: deps → model download → `chroma_db/` → `app/`
- PII policy in logs: `descripcion_breve` logged as length + SHA-256 prefix, never raw
- `X-API-Key` header authentication for `/v1/analyze`; open by default when `API_KEYS` env var is unset
- Prompt injection detection: `descripcion_breve` scanned for suspicious patterns; logs `suspected_injection: true` without rejecting
- `Makefile push-space` target — creates/resets `hf-space` branch with `README_hf.md` swapped in as `README.md`, force-pushes to `space` remote; see README for full workflow
- `README_hf.md` — HF Spaces frontmatter file used only in the Space repo; `README.md` stays clean for GitHub
- Git LFS tracking for `chroma_db/` binaries (`.sqlite3`, `.bin`) — required by Hugging Face Hub's 10 MB per-file limit
- `HF_HOME`, `TRANSFORMERS_CACHE`, `SENTENCE_TRANSFORMERS_HOME` → `/tmp/huggingface` in Dockerfile — HF Spaces only allows writes to `/tmp` at runtime; baked model weights remain accessible without landing on a world-writable path

### Changed
- EMBEDDING_MODEL: `all-MiniLM-L6-v2` → `paraphrase-multilingual-MiniLM-L12-v2` — better recall on Spanish legal text; the switch was previously blocked by Railway's 512 MB RAM limit and became trivial once HF Spaces removed that constraint; see README for full rationale
- `encode_kwargs={"normalize_embeddings": True}` added to every `HuggingFaceEmbeddings` instantiation (`app/ingest.py`, `app/main.py`, `tools/eval_retrieval.py`, `tests/test_e2e.py`) — `paraphrase-multilingual-MiniLM-L12-v2` has no `Normalize` module in its pipeline; without this kwarg embeddings are not unit vectors, L2 distances exceed √2, and LangChain's score formula produces negative values that break the threshold entirely
- `MIN_RELEVANCE_SCORE` default raised from `0.35` to `0.40` — sweep with the new model confirmed 100% recall at all thresholds 0.20–0.45; 0.40 gives ~8% noise reduction at no recall cost
- Deploy target: Railway → Hugging Face Spaces — Railway free tier RAM (512 MB) is too tight for `paraphrase-multilingual-MiniLM-L12-v2` (~500 MB at runtime); HF Spaces provides the headroom needed; see README for `make push-space` workflow
- "Cobertura del análisis" section rendered in code (`_render_coverage_section`) rather than by LLM — deterministic, frees prompt tokens
- `app/ingest.py` uses `split_document` from `legal_splitter` instead of inline `RecursiveCharacterTextSplitter`

### Fixed
- Dockerfile `rm -rf /tmp/*` replaced with targeted `find` deletion of `.lock` and `.incomplete` files — broad cleanup was deleting baked model weights, forcing a re-download on every cold start
- `feedback.jsonl` removed from git tracking and added to `.gitignore` — file was committed with manual test entries from development

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
