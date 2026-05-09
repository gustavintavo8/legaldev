# Contributing to LegalDev

Thank you for your interest in contributing. This project is open source under the MIT license.

## Getting started

```bash
git clone https://github.com/gustavintavo8/legaldev.git
cd legaldev
pip install -r requirements.txt
cp .env.example .env   # add your GROQ_API_KEY
python app/ingest.py   # build the vector store
uvicorn app.main:app --reload
```

## Running tests

```bash
pytest -v
```

Tests are fully mocked — no Groq API key or ChromaDB needed to run them.

## What to contribute

- **New legal documents**: add PDFs to `docs/`, update `DOC_TYPE_MAP` in `ingest.py`, re-run `python app/ingest.py`.
- **Retrieval improvements**: changes to chunking strategy, embedding model, or MMR parameters go in `ingest.py` and `app/config.py`.
- **Prompt improvements**: system prompt and user message construction are in `app/rag.py`.
- **Bug fixes**: open an issue first if the fix is non-trivial.

## Pull request guidelines

1. One logical change per PR.
2. All existing tests must pass (`pytest -v`).
3. If you change the RAG pipeline, include a before/after example in the PR description.
4. Do not commit `.env` or the `chroma_db/` directory.

## Disclaimer

LegalDev is informative tooling, not legal advice. Contributions must not remove or weaken the disclaimer shown to users.
