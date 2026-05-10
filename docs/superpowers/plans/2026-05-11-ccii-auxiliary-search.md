# CCII Auxiliary Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir búsqueda auxiliar para el Código Ético CCII (análoga a cookies) para que el documento sea alcanzable en el retrieval cuando `colegiado=True`.

**Architecture:** Espejo exacto del bloque cookies en `run_pipeline()`: query auxiliar dirigida, mismo threshold (0.35), dedup por content hash. El set `seen` se mueve fuera del bloque cookies para ser compartido. Nueva setting `colegiado_k=6`. Script `tools/eval_retrieval.py` parametrizado para calibración y base de P1.4.

**Tech Stack:** Python, pydantic-settings, LangChain + ChromaDB (solo para eval script), pytest.

---

## Archivos

| Archivo | Acción | Qué cambia |
|---------|--------|-----------|
| `app/config.py` | Modificar | Añadir `colegiado_k: int = 6` junto a `cookies_k` |
| `.env.example` | Modificar | Documentar `COLEGIADO_K=6` |
| `app/rag.py` | Modificar | Mover `seen` fuera del bloque cookies; añadir bloque CCII |
| `tests/test_rag.py` | Modificar | Dos tests nuevos para comportamiento auxiliar CCII |
| `tools/eval_retrieval.py` | Crear | Script de evaluación de retrieval parametrizado |

---

### Task 1: Añadir `colegiado_k` a Settings

**Files:**
- Modify: `app/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Añadir el campo a `app/config.py`**

  El archivo actual tiene:
  ```python
  cookies_k: int = 6
  overfetch_k: int = 100
  ```

  Reemplazar por:
  ```python
  cookies_k: int = 6
  colegiado_k: int = 6
  overfetch_k: int = 100
  ```

- [ ] **Step 2: Documentar en `.env.example`**

  El archivo actual tiene (entre otras líneas):
  ```env
  COOKIES_K=6
  OVERFETCH_K=100
  ```

  Añadir entre esas dos líneas:
  ```env
  COOKIES_K=6
  COLEGIADO_K=6
  OVERFETCH_K=100
  ```

- [ ] **Step 3: Verificar que el setting carga**

  ```bash
  python -c "from app.config import settings; print(settings.colegiado_k)"
  ```

  Expected output: `6`

- [ ] **Step 4: Commit**

  ```bash
  git add app/config.py .env.example
  git commit -m "feat: add colegiado_k setting (default 6)"
  ```

---

### Task 2: Tests para el bloque auxiliar CCII (TDD — escribir antes de implementar)

**Files:**
- Modify: `tests/test_rag.py`

- [ ] **Step 1: Añadir los dos tests al final de `tests/test_rag.py`**

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


  def test_run_pipeline_colegiado_none_no_auxiliary_search():
      docs = [_make_mock_doc("RGPD.pdf")]
      state = _make_state(docs)

      run_pipeline(_make_input(colegiado=None), state)

      assert state.vectorstore.similarity_search_with_relevance_scores.call_count == 1
  ```

  Nota: `_make_input` y `_make_mock_doc` ya existen en `tests/test_rag.py`. `_make_input(colegiado=True)` tiene `usa_cookies=False` por defecto, por lo que solo se esperan 2 llamadas (main + CCII), no 3.

- [ ] **Step 2: Ejecutar para verificar que fallan**

  ```bash
  python -m pytest tests/test_rag.py::test_run_pipeline_colegiado_triggers_auxiliary_search tests/test_rag.py::test_run_pipeline_colegiado_none_no_auxiliary_search -v
  ```

  Expected: ambos `FAILED`. El primero falla porque `call_count == 1` (el auxiliar aún no existe). El segundo puede pasar ya (call_count ya es 1 con `colegiado=None`), lo cual es correcto.

- [ ] **Step 3: Commit de los tests en rojo**

  ```bash
  git add tests/test_rag.py
  git commit -m "test: add failing tests for CCII auxiliary search"
  ```

---

### Task 3: Implementar el bloque auxiliar CCII en `rag.py`

**Files:**
- Modify: `app/rag.py` (aproximadamente líneas 152-163 del archivo original)

- [ ] **Step 1: Localizar el bloque cookies actual**

  Buscar en `app/rag.py` el bloque:

  ```python
  if input.usa_cookies:
      cookies_candidates = state.vectorstore.similarity_search_with_relevance_scores(
          "cookies consentimiento banner rastreo política privacidad",
          k=settings.cookies_k,
      )
      seen = {hashlib.md5(d.page_content.encode()).hexdigest() for d in docs}
      for doc, score in cookies_candidates:
          if score >= settings.min_relevance_score:
              h = hashlib.md5(doc.page_content.encode()).hexdigest()
              if h not in seen:
                  seen.add(h)
                  docs.append(doc)
  ```

- [ ] **Step 2: Reemplazar por la versión con `seen` extraído y bloque CCII añadido**

  ```python
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

  El único cambio en el bloque cookies es eliminar la línea `seen = {...}` de su interior (ahora está antes). El bloque cookies es funcionalmente idéntico.

- [ ] **Step 3: Ejecutar los dos tests nuevos — deben pasar**

  ```bash
  python -m pytest tests/test_rag.py::test_run_pipeline_colegiado_triggers_auxiliary_search tests/test_rag.py::test_run_pipeline_colegiado_none_no_auxiliary_search -v
  ```

  Expected: ambos `PASSED`.

- [ ] **Step 4: Ejecutar la suite completa — sin regresiones**

  ```bash
  python -m pytest -v
  ```

  Expected: todos los tests que pasaban antes siguen pasando. En particular, `test_run_pipeline_calls_relevance_search_with_correct_k` sigue pasando porque usa `_make_input()` (colegiado=None, usa_cookies=False) → sigue siendo 1 llamada.

- [ ] **Step 5: Commit**

  ```bash
  git add app/rag.py
  git commit -m "feat: add CCII auxiliary search when colegiado=True"
  ```

---

### Task 4: Crear `tools/eval_retrieval.py`

**Files:**
- Create: `tools/eval_retrieval.py`

- [ ] **Step 1: Crear el directorio `tools/` si no existe**

  ```bash
  mkdir -p tools
  ```

- [ ] **Step 2: Crear `tools/eval_retrieval.py` con el contenido completo**

  ```python
  """
  Retrieval evaluation script — embrión de P1.4.

  Ejecutar: python tools/eval_retrieval.py
  Requiere: ChromaDB generado (make ingest) y GROQ_API_KEY en .env (o env var).
  Solo hace retrieval — no llama al LLM.
  """
  import os
  import sys

  sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
  os.environ.setdefault("GROQ_API_KEY", "eval-no-llm")

  from langchain_huggingface import HuggingFaceEmbeddings
  from langchain_chroma import Chroma

  from app.config import settings
  from app.models import QuestionnaireInput
  from app.rag import _build_query

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

  # Cada caso: (label, overrides_sobre_BASE_INPUT, normativa_esperada_en_source | None)
  # normativa_esperada=None significa "esperamos que NO haya cobertura (off-topic)"
  CASES = [
      (
          "covered-RGPD",
          {"tipos_datos_personales": ["nombre", "email", "salud"]},
          "RGPD",
      ),
      (
          "covered-cookies",
          {"usa_cookies": True},
          "Guía sobre uso de cookies - AEPD",
      ),
      (
          "covered-CCII",
          {"colegiado": True, "es_empresa": False},
          "Código Ético y Deontológico CCII",
      ),
      (
          "border-minimal",
          {"tipos_datos_personales": ["ninguno"]},
          None,
      ),
      (
          "off-topic-recetas",
          {
              "descripcion_breve": "App de recetas de cocina sin usuarios registrados",
              "tipos_datos_personales": ["ninguno"],
              "tiene_usuarios_registrados": False,
          },
          None,
      ),
  ]


  def run_case(label, overrides, expected_source, vs, threshold):
      inp = QuestionnaireInput(**{**BASE_INPUT, **overrides})
      query = _build_query(inp)
      results = vs.similarity_search_with_relevance_scores(query, k=settings.overfetch_k)
      passed = [doc for doc, score in results if score >= threshold]
      found = (
          any(expected_source in doc.metadata.get("source", "") for doc in passed)
          if expected_source
          else True
      )
      top5 = [
          (doc.metadata.get("source", "?")[:45], round(score, 4))
          for doc, score in results[:5]
      ]
      return {
          "label": label,
          "expected": expected_source or "N/A (off-topic)",
          "found": found,
          "chunks_passed": len(passed),
          "top_score": round(results[0][1], 4) if results else None,
          "top5": top5,
      }


  def main():
      print("Cargando embeddings y ChromaDB...")
      embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
      vs = Chroma(
          persist_directory=settings.chroma_db_path,
          embedding_function=embeddings,
          collection_name="legaldev",
      )
      threshold = settings.min_relevance_score

      print(f"\nRetrieval eval — threshold={threshold}, overfetch_k={settings.overfetch_k}\n")
      print(f"{'Caso':<20} {'Esperado':<45} {'OK':>4} {'Chunks':>6} {'TopScore':>9}")
      print("-" * 90)

      all_passed = True
      for label, overrides, expected_source in CASES:
          r = run_case(label, overrides, expected_source, vs, threshold)
          ok = "YES" if r["found"] else "NO "
          if not r["found"]:
              all_passed = False
          print(
              f"{r['label']:<20} {r['expected']:<45} {ok:>4} "
              f"{r['chunks_passed']:>6} {str(r['top_score']):>9}"
          )
          for src, score in r["top5"]:
              print(f"    {score:.4f}  {src}")

      print()
      if all_passed:
          print("✓ Todos los casos pasaron.")
      else:
          print("✗ Algún caso falló — revisar retrieval.")
          sys.exit(1)


  if __name__ == "__main__":
      main()
  ```

- [ ] **Step 3: Ejecutar el script**

  ```bash
  python tools/eval_retrieval.py
  ```

  Expected output (columna OK):
  - `covered-RGPD` → YES
  - `covered-cookies` → YES  
  - `covered-CCII` → YES (este es el que antes fallaba — confirma que el auxiliar funciona)
  - `border-minimal` → YES (puede que sí haya cobertura con datos personales mínimos)
  - `off-topic-recetas` → YES (off-topic devuelve True por convención cuando expected=None)

  Si `covered-CCII` devuelve NO, el auxiliar no está funcionando. Verificar que el bloque en `rag.py` usa `settings.colegiado_k` y que la query no tiene typo.

  **Nota:** este script evalúa la query principal (`_build_query`), no el auxiliar directamente. El caso `covered-CCII` con `colegiado=True` incluye términos del CCII en la query principal, por lo que el CCII debería aparecer en el overfetch aunque no pase el top_k. Lo que valida el smoke test de Task 5 es que el auxiliar los empuja al contexto del LLM.

- [ ] **Step 4: Commit**

  ```bash
  git add tools/eval_retrieval.py
  git commit -m "feat: add parametrized retrieval eval script (P1.4 base)"
  ```

---

### Task 5: Calibración — tabla antes/después y verificación end-to-end

**Files:**
- Ninguno (verificación + actualización del ROADMAP)

- [ ] **Step 1: Verificar end-to-end con la API de producción**

  Ejecutar en terminal (requiere que el servidor esté desplegado en Railway):

  ```bash
  curl -s -X POST https://legaldev-production.up.railway.app/v1/analyze \
    -H "Content-Type: application/json" \
    -d '{
      "tipo_proyecto": "app_web",
      "descripcion_breve": "Plataforma de gestion de proyectos para ingenieros informaticos colegiados",
      "tiene_usuarios_registrados": true,
      "acceso_publico": false,
      "tipos_datos_personales": ["nombre", "email"],
      "usuarios_menores": false,
      "usuarios_ue": true,
      "transferencia_datos_terceros": false,
      "usa_ia": false,
      "tipo_ia": null,
      "usa_cookies": false,
      "monetizacion": null,
      "contenido_digital": false,
      "ccaa": "Madrid",
      "es_empresa": false,
      "colegiado": true
    }' | python -m json.tool --no-ensure-ascii | grep -E "(normativas_detectadas|Código Ético|chunks_utilizados)"
  ```

  Expected: `"normativas_detectadas"` incluye `"Código Ético y Deontológico CCII"` (o el stem sin `.pdf`). Si la API es la versión local, usar `http://localhost:8000`.

  **Nota:** la API en Railway tiene el código antiguo hasta que hagas push. Para verificar localmente primero: `make dev` y sustituir la URL por `http://localhost:8000/v1/analyze`.

- [ ] **Step 2: Registrar tabla antes/después en el ROADMAP**

  En `docs/superpowers/plans/ROADMAP.md`, bajo P0.3, añadir en la sección Notas:

  ```
  Tabla antes/después (query principal, covered-CCII, overfetch_k=100):
  | Métrica | Antes | Después |
  |---------|-------|---------|
  | CCII en normativas_detectadas (API) | NO | SÍ |
  | Top CCII score (query auxiliar validada) | — | 0.7656 |
  | Chunks utilizados (ejemplo) | ~12 (sin CCII) | ~13-18 (con CCII) |

  Query auxiliar validada: "código deontológico ingeniero informático colegiado responsabilidad profesional"
  Threshold: 0.35 — consistente con cookies y main query.
  ```

- [ ] **Step 3: Marcar P0.3 como completado en el ROADMAP**

  En `docs/superpowers/plans/ROADMAP.md`, cambiar las líneas de P0.3:

  ```markdown
  - [x] **Bloqueado por P0.1** — no implementar antes
  - [x] Añadir `colegiado_k` a `Settings` (default 6, igual que cookies)
  - [x] Implementar búsqueda auxiliar con query: `"código deontológico ingeniero informático colegiado responsabilidad profesional"`
  - [x] Threshold 0.35 (consistente con el resto)
  - [x] Calibrar con los 5 cuestionarios anteriores + uno nuevo con `colegiado=true`
  - [x] Tabla antes/después de posiciones de CCII en el ranking
  ```

- [ ] **Step 4: Commit**

  ```bash
  git add docs/superpowers/plans/ROADMAP.md
  git commit -m "docs: update ROADMAP — P0.3 complete, add calibration table"
  ```
