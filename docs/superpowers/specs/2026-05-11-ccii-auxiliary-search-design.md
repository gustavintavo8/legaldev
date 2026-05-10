# CCII Auxiliary Search — Design Spec
Date: 2026-05-11

## Problema

Con `colegiado=True`, el Código Ético CCII es fonéticamente alcanzable pero semánticamente enterrado. La query principal genera 100 candidatos (`overfetch_k=100`), de los cuales los chunks de LOPDGDD y RGPD — más densos léxicamente — ocupan las primeras 12 posiciones (`top_k_chunks=12`). Los chunks del CCII, aunque puntúan ~0.49 en la query principal enriquecida, quedan fuera del corte. Mismo patrón que cookies/AEPD-cookies.

**Validación previa:** 3 variantes de query auxiliar testeadas contra el índice local:

| Query | Top CCII score | Chunks ≥ 0.35 en top 20 |
|-------|---------------|------------------------|
| `"código deontológico ingeniero informático colegiado responsabilidad profesional"` | **0.7656** | 16 |
| `"código ético deontológico CCII"` | 0.5954 | ~5 |
| Query A + `"ingeniería del software"` | 0.7163 | 15 |

Query A validada como óptima.

## Alcance

Tres archivos modificados/creados:
- Modificar: `app/config.py`
- Modificar: `app/rag.py`
- Modificar: `tests/test_rag.py`
- Modificar: `.env.example`
- Crear: `tools/eval_retrieval.py`

Sin cambios en `app/models.py`, `app/main.py` ni `app/ingest.py`.

---

## Cambios

### 1. `app/config.py` — nuevo setting

Añadir junto a `cookies_k`:

```python
cookies_k: int = 6
colegiado_k: int = 6
```

### 2. `.env.example` — documentar el setting

Añadir junto a `COOKIES_K`:

```env
COOKIES_K=6
COLEGIADO_K=6
```

### 3. `app/rag.py` — búsqueda auxiliar CCII

Actualmente `seen` se inicializa **dentro** del `if input.usa_cookies:`, lo que causaría `NameError` en el bloque CCII si `usa_cookies=False`. La solución: sacar `seen` fuera de ambos bloques, antes de los dos `if`.

**Estructura resultante del área auxiliar:**

```python
# Inicializar seen una sola vez, antes de todos los auxiliares
seen = {hashlib.md5(d.page_content.encode()).hexdigest() for d in docs}

if input.usa_cookies:
    cookies_candidates = state.vectorstore.similarity_search_with_relevance_scores(
        "cookies consentimiento banner rastreo política privacidad",
        k=settings.cookies_k,
    )
    for doc, score in cookies_candidates:
        if score >= settings.min_relevance_score:
            h = hashlib.md5(doc.page_content.encode()).hexdigest()
            if h not in seen:
                seen.add(h)
                docs.append(doc)

if input.colegiado:
    # Auxiliary search — P1.5: move to AUXILIARY_SEARCHES
    ccii_candidates = state.vectorstore.similarity_search_with_relevance_scores(
        "código deontológico ingeniero informático colegiado responsabilidad profesional",
        k=settings.colegiado_k,
    )
    for doc, score in ccii_candidates:
        if score >= settings.min_relevance_score:
            h = hashlib.md5(doc.page_content.encode()).hexdigest()
            if h not in seen:
                seen.add(h)
                docs.append(doc)
```

Este cambio mueve la línea `seen = {...}` del interior del bloque cookies al exterior. El comportamiento de cookies no cambia.

**Invariante:** el bloque CCII solo se ejecuta cuando `colegiado` es `True`. `None` y `False` no lo activan (el modelo tiene `colegiado: bool | None = None`).

### 4. `tests/test_rag.py` — dos tests nuevos

**Test 1:** auxiliar se invoca cuando `colegiado=True`

Con `usa_cookies=False` (default de `_make_input`), solo hay 2 llamadas: main + CCII.

```python
def test_run_pipeline_colegiado_triggers_auxiliary_search():
    docs = [_make_mock_doc("RGPD.pdf")]
    state = MagicMock()
    state.vectorstore.similarity_search_with_relevance_scores.side_effect = [
        [(docs[0], 0.85)],  # main search
        [],                  # ccii auxiliary
    ]
    state.groq_client.invoke.return_value = MagicMock(content="ok")

    run_pipeline(_make_input(colegiado=True), state)

    assert state.vectorstore.similarity_search_with_relevance_scores.call_count == 2
```

**Test 2:** auxiliar NO se invoca cuando `colegiado=None`

```python
def test_run_pipeline_colegiado_none_no_auxiliary_search():
    docs = [_make_mock_doc("RGPD.pdf")]
    state = _make_state(docs)

    run_pipeline(_make_input(colegiado=None), state)

    assert state.vectorstore.similarity_search_with_relevance_scores.call_count == 1
```

Ambos tests usan `_make_input()` y `_make_mock_doc()` ya existentes en `test_rag.py`.

### 5. `tools/eval_retrieval.py` — script de evaluación parametrizado

Script standalone (no importado por la app) para verificar que una normativa esperada aparece en el retrieval dado un cuestionario. Diseñado para ser el embrión de P1.4: acepta cuestionario y normativa esperada como parámetros, no hardcodeado al CCII.

**Interfaz:**

```python
# Uso:
# python tools/eval_retrieval.py
# Devuelve tabla de resultados por cuestionario de prueba

# Cada caso de prueba: (descripción, overrides de _make_input(), normativa_esperada_en_source)
```

**Estructura:**

```python
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("GROQ_API_KEY", "eval-no-llm")

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from app.config import settings
from app.rag import _build_query
from app.models import QuestionnaireInput

BASE_INPUT = dict(
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

CASES = [
    ("covered-RGPD",    {"tipos_datos_personales": ["nombre", "email", "salud"]}, "RGPD"),
    ("covered-cookies", {"usa_cookies": True},                                    "Guía sobre uso de cookies - AEPD"),
    ("covered-CCII",    {"colegiado": True, "es_empresa": False},                 "Código Ético y Deontológico CCII"),
    ("border-minimal",  {"tipos_datos_personales": ["ninguno"]},                  None),
    ("off-topic-recetas", {"descripcion_breve": "App de recetas de cocina sin usuarios registrados", "tipos_datos_personales": ["ninguno"], "tiene_usuarios_registrados": False}, None),
]

def run_case(label, overrides, expected_source, vs, threshold):
    inp = QuestionnaireInput(**{**BASE_INPUT, **overrides})
    query = _build_query(inp)
    results = vs.similarity_search_with_relevance_scores(query, k=settings.overfetch_k)
    passed = [doc for doc, score in results if score >= threshold]

    found = any(expected_source in doc.metadata.get("source", "") for doc in passed) if expected_source else True
    top_sources = [(doc.metadata.get("source", "?")[:40], round(score, 4)) for doc, score in results[:5]]

    return {
        "label": label,
        "expected": expected_source or "N/A",
        "found": found,
        "chunks_passed": len(passed),
        "top_score": round(results[0][1], 4) if results else None,
        "top5": top_sources,
    }
```

El script carga embeddings y ChromaDB una vez, itera `CASES`, imprime tabla de resultados.

---

## Calibración (parte del plan de implementación)

Tras implementar el auxiliar CCII, ejecutar `tools/eval_retrieval.py` y producir la tabla antes/después comparando el caso `covered-CCII` con y sin el bloque auxiliar. La tabla va en las notas del ROADMAP de P0.3.

---

## Compatibilidad con P1.5

El bloque CCII en `rag.py` incluye el comentario `# P1.5: move to AUXILIARY_SEARCHES`. Cuando llegue P1.5, este bloque y el de cookies se consolidan en una lista de tuplas `(condition, query, k)` con un loop genérico. El diseño actual es intencionalmente idéntico al de cookies para que la migración sea mecánica.

---

## Lo que no cambia

- `app/models.py`: `colegiado: bool | None = None` ya existe.
- `app/main.py`: ningún cambio.
- `app/ingest.py`: ningún cambio — el CCII ya está indexado.
- `tests/conftest.py`: los fixtures existentes mantienen `colegiado=None`.
