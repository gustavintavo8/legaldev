.PHONY: dev test ingest eval push-space

dev:
	uv run uvicorn app.main:app --reload

test:
	uv run pytest -v

ingest:
	uv run python app/ingest.py

eval:
	uv run python tools/eval_retrieval.py

# Push to HF Space: builds a one-commit branch (hf-space) on top of main with
# README_hf.md swapped in as README.md, then pushes it to the space remote.
# Requires: git remote add space https://huggingface.co/spaces/<user>/legaldev
push-space:
	@git diff --quiet && git diff --cached --quiet || (echo "Uncommitted changes — commit first."; exit 1)
	$(eval CURRENT := $(shell git rev-parse --abbrev-ref HEAD))
	git checkout hf-space 2>/dev/null || git checkout -b hf-space
	git reset --hard main
	cp README_hf.md README.md
	git add README.md
	git commit -m "chore: HF Space README"
	git push space hf-space:main --force-with-lease
	git checkout $(CURRENT)
