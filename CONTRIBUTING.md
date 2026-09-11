# Contributing to LegalDev

Thank you for your interest in contributing. This project is open source under the MIT license.

## Getting started

```bash
git clone https://github.com/gustavintavo8/legaldev.git
cd legaldev
uv sync                # installs runtime + dev (pytest, ruff)
cp .env.example .env   # add your GROQ_API_KEY
make ingest            # build the vector store (requires PDFs in docs/)
make dev               # uvicorn app.main:app --reload
```

## Running tests

```bash
make test   # uv run pytest -v
```

Tests are fully mocked — no Groq API key or ChromaDB needed to run them.

## What to contribute

- **New legal documents**: add the PDF to `docs/`, add its filename to `REQUIRED_DOCS` in `app/corpus.py` (with the correct `doc_type` in `DOC_TYPE_MAP` in `ingest.py`), then re-run `make ingest`.
- **Retrieval improvements**: chunking strategy and embedding model live in `ingest.py`. Retrieval parameters (`OVERFETCH_K`, `RERANKER_TOP_K`, `MIN_RELEVANCE_SCORE`, `TOP_K_CHUNKS`, `MAX_CHUNKS_PER_SOURCE`, `RGPD_K`, `COOKIES_K`, `COLEGIADO_K`, `RETRIEVAL_TIMEOUT`) are in `app/config.py`. Run `make eval` after any retrieval change to verify recall across the test cases in `tools/eval_cases.yaml`; `make eval-sweep` regenerates `tools/eval_results.md` (recall/FP/noise across thresholds 0.20-0.45).
- **Prompt improvements**: system prompt and user message construction are in `app/rag.py` (`SYSTEM_PROMPT`, `_build_user_message`). The snapshot test in `tests/test_rag.py` pins the prompt hash — update it consciously if you change the prompt. The two sections appended after the LLM's own output — `## Cobertura del análisis` and `## Verificación de citas` — are rendered in code (`_render_coverage_section`, `_render_citation_section` in `app/rag.py`), not by the LLM; don't try to get the model to produce them via prompt changes.
- **Bug fixes**: open an issue first if the fix is non-trivial.

## Adding a new auxiliary search

Auxiliary searches recover normativas that the main query systematically buries due to lexical density (see README "Query descriptiva + búsqueda auxiliar por dominio"). Add one only when you have empirical evidence of the problem (run `tools/diagnose_ranking.py` or `make eval`).

Steps:

1. Add a `k` setting to `Settings` in `app/config.py` and to `.env.example`:
   ```python
   # config.py
   my_domain_k: int = 6
   ```

2. Add an `AuxSearch` entry to `AUXILIARY_SEARCHES` in `app/rag.py`:
   ```python
   AuxSearch(
       condition=lambda inp: <condition based on QuestionnaireInput fields>,
       query="<domain-specific query string — no generic terms>",
       k=settings.my_domain_k,
       name="my_domain",  # labels the legaldev_aux_search_triggered_total{type} metric
   ),
   ```

3. Add a test case to `tools/eval_cases.yaml` that exercises the new condition and expects the normativa in `expected`.

4. Run `make eval` — all cases must pass before opening a PR.

## Adding a new exclusion

`EXCLUSIONS` in `app/rag.py` removes chunks of normativas that are structurally inapplicable given the questionnaire (e.g., ENS for public sector only). Add one when a normativa produces systematic false positives that cannot be fixed by raising the score threshold.

```python
Exclusion(
    condition=lambda inp: <condition when the normativa should be excluded>,
    stem="<filename stem without .pdf>",
),
```

## Adding a new injection

`INJECTIONS` in `app/rag.py` guarantees the best available fragments of a normativa that legally applies but that the CrossEncoder systematically underranks against more "actionable-sounding" AEPD guides (see README "Filtrado por reglas: EXCLUSIONS e INJECTIONS"). Add one when a normativa passes the score threshold on its own but is regularly pushed out of the final top-k.

```python
Injection(
    condition=lambda inp: <condition when the normativa applies>,
    stem="<filename stem without .pdf>",
    k=<fragments to fetch>,
),
```

It runs as a source-filtered search (`filter={"source": f"{stem}.pdf"}`) with no score threshold — an injection is a guarantee, not a suggestion.

## Re-indexing the corpus

Chunking, embedding, and index metadata are built by `app/ingest.py`. Re-run it whenever the source PDFs, the splitter (`app/legal_splitter.py`), or `EMBEDDING_MODEL` (`app/corpus.py`) change:

```bash
# with the 22 PDFs in docs/
make ingest                      # builds into chroma_db.building/, then swaps it into chroma_db/
cat chroma_db/.index_meta.json   # check embedding_model and chunk count
make eval                        # expect 13/13, 0 FP
make eval-sweep                  # regenerates tools/eval_results.md
git add chroma_db/ tools/eval_results.md && git commit -m "chore: rebuild index"
git push && make push-space
```

Notes:

- `ingest.py` never deletes the existing index before the new one is complete: it builds into `chroma_db.building/`, writes `.corpus_version` and `.index_meta.json` (`embedding_model`, `corpus_version`, `chunks`, `documents`, `splitter_version`, `min_chunk_chars`, `created_at`), then swaps it into place. `app/main.py`'s `lifespan` refuses to start if `.index_meta.json` declares an `embedding_model` different from `EMBEDDING_MODEL` — an index built with another embedding model produces meaningless scores, so this fails loud instead of serving garbage. An index built before this metadata existed only logs a WARNING.
- Bump `SPLITTER_VERSION` in `app/ingest.py` whenever the chunking strategy changes; it's recorded in `.index_meta.json` so you can tell which index came from which splitter.
- `MIN_CHUNK_CHARS` (40) drops chunks shorter than that (after `strip()`) as page header/footer noise. Chunks that carry an `article` heading are always kept regardless of length — a one-line derogated article is still complete legal content, not noise.
- **Windows note:** ChromaDB can keep SQLite file handles open after `Chroma.from_documents`, which makes renaming `chroma_db.building/` into `chroma_db/` fail. `ingest.py` calls `chromadb.api.client.SharedSystemClient.clear_system_cache()` and retries the rename a few times before giving up; if it still can't swap, the freshly built index is left intact in `chroma_db.building/` with on-screen instructions to finish the swap by hand. The previous index is never removed before the new one is confirmed complete.
- Use `tools/eval_retrieval.py --chroma-path <dir>` to evaluate an index other than the one at `CHROMA_DB_PATH` (e.g. one you just built but haven't swapped in yet). It reads `.index_meta.json` first and refuses to run if the index was built with a different embedding model than `--model` — the vectors wouldn't be comparable (`--force` overrides this if you know what you're doing).

## Pull request guidelines

1. One logical change per PR.
2. All existing tests must pass (`make test`).
3. If you change the RAG pipeline, include a before/after example in the PR description.
4. Do not commit `.env`. Only commit an updated `chroma_db/` if your PR explicitly adds or removes indexed documents.
