# Sprint 3 — Producción caída y calidad del RAG: plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restaurar la API en producción con un modelo LLM vigente y respaldo automático, y mejorar la calidad y la mantenibilidad del pipeline RAG (retrieval unificado, mejor uso del contexto, verificación de citas, reranker precargado, ingesta trazable, evaluador fiel) sin regresión en el eval de retrieval.

**Architecture:** Dos PRs. PR-A (hotfix) migra el modelo de Groq a `openai/gpt-oss-120b`, añade cliente de respaldo, comprobación del modelo al arrancar y expone el modelo usado. PR-B (sprint) unifica el retrieval en una única función sync ejecutada en hilo con timeout global, aplica exclusiones antes del reranker y un tope de chunks por fuente, añade `app/citations.py` (verificación determinista de citas), precarga el reranker, endurece `/v1/feedback`, hace la ingesta atómica y trazable (`.index_meta.json`, filtro de chunks, encabezado de artículo), corrige el evaluador y limpia dependencias.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, LangChain (core/chroma/groq/huggingface/text-splitters), ChromaDB 1.5, sentence-transformers 5.4 (`BAAI/bge-reranker-base`), Groq API, pytest, ruff, uv.

**Spec:** `docs/superpowers/specs/2026-09-11-sprint3-rag-quality-design.md` (el plan argumenta desde ese documento; léelo primero: contiene las mediciones que justifican cada tarea).

## Global Constraints

- Python `>=3.11`; ruff con reglas `E`, `F`, `I` (E501 ignorada); `uv run ruff check app/ tests/ tools/` y `uv run ruff format --check app/ tests/ tools/` deben pasar antes de cada commit.
- `uv run pytest -m "not slow" --cov=app --cov-fail-under=80` verde en cada commit; ningún test hace red ni carga modelos reales (fixtures mockeadas en `tests/conftest.py`).
- `SYSTEM_PROMPT` **no cambia** en este sprint (su hash está fijado en `tests/test_rag.py::test_system_prompt_snapshot`).
- La versión sigue en `0.4.0`; los cambios van a `CHANGELOG.md` bajo `## [Unreleased]` (el bump lo hace el mantenedor en su PR de release).
- Compatibilidad hacia atrás del contrato HTTP: solo se **añaden** campos a `RAGResponse` (`llm_model`, `citas`) con defaults; los códigos de error no cambian.
- Commits con Conventional Commits (`fix:`, `feat:`, `refactor:`, `test:`, `docs:`, `chore:`) y trailers:
  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01LF8ANP6X2F1VBFwK4eSb4W
  ```
- Trabajo en el worktree `.worktrees/sprint-3` (ya creado, `uv sync --frozen --extra dev` hecho, 186 tests verdes). Todos los comandos se ejecutan desde ahí. `GROQ_API_KEY=test-key-not-real` en el entorno para los tests.
- Ramas: PR-A `fix/groq-model-decommissioned` (Tareas 1–3); PR-B `sprint/3-rag-quality` creada desde la punta de PR-A (Tareas 4–14).
- El `chroma_db/` real está disponible en el worktree (LFS) y los modelos en la caché local de HF: `make eval` funciona sin red con `HF_HUB_OFFLINE=1`. No hay PDFs: **no se reindexa** en este sprint.

**Baseline medido (2026-09-11, antes de tocar código):** 186 tests; eval 13/13, 0 FP, ~95 s; chunks por caso: 14, 13, 18, 19, 15, 16, 16, 19, 16, 9, 5, 16, 14 (orden del YAML).

---

## Estructura de archivos

**Crear**
- `app/citations.py` — extracción y verificación de citas (funciones puras).
- `tests/test_llm_fallback.py` — factoría de cliente Groq, comprobación de modelo, respaldo.
- `tests/test_citations.py` — módulo de citas e integración en `run_pipeline`.
- `tests/test_retrieval_selection.py` — exclusiones pre-reranker y tope por fuente.
- `tests/test_ingest_build.py` — carga con pypdf, filtro de chunks, metadatos, swap atómico.
- `tests/test_lifespan_guard.py` — guardia de arranque índice/modelo.

**Modificar**
- `app/config.py` — settings nuevos (modelo, respaldo, reasoning, timeout global, tope por fuente).
- `app/main.py` — factoría de clientes, comprobación del modelo, warmup del reranker, guardia del índice, `/health/deep`, rate limit en feedback.
- `app/rag.py` — `_invoke_llm`, `_content_to_text`, `RetrievalResult`, `_retrieve`, `_select_diverse`, integración de citas, artículo en `_build_user_message`.
- `app/models.py` — `RAGResponse.llm_model`, `CitationStats`, `RAGResponse.citas`, límites en `FeedbackInput`.
- `app/metrics.py` — `llm_fallback_total`, `citations_verified_ratio`, `citations_unverified_total`.
- `app/reranker.py` — `warmup()`.
- `app/legal_splitter.py` — metadato `article` y prefijo `(cont.)` en sub-chunks.
- `app/ingest.py` — `_load_pages` (pypdf), `MIN_CHUNK_CHARS`, `.index_meta.json`, construcción en `.building` + swap.
- `app/store.py` — `read_index_meta`.
- `app/corpus.py` — `EMBEDDING_MODEL`.
- `tools/eval_retrieval.py` — `--chroma-path`, comprobación de modelo del índice, columna Fuentes; `tools/diagnose_ranking.py` — modelo correcto.
- `tests/conftest.py`, `tests/test_rag.py`, `tests/test_api.py`, `tests/test_config.py`, `tests/test_e2e.py`, `tests/test_concurrency.py`, `tests/test_models.py`, `tests/test_legal_splitter.py`, `tests/test_reranker.py`, `tests/test_store.py`, `tests/test_eval_model_flag.py`.
- `README.md`, `README_hf.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `.env.example`, `Makefile`, `pyproject.toml`, `uv.lock`, `tools/eval_results.md`.

---

## PR-A · Hotfix de producción

### Task 1: Settings del LLM, factoría de cliente, comprobación del modelo y `/health/deep`

**Files:**
- Modify: `app/config.py`
- Modify: `app/main.py`
- Modify: `tests/conftest.py` (fixture `client`), `tests/test_concurrency.py`
- Modify: `tests/test_config.py`, `tests/test_rag.py:31-32`, `tests/test_api.py`
- Create: `tests/test_llm_fallback.py`

**Interfaces:**
- Produces: `app.main._make_groq_client(model: str) -> ChatGroq`; `app.main._check_groq_model(api_key: str, model: str, timeout: float = 5.0) -> bool | None`; `app.state.groq_fallback_client: ChatGroq | None`; `app.state.groq_model_available: bool | None`; settings `groq_fallback_model`, `groq_reasoning_effort`, `groq_verify_model_on_startup`.

- [ ] **Step 1: Tests de settings (fallan porque los defaults son los antiguos)**

En `tests/test_config.py` añade:

```python
def test_groq_model_default_is_a_live_groq_model():
    s = Settings(groq_api_key="x")
    assert s.groq_model == "openai/gpt-oss-120b"


def test_groq_fallback_and_reasoning_defaults():
    s = Settings(groq_api_key="x")
    assert s.groq_fallback_model == "openai/gpt-oss-20b"
    assert s.groq_reasoning_effort == "low"
    assert s.groq_verify_model_on_startup is True
    assert s.groq_max_tokens == 8000


def test_groq_fallback_can_be_disabled_with_empty_string():
    s = Settings(groq_api_key="x", groq_fallback_model="")
    assert s.groq_fallback_model == ""
```

En `tests/test_rag.py` cambia `test_settings_groq_max_tokens_default` para que espere `8000`.

- [ ] **Step 2: Ejecutar y ver fallar**

Run: `uv run pytest tests/test_config.py tests/test_rag.py::test_settings_groq_max_tokens_default -q`
Expected: 4 FAIL (`openai/gpt-oss-120b != meta-llama/...`, atributos inexistentes, 4000 != 8000).

- [ ] **Step 3: Settings**

En `app/config.py` sustituye las líneas de `groq_model` y `groq_max_tokens` y añade los nuevos:

```python
    groq_model: str = "openai/gpt-oss-120b"
    # Segundo modelo si el principal falla (retirado, 429, 5xx). "" lo desactiva.
    groq_fallback_model: str = "openai/gpt-oss-20b"
    # Solo se envía a modelos openai/gpt-oss*. "" no envía el parámetro.
    groq_reasoning_effort: str = "low"
    groq_verify_model_on_startup: bool = True
    ...
    groq_max_tokens: int = 8000
```

- [ ] **Step 4: Tests de la factoría y de la comprobación del modelo**

Crea `tests/test_llm_fallback.py`:

```python
from unittest.mock import MagicMock, patch

import httpx

from app.main import _check_groq_model, _make_groq_client


def _settings(**overrides):
    s = MagicMock()
    s.groq_api_key = "k"
    s.groq_timeout = 30
    s.groq_temperature = 0.0
    s.groq_max_tokens = 8000
    s.groq_reasoning_effort = "low"
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def test_make_groq_client_sends_reasoning_effort_for_gpt_oss():
    with patch("app.main.ChatGroq") as cls, patch("app.main.settings", _settings()):
        _make_groq_client("openai/gpt-oss-120b")
    kwargs = cls.call_args.kwargs
    assert kwargs["model_name"] == "openai/gpt-oss-120b"
    assert kwargs["reasoning_effort"] == "low"
    assert kwargs["max_tokens"] == 8000
    assert kwargs["temperature"] == 0.0


def test_make_groq_client_omits_reasoning_effort_for_other_models():
    with patch("app.main.ChatGroq") as cls, patch("app.main.settings", _settings()):
        _make_groq_client("qwen/qwen3.6-27b")
    assert "reasoning_effort" not in cls.call_args.kwargs


def test_make_groq_client_omits_reasoning_effort_when_empty():
    with (
        patch("app.main.ChatGroq") as cls,
        patch("app.main.settings", _settings(groq_reasoning_effort="")),
    ):
        _make_groq_client("openai/gpt-oss-120b")
    assert "reasoning_effort" not in cls.call_args.kwargs


def test_check_groq_model_200_is_available():
    with patch("app.main.httpx.get", return_value=MagicMock(status_code=200)):
        assert _check_groq_model("k", "openai/gpt-oss-120b") is True


def test_check_groq_model_404_is_not_available(caplog):
    with patch("app.main.httpx.get", return_value=MagicMock(status_code=404)):
        assert _check_groq_model("k", "meta-llama/llama-4-scout-17b-16e-instruct") is False
    assert "NOT available" in caplog.text
    assert "deprecations" in caplog.text


def test_check_groq_model_network_error_is_inconclusive():
    with patch("app.main.httpx.get", side_effect=httpx.ConnectError("boom")):
        assert _check_groq_model("k", "openai/gpt-oss-120b") is None


def test_check_groq_model_other_status_is_inconclusive():
    with patch("app.main.httpx.get", return_value=MagicMock(status_code=401)):
        assert _check_groq_model("bad-key", "openai/gpt-oss-120b") is None
```

Y en `tests/test_api.py` añade:

```python
def test_deep_health_reports_model_names_and_startup_check(client):
    import app.main as main_module

    main_module._deep_health_cache.clear()
    data = client.get("/health/deep").json()
    assert data["groq_model"] == main_module.settings.groq_model
    assert data["groq_fallback_model"] == main_module.settings.groq_fallback_model
    assert data["groq_model_available_at_startup"] is True
    main_module._deep_health_cache.clear()
```

- [ ] **Step 5: Ejecutar y ver fallar**

Run: `uv run pytest tests/test_llm_fallback.py tests/test_api.py::test_deep_health_reports_model_names_and_startup_check -q`
Expected: FAIL con `ImportError: cannot import name '_check_groq_model'`.

- [ ] **Step 6: Implementación en `app/main.py`**

Añade `import httpx` a los imports y, tras `limiter = Limiter(...)`:

```python
GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"
GROQ_DEPRECATIONS_URL = "https://console.groq.com/docs/deprecations"


def _make_groq_client(model: str) -> ChatGroq:
    kwargs: dict = {
        "api_key": settings.groq_api_key,
        "model_name": model,
        "timeout": settings.groq_timeout,
        "temperature": settings.groq_temperature,
        "max_tokens": settings.groq_max_tokens,
    }
    # reasoning_effort solo existe en la familia gpt-oss; Groq rechaza el parámetro en otros modelos.
    if settings.groq_reasoning_effort and model.startswith("openai/gpt-oss"):
        kwargs["reasoning_effort"] = settings.groq_reasoning_effort
    return ChatGroq(**kwargs)


def _check_groq_model(api_key: str, model: str, timeout: float = 5.0) -> bool | None:
    """True si Groq sirve *model*, False si no existe (retirado/desconocido), None si no se pudo comprobar.

    Nunca aborta el arranque: un fallo de red en el boot no debe tumbar el servicio.
    """
    try:
        resp = httpx.get(
            f"{GROQ_MODELS_URL}/{model}",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
    except Exception as e:
        logger.warning("Groq model check skipped for %s: %s", model, type(e).__name__)
        return None
    if resp.status_code == 200:
        logger.info("Groq model available: %s", model)
        return True
    if resp.status_code == 404:
        logger.error(
            "Groq model NOT available: %s (HTTP 404). It may have been decommissioned — "
            "see %s and set GROQ_MODEL to a live model.",
            model,
            GROQ_DEPRECATIONS_URL,
        )
        return False
    logger.warning("Groq model check inconclusive for %s: HTTP %d", model, resp.status_code)
    return None
```

En `lifespan`, sustituye el bloque `app.state.groq_client = ChatGroq(...)` por:

```python
    logger.info("Initializing Groq client with model %s", settings.groq_model)
    app.state.groq_client = _make_groq_client(settings.groq_model)
    app.state.groq_fallback_client = (
        _make_groq_client(settings.groq_fallback_model)
        if settings.groq_fallback_model
        else None
    )
    if app.state.groq_fallback_client is not None:
        logger.info("Groq fallback model: %s", settings.groq_fallback_model)
    app.state.groq_model_available = (
        _check_groq_model(settings.groq_api_key, settings.groq_model)
        if settings.groq_verify_model_on_startup
        else None
    )
```

En `health_deep`, el diccionario `result` pasa a ser:

```python
    result: dict = {
        "chroma": "ok",
        "groq": "ok",
        "groq_model": settings.groq_model,
        "groq_fallback_model": settings.groq_fallback_model or None,
        "groq_model_available_at_startup": request.app.state.groq_model_available,
        "corpus_version": request.app.state.corpus_version,
    }
```

- [ ] **Step 7: Aislar la red en los fixtures**

En `tests/conftest.py`, dentro del `with (...)` de la fixture `client`, añade `patch("app.main._check_groq_model", return_value=True),`. En `tests/test_concurrency.py`, en el `with (...)` de `_probe_health_during_analyze`, añade la misma línea.

- [ ] **Step 8: Ejecutar toda la suite**

Run: `uv run pytest -q -m "not slow"`
Expected: todo verde (186 + 11 nuevos).

- [ ] **Step 9: Commit**

```bash
git add app/config.py app/main.py tests/conftest.py tests/test_concurrency.py tests/test_config.py tests/test_rag.py tests/test_api.py tests/test_llm_fallback.py
git commit -m "fix(llm): migrate to openai/gpt-oss-120b (llama-4-scout decommissioned) and verify model at startup"
```

---

### Task 2: Respaldo automático en `run_pipeline`, `llm_model` en la respuesta, métrica

**Files:**
- Modify: `app/rag.py` (bloque `try: response = await asyncio.to_thread(state.groq_client.invoke, ...)`)
- Modify: `app/models.py` (`RAGResponse`), `app/metrics.py`
- Modify: `tests/test_rag.py` (`_make_state`, `test_run_pipeline_groq_error_raises_503`), `tests/test_e2e.py`, `tests/test_api.py`
- Modify: `tests/test_llm_fallback.py`

**Interfaces:**
- Consumes: `state.groq_fallback_client` (Task 1).
- Produces: `app.rag._invoke_llm(state, messages: list) -> tuple[str, str]` (texto, modelo usado); `app.rag._content_to_text(content) -> str`; `RAGResponse.llm_model: str`; `app.metrics.llm_fallback_total` (Counter, label `reason`).

- [ ] **Step 1: Tests**

Añade a `tests/test_llm_fallback.py`:

```python
import asyncio

import pytest
from prometheus_client import REGISTRY

from app.config import settings
from app.models import QuestionnaireInput
from app.rag import _content_to_text, run_pipeline


def _input():
    return QuestionnaireInput(
        tipo_proyecto="app_web",
        descripcion_breve="App de gestión",
        tiene_usuarios_registrados=True,
        acceso_publico=False,
        tipos_datos_personales=["email"],
        usuarios_menores=False,
        usuarios_ue=True,
        transferencia_datos_terceros=False,
        usa_ia=False,
        tipo_ia=None,
        usa_cookies=False,
        monetizacion=None,
        contenido_digital=False,
        ccaa="Madrid",
        es_empresa=False,
        colegiado=None,
    )


def _doc(source="RGPD.pdf"):
    d = MagicMock()
    d.page_content = f"Contenido de {source}"
    d.metadata = {"source": source}
    return d


def _state(primary_content="Respuesta principal"):
    state = MagicMock()
    state.vectorstore.similarity_search_with_relevance_scores.return_value = [
        (_doc(), 0.85),
        (_doc(), 0.80),
    ]
    state.groq_client.invoke.return_value = MagicMock(content=primary_content)
    state.groq_fallback_client = MagicMock()
    state.groq_fallback_client.invoke.return_value = MagicMock(
        content="Respuesta del respaldo"
    )
    state.indexed_normativas = frozenset({"RGPD"})
    state.corpus_version = "v1"
    return state


def _metric(name, **labels):
    for metric in REGISTRY.collect():
        for sample in metric.samples:
            if sample.name == name and all(
                sample.labels.get(k) == v for k, v in labels.items()
            ):
                return sample.value
    return 0.0


def test_primary_success_reports_primary_model(mock_reranker):
    result = asyncio.run(run_pipeline(_input(), _state()))
    assert result.respuesta_completa.startswith("Respuesta principal")
    assert result.llm_model == settings.groq_model


def test_fallback_used_when_primary_fails(mock_reranker, caplog):
    state = _state()
    state.groq_client.invoke.side_effect = Exception("model_decommissioned")
    before = _metric("legaldev_llm_fallback_total", reason="Exception")
    result = asyncio.run(run_pipeline(_input(), state))
    assert result.respuesta_completa.startswith("Respuesta del respaldo")
    assert result.llm_model == settings.groq_fallback_model
    assert _metric("legaldev_llm_fallback_total", reason="Exception") == before + 1
    assert '"event": "llm_fallback"' in caplog.text


def test_503_when_both_models_fail(mock_reranker):
    state = _state()
    state.groq_client.invoke.side_effect = Exception("down")
    state.groq_fallback_client.invoke.side_effect = Exception("also down")
    with pytest.raises(Exception) as exc_info:
        asyncio.run(run_pipeline(_input(), state))
    assert exc_info.value.status_code == 503


def test_503_when_no_fallback_configured(mock_reranker):
    state = _state()
    state.groq_client.invoke.side_effect = Exception("down")
    state.groq_fallback_client = None
    with pytest.raises(Exception) as exc_info:
        asyncio.run(run_pipeline(_input(), state))
    assert exc_info.value.status_code == 503


def test_content_to_text_accepts_str_and_blocks():
    assert _content_to_text("hola") == "hola"
    blocks = [
        {"type": "reasoning", "reasoning": "pensando"},
        {"type": "text", "text": "hola "},
        "mundo",
    ]
    assert _content_to_text(blocks) == "hola mundo"
```

En `tests/test_api.py`:

```python
def test_analyze_includes_llm_model(client, sample_input_dict):
    from app.config import settings

    response = client.post("/v1/analyze", json=sample_input_dict)
    assert response.json()["llm_model"] == settings.groq_model
```

Actualiza fixtures existentes que construyen `state = MagicMock()`: en `tests/test_rag.py` añade `state.groq_fallback_client = None` dentro de `_make_state` y en `test_run_pipeline_groq_error_raises_503` (si no, el MagicMock auto-creado haría de respaldo y el 503 no llegaría). En `tests/test_e2e.py` añade `state.groq_fallback_client = None` tras `state.groq_client.invoke.return_value = ...`.

- [ ] **Step 2: Ejecutar y ver fallar**

Run: `uv run pytest tests/test_llm_fallback.py tests/test_api.py::test_analyze_includes_llm_model -q`
Expected: FAIL (`_content_to_text` no existe; `llm_model` no existe).

- [ ] **Step 3: Implementación**

`app/metrics.py`:

```python
llm_fallback_total = Counter(
    "legaldev_llm_fallback_total",
    "LLM calls served by the fallback model after the primary model failed",
    ["reason"],
)
```

`app/models.py`, en `RAGResponse` tras `corpus_version`:

```python
    llm_model: str = "unknown"
```

`app/rag.py`, antes de `run_pipeline`:

```python
def _content_to_text(content) -> str:
    """LangChain puede devolver content como str o como lista de bloques (modelos con razonamiento)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content)


async def _invoke_llm(state, messages: list) -> tuple[str, str]:
    """Invoca el modelo principal; si falla por cualquier motivo, reintenta una vez con el respaldo.

    Devuelve (texto, modelo_usado). Lanza HTTPException(503) si ningún modelo responde.
    Se hace fallback ante cualquier excepción: Groq devuelve 400 model_decommissioned para
    modelos retirados, 404 para desconocidos, 429 por cuota y 5xx en incidentes — en todos
    los casos el segundo modelo (cuota independiente) puede responder.
    """
    try:
        response = await asyncio.to_thread(state.groq_client.invoke, messages)
        return _content_to_text(response.content), settings.groq_model
    except Exception as e:
        fallback = getattr(state, "groq_fallback_client", None)
        if fallback is None:
            logger.error("Groq API error: %s", e)
            raise HTTPException(
                status_code=503,
                detail="LLM service unavailable. Please try again later.",
            )
        logger.warning(
            json.dumps(
                {
                    "event": "llm_fallback",
                    "request_id": request_id_var.get(),
                    "primary_model": settings.groq_model,
                    "primary_error": type(e).__name__,
                    "fallback_model": settings.groq_fallback_model,
                }
            )
        )
        _metrics.llm_fallback_total.labels(reason=type(e).__name__).inc()
    try:
        response = await asyncio.to_thread(fallback.invoke, messages)
        return _content_to_text(response.content), settings.groq_fallback_model
    except Exception as e:
        logger.error("Groq fallback API error: %s", e)
        raise HTTPException(
            status_code=503,
            detail="LLM service unavailable. Please try again later.",
        )
```

En `run_pipeline`, sustituye el bloque `try: response = await asyncio.to_thread(state.groq_client.invoke, messages) ... raise HTTPException(503)` por:

```python
    answer, llm_model = await _invoke_llm(state, messages)
```

Usa `answer` donde antes se usaba `response.content`, añade `"llm_model": llm_model,` al `json.dumps` del evento `rag_pipeline` y `llm_model=llm_model,` al constructor de `RAGResponse`.

- [ ] **Step 4: Ejecutar toda la suite**

Run: `uv run pytest -q -m "not slow"`
Expected: verde.

- [ ] **Step 5: Commit**

```bash
git add app/rag.py app/models.py app/metrics.py tests/
git commit -m "feat(llm): fall back to a second Groq model when the primary fails; expose llm_model"
```

---

### Task 3: Docs del hotfix, push y PR-A

**Files:**
- Modify: `README.md` (badge Groq, "Cómo funciona" paso 3, "Groq en vez de OpenAI", tabla de variables, limitaciones), `.env.example`, `CHANGELOG.md`

- [ ] **Step 1: README**

  - Badge: `[![Groq](https://img.shields.io/badge/Groq-gpt--oss--120b-f55036?logo=groq)](https://groq.com/)`.
  - Paso 3 del diagrama "Cómo funciona": `LLM call (Groq · openai/gpt-oss-120b · temperature=0 · reasoning_effort=low)` y una línea `→ fallback: openai/gpt-oss-20b si el principal falla (modelo retirado, 429, 5xx)`.
  - Sección "Groq en vez de OpenAI": sustituir el párrafo del modelo por:

    > El modelo por defecto es `openai/gpt-oss-120b` (131k de contexto, 65k de salida). Groq retira modelos con pocos meses de aviso —`llama-4-scout`, el modelo original de LegalDev, dejó de existir el 17/07/2026 y la API estuvo devolviendo 503 hasta detectarlo—, así que el sistema (1) comprueba al arrancar que `GROQ_MODEL` existe (`GET /openai/v1/models/{model}`) y lo registra en `/health/deep`, (2) mantiene un segundo modelo (`GROQ_FALLBACK_MODEL`, por defecto `openai/gpt-oss-20b`) al que recurre si el principal falla por cualquier causa, y (3) informa en cada respuesta qué modelo la generó (`llm_model`). En gpt-oss los tokens de razonamiento cuentan como salida: `GROQ_REASONING_EFFORT=low` y `GROQ_MAX_TOKENS=8000`.
  - Tabla de variables: `GROQ_MODEL` default `openai/gpt-oss-120b`; nuevas filas `GROQ_FALLBACK_MODEL` (`openai/gpt-oss-20b`, vacío desactiva), `GROQ_REASONING_EFFORT` (`low`; solo gpt-oss), `GROQ_VERIFY_MODEL_ON_STARTUP` (`true`); `GROQ_MAX_TOKENS` default `8000`.
  - Bloque `.env` de ejemplo del README: mismos valores.
  - Ejemplo JSON de respuesta: añadir `"llm_model": "openai/gpt-oss-120b"` y `"corpus_version": "858b81eb27fe"`.
  - `/health/deep`: documentar los campos nuevos en la sección API (añadir subsección `GET /health/deep`).
  - Limitaciones: nueva viñeta **"Los modelos de Groq se retiran."** con el resumen anterior.

- [ ] **Step 2: `.env.example`**

Sustituye el contenido completo por:

```env
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=openai/gpt-oss-120b
GROQ_FALLBACK_MODEL=openai/gpt-oss-20b
GROQ_REASONING_EFFORT=low
GROQ_VERIFY_MODEL_ON_STARTUP=true
GROQ_TIMEOUT=30
GROQ_TEMPERATURE=0.0
GROQ_MAX_TOKENS=8000
CHROMA_DB_PATH=./chroma_db
DOCS_PATH=./docs
TOP_K_CHUNKS=12
COOKIES_K=6
RGPD_K=6
COLEGIADO_K=6
OVERFETCH_K=100
RERANKER_TOP_K=25
MIN_RELEVANCE_SCORE=0.40
CHROMA_TIMEOUT=10
RATE_LIMIT=10/minute
# Para producción, reemplaza * con tus dominios separados por comas:
# ALLOWED_ORIGINS=https://tuapp.com,https://www.tuapp.com
ALLOWED_ORIGINS=*
TRUST_PROXY_HEADERS=false
LOG_LEVEL=INFO
# API_KEYS=key1,key2  (vacío = endpoint abierto)
```

- [ ] **Step 3: CHANGELOG**

Bajo `## [Unreleased]` (crear la sección encima de `## [0.4.0]`):

```markdown
## [Unreleased]

### Fixed
- Producción devolvía 503 en todos los análisis desde el 17/07/2026: Groq retiró `meta-llama/llama-4-scout-17b-16e-instruct`. El modelo por defecto pasa a `openai/gpt-oss-120b` (sustituto recomendado por Groq).

### Added
- Modelo de respaldo (`GROQ_FALLBACK_MODEL`, por defecto `openai/gpt-oss-20b`): si el principal falla por cualquier causa se reintenta con él; evento `llm_fallback` en logs y métrica `legaldev_llm_fallback_total{reason}`.
- Comprobación del modelo al arrancar (`GROQ_VERIFY_MODEL_ON_STARTUP`): log ERROR si Groq responde 404; resultado en `/health/deep` junto a `groq_model` y `groq_fallback_model`.
- `RAGResponse.llm_model`: modelo que generó cada informe.
- `GROQ_REASONING_EFFORT` (default `low`), enviado solo a modelos `openai/gpt-oss*`.

### Changed
- `GROQ_MAX_TOKENS` por defecto 4000 → 8000 (en gpt-oss los tokens de razonamiento cuentan como salida).
```

- [ ] **Step 4: Lint, tests, commit, push, PR**

```bash
uv run ruff check app/ tests/ && uv run ruff format --check app/ tests/
uv run pytest -q -m "not slow" --cov=app --cov-fail-under=80
git add README.md .env.example CHANGELOG.md
git commit -m "docs: document Groq model migration, fallback model and startup check"
git push -u origin fix/groq-model-decommissioned
gh pr create --base main --title "fix(llm): restore production — llama-4-scout was decommissioned by Groq" --body-file <descripción>
```

La descripción del PR incluye: síntoma (`/health/deep` real), causa (deprecations), cambio, cómo verificar tras desplegar (`/health/deep` → `groq: ok`, `groq_model_available_at_startup: true`), y el paso manual `make push-space`.

- [ ] **Step 5: Crear la rama del sprint**

```bash
git checkout -b sprint/3-rag-quality
```

---

## PR-B · Sprint de calidad

### Task 4: Commit de los documentos de diseño y plan

**Files:**
- Create: `docs/superpowers/specs/2026-09-11-sprint3-rag-quality-design.md`, `docs/superpowers/plans/2026-09-11-sprint3-rag-quality.md` (ya escritos en el worktree; `docs/superpowers/` está en `.gitignore` aunque sus archivos están trackeados → `git add -f`).

- [ ] **Step 1: Commit**

```bash
git add -f docs/superpowers/specs/2026-09-11-sprint3-rag-quality-design.md docs/superpowers/plans/2026-09-11-sprint3-rag-quality.md
git commit -m "docs(sprint3): design spec and implementation plan"
```

---

### Task 5: Retrieval unificado con timeout global (refactor sin cambio de comportamiento)

**Files:**
- Modify: `app/rag.py` (elimina `_search_with_timeout` y el retrieval duplicado de `run_pipeline`; `retrieve_docs_sync` pasa a envolver `_retrieve`)
- Modify: `app/config.py` (`chroma_timeout` → `retrieval_timeout`)
- Modify: `tests/test_rag.py` (`test_search_with_timeout_raises_503_on_slow_chroma` → `test_run_pipeline_retrieval_timeout_raises_503`), `tests/test_e2e.py` (`mock_settings.retrieval_timeout`)
- Modify: `tools/eval_retrieval.py` (columna **Fuentes**)

**Interfaces:**
- Produces: `app.rag.RetrievalResult` (dataclass: `docs: list`, `candidates: int`, `top_score: float | None`, `pre_rerank: int`, `injected_stems: list[str]`); `app.rag._retrieve(inp, vs, threshold) -> RetrievalResult`; `app.rag.retrieve_docs_sync(inp, vs, threshold) -> list` (sin cambios de firma); setting `retrieval_timeout: float = 60.0`.

- [ ] **Step 1: Test del timeout global (falla porque el setting no existe)**

Sustituye `test_search_with_timeout_raises_503_on_slow_chroma` en `tests/test_rag.py` por:

```python
def test_run_pipeline_retrieval_timeout_raises_503(sample_input, mock_reranker, monkeypatch):
    """El retrieval completo (Chroma + reranker) corre en un hilo bajo un único timeout."""
    monkeypatch.setattr(settings, "retrieval_timeout", 0.05)
    state = _make_state([_make_mock_doc()])

    def _slow(*args, **kwargs):
        time.sleep(0.3)
        return [(_make_mock_doc(), 0.85)]

    state.vectorstore.similarity_search_with_relevance_scores.side_effect = _slow

    with pytest.raises(Exception) as exc_info:
        asyncio.run(run_pipeline(sample_input, state))

    assert exc_info.value.status_code == 503
    assert "timed out" in exc_info.value.detail


def test_retrieve_returns_stats():
    from app.rag import _retrieve

    vs = MagicMock()
    vs.similarity_search_with_relevance_scores.return_value = [
        (_make_mock_doc("RGPD.pdf"), 0.9),
        (_make_mock_doc("LOPDGDD.pdf"), 0.7),
    ]
    with patch("app.reranker.rerank", side_effect=lambda q, docs, top_k: docs[:top_k]):
        result = _retrieve(
            _make_input(tipos_datos_personales=["ninguno"], usa_cookies=False),
            vs,
            settings.min_relevance_score,
        )
    assert result.candidates == 2
    assert result.top_score == 0.9
    assert result.pre_rerank == 2
    assert result.injected_stems == []
    assert [d.metadata["source"] for d in result.docs] == ["RGPD.pdf", "LOPDGDD.pdf"]
```

(añade `from unittest.mock import MagicMock, patch` al import de test_rag.)

- [ ] **Step 2: Ejecutar y ver fallar**

Run: `uv run pytest tests/test_rag.py -q -k "timeout or returns_stats"`
Expected: FAIL (`retrieval_timeout` no existe; `_retrieve` no existe).

- [ ] **Step 3: Config**

En `app/config.py` sustituye `chroma_timeout: float = 10.0` por:

```python
    # Timeout global de la fase de retrieval (búsquedas Chroma + reranker CPU), en segundos.
    retrieval_timeout: float = 60.0
```

- [ ] **Step 4: `_retrieve` en `app/rag.py`**

Elimina `_search_with_timeout`. Sustituye `retrieve_docs_sync` completa por:

```python
@dataclass
class RetrievalResult:
    docs: list
    candidates: int
    top_score: float | None
    pre_rerank: int
    injected_stems: list[str]


def _stem(doc) -> str:
    return Path(doc.metadata.get("source", "")).stem


def _content_hash(doc) -> str:
    return hashlib.md5(doc.page_content.encode()).hexdigest()


def _retrieve(inp: QuestionnaireInput, vs, threshold: float) -> RetrievalResult:
    """Fase de retrieval completa: principal → auxiliares → rerank → exclusiones → inyecciones.

    Es la ÚNICA implementación. Es síncrona y bloqueante (Chroma + CrossEncoder en CPU):
    run_pipeline la ejecuta en un hilo bajo settings.retrieval_timeout; las herramientas de
    eval/diagnóstico la llaman directamente vía retrieve_docs_sync.
    """
    query = _build_query(inp)

    # 1. Candidatos principales
    candidates = vs.similarity_search_with_relevance_scores(
        query, k=settings.overfetch_k
    )
    docs = [doc for doc, score in candidates if score >= threshold]
    seen = {_content_hash(d) for d in docs}
    main_n = len(docs)

    # 2. Búsqueda auxiliar — ver README "Query descriptiva + búsqueda auxiliar por dominio"
    for aux in AUXILIARY_SEARCHES:
        if not aux.condition(inp):
            continue
        _metrics.aux_search_triggered.labels(type=aux.name).inc()
        for doc, score in vs.similarity_search_with_relevance_scores(aux.query, k=aux.k):
            if score < threshold:
                continue
            h = _content_hash(doc)
            if h not in seen:
                seen.add(h)
                docs.append(doc)

    # 3. Recorte de la lista principal + CrossEncoder
    pre_rerank = docs[: min(settings.reranker_top_k, main_n)] + docs[main_n:]
    docs = _reranker.rerank(query, pre_rerank, top_k=settings.top_k_chunks)

    # 4. Exclusiones
    excluded_stems = {exc.stem for exc in EXCLUSIONS if exc.condition(inp)}
    if excluded_stems:
        docs = [doc for doc in docs if _stem(doc) not in excluded_stems]

    # 5. Inyecciones — búsqueda filtrada por fuente, SIN umbral: una INJECTION es una garantía.
    #    filter= es la API de langchain_chroma (where= es la interna de Chroma y falla vía **kwargs).
    seen_injected = {_content_hash(d) for d in docs}
    injected_stems: list[str] = []
    for inj in INJECTIONS:
        if not inj.condition(inp) or inj.stem in excluded_stems:
            continue
        inj_candidates = vs.similarity_search_with_relevance_scores(
            query, k=inj.k, filter={"source": f"{inj.stem}.pdf"}
        )
        added = 0
        for doc, _score in inj_candidates:
            h = _content_hash(doc)
            if h not in seen_injected:
                seen_injected.add(h)
                docs.append(doc)
                added += 1
        if added:
            injected_stems.append(inj.stem)

    return RetrievalResult(
        docs=docs,
        candidates=len(candidates),
        top_score=round(candidates[0][1], 3) if candidates else None,
        pre_rerank=len(pre_rerank),
        injected_stems=injected_stems,
    )


def retrieve_docs_sync(inp: QuestionnaireInput, vs, threshold: float) -> list:
    """Documentos del retrieval como lista plana (herramientas de eval y diagnóstico)."""
    return _retrieve(inp, vs, threshold).docs
```

- [ ] **Step 5: `run_pipeline` usa `_retrieve`**

Sustituye desde `t0 = time.perf_counter()` hasta el final del bucle de inyecciones (inclusive `injected_stems`) por:

```python
    t0 = time.perf_counter()
    try:
        retrieval = await asyncio.wait_for(
            asyncio.to_thread(
                _retrieve, input, state.vectorstore, settings.min_relevance_score
            ),
            timeout=settings.retrieval_timeout,
        )
    except asyncio.TimeoutError:
        # Limitación conocida: cancelar to_thread no interrumpe el hilo; el trabajo termina solo.
        logger.error(
            json.dumps(
                {
                    "event": "retrieval_timeout",
                    "request_id": request_id_var.get(),
                    "timeout_s": settings.retrieval_timeout,
                }
            )
        )
        raise HTTPException(
            status_code=503,
            detail="Retrieval timed out. Please try again.",
        )
    docs = retrieval.docs
    t_retrieval = time.perf_counter()
    _metrics.retrieval_duration.observe(t_retrieval - t0)
```

En el resto de `run_pipeline` sustituye `len(candidates)` por `retrieval.candidates`, `round(candidates[0][1], 3) if candidates else None` por `retrieval.top_score`, `len(pre_rerank)` por `retrieval.pre_rerank`, `injected_stems` por `retrieval.injected_stems`, y `if candidates: _metrics.top_score.observe(candidates[0][1])` por `if retrieval.top_score is not None: _metrics.top_score.observe(retrieval.top_score)`.

- [ ] **Step 6: Actualizar el E2E y el eval**

En `tests/test_e2e.py` cambia `mock_settings.chroma_timeout = 30.0` por `mock_settings.retrieval_timeout = 120.0`.

En `tools/eval_retrieval.py`, `run_case` añade `"sources": len(retrieved_stems),` al dict devuelto; `_run_standard_eval` añade la columna: cabecera `{'Fuentes':>7}` tras `Chunks` y valor `{r['sources']:>7}`.

- [ ] **Step 7: Ejecutar suite y lint**

Run: `uv run pytest -q -m "not slow" && uv run ruff check app/ tests/ tools/ && uv run ruff format --check app/ tests/ tools/`
Expected: verde. Todos los tests que cuentan llamadas a `similarity_search_with_relevance_scores` siguen pasando porque el orden de llamadas no cambia.

- [ ] **Step 8: Eval real (baseline con columna Fuentes)**

Run: `GROQ_API_KEY=eval HF_HUB_OFFLINE=1 uv run python tools/eval_retrieval.py`
Expected: 13/13 OK, 0 FP, mismos chunks que el baseline. **Anota la columna Fuentes por caso** en la sección "Resultados" al final de este plan.

- [ ] **Step 9: Commit**

```bash
git add app/rag.py app/config.py tests/test_rag.py tests/test_e2e.py tools/eval_retrieval.py
git commit -m "refactor(retrieval): single _retrieve implementation shared by API and eval; global retrieval timeout"
```

---

### Task 6: Exclusiones antes del reranker y tope de chunks por fuente

**Files:**
- Modify: `app/rag.py` (`_retrieve`), `app/config.py`
- Modify: `tests/test_rag.py::test_run_pipeline_invokes_reranker_with_correct_top_k`, `tests/test_e2e.py`
- Create: `tests/test_retrieval_selection.py`

**Interfaces:**
- Consumes: `_retrieve`, `_stem` (Task 5).
- Produces: `app.rag._select_diverse(ranked: list, top_k: int, max_per_source: int) -> list`; setting `max_chunks_per_source: int = 4`; `rerank` se invoca con `top_k=len(pre_rerank)`.

- [ ] **Step 1: Tests**

Crea `tests/test_retrieval_selection.py`:

```python
import asyncio
from unittest.mock import MagicMock, patch

from app.config import settings
from app.models import QuestionnaireInput
from app.rag import _select_diverse, run_pipeline


def _doc(source, text=None):
    d = MagicMock()
    d.page_content = text or f"{source}-{id(d)}"
    d.metadata = {"source": source}
    return d


def _input(**overrides):
    base = dict(
        tipo_proyecto="app_web",
        descripcion_breve="App de gestión",
        tiene_usuarios_registrados=True,
        acceso_publico=False,
        tipos_datos_personales=["ninguno"],
        usuarios_menores=False,
        usuarios_ue=True,
        transferencia_datos_terceros=False,
        usa_ia=False,
        tipo_ia=None,
        usa_cookies=False,
        monetizacion=None,
        contenido_digital=False,
        ccaa="Madrid",
        es_empresa=False,
        colegiado=None,
    )
    base.update(overrides)
    return QuestionnaireInput(**base)


def test_select_diverse_caps_chunks_per_source_and_keeps_order():
    ranked = [_doc("A.pdf") for _ in range(6)] + [_doc("B.pdf"), _doc("B.pdf")]
    chosen = _select_diverse(ranked, top_k=5, max_per_source=4)
    assert [d.metadata["source"] for d in chosen] == ["A.pdf"] * 4 + ["B.pdf"]


def test_select_diverse_backfills_with_skipped_when_short():
    ranked = [_doc("A.pdf") for _ in range(6)]
    chosen = _select_diverse(ranked, top_k=5, max_per_source=4)
    assert len(chosen) == 5
    assert chosen == ranked[:5]


def test_select_diverse_disabled_with_zero():
    ranked = [_doc("A.pdf") for _ in range(6)]
    assert _select_diverse(ranked, top_k=3, max_per_source=0) == ranked[:3]


def test_select_diverse_returns_all_when_fewer_than_top_k():
    ranked = [_doc("A.pdf"), _doc("B.pdf")]
    assert _select_diverse(ranked, top_k=12, max_per_source=4) == ranked


def test_excluded_docs_never_reach_the_reranker(mock_reranker):
    ens = _doc("Real Decreto 311-2022 ENS.pdf")
    rgpd = [_doc("RGPD.pdf"), _doc("RGPD.pdf")]
    state = MagicMock()
    state.vectorstore.similarity_search_with_relevance_scores.return_value = [
        (ens, 0.9),
        (rgpd[0], 0.8),
        (rgpd[1], 0.7),
    ]
    state.groq_client.invoke.return_value = MagicMock(content="ok")
    state.groq_fallback_client = None
    state.indexed_normativas = frozenset({"RGPD", "Real Decreto 311-2022 ENS"})
    state.corpus_version = "v1"

    with patch("app.reranker.rerank", side_effect=lambda q, docs, top_k: docs) as rr:
        asyncio.run(run_pipeline(_input(), state))

    docs_sent = rr.call_args.args[1]
    assert ens not in docs_sent
    assert rr.call_args.kwargs["top_k"] == len(docs_sent)


def test_excluded_docs_do_not_consume_reranker_slots(monkeypatch):
    """Con reranker_top_k=2, ENS (excluida) no debe ocupar una de las dos plazas."""
    monkeypatch.setattr(settings, "reranker_top_k", 2)
    ens = _doc("Real Decreto 311-2022 ENS.pdf")
    rgpd = [_doc("RGPD.pdf"), _doc("RGPD.pdf")]
    state = MagicMock()
    state.vectorstore.similarity_search_with_relevance_scores.return_value = [
        (ens, 0.9),
        (rgpd[0], 0.8),
        (rgpd[1], 0.7),
    ]
    state.groq_client.invoke.return_value = MagicMock(content="ok")
    state.groq_fallback_client = None
    state.indexed_normativas = frozenset({"RGPD"})
    state.corpus_version = "v1"

    with patch("app.reranker.rerank", side_effect=lambda q, docs, top_k: docs) as rr:
        result = asyncio.run(run_pipeline(_input(), state))

    assert rr.call_args.args[1] == rgpd
    assert result.chunks_utilizados == 2


def test_run_pipeline_applies_per_source_cap(monkeypatch):
    monkeypatch.setattr(settings, "top_k_chunks", 3)
    monkeypatch.setattr(settings, "max_chunks_per_source", 2)
    guia = [_doc("Guía de Privacidad desde el Diseño - AEPD.pdf") for _ in range(3)]
    lopd = _doc("LOPDGDD.pdf")
    state = MagicMock()
    state.vectorstore.similarity_search_with_relevance_scores.return_value = [
        (d, 0.9) for d in guia
    ] + [(lopd, 0.8)]
    state.groq_client.invoke.return_value = MagicMock(content="ok")
    state.groq_fallback_client = None
    state.indexed_normativas = frozenset()
    state.corpus_version = "v1"

    with patch("app.reranker.rerank", side_effect=lambda q, docs, top_k: docs):
        result = asyncio.run(run_pipeline(_input(), state))

    assert result.chunks_utilizados == 3
    sent = state.groq_client.invoke.call_args.args[0][1].content
    assert "LOPDGDD.pdf" in sent
```

En `tests/test_rag.py::test_run_pipeline_invokes_reranker_with_correct_top_k` cambia la aserción final por `assert call_args.kwargs.get("top_k") == len(call_args.args[1])`. En `tests/test_e2e.py` añade `mock_settings.max_chunks_per_source = 4`.

- [ ] **Step 2: Ejecutar y ver fallar**

Run: `uv run pytest tests/test_retrieval_selection.py -q`
Expected: FAIL (`_select_diverse` no existe).

- [ ] **Step 3: Implementación**

`app/config.py`:

```python
    # Máximo de chunks de una misma normativa en el top-k del reranker (0 desactiva).
    max_chunks_per_source: int = 4
```

`app/rag.py`, antes de `_retrieve`:

```python
def _select_diverse(ranked: list, top_k: int, max_per_source: int) -> list:
    """Toma hasta top_k docs del orden del reranker con un máximo por normativa.

    Conserva el orden. Si el tope deja plazas libres, se rellenan con los docs
    saltados (en su orden original). max_per_source <= 0 desactiva el tope.
    """
    if max_per_source <= 0:
        return ranked[:top_k]
    chosen: list = []
    skipped: list = []
    per_source: dict[str, int] = {}
    for doc in ranked:
        if len(chosen) >= top_k:
            break
        stem = _stem(doc)
        if per_source.get(stem, 0) >= max_per_source:
            skipped.append(doc)
            continue
        per_source[stem] = per_source.get(stem, 0) + 1
        chosen.append(doc)
    if len(chosen) < top_k:
        chosen.extend(skipped[: top_k - len(chosen)])
    return chosen
```

En `_retrieve`, mueve el cálculo de `excluded_stems` al principio (justo después de `query = ...`) y reescribe los pasos 1–4:

```python
    excluded_stems = {exc.stem for exc in EXCLUSIONS if exc.condition(inp)}

    # 1. Candidatos principales — las normativas excluidas no ocupan plazas ni del recorte
    #    ni del reranker (antes se filtraban después y desperdiciaban 1-3 plazas del top-12).
    candidates = vs.similarity_search_with_relevance_scores(
        query, k=settings.overfetch_k
    )
    docs = [
        doc
        for doc, score in candidates
        if score >= threshold and _stem(doc) not in excluded_stems
    ][: settings.reranker_top_k]
    seen = {_content_hash(d) for d in docs}

    # 2. Búsqueda auxiliar — ver README "Query descriptiva + búsqueda auxiliar por dominio"
    for aux in AUXILIARY_SEARCHES:
        if not aux.condition(inp):
            continue
        _metrics.aux_search_triggered.labels(type=aux.name).inc()
        for doc, score in vs.similarity_search_with_relevance_scores(aux.query, k=aux.k):
            if score < threshold or _stem(doc) in excluded_stems:
                continue
            h = _content_hash(doc)
            if h not in seen:
                seen.add(h)
                docs.append(doc)

    # 3. CrossEncoder sobre todos los candidatos (orden completo) + tope por fuente
    pre_rerank = docs
    ranked = _reranker.rerank(query, pre_rerank, top_k=len(pre_rerank))
    docs = _select_diverse(ranked, settings.top_k_chunks, settings.max_chunks_per_source)
```

Elimina el paso 4 (exclusiones post-rerank); el paso 5 (inyecciones) queda igual (sigue consultando `excluded_stems`).

- [ ] **Step 4: Suite + lint**

Run: `uv run pytest -q -m "not slow" && uv run ruff check app/ tests/ && uv run ruff format --check app/ tests/`
Expected: verde.

- [ ] **Step 5: Eval real (después)**

Run: `GROQ_API_KEY=eval HF_HUB_OFFLINE=1 uv run python tools/eval_retrieval.py`
Expected: 13/13 OK, 0 FP; columna **Fuentes** ≥ la de Task 5 en todos los casos. Anota los números en "Resultados". Si algún caso pierde una normativa esperada, la causa más probable es el tope: sube `max_chunks_per_source` a 5 y repite; no toques las reglas.

- [ ] **Step 6: Commit**

```bash
git add app/rag.py app/config.py tests/
git commit -m "feat(retrieval): exclude before reranking and cap chunks per source in the LLM context"
```

---

### Task 7: Verificación de citas

**Files:**
- Create: `app/citations.py`, `tests/test_citations.py`
- Modify: `app/models.py` (`CitationStats`, `RAGResponse.citas`), `app/metrics.py`, `app/rag.py` (`_render_citation_section`, integración), `tests/test_models.py`

**Interfaces:**
- Produces: `app.citations.extract_quotes(answer: str) -> list[str]`; `app.citations.normalize(text: str) -> str`; `app.citations.verify_citations(answer: str, docs: list) -> CitationStats`; `app.models.CitationStats(total: int, verificadas: int, no_verificadas: list[str])`; `RAGResponse.citas: CitationStats`; `app.rag._render_citation_section(stats: CitationStats) -> str`; métricas `legaldev_citations_verified_ratio` (Histogram), `legaldev_citations_unverified_total` (Counter).

- [ ] **Step 1: Tests del módulo**

Crea `tests/test_citations.py`:

```python
import asyncio
from unittest.mock import MagicMock

from app.citations import extract_quotes, normalize, verify_citations
from app.models import CitationStats


def _doc(text, source="RGPD.pdf"):
    d = MagicMock()
    d.page_content = text
    d.metadata = {"source": source}
    return d


CHUNK = (
    "Artículo 5. Principios relativos al tratamiento. Los datos personales serán "
    "tratados de manera lícita, leal y transparente en relación con el interesado."
)


def test_extract_quotes_standard_format():
    answer = '> "tratados de manera lícita, leal y transparente" — RGPD, p. 36'
    assert extract_quotes(answer) == ["tratados de manera lícita, leal y transparente"]


def test_extract_quotes_typographic_and_guillemets():
    answer = (
        "> “tratados de manera lícita” — RGPD, p. 36\n"
        "> «leal y transparente» – LOPDGDD, p. 2\n"
    )
    assert extract_quotes(answer) == ["tratados de manera lícita", "leal y transparente"]


def test_extract_quotes_without_dash_still_captures():
    assert extract_quotes('> "leal y transparente"') == ["leal y transparente"]


def test_extract_quotes_ignores_non_blockquote_lines():
    answer = 'El RGPD dice "algo" en el artículo 5.\n**Interpretación:** "nada"'
    assert extract_quotes(answer) == []


def test_normalize_removes_whitespace_quotes_hyphens_and_case():
    assert normalize('Trata-\nmient o "lícito"') == "tratamientolícito"


def test_verify_exact_quote_is_verified():
    stats = verify_citations(
        '> "tratados de manera lícita, leal y transparente" — RGPD, p. 36',
        [_doc(CHUNK)],
    )
    assert stats == CitationStats(total=1, verificadas=1, no_verificadas=[])


def test_verify_tolerates_pdf_extraction_spacing():
    chunk = "Los dat os personales ser án trat ados de manera líc ita, leal y transparen te."
    stats = verify_citations(
        '> "Los datos personales serán tratados de manera lícita" — RGPD',
        [_doc(chunk)],
    )
    assert stats.verificadas == 1


def test_verify_tolerates_line_break_hyphenation():
    chunk = "serán tratados de manera lícita, leal y trans-\nparente en relación"
    stats = verify_citations('> "leal y transparente en relación" — RGPD', [_doc(chunk)])
    assert stats.verificadas == 1


def test_verify_ellipsis_splits_into_segments():
    stats = verify_citations(
        '> "Los datos personales serán […] leal y transparente" — RGPD',
        [_doc(CHUNK)],
    )
    assert stats.verificadas == 1


def test_verify_paraphrase_is_not_verified():
    stats = verify_citations(
        '> "los datos deben tratarse siempre con lealtad absoluta" — RGPD, p. 36',
        [_doc(CHUNK)],
    )
    assert stats.total == 1
    assert stats.verificadas == 0
    assert stats.no_verificadas == ["los datos deben tratarse siempre con lealtad absoluta"]


def test_verify_too_short_quote_is_not_verified():
    stats = verify_citations('> "lícita" — RGPD', [_doc(CHUNK)])
    assert stats.verificadas == 0


def test_verify_quote_spanning_two_chunks_is_not_verified():
    stats = verify_citations(
        '> "fin del primero inicio del segundo" — RGPD',
        [_doc("texto fin del primero"), _doc("inicio del segundo texto")],
    )
    assert stats.verificadas == 0


def test_verify_no_quotes_gives_zero_total():
    assert verify_citations("Sin citas.", [_doc(CHUNK)]) == CitationStats(
        total=0, verificadas=0, no_verificadas=[]
    )


def test_verify_truncates_unverified_to_120_chars():
    long_quote = "x" * 200
    stats = verify_citations(f'> "{long_quote}" — RGPD', [_doc(CHUNK)])
    assert len(stats.no_verificadas[0]) == 120
```

- [ ] **Step 2: Ejecutar y ver fallar**

Run: `uv run pytest tests/test_citations.py -q`
Expected: FAIL con `ModuleNotFoundError: app.citations`.

- [ ] **Step 3: Modelo y módulo**

`app/models.py`, antes de `RAGResponse`:

```python
class CitationStats(BaseModel):
    total: int
    verificadas: int
    no_verificadas: list[str]
```

y en `RAGResponse`:

```python
    citas: CitationStats = Field(
        default_factory=lambda: CitationStats(total=0, verificadas=0, no_verificadas=[])
    )
```

Crea `app/citations.py`:

```python
"""Verificación determinista de citas: ¿cada cita textual del informe existe en los fragmentos?

El SYSTEM_PROMPT exige citas literales; este módulo comprueba que lo sean. La comparación
ignora mayúsculas, comillas, guiones y TODO el espacio en blanco, porque el texto extraído
de los PDFs contiene artefactos ("tratamient o", "prot ecci ón") y saltos de línea con guion
que el LLM corrige al citar.
"""

import re
import unicodedata

from app.models import CitationStats

MIN_SEGMENT_CHARS = 12
MAX_REPORTED_CHARS = 120

_BLOCKQUOTE_RE = re.compile(r"^\s*>\s*(.+)$", re.MULTILINE)
# Primera comilla de apertura … última comilla de cierre seguida de guion (— – -).
_QUOTED_BEFORE_DASH_RE = re.compile(r"[\"“«](.*)[\"”»]\s*[—–-]")
_QUOTED_RE = re.compile(r"[\"“«](.+)[\"”»]")
_ELLIPSIS_RE = re.compile(r"\[\s*(?:\.\.\.|…)\s*\]|\.\.\.|…")
_STRIP_RE = re.compile(r"[\s\"“”«»'‘’\-–—­]+")


def extract_quotes(answer: str) -> list[str]:
    quotes: list[str] = []
    for m in _BLOCKQUOTE_RE.finditer(answer):
        line = m.group(1)
        q = _QUOTED_BEFORE_DASH_RE.search(line) or _QUOTED_RE.search(line)
        if q:
            quotes.append(q.group(1).strip())
    return quotes


def normalize(text: str) -> str:
    return _STRIP_RE.sub("", unicodedata.normalize("NFKC", text)).casefold()


def verify_citations(answer: str, docs: list) -> CitationStats:
    # "|" no sobrevive a la normalización de ningún texto, así que separa chunks sin falsos positivos.
    corpus = "|".join(normalize(d.page_content) for d in docs)
    quotes = extract_quotes(answer)
    unverified: list[str] = []
    for quote in quotes:
        segments = [normalize(s) for s in _ELLIPSIS_RE.split(quote)]
        segments = [s for s in segments if len(s) >= MIN_SEGMENT_CHARS]
        if not segments or not all(s in corpus for s in segments):
            unverified.append(quote[:MAX_REPORTED_CHARS])
    return CitationStats(
        total=len(quotes),
        verificadas=len(quotes) - len(unverified),
        no_verificadas=unverified,
    )
```

- [ ] **Step 4: Ejecutar los tests del módulo**

Run: `uv run pytest tests/test_citations.py -q`
Expected: PASS (14 tests). Si `test_normalize_removes_whitespace_quotes_hyphens_and_case` falla por el orden de casefold/NFKC, revisa que `normalize` aplique `casefold()` después de eliminar caracteres: el resultado esperado es exactamente `tratamientolícito`.

- [ ] **Step 5: Tests de integración**

Añade a `tests/test_citations.py`:

```python
from app.rag import _render_citation_section, run_pipeline


def test_render_citation_section_empty_when_no_quotes():
    assert _render_citation_section(CitationStats(total=0, verificadas=0, no_verificadas=[])) == ""


def test_render_citation_section_lists_unverified():
    text = _render_citation_section(
        CitationStats(total=3, verificadas=2, no_verificadas=["cita inventada"])
    )
    assert "## Verificación de citas" in text
    assert "2 de 3" in text
    assert "- \"cita inventada\"" in text


def test_run_pipeline_reports_citation_stats(mock_reranker):
    from app.models import QuestionnaireInput

    inp = QuestionnaireInput(
        tipo_proyecto="app_web",
        descripcion_breve="App de gestión",
        tiene_usuarios_registrados=True,
        acceso_publico=False,
        tipos_datos_personales=["ninguno"],
        usuarios_menores=False,
        usuarios_ue=True,
        transferencia_datos_terceros=False,
        usa_ia=False,
        tipo_ia=None,
        usa_cookies=False,
        monetizacion=None,
        contenido_digital=False,
        ccaa="Madrid",
        es_empresa=False,
        colegiado=None,
    )
    state = MagicMock()
    state.vectorstore.similarity_search_with_relevance_scores.return_value = [
        (_doc(CHUNK), 0.9),
        (_doc(CHUNK + " Segundo fragmento."), 0.8),
    ]
    state.groq_client.invoke.return_value = MagicMock(
        content=(
            "## RGPD\n\n"
            '> "tratados de manera lícita, leal y transparente" — RGPD, p. 36\n\n'
            '> "esta cita no existe en ningún fragmento recuperado" — RGPD, p. 1\n'
        )
    )
    state.groq_fallback_client = None
    state.indexed_normativas = frozenset({"RGPD"})
    state.corpus_version = "v1"

    result = asyncio.run(run_pipeline(inp, state))

    assert result.citas.total == 2
    assert result.citas.verificadas == 1
    assert result.citas.no_verificadas == [
        "esta cita no existe en ningún fragmento recuperado"
    ]
    assert "## Verificación de citas" in result.respuesta_completa
    assert "1 de 2" in result.respuesta_completa
```

Y en `tests/test_models.py`:

```python
def test_rag_response_citas_defaults_to_empty_stats():
    r = RAGResponse(
        respuesta_completa="x", normativas_detectadas=[], chunks_utilizados=0, disclaimer="d"
    )
    assert r.citas.total == 0
    assert r.citas.no_verificadas == []
```

- [ ] **Step 6: Ejecutar y ver fallar**

Run: `uv run pytest tests/test_citations.py tests/test_models.py -q`
Expected: FAIL (`_render_citation_section` no existe).

- [ ] **Step 7: Integración en `app/rag.py` y métricas**

`app/metrics.py`:

```python
citations_verified_ratio = Histogram(
    "legaldev_citations_verified_ratio",
    "Share of LLM quotes found verbatim in the retrieved chunks (per response)",
    buckets=[0.0, 0.25, 0.5, 0.75, 0.9, 1.0],
)

citations_unverified_total = Counter(
    "legaldev_citations_unverified_total",
    "LLM quotes not found verbatim in the retrieved chunks",
)
```

`app/rag.py`: importa `from app.citations import verify_citations` y `from app.models import CitationStats, QuestionnaireInput, RAGResponse`. Tras `_render_coverage_section`:

```python
def _render_citation_section(stats: CitationStats) -> str:
    if stats.total == 0:
        return ""
    lines = [
        "\n\n## Verificación de citas",
        f"Se han verificado textualmente {stats.verificadas} de {stats.total} citas contra los fragmentos recuperados.",
    ]
    if stats.no_verificadas:
        lines.append(
            "Citas no verificadas (posible paráfrasis o interpolación; contrastar con la fuente oficial):"
        )
        for quote in stats.no_verificadas:
            lines.append(f'- "{quote}"')
    return "\n".join(lines)
```

En `run_pipeline`, después de obtener `answer, llm_model` y antes del log `rag_pipeline`:

```python
    citations = verify_citations(answer, docs)
    if citations.total:
        _metrics.citations_verified_ratio.observe(citations.verificadas / citations.total)
        _metrics.citations_unverified_total.inc(len(citations.no_verificadas))
```

Añade `"citations_total": citations.total, "citations_verified": citations.verificadas,` al `json.dumps` del evento `rag_pipeline`, y construye la respuesta con:

```python
    coverage_section = _render_coverage_section(not_retrieved)
    citation_section = _render_citation_section(citations)
    return RAGResponse(
        respuesta_completa=answer + coverage_section + citation_section,
        normativas_detectadas=normativas,
        chunks_utilizados=len(docs),
        disclaimer=DISCLAIMER,
        corpus_version=state.corpus_version,
        llm_model=llm_model,
        citas=citations,
    )
```

- [ ] **Step 8: Suite + lint**

Run: `uv run pytest -q -m "not slow" && uv run ruff check app/ tests/ && uv run ruff format --check app/ tests/`
Expected: verde. Los tests existentes que comparan `respuesta_completa` con igualdad exacta (`test_run_pipeline_returns_rag_response`) siguen pasando porque su respuesta mock no contiene citas (`total == 0` → sección vacía).

- [ ] **Step 9: Commit**

```bash
git add app/citations.py app/models.py app/metrics.py app/rag.py tests/test_citations.py tests/test_models.py
git commit -m "feat(citations): verify LLM quotes against retrieved chunks and report the result"
```

---

### Task 8: Reranker precargado en el arranque

> La cuantización int8 se midió antes de planificar y **queda descartada** (ver "Decisión int8" al final del plan y la sección 4.5 del spec): no se añade ningún flag ni código de cuantización.

**Files:**
- Modify: `app/reranker.py`, `app/main.py` (lifespan)
- Modify: `tests/test_reranker.py`, `tests/test_api.py`, `tests/conftest.py`, `tests/test_concurrency.py`

**Interfaces:**
- Produces: `app.reranker.warmup() -> None` (carga el modelo y ejecuta una predicción mínima); `lifespan` la invoca tras leer `corpus_version`.

- [ ] **Step 1: Tests**

Añade a `tests/test_reranker.py`:

```python
import pytest


@pytest.fixture(autouse=True)
def _reset_encoder_singleton():
    import app.reranker as rr

    rr._encoder = None
    yield
    rr._encoder = None


def test_warmup_loads_encoder_and_runs_one_prediction():
    import app.reranker as rr

    with patch("app.reranker.CrossEncoder") as cls:
        rr.warmup()
    cls.assert_called_once()
    cls.return_value.predict.assert_called_once()


def test_warmup_twice_loads_the_model_once():
    import app.reranker as rr

    with patch("app.reranker.CrossEncoder") as cls:
        rr.warmup()
        rr.warmup()
    cls.assert_called_once()
```

En `tests/test_api.py` añade:

```python
def test_lifespan_warms_up_reranker(client):
    import app.reranker as rr

    rr.warmup.assert_called_once()
```

- [ ] **Step 2: Ejecutar y ver fallar**

Run: `uv run pytest tests/test_reranker.py tests/test_api.py::test_lifespan_warms_up_reranker -q`
Expected: FAIL (`warmup` no existe / `AttributeError`).

- [ ] **Step 3: Implementación**

`app/reranker.py`: añade tras `get_encoder`:

```python
def warmup() -> None:
    """Carga el modelo y ejecuta una predicción mínima para que la primera petición no lo pague.

    La carga desde disco cuesta ~2 s y la primera predicción compila kernels; en producción
    (CPU compartida) ese coste se sumaba al primer análisis. Idempotente: get_encoder es singleton.
    """
    get_encoder().predict([("warmup", "warmup")])
```

`app/main.py`: `from app import reranker as _reranker`; en `lifespan`, tras `app.state.corpus_version = ...` y antes del log "LegalDev is ready":

```python
    logger.info("Warming up reranker (%s)", _reranker._MODEL_NAME)
    _reranker.warmup()
```

`tests/conftest.py` fixture `client`: añade `patch("app.reranker.warmup"),` al `with`. `tests/test_concurrency.py`: igual.

- [ ] **Step 4: Suite + lint**

Run: `uv run pytest -q -m "not slow" && uv run ruff check app/ tests/ && uv run ruff format --check app/ tests/`
Expected: verde.

- [ ] **Step 5: Commit**

```bash
git add app/reranker.py app/main.py tests/
git commit -m "perf(reranker): warm up the CrossEncoder at startup"
```

---

### Task 9: Endurecer `/v1/feedback`

**Files:**
- Modify: `app/models.py` (`FeedbackInput`), `app/main.py` (`feedback_v1`), `tests/test_api.py`

- [ ] **Step 1: Tests**

En `tests/test_api.py`:

```python
def test_feedback_rejects_long_comment(client):
    resp = client.post(
        "/v1/feedback", json={"request_id": "abc123", "rating": 5, "comment": "x" * 2001}
    )
    assert resp.status_code == 422


@pytest.mark.parametrize("bad_id", ["", "x" * 65, "abc 123", "<script>"])
def test_feedback_rejects_malformed_request_id(client, bad_id):
    resp = client.post("/v1/feedback", json={"request_id": bad_id, "rating": 5})
    assert resp.status_code == 422


def test_feedback_accepts_uuid_request_id(client, tmp_path, monkeypatch):
    import app.main as main_module

    monkeypatch.setattr(main_module, "FEEDBACK_FILE", tmp_path / "f.jsonl")
    resp = client.post(
        "/v1/feedback",
        json={"request_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6", "rating": 3},
    )
    assert resp.status_code == 201


def test_feedback_is_rate_limited(client, tmp_path, monkeypatch):
    import app.main as main_module

    monkeypatch.setattr(main_module, "FEEDBACK_FILE", tmp_path / "f.jsonl")
    codes = [
        client.post("/v1/feedback", json={"request_id": "abc123", "rating": 5}).status_code
        for _ in range(11)
    ]
    assert codes[:10] == [201] * 10
    assert codes[10] == 429
```

(añade `import pytest` al módulo si falta.)

- [ ] **Step 2: Ejecutar y ver fallar**

Run: `uv run pytest tests/test_api.py -q -k feedback`
Expected: 3 grupos FAIL (201 en vez de 422/429).

- [ ] **Step 3: Implementación**

`app/models.py`:

```python
class FeedbackInput(BaseModel):
    # X-Request-ID es hex de 8 chars generado por el servidor; se admite también formato UUID.
    request_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)
```

`app/main.py`:

```python
@v1.post("/feedback", status_code=201)
@limiter.limit(settings.rate_limit)
def feedback_v1(input: FeedbackInput, request: Request):
    entry = input.model_dump()
    with FEEDBACK_FILE.open("a", encoding="utf-8") as f:
        f.write(_json.dumps(entry) + "\n")
    return {"status": "ok"}
```

- [ ] **Step 4: Suite, lint, commit**

```bash
uv run pytest -q -m "not slow" && uv run ruff check app/ tests/ && uv run ruff format --check app/ tests/
git add app/models.py app/main.py tests/test_api.py
git commit -m "fix(feedback): bound request_id/comment and rate-limit POST /v1/feedback"
```

---

### Task 10: Ingesta robusta y trazable + guardia de arranque

**Files:**
- Modify: `app/corpus.py` (`EMBEDDING_MODEL`), `app/legal_splitter.py`, `app/ingest.py`, `app/store.py`, `app/main.py`, `app/rag.py` (`_build_user_message`)
- Modify: `tests/test_legal_splitter.py`, `tests/test_store.py`, `tests/test_rag.py`, `tests/test_e2e.py`, `tests/conftest.py`
- Create: `tests/test_ingest_build.py`, `tests/test_lifespan_guard.py`

**Interfaces:**
- Produces: `app.corpus.EMBEDDING_MODEL: str`; `app.ingest._load_pages(pdf_path: Path) -> list[Document]`; `app.ingest._is_meaningful(chunk: Document) -> bool`; `app.ingest.MIN_CHUNK_CHARS = 40`; `app.ingest.SPLITTER_VERSION = 2`; `app.ingest._write_index_meta(target: Path, *, corpus_version: str, chunks: int, documents: int) -> None`; `app.ingest._swap_dirs(build_dir: Path, final_dir: Path, attempts: int = 5) -> None`; `app.store.read_index_meta(chroma_db_path: str) -> dict`; metadato de chunk `article: str`.

- [ ] **Step 1: Tests del splitter**

Añade a `tests/test_legal_splitter.py`:

```python
def test_article_heading_is_recorded_in_metadata():
    text = (
        "Artículo 12. Transparencia de la información. El responsable tomará las medidas oportunas.\n\n"
        "Artículo 13. Información que deberá facilitarse cuando los datos se obtengan del interesado."
    )
    chunks = split_document(Document(page_content=text, metadata={"source": "RGPD.pdf"}))
    assert chunks[0].metadata["article"] == "Artículo 12"
    assert chunks[1].metadata["article"] == "Artículo 13"


def test_long_article_subchunks_carry_heading_and_cont_prefix():
    long_article = "Artículo 35. Evaluación de impacto. " + ("Texto del artículo. " * 120)
    chunks = split_document(Document(page_content=long_article, metadata={"source": "RGPD.pdf"}))
    assert len(chunks) >= 2
    assert all(c.metadata["article"] == "Artículo 35" for c in chunks)
    assert chunks[0].page_content.startswith("Artículo 35.")
    assert all(c.page_content.startswith("Artículo 35 (cont.): ") for c in chunks[1:])


def test_text_without_heading_has_no_article_metadata():
    chunks = split_document(
        Document(page_content="Texto introductorio sin artículos. " * 5, metadata={"source": "g.pdf"})
    )
    assert all("article" not in c.metadata for c in chunks)
```

- [ ] **Step 2: Ejecutar y ver fallar**

Run: `uv run pytest tests/test_legal_splitter.py -q`
Expected: 2 FAIL (`KeyError: 'article'`).

- [ ] **Step 3: Splitter**

`app/legal_splitter.py`:

```python
import re

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

_ARTICLE_PATTERN = re.compile(
    r"(?=(?:Artículo|Art\.|Considerando|ARTÍCULO)\s+\d+)",
    re.MULTILINE,
)
_ARTICLE_HEADING = re.compile(r"^(?:Artículo|Art\.|Considerando|ARTÍCULO)\s+\d+")
_MAX_ARTICLE_CHARS = 1500
_FALLBACK_SPLITTER = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)


def split_document(doc: Document) -> list[Document]:
    text = doc.page_content.strip()
    if not text:
        return []

    parts = _ARTICLE_PATTERN.split(text)
    chunks: list[Document] = []

    for part in parts:
        part = part.strip()
        if not part:
            continue
        metadata = dict(doc.metadata)
        heading_match = _ARTICLE_HEADING.match(part)
        heading = heading_match.group(0) if heading_match else None
        if heading:
            metadata["article"] = heading
        if len(part) <= _MAX_ARTICLE_CHARS:
            chunks.append(Document(page_content=part, metadata=metadata))
            continue
        # Artículo largo: cada sub-chunk conserva el encabezado para que sea autodescriptivo
        # (embedding, reranker y cita del LLM saben de qué artículo es).
        sub = _FALLBACK_SPLITTER.create_documents([part], metadatas=[metadata])
        for i, sub_doc in enumerate(sub):
            if heading and i > 0:
                sub_doc.page_content = f"{heading} (cont.): {sub_doc.page_content}"
        chunks.extend(sub)

    if not chunks:
        return _FALLBACK_SPLITTER.split_documents([doc])
    return chunks
```

Run: `uv run pytest tests/test_legal_splitter.py -q` → PASS.

- [ ] **Step 4: Tests de ingesta y store**

Crea `tests/test_ingest_build.py`:

```python
import json
from pathlib import Path

import pytest
from langchain_core.documents import Document

from app import ingest
from app.corpus import EMBEDDING_MODEL


def test_is_meaningful_drops_tiny_chunks():
    assert ingest._is_meaningful(Document(page_content="ES", metadata={})) is False
    assert ingest._is_meaningful(Document(page_content="  12  ", metadata={})) is False
    assert ingest._is_meaningful(Document(page_content="x" * 40, metadata={})) is True


def test_load_pages_with_pypdf(tmp_path):
    from fpdf import FPDF

    pdf = FPDF()
    for i in range(2):
        pdf.add_page()
        pdf.set_font("Helvetica", size=11)
        pdf.multi_cell(0, 8, f"Articulo {i + 1}. Texto de la pagina {i + 1}.")
    path = tmp_path / "Norma.pdf"
    pdf.output(str(path))

    pages = ingest._load_pages(path)

    assert len(pages) == 2
    assert pages[0].metadata == {"source": "Norma.pdf", "page": 0, "total_pages": 2}
    assert "Texto de la pagina 1" in pages[0].page_content
    assert pages[1].metadata["page"] == 1


def test_write_index_meta(tmp_path):
    ingest._write_index_meta(tmp_path, corpus_version="abc123", chunks=10, documents=2)
    meta = json.loads((tmp_path / ".index_meta.json").read_text(encoding="utf-8"))
    assert meta["embedding_model"] == EMBEDDING_MODEL
    assert meta["corpus_version"] == "abc123"
    assert meta["chunks"] == 10
    assert meta["documents"] == 2
    assert meta["splitter_version"] == ingest.SPLITTER_VERSION
    assert meta["min_chunk_chars"] == ingest.MIN_CHUNK_CHARS
    assert meta["created_at"].endswith("+00:00")


def test_swap_dirs_replaces_old_index(tmp_path):
    final = tmp_path / "chroma_db"
    final.mkdir()
    (final / "old.txt").write_text("old")
    build = tmp_path / "chroma_db.building"
    build.mkdir()
    (build / "new.txt").write_text("new")

    ingest._swap_dirs(build, final)

    assert (final / "new.txt").exists()
    assert not (final / "old.txt").exists()
    assert not build.exists()
    assert not (tmp_path / "chroma_db.old").exists()


def test_swap_dirs_restores_previous_index_when_move_fails(tmp_path, monkeypatch):
    final = tmp_path / "chroma_db"
    final.mkdir()
    (final / "old.txt").write_text("old")
    build = tmp_path / "chroma_db.building"
    build.mkdir()
    (build / "new.txt").write_text("new")

    original_rename = Path.rename

    def _failing_rename(self, target):
        if self == build:
            raise PermissionError("file in use")
        return original_rename(self, target)

    monkeypatch.setattr(Path, "rename", _failing_rename)
    monkeypatch.setattr(ingest.time, "sleep", lambda s: None)

    with pytest.raises(SystemExit):
        ingest._swap_dirs(build, final, attempts=2)

    assert (final / "old.txt").exists()
    assert (build / "new.txt").exists()


def test_swap_dirs_when_no_previous_index(tmp_path):
    final = tmp_path / "chroma_db"
    build = tmp_path / "chroma_db.building"
    build.mkdir()
    (build / "new.txt").write_text("new")
    ingest._swap_dirs(build, final)
    assert (final / "new.txt").exists()
```

Añade a `tests/test_store.py`:

```python
def test_read_index_meta_returns_dict(tmp_path):
    (tmp_path / ".index_meta.json").write_text('{"embedding_model": "m", "chunks": 3}')
    assert store.read_index_meta(str(tmp_path)) == {"embedding_model": "m", "chunks": 3}


def test_read_index_meta_missing_file_returns_empty(tmp_path):
    assert store.read_index_meta(str(tmp_path)) == {}
```

- [ ] **Step 5: Ejecutar y ver fallar**

Run: `uv run pytest tests/test_ingest_build.py tests/test_store.py -q`
Expected: FAIL (atributos inexistentes).

- [ ] **Step 6: Implementación de corpus, store e ingest**

`app/corpus.py`, al principio:

```python
# Única fuente de verdad del modelo de embeddings. Cambiarlo exige reindexar: los vectores
# de un modelo no son comparables con los de otro (el arranque lo comprueba vía .index_meta.json).
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
```

`app/store.py`:

```python
import json


def read_index_meta(chroma_db_path: str) -> dict:
    meta_file = Path(chroma_db_path) / ".index_meta.json"
    if meta_file.exists():
        return json.loads(meta_file.read_text(encoding="utf-8"))
    return {}
```

`app/ingest.py` completo:

```python
import gc
import hashlib
import json
import logging
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from pypdf import PdfReader

from app.corpus import EMBEDDING_MODEL, REQUIRED_DOCS
from app.legal_splitter import split_document

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DOCS_PATH = os.getenv("DOCS_PATH", "./docs")
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_db")
COLLECTION_NAME = "legaldev"

# Chunks más cortos son cabeceras/pies de página ("ES", números) cuyo embedding es ruido.
MIN_CHUNK_CHARS = 40
# Súbelo cuando cambie la estrategia de chunking; queda registrado en .index_meta.json.
SPLITTER_VERSION = 2

DOC_TYPE_MAP = { ... sin cambios ... }


def get_doc_type(filename: str) -> str:
    ... sin cambios ...


def _compute_corpus_version(docs_dir: Path) -> str:
    ... sin cambios ...


def _check_required_docs(docs_dir: Path) -> None:
    ... sin cambios ...


def _load_pages(pdf_path: Path) -> list[Document]:
    """Una página por Document, con page 0-indexed (como PyPDFLoader; _build_user_message suma 1)."""
    reader = PdfReader(str(pdf_path))
    total = len(reader.pages)
    return [
        Document(
            page_content=page.extract_text() or "",
            metadata={"source": pdf_path.name, "page": i, "total_pages": total},
        )
        for i, page in enumerate(reader.pages)
    ]


def _is_meaningful(chunk: Document) -> bool:
    return len(chunk.page_content.strip()) >= MIN_CHUNK_CHARS


def _write_index_meta(target: Path, *, corpus_version: str, chunks: int, documents: int) -> None:
    meta = {
        "embedding_model": EMBEDDING_MODEL,
        "corpus_version": corpus_version,
        "chunks": chunks,
        "documents": documents,
        "splitter_version": SPLITTER_VERSION,
        "min_chunk_chars": MIN_CHUNK_CHARS,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (target / ".index_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _swap_dirs(build_dir: Path, final_dir: Path, attempts: int = 5) -> None:
    """Sustituye final_dir por build_dir sin destruir nunca el índice viejo antes de tener el nuevo.

    ChromaDB puede mantener descriptores abiertos (sobre todo en Windows), así que el
    rename se reintenta; si no lo consigue, restaura el índice anterior y aborta.
    """
    old_dir = final_dir.with_name(final_dir.name + ".old")
    if old_dir.exists():
        shutil.rmtree(old_dir)
    if final_dir.exists():
        final_dir.rename(old_dir)
    for attempt in range(1, attempts + 1):
        try:
            build_dir.rename(final_dir)
            break
        except OSError as e:
            logger.warning("Swap attempt %d/%d failed: %s", attempt, attempts, e)
            gc.collect()
            time.sleep(1.0)
    else:
        if old_dir.exists():
            old_dir.rename(final_dir)
        raise SystemExit(
            f"Could not move {build_dir} into place; previous index restored. "
            f"Close any process using it and run: mv {build_dir} {final_dir}"
        )
    if old_dir.exists():
        shutil.rmtree(old_dir, ignore_errors=True)


def main() -> None:
    docs_dir = Path(DOCS_PATH)
    _check_required_docs(docs_dir)

    pdf_files = sorted(docs_dir.glob("*.pdf"))
    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL, encode_kwargs={"normalize_embeddings": True}
    )
    all_chunks: list[Document] = []
    dropped = 0

    for pdf_path in pdf_files:
        doc_type = get_doc_type(pdf_path.name)
        chunks: list[Document] = []
        for page in _load_pages(pdf_path):
            page.metadata["doc_type"] = doc_type
            for chunk in split_document(page):
                if _is_meaningful(chunk):
                    chunks.append(chunk)
                else:
                    dropped += 1
        logger.info(
            "Indexing %s → %d chunks (doc_type=%s)", pdf_path.name, len(chunks), doc_type
        )
        all_chunks.extend(chunks)

    logger.info("Dropped %d chunks shorter than %d chars", dropped, MIN_CHUNK_CHARS)
    corpus_version = _compute_corpus_version(docs_dir)

    final_dir = Path(CHROMA_DB_PATH)
    build_dir = final_dir.with_name(final_dir.name + ".building")
    if build_dir.exists():
        shutil.rmtree(build_dir)

    logger.info("Generating embeddings and persisting %d chunks into %s...", len(all_chunks), build_dir)
    vectorstore = Chroma.from_documents(
        documents=all_chunks,
        embedding=embeddings,
        persist_directory=str(build_dir),
        collection_name=COLLECTION_NAME,
    )
    (build_dir / ".corpus_version").write_text(corpus_version)
    _write_index_meta(
        build_dir, corpus_version=corpus_version, chunks=len(all_chunks), documents=len(pdf_files)
    )
    del vectorstore
    gc.collect()

    _swap_dirs(build_dir, final_dir)
    logger.info(
        "Indexing complete — %d total chunks across %d documents (corpus %s)",
        len(all_chunks),
        len(pdf_files),
        corpus_version,
    )


if __name__ == "__main__":
    main()
```

Run: `uv run pytest tests/test_ingest_build.py tests/test_store.py tests/test_ingest.py -q` → PASS.

- [ ] **Step 7: Tests de la guardia de arranque y del artículo en el mensaje**

Crea `tests/test_lifespan_guard.py`:

```python
from unittest.mock import MagicMock, patch

import pytest


def _lifespan_patches(index_meta):
    mock_vs = MagicMock()
    mock_vs._collection.count.return_value = 10
    mock_vs._collection.get.return_value = {"metadatas": [{"source": "RGPD.pdf"}]}
    return (
        patch("app.main.HuggingFaceEmbeddings"),
        patch("app.main.Chroma", return_value=mock_vs),
        patch("app.main.ChatGroq"),
        patch("app.main._check_groq_model", return_value=True),
        patch("app.reranker.warmup"),
        patch("app.store.read_corpus_version", return_value="v"),
        patch("app.store.read_index_meta", return_value=index_meta),
    )


def test_startup_aborts_when_index_model_differs():
    from fastapi.testclient import TestClient

    from app.main import app

    p = _lifespan_patches({"embedding_model": "all-MiniLM-L6-v2"})
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6]:
        with pytest.raises(RuntimeError, match="built with 'all-MiniLM-L6-v2'"):
            with TestClient(app):
                pass


def test_startup_warns_when_index_has_no_meta(caplog):
    from fastapi.testclient import TestClient

    from app.main import app

    p = _lifespan_patches({})
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6]:
        with TestClient(app) as c:
            assert c.get("/health").status_code == 200
    assert "no .index_meta.json" in caplog.text


def test_startup_ok_when_index_model_matches():
    from fastapi.testclient import TestClient

    from app.corpus import EMBEDDING_MODEL
    from app.main import app

    p = _lifespan_patches({"embedding_model": EMBEDDING_MODEL})
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6]:
        with TestClient(app) as c:
            assert c.get("/health").status_code == 200
```

En `tests/test_rag.py`:

```python
def test_build_user_message_includes_article_when_present():
    doc = _make_mock_doc("RGPD.pdf")
    doc.metadata["article"] = "Artículo 5"
    doc.metadata["page"] = 35
    result = _build_user_message(_make_input(), [doc], [])
    assert "Fuente 1: RGPD.pdf, Artículo 5, p. 36" in result
```

- [ ] **Step 8: Ejecutar y ver fallar**

Run: `uv run pytest tests/test_lifespan_guard.py tests/test_rag.py::test_build_user_message_includes_article_when_present -q`
Expected: FAIL.

- [ ] **Step 9: main.py, rag.py, fixtures**

`app/main.py`: sustituye `EMBEDDING_MODEL = "..."` por `from app.corpus import EMBEDDING_MODEL`. En `lifespan`, justo antes de `count = store.count(...)`:

```python
    index_meta = store.read_index_meta(settings.chroma_db_path)
    indexed_model = index_meta.get("embedding_model")
    if indexed_model is None:
        logger.warning(
            "Index has no .index_meta.json (built before splitter v2); cannot verify it matches %s",
            EMBEDDING_MODEL,
        )
    elif indexed_model != EMBEDDING_MODEL:
        # Un índice de otro modelo produce scores sin sentido: mejor fallar alto que servir basura.
        raise RuntimeError(
            f"ChromaDB index was built with '{indexed_model}' but the app uses "
            f"'{EMBEDDING_MODEL}'. Re-run 'make ingest'."
        )
```

`app/rag.py`, en `_build_user_message`:

```python
        article = doc.metadata.get("article")
        article_str = f", {article}" if article else ""
        lines.append(f"\n### Fuente {i}: {source}{article_str}{page_str}")
```

`tests/conftest.py` fixture `client`: añade `patch("app.store.read_index_meta", return_value={}),`. `tests/test_concurrency.py`: igual.

`tests/test_e2e.py`: sustituye los imports de `PyPDFLoader`/`RecursiveCharacterTextSplitter` y la carga por:

```python
    from app.ingest import _load_pages
    from app.legal_splitter import split_document

    pdf_path = next(tiny_pdf_dir.glob("*.pdf"))
    chunks = [c for page in _load_pages(pdf_path) for c in split_document(page)]
```

(el resto del test igual; el modelo de embeddings pasa a importarse de `app.corpus`).

- [ ] **Step 10: Suite, lint, E2E**

Run: `uv run pytest -q -m "not slow" && uv run ruff check app/ tests/ && uv run ruff format --check app/ tests/ && HF_HUB_OFFLINE=1 uv run pytest tests/test_e2e.py -m slow -q`
Expected: verde (el E2E tarda ~30 s: Chroma real + embeddings reales, LLM mock).

- [ ] **Step 11: Commit**

```bash
git add app/ tests/
git commit -m "feat(ingest): atomic index build with .index_meta.json, chunk noise filter, article heading in sub-chunks; startup guard against model mismatch"
```

---

### Task 11: Evaluador fiel (`--chroma-path`, comprobación del modelo, sweep regenerado)

**Files:**
- Modify: `tools/eval_retrieval.py`, `tools/diagnose_ranking.py`, `Makefile`, `tests/test_eval_model_flag.py`, `tools/eval_results.md` (regenerado)

**Interfaces:**
- Produces: `tools.eval_retrieval._check_index_model(meta: dict, model: str, force: bool) -> None` (aborta con `SystemExit` si hay desajuste y no `force`); flag `--chroma-path`; flag `--force`.

- [ ] **Step 1: Tests**

En `tests/test_eval_model_flag.py`:

```python
def test_chroma_path_flag_defaults_to_settings():
    er = _load_eval_retrieval()
    args = er._build_parser().parse_args([])
    assert args.chroma_path == er.settings.chroma_db_path
    assert args.force is False


def test_check_index_model_aborts_on_mismatch():
    er = _load_eval_retrieval()
    with pytest.raises(SystemExit):
        er._check_index_model({"embedding_model": "a"}, "b", force=False)


def test_check_index_model_force_skips_abort():
    er = _load_eval_retrieval()
    er._check_index_model({"embedding_model": "a"}, "b", force=True)


def test_check_index_model_passes_when_match_or_missing():
    er = _load_eval_retrieval()
    er._check_index_model({"embedding_model": "a"}, "a", force=False)
    er._check_index_model({}, "a", force=False)
```

- [ ] **Step 2: Ejecutar y ver fallar** — `uv run pytest tests/test_eval_model_flag.py -q` → FAIL.

- [ ] **Step 3: Implementación**

En `tools/eval_retrieval.py`: importa `from app import store` y `from app.corpus import EMBEDDING_MODEL`; `--model` default `EMBEDDING_MODEL`; añade:

```python
    parser.add_argument(
        "--chroma-path",
        default=settings.chroma_db_path,
        help="Directorio del índice ChromaDB a evaluar (default: CHROMA_DB_PATH)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Evaluar aunque .index_meta.json declare otro modelo de embeddings (resultados NO comparables)",
    )
```

```python
def _check_index_model(meta: dict, model: str, force: bool) -> None:
    indexed = meta.get("embedding_model")
    if indexed is None:
        print("Aviso: el índice no tiene .index_meta.json; no se puede comprobar el modelo.")
        return
    if indexed != model and not force:
        raise SystemExit(
            f"El índice fue construido con '{indexed}' pero --model es '{model}': los vectores no son "
            "comparables y el eval sería basura. Usa el mismo modelo o --chroma-path a un índice "
            "construido con ese modelo (o --force si sabes lo que haces)."
        )
```

En `main()`: `_check_index_model(store.read_index_meta(args.chroma_path), args.model, args.force)` antes de crear `Chroma(persist_directory=args.chroma_path, ...)`.

`tools/diagnose_ranking.py`: `HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL, encode_kwargs={"normalize_embeddings": True})` (hoy usa `all-MiniLM-L6-v2` sin normalizar: contra el índice actual produce posiciones sin sentido).

`Makefile`: añade `eval-sweep` a `.PHONY` y el target:

```make
eval-sweep:
	uv run python tools/eval_retrieval.py --sweep
```

- [ ] **Step 4: Regenerar resultados**

Run: `GROQ_API_KEY=eval HF_HUB_OFFLINE=1 uv run python tools/eval_retrieval.py --sweep` (≈ 10 min; ejecuta en segundo plano). Verifica que `tools/eval_results.md` tiene las columnas Avg Recall / Avg FP / Avg Noise y la fecha de hoy.

- [ ] **Step 5: Suite, lint, commit**

```bash
uv run pytest -q -m "not slow" && uv run ruff check app/ tests/ tools/ && uv run ruff format --check app/ tests/ tools/
git add tools/ Makefile tests/test_eval_model_flag.py
git commit -m "fix(eval): --chroma-path, refuse mismatched embedding model, regenerate sweep results"
```

---

### Task 12: Dependencias de runtime

**Files:**
- Modify: `pyproject.toml`, `uv.lock`

- [ ] **Step 1: Comprobar que nada importa lo que se va a quitar**

Run: `grep -rn "langchain_community\|^import langchain$\|^from langchain import" app tools tests`
Expected: sin resultados (Task 10 ya migró `PyPDFLoader`).

- [ ] **Step 2: Editar dependencias**

En `pyproject.toml` elimina `"langchain~=1.2.18",` y `"langchain-community~=0.4.1",`; añade `"langchain-core~=1.4.0",` (se importa directamente en `app/rag.py`, `app/legal_splitter.py`, `app/ingest.py`).

- [ ] **Step 3: Regenerar lock y sincronizar**

Run: `uv lock && uv sync --frozen --extra dev`
Expected: sin errores; `uv tree --depth 1` ya no muestra `langchain` ni `langchain-community`.

- [ ] **Step 4: Suite completa + E2E**

Run: `uv run pytest -q -m "not slow" && HF_HUB_OFFLINE=1 uv run pytest tests/test_e2e.py -m slow -q`
Expected: verde.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(deps): drop unused langchain meta-package and langchain-community; depend on langchain-core explicitly"
```

---

### Task 13: Documentación

**Files:**
- Modify: `README.md`, `README_hf.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `.env.example`

- [ ] **Step 1: README**

  - Badge de tests con el número real (`uv run pytest -q -m "not slow" | tail -1`).
  - "Cómo funciona": diagrama actualizado al flujo de la sección 5 del spec (exclusiones antes del recorte, `_select_diverse ≤ 4 por fuente`, inyecciones, LLM principal → respaldo, verificación de citas). Indexación: `pypdf → legal_splitter (article metadata, "(cont.)") → filtro ≥ 40 chars → ChromaDB (.index_meta.json)`.
  - Tech Stack: `PDF loading  pypdf` y quitar LangChain community.
  - Nueva subsección en "Decisiones técnicas": **"Verificación de citas en código"** (por qué determinista; normalización sin espacios por los artefactos del PDF; qué expone `citas`; qué NO hace: no altera la respuesta).
  - Nueva subsección: **"Exclusiones antes del reranker y tope por fuente"** con la tabla de H3 y la columna Fuentes antes/después (de "Resultados").
  - Nueva subsección: **"Un solo retrieval para API y eval"** (sustituye a la mención de `retrieve_docs_sync` en la sección de evaluación).
  - Sección "Limitaciones conocidas": actualizar la de latencia con las cifras de H6 y la decisión int8; añadir **"La guardia por umbral es débil"** con la tabla de H5 y por qué no hay guardia por reranker; añadir la de retirada de modelos (ya en PR-A).
  - Estructura del proyecto: añadir `app/citations.py`; `tests/` actualizado.
  - Variables de entorno: `RETRIEVAL_TIMEOUT` (60) sustituye a `CHROMA_TIMEOUT`; `MAX_CHUNKS_PER_SOURCE` (4); `RERANKER_TOP_K` (25).
  - API: ejemplo de respuesta con `citas` y `llm_model`; `/health/deep` documentado.
  - Deploy: paso "Reindexar" apunta al runbook de CONTRIBUTING.
  - "Qué aprendí": añadir dos viñetas honestas — la retirada silenciosa del modelo (dos meses de 503) y "medir antes de construir" (BM25 y guardia por reranker descartados con datos).

- [ ] **Step 2: `.env.example`**: `CHROMA_TIMEOUT=10` → `RETRIEVAL_TIMEOUT=60`; añadir `MAX_CHUNKS_PER_SOURCE=4`.

- [ ] **Step 3: CONTRIBUTING**: sección **"Re-indexing the corpus"** (runbook de la sección 7 del spec), mención de `.index_meta.json` y de `SPLITTER_VERSION`; en "Retrieval improvements" añadir `MAX_CHUNKS_PER_SOURCE`, `RETRIEVAL_TIMEOUT` y `make eval-sweep`; en "Prompt improvements" mencionar que la sección "Verificación de citas" se genera en código.

- [ ] **Step 4: CHANGELOG `[Unreleased]`** — añadir bajo las entradas de PR-A:

```markdown
### Added
- Verificación determinista de citas (`app/citations.py`): cada cita del informe se busca literalmente en los fragmentos recuperados; `RAGResponse.citas` y sección "Verificación de citas" al final del informe; métricas `legaldev_citations_verified_ratio` y `legaldev_citations_unverified_total`.
- Tope de chunks por normativa en el contexto (`MAX_CHUNKS_PER_SOURCE`, default 4).
- Reranker precargado en el arranque (`warmup` en `lifespan`). La cuantización int8 se midió y se descartó: 1,6× en 2 hilos pero altera el ranking.
- `.index_meta.json` escrito por la ingesta (modelo de embeddings, versión del corpus, nº de chunks, versión del splitter); el arranque aborta si el índice se construyó con otro modelo.
- Metadato `article` en los chunks y prefijo `Artículo N (cont.):` en sub-chunks de artículos largos (activo tras reindexar).
- `tools/eval_retrieval.py --chroma-path` y comprobación de modelo del índice; `make eval-sweep`.

### Changed
- Retrieval unificado en `_retrieve` (API y eval ejecutan el mismo código); timeout global `RETRIEVAL_TIMEOUT` (60 s) sustituye a `CHROMA_TIMEOUT`.
- Las EXCLUSIONS se aplican antes del recorte y del reranker: las normativas excluidas ya no consumen plazas del contexto.
- La ingesta construye el índice en `chroma_db.building` y solo después sustituye el anterior; descarta chunks de menos de 40 caracteres; lee PDFs con `pypdf` directamente.
- Dependencias: eliminadas `langchain` y `langchain-community`; `langchain-core` explícita.

### Fixed
- `/v1/feedback`: `request_id` acotado (1–64 chars, `[A-Za-z0-9_-]`), `comment` ≤ 2000 chars, rate limit.
- `tools/diagnose_ranking.py` usaba `all-MiniLM-L6-v2` contra un índice multilingüe.
- `tools/eval_results.md` regenerado con el formato actual.
```

- [ ] **Step 5: Commit**

```bash
git add README.md README_hf.md CHANGELOG.md CONTRIBUTING.md .env.example
git commit -m "docs: sprint 3 — retrieval, citations, ingest, eval and configuration"
```

---

### Task 14: Verificación final y PR-B

- [ ] **Step 1: Verificación completa**

```bash
uv run ruff check app/ tests/ tools/ && uv run ruff format --check app/ tests/ tools/
uv run pytest -v -m "not slow" --cov=app --cov-report=term-missing --cov-fail-under=80
HF_HUB_OFFLINE=1 uv run pytest tests/test_e2e.py -v -m slow
GROQ_API_KEY=eval HF_HUB_OFFLINE=1 uv run python tools/eval_retrieval.py
```

Expected: lint limpio; suite verde con cobertura ≥ 80 %; E2E verde; eval 13/13, 0 FP, Fuentes ≥ baseline.

- [ ] **Step 2: Revisión de código** (skill `superpowers:requesting-code-review` sobre `main..HEAD`) y corrección de hallazgos.

- [ ] **Step 3: Push y PR**

```bash
git push -u origin sprint/3-rag-quality
gh pr create --base main --title "sprint 3: unified retrieval, citation verification, robust ingest, hardened feedback" --body-file <descripción>
```

Descripción: enlaza spec y plan; tabla de resultados del eval antes/después; decisión int8 con cifras; lista de pasos manuales (mergear PR-A primero y rebasar; `make push-space`; reindexado opcional).

---

## Resultados (rellenar durante la ejecución)

### Eval de retrieval — chunks / fuentes por caso

| Caso | Baseline chunks | Baseline fuentes (Task 5) | Después (Task 6) chunks / fuentes |
|---|---|---|---|
| rgpd-lopdgdd-basico | 14 | 5 | 15 / 7 |
| datos-sensibles-salud | 13 | 5 | 15 / 6 |
| ia-generativa | 18 | 5 | 18 / 8 |
| ia-agente | 19 | 6 | 20 / 9 |
| menores-datos-personales | 15 | 4 | 15 / 7 |
| cookies-webapp | 16 | 7 | 19 / 7 |
| ccii-ingeniero-colegiado | 16 | 5 | 17 / 5 |
| query-compleja-rgpd-colegiado-ia | 19 | 9 | 24 / 10 |
| lssi-web-publica | 16 | 6 | 17 / 6 |
| sin-datos-personales | 9 | 3 | 12 / 4 |
| off-topic-recetas | 5 | 2 | 5 / 2 |
| probe-8-plantas-dominio-lejano | 16 | 7 | 19 / 7 |
| sin-ia-sin-cookies-app-basica | 14 | 5 | 15 / 5 |

Recall 13/13 y 0 falsos positivos en ambas mediciones (Task 5 baseline y Task 6). La columna Fuentes no baja en ningún caso.

### Decisión int8 (medida antes de ejecutar; Task 8 solo hace warm-up)

Medición sobre 5 queries × 35 pares, `BAAI/bge-reranker-base`, cuantización dinámica in place de las 74 capas Linear (278 M parámetros):

| Hilos | fp32 s/query | int8 s/query | Aceleración | Top-12 idéntico |
|---|---|---|---|---|
| 6 | 6,53 | 6,50 | 1,0× | no: 8/12, 8/12, 8/12, 7/12, 11/12 |
| 2 | 17,58 | 11,06 | 1,6× | no (mismos solapes) |

Orden del top-5 distinto en las 5 queries; correlación fp32/int8 entre 0,23 y 0,82; diferencia máxima 0,83 en probabilidad. **Decisión: no se implementa** (criterio: ≥ 1,5× con top-12 idéntico; no se cumple la segunda parte).

### Tests

- Antes: 186. Después: 288.
