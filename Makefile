.PHONY: dev test ingest eval

dev:
	uvicorn app.main:app --reload

test:
	pytest -v

ingest:
	python app/ingest.py

eval:
	python tools/eval_retrieval.py
