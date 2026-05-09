.PHONY: dev test ingest

dev:
	uvicorn app.main:app --reload

test:
	pytest -v

ingest:
	python app/ingest.py
