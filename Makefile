.PHONY: dev test ingest eval push-space

dev:
	uv run uvicorn app.main:app --reload

test:
	uv run pytest -v

ingest:
	uv run python app/ingest.py

eval:
	uv run python tools/eval_retrieval.py

# push-space: deploy HEAD snapshot of main to HF Space via orphan commit.
#
# Each deploy creates a new root commit (no git history) so pre-LFS binary
# blobs in older main commits are never transferred to HF Space.
#
# Uses --force-with-lease after 'git fetch space' so the push aborts if the
# Space has commits we haven't seen, instead of overwriting them silently.
# Only the 'space' remote is ever touched — GitHub origin is never modified.
#
# Requires: git remote add space https://huggingface.co/spaces/<user>/legaldev
push-space:
	@git diff --quiet && git diff --cached --quiet || \
		(echo "Error: uncommitted changes — commit or stash first."; exit 1)
	@CURRENT=$$(git rev-parse --abbrev-ref HEAD); \
	MAIN_SHORT=$$(git rev-parse --short main); \
	if [ "$$CURRENT" = "_hf-space-tmp" ]; then \
		echo "Warning: on leftover temp branch from a previous aborted run — returning to main."; \
		git checkout main; \
		CURRENT=main; \
	fi; \
	git branch -D _hf-space-tmp 2>/dev/null || true; \
	\
	echo "→ Checking all files in main for large blobs (must all be LFS pointers)..."; \
	BLOBS=$$(git ls-tree -r --long main | awk '$$4+0 > 1048576 {print "  " $$5 " (" $$4 " bytes)"}'); \
	if [ -n "$$BLOBS" ]; then \
		echo "ABORT: large blobs found in main — cannot deploy to HF Space without LFS tracking:"; \
		printf '%s\n' "$$BLOBS"; \
		echo "  Ensure each file is tracked via 'git lfs track' and re-committed as an LFS pointer."; \
		echo "  See: https://git-lfs.com/"; \
		exit 1; \
	fi; \
	echo "  Blob check passed."; \
	\
	echo "→ Fetching space remote (required for --force-with-lease)..."; \
	git fetch space; \
	\
	echo "→ Creating orphan snapshot from main@$$MAIN_SHORT..."; \
	git checkout --orphan _hf-space-tmp; \
	git rm -rf --cached . >/dev/null; \
	git checkout main -- .; \
	cp README_hf.md README.md; \
	git add README.md; \
	git commit -m "deploy: HF Space snapshot from main@$$MAIN_SHORT"; \
	\
	echo "→ Pushing to space:main (--force-with-lease, fetch already done)..."; \
	git push space HEAD:main --force-with-lease; \
	\
	git checkout "$$CURRENT"; \
	git branch -D _hf-space-tmp; \
	echo "✓ Deployed to HF Space (main@$$MAIN_SHORT)."
