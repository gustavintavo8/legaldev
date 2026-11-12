.PHONY: dev test ingest eval eval-sweep push-space todos mcp-dev mcp-stdio mcp-inspect validate-mapping eval-baselines

dev:
	uv run uvicorn app.main:app --reload

test:
	uv run pytest -v

ingest:
	uv run python -m app.ingest

eval:
	uv run python tools/eval_retrieval.py

eval-sweep:
	uv run python tools/eval_retrieval.py --sweep

# Trabajo pendiente del TFG. todos lista los marcadores de tools/list_todos.py; el resto de
# objetivos existen para fijar el nombre y avisan con error hasta que su paquete esté hecho.
todos:
	uv run python tools/list_todos.py

# API con /mcp en http://localhost:8000/mcp. Necesita MCP_API_KEYS o API_KEYS (en el entorno
# o en .env): sin claves /mcp no se monta y el registro lo avisa (RNF-15).
mcp-dev:
	MCP_ENABLED=true uv run uvicorn app.main:app --reload

# Servidor MCP local por stdio (docs/mcp/README.md, «Modo stdio»). Un cliente lo lanza con
# uv run --directory <ruta del repositorio> python -m app.mcp_stdio
mcp-stdio:
	uv run python -m app.mcp_stdio

# Comprobación de /mcp con el modo CLI de MCP Inspector (docs/mcp/README.md, «MCP Inspector»):
# tools/list (con --strict, portabilidad de los esquemas) y listar_normativas en las dos eras,
# y que sin clave y con una clave falsa el Inspector sale con 3 (auth_required). No llama a
# analizar_proyecto, así que no gasta cuota de Groq. Necesita LEGALDEV_API_KEY; LEGALDEV_URL
# es la base del servidor (por defecto, la API local de make mcp-dev).
INSPECTOR = npx -y @modelcontextprotocol/inspector@2.13.0 --cli
MCP_URL = $${LEGALDEV_URL:-http://localhost:8000}/mcp

mcp-inspect:
	@test -n "$$LEGALDEV_API_KEY" || { echo "Falta LEGALDEV_API_KEY (la clave de /mcp)" >&2; exit 1; }
	@set -e; for era in modern legacy; do \
		echo "-> $$era: tools/list --strict y listar_normativas"; \
		$(INSPECTOR) "$(MCP_URL)" --transport http --header "X-API-Key: $$LEGALDEV_API_KEY" \
			--protocol-era $$era --stored-auth-only --method tools/list --strict -q > /dev/null; \
		$(INSPECTOR) "$(MCP_URL)" --transport http --header "X-API-Key: $$LEGALDEV_API_KEY" \
			--protocol-era $$era --stored-auth-only --method tools/call \
			--tool-name listar_normativas -q > /dev/null; \
	done
	@echo "-> sin clave y con una clave falsa"
	@$(INSPECTOR) "$(MCP_URL)" --transport http --protocol-era modern --stored-auth-only \
		--method tools/list -q 2> /dev/null; test $$? -eq 3
	@$(INSPECTOR) "$(MCP_URL)" --transport http --header "X-API-Key: clave-falsa" \
		--protocol-era modern --stored-auth-only --method tools/list -q 2> /dev/null; test $$? -eq 3
	@echo "OK: las dos eras responden y /mcp rechaza sin clave y con una clave falsa"

validate-mapping:
	@echo "TODO(PT3/PP-09): validación de data/mapeo_controles.yaml contra data/catalogo_controles.yaml sin implementar (app/controls.py)" >&2; exit 1

eval-baselines:
	@echo "TODO(PT5/PI1): líneas base B1, B2 y B3 frente a S sin implementar (python -m eval.run)" >&2; exit 1

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
