# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Modelo de respaldo (`GROQ_FALLBACK_MODEL`, por defecto `openai/gpt-oss-20b`): si el principal falla por cualquier causa se reintenta con él; evento `llm_fallback` en logs y métrica `legaldev_llm_fallback_total{reason}`.
- Comprobación del modelo al arrancar (`GROQ_VERIFY_MODEL_ON_STARTUP`): log ERROR si Groq responde 404; resultado en `/health/deep` junto a `groq_model` y `groq_fallback_model`.
- `RAGResponse.llm_model`: modelo que generó cada informe.
- `GROQ_REASONING_EFFORT` (default `low`), enviado solo a modelos `openai/gpt-oss*`.
- Verificación determinista de citas (`app/citations.py`): cada cita del informe se busca literalmente en los fragmentos recuperados; `RAGResponse.citas` y sección "Verificación de citas" al final del informe; métricas `legaldev_citations_verified_ratio` y `legaldev_citations_unverified_total`.
- Tope de chunks por normativa en el contexto (`MAX_CHUNKS_PER_SOURCE`, default 4).
- INJECTION nueva: la "Guía sobre uso de cookies - AEPD" cuando `usa_cookies=True` (k=2). Medido en el eval: al dejar de gastar plazas del reranker en normativas excluidas, sus chunks caían a las posiciones 13-14 del CrossEncoder (fuera del top-12), así que se garantiza por regla como RGPD, LSSI y CCII.
- Reranker precargado en el arranque (`warmup` en `lifespan`). La cuantización int8 se midió y se descartó: 1,6× en 2 hilos pero altera el ranking.
- `.index_meta.json` escrito por la ingesta (modelo de embeddings, versión del corpus, nº de chunks, versión del splitter); el arranque aborta si el índice se construyó con otro modelo.
- Metadato `article` en los chunks y prefijo `Artículo N (cont.):` en sub-chunks de artículos largos (activo tras reindexar).
- `tools/eval_retrieval.py --chroma-path` y comprobación de modelo del índice; `make eval-sweep`.

### Changed
- Índice ChromaDB reconstruido (2026-09-12) con el splitter v2 a partir de los 22 documentos descargados de sus fuentes oficiales (EUR-Lex, BOE, AEPD, CCII; ver `docs/CORPUS_SOURCES.md`): 13.756 chunks, `corpus_version` `7a2029a4dfd8`, `.index_meta.json` presente (la guardia de arranque ya verifica el modelo de embeddings). La «Directiva de Responsabilidad por Productos con IA» corresponde a la Directiva (UE) 2024/2853 en vigor.
- `GROQ_MAX_TOKENS` por defecto 4000 → 8000 (en gpt-oss los tokens de razonamiento cuentan como salida).
- Retrieval unificado en `_retrieve` (API y eval ejecutan el mismo código); timeout global `RETRIEVAL_TIMEOUT` (60 s) sustituye a `CHROMA_TIMEOUT`.
- Las EXCLUSIONS se aplican antes del recorte y del reranker: las normativas excluidas ya no consumen plazas del contexto.
- `retrieval_duration` ahora incluye las búsquedas de inyección (antes se contabilizaban en `llm_duration`).
- La ingesta construye el índice en `chroma_db.building` y solo después sustituye el anterior; descarta chunks de menos de 40 caracteres; lee PDFs con `pypdf` directamente.
- Dependencias: eliminadas `langchain` y `langchain-community`; `langchain-core` explícita.

### Fixed
- `make ingest` ejecuta `python -m app.ingest` (con `python app/ingest.py` el paquete `app` no se resolvía y la ingesta fallaba al importar).
- Verificación de citas: se tolera hasta un 10 % de diferencia en cada extremo del segmento (punto final añadido por el LLM, palabra cortada en el borde del chunk). Medido en producción: 4 de 12 citas literales se marcaban como no verificadas; la cita ajena al contexto sigue detectándose.
- Producción devolvía 503 en todos los análisis desde el 17/07/2026: Groq retiró `meta-llama/llama-4-scout-17b-16e-instruct`. El modelo por defecto pasa a `openai/gpt-oss-120b` (sustituto recomendado por Groq).
- `/v1/feedback`: `request_id` acotado (1–64 chars, `[A-Za-z0-9_-]`), `comment` ≤ 2000 chars, rate limit.
- `tools/diagnose_ranking.py` usaba `all-MiniLM-L6-v2` contra un índice multilingüe.
- `tools/eval_results.md` regenerado con el formato actual.
- `make ingest` no podía completar el intercambio del índice en Windows (handles de SQLite retenidos por ChromaDB); ahora se liberan explícitamente.

## [0.4.0] - 2026-06-24

### Added
- INJECTIONS incondicionales: la normativa aplicable se garantiza aunque el proyecto sea de dominio lejano (RGPD ahora se recupera en casos donde antes no). [P3]
- 2 casos nuevos en la suite de evaluación (dominio lejano + 1-chunk).

### Changed
- normativas_detectadas usa umbral ≥2 chunks: coherencia entre la normativa del header y las secciones del cuerpo. [P2a]
- Retrieval unificado en retrieve_docs_sync: el eval ejecuta ahora la misma lógica que producción (elimina la divergencia eval↔producción).

### Fixed
- filter= en la búsqueda de Chroma (antes where=): las INJECTIONS habrían lanzado TypeError con Chroma real.

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
