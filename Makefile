.PHONY: dev test ingest eval

dev:
	uv run uvicorn app.main:app --reload

test:
	uv run pytest -v

ingest:
	uv run python app/ingest.py

eval:
	uv run python tools/eval_retrieval.py
