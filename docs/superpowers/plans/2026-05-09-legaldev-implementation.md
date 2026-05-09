# LegalDev RAG — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastAPI RAG service that takes a software project questionnaire and returns applicable Spanish/EU legal regulations with developer-facing technical implications.

**Architecture:** FastAPI app with a `lifespan` context that initializes HuggingFace embeddings, a persistent ChromaDB vector store, and a Groq LLM client — all stored in `app.state`. The `/analyze` endpoint passes `app.state` to `rag.run_pipeline()`, which builds a semantic query, retrieves top-8 chunks from ChromaDB, prompts the Groq LLM, and returns a structured `RAGResponse`. PDFs are indexed offline via `ingest.py` before Docker build.

**Tech Stack:** Python 3.11+, FastAPI, LangChain (langchain-community, langchain-chroma, langchain-groq, langchain-text-splitters), ChromaDB, sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2), Groq API (llama-4-scout), pydantic-settings, pytest, httpx

---

## File Map

| File | Purpose |
|------|---------|
| `requirements.txt` | All Python dependencies |
| `.env.example` | Template for required env vars |
| `.gitignore` | Ignore chroma_db, .env, __pycache__, etc. |
| `app/__init__.py` | Makes app a package |
| `app/config.py` | `Settings` via pydantic-settings |
| `app/models.py` | `QuestionnaireInput`, `RAGResponse` Pydantic models |
| `app/rag.py` | `_build_query()`, `_build_user_message()`, `run_pipeline()` |
| `app/main.py` | FastAPI app, lifespan, 3 endpoints |
| `app/ingest.py` | Standalone PDF indexing script |
| `Dockerfile` | Production image |
| `docker-compose.yml` | Local dev with volume mounts |
| `README.md` | Setup, usage, curl examples |
| `tests/__init__.py` | Empty |
| `tests/conftest.py` | Shared fixtures, env var setup |
| `tests/test_models.py` | QuestionnaireInput + RAGResponse validation |
| `tests/test_rag.py` | `_build_query()` and `run_pipeline()` unit tests |
| `tests/test_api.py` | Endpoint tests via TestClient |
| `tests/test_ingest.py` | `get_doc_type()` unit tests |

---

## Task 0: Project Scaffold

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `app/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `docs/` (empty folder for PDFs)

- [ ] **Step 1: Create requirements.txt**

```
fastapi
uvicorn[standard]
langchain
langchain-community
langchain-chroma
langchain-groq
langchain-text-splitters
chromadb
sentence-transformers
pypdf
python-dotenv
pydantic
pydantic-settings
httpx
pytest
```

- [ ] **Step 2: Create .env.example**

```
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
CHROMA_DB_PATH=./chroma_db
DOCS_PATH=./docs
TOP_K_CHUNKS=8
```

- [ ] **Step 3: Create .gitignore**

```
.env
__pycache__/
*.pyc
*.pyo
.pytest_cache/
chroma_db/
docs/*.pdf
*.egg-info/
dist/
build/
.venv/
venv/
```

- [ ] **Step 4: Create app/__init__.py and tests/__init__.py**

Both files are empty. Just create them.

- [ ] **Step 5: Create tests/conftest.py**

```python
import os
os.environ.setdefault("GROQ_API_KEY", "test-key-not-real")

import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_doc():
    doc = MagicMock()
    doc.page_content = "El RGPD establece que los datos personales deben tratarse de forma lícita."
    doc.metadata = {"source": "RGPD.pdf", "doc_type": "normativa_europea"}
    return doc


@pytest.fixture
def sample_input():
    from app.models import QuestionnaireInput
    return QuestionnaireInput(
        tipo_proyecto="app_web",
        descripcion_breve="Plataforma SaaS para gestión de facturas",
        tiene_usuarios_registrados=True,
        acceso_publico=False,
        tipos_datos_personales=["nombre", "email"],
        usuarios_menores=False,
        usuarios_ue=True,
        transferencia_datos_terceros=False,
        usa_ia=True,
        tipo_ia="generativa",
        usa_cookies=True,
        monetizacion="suscripcion",
        contenido_digital=False,
        ccaa="Asturias",
        es_empresa=False,
        colegiado=None,
    )


@pytest.fixture
def sample_input_dict():
    return {
        "tipo_proyecto": "app_web",
        "descripcion_breve": "Plataforma SaaS para gestión de facturas",
        "tiene_usuarios_registrados": True,
        "acceso_publico": False,
        "tipos_datos_personales": ["nombre", "email"],
        "usuarios_menores": False,
        "usuarios_ue": True,
        "transferencia_datos_terceros": False,
        "usa_ia": True,
        "tipo_ia": "generativa",
        "usa_cookies": True,
        "monetizacion": "suscripcion",
        "contenido_digital": False,
        "ccaa": "Asturias",
        "es_empresa": False,
        "colegiado": None,
    }


@pytest.fixture
def client(mock_doc):
    from unittest.mock import patch
    with patch("app.main.HuggingFaceEmbeddings"), \
         patch("app.main.Chroma") as mock_chroma_cls, \
         patch("app.main.ChatGroq") as mock_groq_cls:

        mock_vectorstore = MagicMock()
        mock_vectorstore.similarity_search.return_value = [mock_doc]
        mock_vectorstore._collection.count.return_value = 1234
        mock_chroma_cls.return_value = mock_vectorstore

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="Respuesta de prueba sobre RGPD")
        mock_groq_cls.return_value = mock_llm

        from app.main import app
        from fastapi.testclient import TestClient
        with TestClient(app) as c:
            yield c
```

- [ ] **Step 6: Install dependencies**

```bash
pip install -r requirements.txt
```

Expected: all packages install without errors. `sentence-transformers` will download the embedding model (~90 MB) on first use.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt .env.example .gitignore app/__init__.py tests/__init__.py tests/conftest.py
git commit -m "feat: project scaffold — dependencies, env template, test setup"
```

---

## Task 1: config.py

**Files:**
- Create: `app/config.py`

- [ ] **Step 1: Create app/config.py**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    groq_api_key: str
    groq_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    chroma_db_path: str = "./chroma_db"
    docs_path: str = "./docs"
    top_k_chunks: int = 8


settings = Settings()
```

- [ ] **Step 2: Verify Settings loads correctly**

```bash
GROQ_API_KEY=test python -c "from app.config import settings; print(settings.groq_model)"
```

Expected:
```
meta-llama/llama-4-scout-17b-16e-instruct
```

- [ ] **Step 3: Commit**

```bash
git add app/config.py
git commit -m "feat: add Settings via pydantic-settings"
```

---

## Task 2: models.py

**Files:**
- Create: `app/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_models.py`:

```python
import pytest
from pydantic import ValidationError
from app.models import QuestionnaireInput, RAGResponse


def test_questionnaire_input_valid(sample_input_dict):
    q = QuestionnaireInput(**sample_input_dict)
    assert q.tipo_proyecto == "app_web"
    assert q.tiene_usuarios_registrados is True
    assert q.tipos_datos_personales == ["nombre", "email"]
    assert q.tipo_ia == "generativa"
    assert q.colegiado is None


def test_questionnaire_input_minimal():
    q = QuestionnaireInput(
        tipo_proyecto="api",
        descripcion_breve="API pública de consulta meteorológica",
        tiene_usuarios_registrados=False,
        acceso_publico=True,
        tipos_datos_personales=["ninguno"],
        usuarios_menores=False,
        usuarios_ue=False,
        transferencia_datos_terceros=False,
        usa_ia=False,
        usa_cookies=False,
        contenido_digital=False,
        ccaa="Madrid",
        es_empresa=True,
    )
    assert q.tipo_ia is None
    assert q.monetizacion is None
    assert q.colegiado is None


def test_questionnaire_input_descripcion_max_length():
    with pytest.raises(ValidationError):
        QuestionnaireInput(
            tipo_proyecto="app_web",
            descripcion_breve="x" * 501,
            tiene_usuarios_registrados=False,
            acceso_publico=True,
            tipos_datos_personales=["ninguno"],
            usuarios_menores=False,
            usuarios_ue=False,
            transferencia_datos_terceros=False,
            usa_ia=False,
            usa_cookies=False,
            contenido_digital=False,
            ccaa="Madrid",
            es_empresa=True,
        )


def test_rag_response():
    r = RAGResponse(
        respuesta_completa="Debes implementar consentimiento explícito según el RGPD.",
        normativas_detectadas=["RGPD", "LOPDGDD"],
        chunks_utilizados=5,
        disclaimer="⚠️ Esta información es orientativa.",
    )
    assert r.chunks_utilizados == 5
    assert "RGPD" in r.normativas_detectadas
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_models.py -v
```

Expected: `ERROR` — `ModuleNotFoundError: No module named 'app.models'`

- [ ] **Step 3: Create app/models.py**

```python
from typing import Optional
from pydantic import BaseModel, Field


class QuestionnaireInput(BaseModel):
    tipo_proyecto: str
    descripcion_breve: str = Field(max_length=500)
    tiene_usuarios_registrados: bool
    acceso_publico: bool

    tipos_datos_personales: list[str]
    usuarios_menores: bool
    usuarios_ue: bool
    transferencia_datos_terceros: bool

    usa_ia: bool
    tipo_ia: Optional[str] = None
    usa_cookies: bool
    monetizacion: Optional[str] = None
    contenido_digital: bool

    ccaa: str
    es_empresa: bool
    colegiado: Optional[bool] = None


class RAGResponse(BaseModel):
    respuesta_completa: str
    normativas_detectadas: list[str]
    chunks_utilizados: int
    disclaimer: str
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_models.py -v
```

Expected:
```
PASSED tests/test_models.py::test_questionnaire_input_valid
PASSED tests/test_models.py::test_questionnaire_input_minimal
PASSED tests/test_models.py::test_questionnaire_input_descripcion_max_length
PASSED tests/test_models.py::test_rag_response
4 passed
```

- [ ] **Step 5: Commit**

```bash
git add app/models.py tests/test_models.py
git commit -m "feat: add QuestionnaireInput and RAGResponse Pydantic models"
```

---

## Task 3: rag.py — query construction

**Files:**
- Create: `app/rag.py` (partial — `_build_query` only for now)
- Create: `tests/test_rag.py` (partial)

- [ ] **Step 1: Write failing tests**

Create `tests/test_rag.py`:

```python
from app.rag import _build_query
from app.models import QuestionnaireInput


def _make_input(**overrides):
    base = dict(
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
    base.update(overrides)
    return QuestionnaireInput(**base)


def test_build_query_includes_tipo_proyecto():
    assert "api" in _build_query(_make_input(tipo_proyecto="api"))


def test_build_query_includes_datos_personales():
    result = _build_query(_make_input(tipos_datos_personales=["salud", "ubicacion"]))
    assert "datos personales" in result
    assert "salud" in result
    assert "ubicacion" in result


def test_build_query_excludes_ninguno():
    result = _build_query(_make_input(tipos_datos_personales=["ninguno"]))
    assert "datos personales" not in result


def test_build_query_ia_with_tipo():
    result = _build_query(_make_input(usa_ia=True, tipo_ia="generativa"))
    assert "inteligencia artificial" in result
    assert "generativa" in result


def test_build_query_ia_without_tipo():
    result = _build_query(_make_input(usa_ia=True, tipo_ia=None))
    assert "inteligencia artificial" in result


def test_build_query_no_ia():
    result = _build_query(_make_input(usa_ia=False))
    assert "inteligencia artificial" not in result


def test_build_query_cookies():
    assert "cookies" in _build_query(_make_input(usa_cookies=True))


def test_build_query_usuarios_menores():
    assert "menores" in _build_query(_make_input(usuarios_menores=True))


def test_build_query_always_includes_ccaa_and_spain():
    result = _build_query(_make_input(ccaa="Cataluña"))
    assert "Cataluña" in result
    assert "España" in result


def test_build_query_monetizacion_ninguna_excluded():
    assert "ninguna" not in _build_query(_make_input(monetizacion="ninguna"))


def test_build_query_monetizacion_included():
    assert "publicidad" in _build_query(_make_input(monetizacion="publicidad"))
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_rag.py -v
```

Expected: `ERROR` — `ImportError: cannot import name '_build_query' from 'app.rag'`

- [ ] **Step 3: Create app/rag.py with constants and _build_query**

```python
import logging
from fastapi import HTTPException
from langchain_core.messages import SystemMessage, HumanMessage

from app.models import QuestionnaireInput, RAGResponse
from app.config import settings

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "⚠️ Esta información es orientativa y no constituye asesoramiento legal. "
    "Para decisiones con impacto legal, consulta con un abogado especializado "
    "en derecho digital."
)

SYSTEM_PROMPT = (
    "Eres LegalDev, un asistente especializado en normativa legal aplicable a proyectos "
    "de software en España y la Unión Europea.\n\n"
    "Tu misión es analizar el contexto de un proyecto de software y explicar qué normativas "
    "legales le aplican, con implicaciones técnicas concretas y accionables para el developer.\n\n"
    "Reglas:\n"
    "- Responde siempre en español\n"
    "- Sé específico y técnico: no digas 'debes cumplir el RGPD', di qué tienes que implementar exactamente\n"
    "- Organiza la respuesta por normativa aplicable\n"
    "- Incluye siempre el disclaimer al final\n"
    "- No inventes normativas que no estén en el contexto proporcionado\n\n"
    "Disclaimer obligatorio al final de cada respuesta:\n"
    '"⚠️ Esta información es orientativa y no constituye asesoramiento legal. '
    'Para decisiones con impacto legal, consulta con un abogado especializado en derecho digital."'
)


def _build_query(input: QuestionnaireInput) -> str:
    parts = [input.tipo_proyecto]

    if input.tiene_usuarios_registrados:
        parts.append("usuarios registrados")

    if input.tipos_datos_personales and "ninguno" not in input.tipos_datos_personales:
        parts.append("tratamiento datos personales")
        parts.extend(input.tipos_datos_personales)

    if input.usuarios_menores:
        parts.append("usuarios menores de edad")

    if input.usuarios_ue:
        parts.append("usuarios Unión Europea")

    if input.transferencia_datos_terceros:
        parts.append("transferencia datos terceros")

    if input.usa_ia:
        ia_text = "inteligencia artificial"
        if input.tipo_ia:
            ia_text += f" {input.tipo_ia}"
        parts.append(ia_text)

    if input.usa_cookies:
        parts.append("cookies")

    if input.monetizacion and input.monetizacion != "ninguna":
        parts.append(input.monetizacion)

    if input.contenido_digital:
        parts.append("contenido digital")

    parts.append("cumplimiento legal España")
    parts.append(input.ccaa)
    parts.append(input.descripcion_breve)

    return " ".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_rag.py -v
```

Expected:
```
PASSED tests/test_rag.py::test_build_query_includes_tipo_proyecto
PASSED tests/test_rag.py::test_build_query_includes_datos_personales
PASSED tests/test_rag.py::test_build_query_excludes_ninguno
PASSED tests/test_rag.py::test_build_query_ia_with_tipo
PASSED tests/test_rag.py::test_build_query_ia_without_tipo
PASSED tests/test_rag.py::test_build_query_no_ia
PASSED tests/test_rag.py::test_build_query_cookies
PASSED tests/test_rag.py::test_build_query_usuarios_menores
PASSED tests/test_rag.py::test_build_query_always_includes_ccaa_and_spain
PASSED tests/test_rag.py::test_build_query_monetizacion_ninguna_excluded
PASSED tests/test_rag.py::test_build_query_monetizacion_included
11 passed
```

- [ ] **Step 5: Commit**

```bash
git add app/rag.py tests/test_rag.py
git commit -m "feat: add _build_query semantic query construction"
```

---

## Task 4: rag.py — run_pipeline

**Files:**
- Modify: `app/rag.py` (add `_build_user_message` and `run_pipeline`)
- Modify: `tests/test_rag.py` (add run_pipeline tests)

- [ ] **Step 1: Add failing tests to tests/test_rag.py**

First, add these imports to the top of `tests/test_rag.py` (after the existing imports):

```python
import pytest
from unittest.mock import MagicMock
from app.rag import run_pipeline, DISCLAIMER
from app.config import settings
```

Then append these functions to the end of `tests/test_rag.py`:

```python
def _make_mock_doc(source="RGPD.pdf", doc_type="normativa_europea"):
    doc = MagicMock()
    doc.page_content = f"Contenido de prueba de {source}"
    doc.metadata = {"source": source, "doc_type": doc_type}
    return doc


def _make_state(docs, llm_response="Respuesta de prueba"):
    state = MagicMock()
    state.vectorstore.similarity_search.return_value = docs
    state.groq_client.invoke.return_value = MagicMock(content=llm_response)
    return state


def test_run_pipeline_returns_rag_response(sample_input):
    docs = [
        _make_mock_doc("RGPD.pdf"),
        _make_mock_doc("LOPDGDD.pdf", "normativa_española"),
    ]
    state = _make_state(docs, "Debes implementar consentimiento explícito.")

    result = run_pipeline(sample_input, state)

    assert result.respuesta_completa == "Debes implementar consentimiento explícito."
    assert result.chunks_utilizados == 2
    assert result.disclaimer == DISCLAIMER
    assert "RGPD" in result.normativas_detectadas
    assert "LOPDGDD" in result.normativas_detectadas


def test_run_pipeline_normativas_deduplicadas(sample_input):
    docs = [_make_mock_doc("RGPD.pdf"), _make_mock_doc("RGPD.pdf")]
    result = run_pipeline(sample_input, _make_state(docs))
    assert result.normativas_detectadas.count("RGPD") == 1


def test_run_pipeline_groq_error_raises_503(sample_input):
    state = MagicMock()
    state.vectorstore.similarity_search.return_value = [_make_mock_doc()]
    state.groq_client.invoke.side_effect = Exception("Connection refused")

    with pytest.raises(Exception) as exc_info:
        run_pipeline(sample_input, state)

    assert exc_info.value.status_code == 503


def test_run_pipeline_calls_similarity_search_with_k(sample_input):
    docs = [_make_mock_doc()]
    state = _make_state(docs)

    run_pipeline(sample_input, state)

    state.vectorstore.similarity_search.assert_called_once()
    call_args = state.vectorstore.similarity_search.call_args
    assert call_args.kwargs.get("k") == settings.top_k_chunks
```

- [ ] **Step 2: Run failing tests**

```bash
pytest tests/test_rag.py::test_run_pipeline_returns_rag_response -v
```

Expected: `FAILED` — `ImportError: cannot import name 'run_pipeline' from 'app.rag'`

- [ ] **Step 3: Add _build_user_message and run_pipeline to app/rag.py**

Append to the end of `app/rag.py`:

```python
def _build_user_message(input: QuestionnaireInput, docs: list) -> str:
    lines = [
        "## Contexto del proyecto",
        f"- Tipo: {input.tipo_proyecto}",
        f"- Descripción: {input.descripcion_breve}",
        f"- Usuarios registrados: {input.tiene_usuarios_registrados}",
        f"- Acceso público: {input.acceso_publico}",
        f"- Datos personales: {', '.join(input.tipos_datos_personales)}",
        f"- Usuarios menores: {input.usuarios_menores}",
        f"- Usuarios en UE: {input.usuarios_ue}",
        f"- Transferencia a terceros: {input.transferencia_datos_terceros}",
        f"- Usa IA: {input.usa_ia}" + (f" ({input.tipo_ia})" if input.tipo_ia else ""),
        f"- Usa cookies: {input.usa_cookies}",
        f"- Monetización: {input.monetizacion or 'ninguna'}",
        f"- Contenido digital: {input.contenido_digital}",
        f"- CCAA: {input.ccaa}",
        f"- Es empresa: {input.es_empresa}",
        "",
        "## Normativa relevante recuperada",
    ]

    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("source", "desconocido")
        lines.append(f"\n### Fuente {i}: {source}")
        lines.append(doc.page_content)

    return "\n".join(lines)


def run_pipeline(input: QuestionnaireInput, state) -> RAGResponse:
    query = _build_query(input)
    logger.info("Running RAG pipeline, query: %s", query[:100])

    docs = state.vectorstore.similarity_search(query, k=settings.top_k_chunks)
    logger.info("Retrieved %d chunks", len(docs))

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=_build_user_message(input, docs)),
    ]

    try:
        response = state.groq_client.invoke(messages)
    except Exception as e:
        logger.error("Groq API error: %s", e)
        raise HTTPException(
            status_code=503,
            detail="LLM service unavailable. Please try again later.",
        )

    normativas = list({
        doc.metadata["source"].replace(".pdf", "")
        for doc in docs
        if "source" in doc.metadata
    })

    return RAGResponse(
        respuesta_completa=response.content,
        normativas_detectadas=normativas,
        chunks_utilizados=len(docs),
        disclaimer=DISCLAIMER,
    )
```

- [ ] **Step 4: Run all rag tests**

```bash
pytest tests/test_rag.py -v
```

Expected: all 15 tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/rag.py tests/test_rag.py
git commit -m "feat: add run_pipeline — retrieval, LLM call, response assembly"
```

---

## Task 5: main.py

**Files:**
- Create: `app/main.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Write failing endpoint tests**

Create `tests/test_api.py`:

```python
def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "LegalDev"
    assert data["version"] == "0.1.0"
    assert "description" in data


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["docs_indexed"] == 1234


def test_analyze_returns_rag_response(client, sample_input_dict):
    response = client.post("/analyze", json=sample_input_dict)
    assert response.status_code == 200
    data = response.json()
    assert data["respuesta_completa"] == "Respuesta de prueba sobre RGPD"
    assert "normativas_detectadas" in data
    assert data["chunks_utilizados"] == 1
    assert "disclaimer" in data


def test_analyze_invalid_input_missing_fields(client):
    response = client.post("/analyze", json={"tipo_proyecto": "app_web"})
    assert response.status_code == 422


def test_analyze_descripcion_too_long(client, sample_input_dict):
    sample_input_dict["descripcion_breve"] = "x" * 501
    response = client.post("/analyze", json=sample_input_dict)
    assert response.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_api.py -v
```

Expected: `ERROR` — `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 3: Create app/main.py**

```python
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_groq import ChatGroq

from app.config import settings
from app.models import QuestionnaireInput, RAGResponse
from app.rag import run_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
CHROMA_COLLECTION = "legaldev"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
    app.state.embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    logger.info("Connecting to ChromaDB at %s", settings.chroma_db_path)
    app.state.vectorstore = Chroma(
        persist_directory=settings.chroma_db_path,
        embedding_function=app.state.embeddings,
        collection_name=CHROMA_COLLECTION,
    )
    logger.info("Initializing Groq client with model %s", settings.groq_model)
    app.state.groq_client = ChatGroq(
        api_key=settings.groq_api_key,
        model_name=settings.groq_model,
    )
    logger.info("LegalDev is ready")
    yield


app = FastAPI(
    title="LegalDev",
    version="0.1.0",
    description="Asistente RAG de normativa legal para developers en España",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "name": "LegalDev",
        "version": "0.1.0",
        "description": "Asistente RAG de normativa legal para developers en España",
    }


@app.get("/health")
def health(request: Request):
    docs_indexed = request.app.state.vectorstore._collection.count()
    return {"status": "ok", "docs_indexed": docs_indexed}


@app.post("/analyze", response_model=RAGResponse)
def analyze(input: QuestionnaireInput, request: Request):
    return run_pipeline(input, request.app.state)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_api.py -v
```

Expected:
```
PASSED tests/test_api.py::test_root
PASSED tests/test_api.py::test_health
PASSED tests/test_api.py::test_analyze_returns_rag_response
PASSED tests/test_api.py::test_analyze_invalid_input_missing_fields
PASSED tests/test_api.py::test_analyze_descripcion_too_long
5 passed
```

- [ ] **Step 5: Run full test suite**

```bash
pytest -v
```

Expected: all tests pass (models + rag + api).

- [ ] **Step 6: Commit**

```bash
git add app/main.py tests/test_api.py
git commit -m "feat: add FastAPI app with lifespan, CORS, and three endpoints"
```

---

## Task 6: ingest.py

**Files:**
- Create: `app/ingest.py`
- Create: `tests/test_ingest.py`

- [ ] **Step 1: Write failing tests for get_doc_type**

Create `tests/test_ingest.py`:

```python
from app.ingest import get_doc_type


def test_rgpd():
    assert get_doc_type("RGPD.pdf") == "normativa_europea"

def test_eu_ai_act():
    assert get_doc_type("EU AI Act.pdf") == "normativa_europea"

def test_nis2():
    assert get_doc_type("Directiva NIS2.pdf") == "normativa_europea"

def test_responsabilidad_ia():
    assert get_doc_type("Directiva de Responsabilidad por Productos con IA.pdf") == "normativa_europea"

def test_lopdgdd():
    assert get_doc_type("LOPDGDD.pdf") == "normativa_española"

def test_ens():
    assert get_doc_type("ENS.pdf") == "normativa_española"

def test_lssi():
    assert get_doc_type("LSSI.pdf") == "normativa_española"

def test_propiedad_intelectual():
    assert get_doc_type("Ley de Propiedad Intelectual.pdf") == "normativa_española"

def test_codigo_etico():
    assert get_doc_type("Código Ético y Deontológico CCII.pdf") == "deontologia"

def test_aepd_cookies():
    assert get_doc_type("Guía sobre uso de cookies - AEPD.pdf") == "guia_aepd"

def test_aepd_anonimizacion():
    assert get_doc_type("Guía de Anonimización - AEPD.pdf") == "guia_aepd"

def test_aepd_adecuacion_ia():
    assert get_doc_type("Adecuación al RGPD de tratamientos que incorporan IA - AEPD.pdf") == "guia_aepd"

def test_unknown():
    assert get_doc_type("Documento desconocido.pdf") == "otro"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_ingest.py -v
```

Expected: `ERROR` — `ModuleNotFoundError: No module named 'app.ingest'`

- [ ] **Step 3: Create app/ingest.py**

```python
import logging
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DOCS_PATH = os.getenv("DOCS_PATH", "./docs")
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_db")
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
COLLECTION_NAME = "legaldev"

DOC_TYPE_MAP = {
    "RGPD.pdf": "normativa_europea",
    "EU AI Act.pdf": "normativa_europea",
    "Directiva NIS2.pdf": "normativa_europea",
    "Directiva de Responsabilidad por Productos con IA.pdf": "normativa_europea",
    "LOPDGDD.pdf": "normativa_española",
    "ENS.pdf": "normativa_española",
    "LSSI.pdf": "normativa_española",
    "Ley de Propiedad Intelectual.pdf": "normativa_española",
    "Código Ético y Deontológico CCII.pdf": "deontologia",
}


def get_doc_type(filename: str) -> str:
    if "AEPD" in filename:
        return "guia_aepd"
    return DOC_TYPE_MAP.get(filename, "otro")


def main() -> None:
    docs_dir = Path(DOCS_PATH)
    pdf_files = sorted(docs_dir.glob("*.pdf"))

    if not pdf_files:
        logger.warning("No PDF files found in %s", DOCS_PATH)
        return

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    all_chunks = []

    for pdf_path in pdf_files:
        filename = pdf_path.name
        doc_type = get_doc_type(filename)
        loader = PyPDFLoader(str(pdf_path))
        pages = loader.load()
        chunks = splitter.split_documents(pages)

        for chunk in chunks:
            chunk.metadata["source"] = filename
            chunk.metadata["doc_type"] = doc_type

        logger.info("Indexing %s → %d chunks (doc_type=%s)", filename, len(chunks), doc_type)
        all_chunks.extend(chunks)

    if Path(CHROMA_DB_PATH).exists():
        shutil.rmtree(CHROMA_DB_PATH)
        logger.info("Wiped existing ChromaDB at %s", CHROMA_DB_PATH)

    logger.info("Generating embeddings and persisting %d chunks...", len(all_chunks))
    Chroma.from_documents(
        documents=all_chunks,
        embedding=embeddings,
        persist_directory=CHROMA_DB_PATH,
        collection_name=COLLECTION_NAME,
    )

    logger.info(
        "Indexing complete — %d total chunks across %d documents",
        len(all_chunks),
        len(pdf_files),
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_ingest.py -v
```

Expected:
```
PASSED tests/test_ingest.py::test_rgpd
...
13 passed
```

- [ ] **Step 5: Run full test suite**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/ingest.py tests/test_ingest.py
git commit -m "feat: add ingest.py — PDF indexing with doc_type metadata"
```

---

## Task 7: Dockerfile + docker-compose.yml

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY chroma_db/ ./chroma_db/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Create docker-compose.yml**

```yaml
version: "3.8"

services:
  legaldev:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./chroma_db:/app/chroma_db
      - ./docs:/app/docs
```

- [ ] **Step 3: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "feat: add Dockerfile and docker-compose for local dev and Railway deploy"
```

---

## Task 8: README.md

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create README.md**

```markdown
# LegalDev

Asistente RAG de normativa legal para developers en España. Dado un cuestionario sobre tu proyecto de software, devuelve las normativas españolas y europeas aplicables con implicaciones técnicas concretas.

> ⚠️ Esta herramienta es de orientación informativa y no constituye asesoramiento legal. Para decisiones con impacto legal, consulta con un abogado especializado en derecho digital.

---

## Instalación y setup local

### Requisitos

- Python 3.11+
- Docker + Docker Compose (opcional)
- Cuenta en [Groq](https://console.groq.com) (gratuita)

### 1. Clonar e instalar

```bash
git clone <repo-url>
cd legaldev
pip install -r requirements.txt
```

### 2. Configurar variables de entorno

```bash
cp .env.example .env
# Edita .env y añade tu GROQ_API_KEY
```

### 3. Añadir los PDFs a docs/

Copia los 16 documentos legales en la carpeta `docs/`:

```
RGPD.pdf
EU AI Act.pdf
Directiva NIS2.pdf
Directiva de Responsabilidad por Productos con IA.pdf
LOPDGDD.pdf
ENS.pdf
LSSI.pdf
Ley de Propiedad Intelectual.pdf
Guía para el cumplimiento del deber de informar - AEPD.pdf
Guía de Análisis de Riesgos para tratamientos de datos personales - AEPD.pdf
Guía de Privacidad desde el Diseño - AEPD.pdf
Guía sobre uso de cookies - AEPD.pdf
Guía de Anonimización - AEPD.pdf
Adecuación al RGPD de tratamientos que incorporan IA - AEPD.pdf
IA Agentica desde la perspectiva de proteccion de datos - AEPD.pdf
Código Ético y Deontológico CCII.pdf
```

### 4. Indexar los documentos

```bash
python app/ingest.py
```

Genera `chroma_db/` con el vector store. Solo es necesario ejecutarlo una vez (o cuando cambien los documentos).

---

## Arrancar el servidor

### Desarrollo (uvicorn)

```bash
uvicorn app.main:app --reload
```

API disponible en http://localhost:8000. Documentación interactiva en http://localhost:8000/docs.

### Docker Compose

```bash
# Genera chroma_db/ primero, luego:
docker-compose up --build
```

---

## Uso de la API

### POST /analyze

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "tipo_proyecto": "app_web",
    "descripcion_breve": "Plataforma SaaS para gestión de contratos entre empresas",
    "tiene_usuarios_registrados": true,
    "acceso_publico": false,
    "tipos_datos_personales": ["nombre", "email", "financieros"],
    "usuarios_menores": false,
    "usuarios_ue": true,
    "transferencia_datos_terceros": true,
    "usa_ia": true,
    "tipo_ia": "generativa",
    "usa_cookies": true,
    "monetizacion": "suscripcion",
    "contenido_digital": false,
    "ccaa": "Madrid",
    "es_empresa": true,
    "colegiado": null
  }'
```

Respuesta:

```json
{
  "respuesta_completa": "## RGPD\n\nDado que tu plataforma trata datos financieros...",
  "normativas_detectadas": ["RGPD", "LOPDGDD", "EU AI Act"],
  "chunks_utilizados": 8,
  "disclaimer": "⚠️ Esta información es orientativa y no constituye asesoramiento legal..."
}
```

### GET /health

```bash
curl http://localhost:8000/health
# {"status": "ok", "docs_indexed": 3842}
```

---

## Deploy en Railway

1. Genera `chroma_db/` localmente: `python app/ingest.py`
2. El vector store se embebe en la imagen Docker al hacer build
3. Conecta el repo en [Railway](https://railway.app)
4. Añade la variable de entorno `GROQ_API_KEY` en el panel de Railway
5. Railway detecta el `Dockerfile` automáticamente y despliega

---

## Tests

```bash
pytest -v
```

---

## Normativas indexadas

| Documento | Tipo |
|-----------|------|
| RGPD | Normativa europea |
| EU AI Act | Normativa europea |
| Directiva NIS2 | Normativa europea |
| Directiva de Responsabilidad por Productos con IA | Normativa europea |
| LOPDGDD | Normativa española |
| ENS | Normativa española |
| LSSI | Normativa española |
| Ley de Propiedad Intelectual | Normativa española |
| Guías AEPD (×7) | Guías oficiales AEPD |
| Código Ético y Deontológico CCII | Deontología |

---

## Aviso legal

LegalDev es una herramienta de orientación informativa. La información proporcionada no constituye asesoramiento legal y no debe utilizarse como sustituto de la consulta con un abogado especializado en derecho digital o tecnológico.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with setup, usage, curl examples, and legal disclaimer"
```

---

## Final Verification

- [ ] **Run full test suite**

```bash
pytest -v
```

Expected: all tests pass across test_models, test_rag, test_api, test_ingest.

- [ ] **Optional: smoke test with real credentials**

If you have a real `GROQ_API_KEY` and PDFs in `docs/`:

```bash
python app/ingest.py
uvicorn app.main:app
curl http://localhost:8000/health
```

Expected health response: `{"status": "ok", "docs_indexed": <N>}` where N > 0.
