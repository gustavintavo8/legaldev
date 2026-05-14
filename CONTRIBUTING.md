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
- **Retrieval improvements**: chunking strategy and embedding model live in `ingest.py`. Retrieval parameters (`OVERFETCH_K`, `MIN_RELEVANCE_SCORE`, `TOP_K_CHUNKS`, `RGPD_K`, `COOKIES_K`, `COLEGIADO_K`) are in `app/config.py`. Run `make eval` after any retrieval change to verify recall across the test cases in `tools/eval_cases.yaml`.
- **Prompt improvements**: system prompt and user message construction are in `app/rag.py` (`SYSTEM_PROMPT`, `_build_user_message`). The snapshot test in `tests/test_rag.py` pins the prompt hash — update it consciously if you change the prompt.
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

## Pull request guidelines

1. One logical change per PR.
2. All existing tests must pass (`make test`).
3. If you change the RAG pipeline, include a before/after example in the PR description.
4. Do not commit `.env`. Only commit an updated `chroma_db/` if your PR explicitly adds or removes indexed documents.
