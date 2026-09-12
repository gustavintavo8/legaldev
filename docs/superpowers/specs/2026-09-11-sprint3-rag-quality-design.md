# Sprint 3 — Producción caída y calidad del RAG: diseño

> Documento de diseño del sprint 3 de LegalDev. Fecha: 2026-09-11. Estado del repo al empezar: `main@c3ca811` (v0.4.0), 186 tests verdes, eval de retrieval 13/13 con 0 falsos positivos.
>
> Este documento argumenta **qué** se cambia y **por qué**, con las mediciones que lo justifican. El plan de implementación paso a paso está en `docs/superpowers/plans/2026-09-11-sprint3-rag-quality.md`.

---

## 1. Contexto

LegalDev es una API RAG (FastAPI + ChromaDB + reranker CrossEncoder + Groq) que recibe un cuestionario de 16 campos sobre un proyecto software y devuelve un informe legal estructurado con citas textuales de 22 normativas indexadas (13.873 chunks).

Pipeline actual (`app/rag.py`):

```
_build_query(cuestionario)
  → similarity_search(k=100) · filtro score ≥ 0.40
  → AUXILIARY_SEARCHES condicionales (rgpd, cookies, colegiado) · dedupe por hash
  → pre_rerank = top-25 principal + auxiliares
  → CrossEncoder bge-reranker-base → top-12
  → EXCLUSIONS (ENS, LPI, guías IA, LOPDGDD) — se aplican DESPUÉS del recorte
  → INJECTIONS (RGPD, EU AI Act, LSSI, IA Agéntica, CCII) — búsqueda filtrada por fuente, sin umbral
  → LLM (Groq, temperature 0) → RAGResponse + sección "Cobertura del análisis"
```

Toda la lógica de retrieval existe **dos veces**: en `run_pipeline` (async, con timeouts por búsqueda) y en `retrieve_docs_sync` (sync, usada por el eval). Un test de sincronía vigila que no diverjan.

---

## 2. Diagnóstico medido

Todas las cifras de esta sección se han medido el 2026-09-11 sobre el `chroma_db/` real del repo (13.873 chunks, modelo `paraphrase-multilingual-MiniLM-L12-v2`), con los scripts de exploración de la sesión. Donde el hallazgo cambia una decisión, se indica.

### H1 · Producción está caída desde julio (P0)

`GET https://gustavintavo8-legaldev.hf.space/health/deep` devuelve:

```json
{"chroma":"ok","groq":"error: NotFoundError","corpus_version":"858b81eb27fe"}
```

El modelo configurado por defecto, `meta-llama/llama-4-scout-17b-16e-instruct`, fue **retirado por Groq el 17/07/2026** (página oficial de deprecations). Groq recomienda como sustituto `openai/gpt-oss-120b` (producción, 131k de contexto, 65k tokens de salida) o `qwen/qwen3.6-27b` (preview). También están retirados `llama-4-maverick` (09/03/2026) y, desde el 16/08/2026, `llama-3.3-70b-versatile` y `llama-3.1-8b-instant`.

Consecuencia: **cada `POST /v1/analyze` en producción devuelve 503 desde hace casi dos meses**, y nada lo hace visible salvo `/health/deep`.

Causa raíz de fondo: el sistema no tiene (a) comprobación de que el modelo existe al arrancar, (b) modelo de respaldo, (c) visibilidad del modelo en uso en la respuesta o en la salud profunda.

### H2 · Duplicación del retrieval

`run_pipeline` (~85 líneas de retrieval) y `retrieve_docs_sync` (~65 líneas) implementan la misma secuencia. Hay tres comentarios `keep in sync` y un test (`test_retrieve_docs_sync_and_run_pipeline_produce_same_stems`) que solo detecta divergencias en un escenario concreto. Es deuda que encarece cualquier cambio en el retrieval (como los de este sprint).

### H3 · Las exclusiones se aplican después del recorte y desperdician plazas

El reranker devuelve top-12 y **después** se eliminan las normativas excluidas. Medido con el CrossEncoder real sobre los 13 casos del eval (posición en el top-12 de chunks que luego se excluyen):

| Caso | Chunks del top-12 excluidos a posteriori | Contexto final del reranker |
|---|---|---|
| datos-sensibles-salud | 2 (Adecuación RGPD+IA #1, ENS #2) | 10 |
| ia-agente | 1 (ENS #7) | 11 |
| ccii-ingeniero-colegiado | 1 (ENS #12) | 11 |
| query-compleja-rgpd-colegiado-ia | 3 (IA Agéntica #1, ENS #4, ENS #9) | 9 |
| sin-datos-personales | 3 (LPI #5, ENS #7, ENS #8) | 9 |
| off-topic-recetas | 1 (LPI #7) | — |

Las normativas que sabemos que no aplican ocupan plazas del reranker y del top-12 que deberían ir a normativas aplicables. Además, rerankear chunks que se van a descartar es CPU tirada (el reranker es el cuello de botella, ver H6).

### H4 · Baja diversidad del contexto

El top-12 del reranker está dominado por una o dos guías AEPD. Ejemplos medidos:

| Caso | Composición del top-12 |
|---|---|
| menores-datos-personales | Privacidad desde el Diseño ×6, LOPDGDD ×5, Análisis de Riesgos ×1 |
| ia-generativa | Privacidad desde el Diseño ×6, LOPDGDD ×5, Análisis de Riesgos ×1 (EU AI Act: 0 → llega solo por INJECTION) |
| cookies-webapp | Deber de informar ×2, Privacidad ×3, LOPDGDD ×3, Riesgos ×2, Adecuación ×1, Cookies ×1 |

El criterio del prompt exige ≥ 2 chunks por normativa para abrir sección; seis chunks de la misma guía no aportan más secciones, solo más texto redundante, y desplazan normativas con 1 chunk (que quedan fuera del informe).

### H5 · La guardia anti-alucinación por umbral está casi muerta, y el reranker no la sustituye

Con el modelo multilingüe, la puntuación de relevancia (`1 - d/√2` sobre L2 de vectores normalizados) vive en un rango muy comprimido:

| Caso | Scores top-3 / #100 | Candidatos que pasan 0.40 |
|---|---|---|
| rgpd-lopdgdd-basico | 0.562 · 0.554 · 0.550 / 0.428 | 100 / 100 |
| query-compleja | 0.714 · 0.694 · 0.688 / 0.600 | 100 / 100 |
| sin-datos-personales (off-topic) | 0.510 · 0.501 · 0.495 / 0.357 | 49 / 100 |
| off-topic-recetas | 0.471 · 0.471 · 0.469 / 0.330 | 17 / 100 |
| plantas (dominio lejano) | 0.443 · 0.423 · 0.416 / 0.299 | 4 / 100 |

El umbral solo recorta en dominios lejanos; en cualquier proyecto con vocabulario legal pasan los 100. El 404 "sin cobertura" solo sería alcanzable si además no se activa ninguna INJECTION.

Se evaluó sustituirlo por una guardia sobre la probabilidad del CrossEncoder. **Descartado con datos**: el reranker tampoco discrimina. Para `off-topic-recetas` (app de recetas sin usuarios ni datos) la guía "Privacidad desde el Diseño" puntúa 0.37 y "Deber de informar" 0.20, mientras que en `ccii-ingeniero-colegiado` los chunks del Código CCII —que son los esperados— puntúan 0.05–0.07. Un umbral que eliminase el ruido off-topic eliminaría también normativas correctas. La ordenación del reranker está dominada por el género textual (guías explicativas > texto legal), no por aplicabilidad.

Decisión: no se implementa guardia nueva; se documenta la limitación. La aplicabilidad sigue siendo cuestión de reglas (EXCLUSIONS/INJECTIONS), no de similitud.

### H6 · Latencia del reranker

35 pares (query de ~740 chars + chunks de ~460 chars, mediana 253 tokens, máximo 393):

| Configuración | Tiempo |
|---|---|
| fp32, 6 hilos (portátil de desarrollo) | 8,3 s |
| fp32, 2 hilos (≈ CPU del tier gratuito de HF Spaces) | 20,5 s |
| Carga del modelo desde disco | 2,1 s |

El modelo se carga **de forma perezosa en la primera petición** (`get_encoder()`), que paga la carga además del rerank. La truncación por longitud no ayuda (los pares ya caben en 512). La cuantización dinámica int8 se midió y se descartó: acelera 1,6× con 2 hilos pero cambia el ranking (detalle en 4.5).

### H7 · Nadie verifica las citas

El `SYSTEM_PROMPT` exige citas textuales entre comillas con normativa y página, y el README lo presenta como el mecanismo de grounding principal. Pero **ninguna parte del sistema comprueba que las citas existan en los fragmentos recuperados**. Un LLM a temperatura 0 puede parafrasear o inventar dentro de las comillas y el usuario no tiene forma de saberlo.

### H8 · El índice tiene ruido y carece de metadatos de construcción

- 13.873 chunks; longitud mediana 455 chars, p95 497, máximo 1.500 (el README dice "500 chars", el splitter legal permite artículos de hasta 1.500).
- **112 chunks con menos de 80 caracteres** (mínimo: 2 caracteres). Son cabeceras/pies de página ("ES", números) cuyo embedding es ruido puro.
- Solo 791 chunks (5,7 %) empiezan en `Artículo`/`Considerando`. Es lo esperable (los reglamentos tienen ~100 artículos y ~170 considerandos numerados como "(n)"), pero los sub-chunks de artículos largos **pierden el encabezado**: el segundo fragmento del artículo 5 del RGPD no sabe que es del artículo 5, ni lo sabe el LLM al citar.
- El índice no registra con qué modelo de embeddings se construyó. El README avisa manualmente de que cambiar `EMBEDDING_MODEL` sin reindexar rompe los scores en silencio; el código no lo impide.
- `ingest.py` borra el índice existente **antes** de generar el nuevo: si la ingesta falla a mitad, no queda índice.

Los PDFs fuente no están en este entorno; las mejoras de ingesta se implementan y testean con PDFs sintéticos, y **surten efecto en el siguiente `make ingest`** (runbook en la sección 7).

### H9 · El evaluador acepta un modelo distinto al del índice

`tools/eval_retrieval.py --model X` embebe las queries con X pero busca en un índice construido con otro modelo. Los vectores no son comparables y el resultado es basura silenciosa. Además `tools/eval_results.md` está marcado como obsoleto por el propio archivo.

### H10 · `/v1/feedback` sin límites

`FeedbackInput.comment` no tiene `max_length`, `request_id` acepta cualquier cadena, y el endpoint no tiene rate limit. Es escritura ilimitada en disco abierta a cualquiera.

### H11 · Dependencias de runtime innecesarias

`langchain` (metapaquete) no se importa en ningún sitio. `langchain-community` solo se usa para `PyPDFLoader` en la ingesta, y `pypdf` ya es dependencia directa. Ambas entran en la imagen Docker.

### H12 · Documentación desincronizada

Badge de "69 tests" (hay 186), `.env.example` con `MMR_FETCH_K` (no existe), `TOP_K_CHUNKS=8` (el default es 12) y `MIN_RELEVANCE_SCORE`/`CHROMA_TIMEOUT` que cambian en este sprint; README describe el modelo retirado; `tools/eval_results.md` obsoleto.

### Spike descartado · Retrieval híbrido BM25 + denso (RRF)

Se midió BM25 (rank-bm25, tokenización sin acentos) sobre los 13.873 chunks y fusión RRF (k=60) con el retrieval denso, mirando la posición del primer chunk de cada normativa esperada:

| Caso · normativa | Denso | BM25 | RRF |
|---|---|---|---|
| rgpd-basico · RGPD | #44 | #10 | #29 |
| salud · RGPD | #35 | #10 | #30 |
| menores · RGPD | #47 | #14 | #34 |
| ccii · Código CCII | #76 | #5 | #16 |
| cookies · Guía cookies | #100 | #25 | #17 |
| ia-agente · IA Agéntica | #32 | #3 | #6 |
| **ia-generativa · EU AI Act** | **#18** | **fuera del top-100** | **#39** |
| query-compleja · RGPD | #16 | #38 | #35 |
| lssi-web-publica · LSSI | #23 | #15 | #38 |

BM25 rescata lo que el denso entierra (RGPD, CCII, cookies) pero pierde por completo el EU AI Act, y la fusión empeora varias normativas que el denso ya colocaba dentro del recorte de 25. Coste: +200–270 ms por query en Python puro. Como las INJECTIONS ya garantizan las normativas críticas y el eval documental está en 13/13, **no hay métrica que pueda demostrar la mejora** sin un gold standard a nivel de chunk. Se difiere (sección 9) con estos datos.

---

## 3. Objetivos del sprint

1. **Restaurar producción** con un modelo vigente, con respaldo automático ante retirada de modelos o errores del proveedor, y con visibilidad del modelo en uso.
2. **Una sola implementación del retrieval**, compartida por API y eval, con un único timeout global.
3. **Mejor uso de las plazas del contexto**: excluir antes de rerankear y limitar chunks por fuente.
4. **Verificación determinista de citas** y exposición del resultado al cliente.
5. **Reranker listo al arrancar** (la cuantización int8 se midió y se descartó porque altera el ranking).
6. **Endurecer `/v1/feedback`.**
7. **Ingesta robusta y trazable** (metadatos del índice, filtro de ruido, encabezado de artículo en sub-chunks, construcción atómica) con guardia de arranque ante índice/modelo incompatibles.
8. **Evaluador fiel** (ruta del índice, comprobación de modelo, resultados regenerados).
9. **Menos dependencias de runtime.**
10. **Documentación al día.**

### No objetivos

- Cambiar el modelo de embeddings o el splitter sobre el corpus real (no hay PDFs en este entorno; requiere reindexar y commitear ~100 MB por LFS — decisión de producto del mantenedor).
- Retrieval híbrido (ver spike).
- Frontend (`legaldev-web` es otro repo).
- Subir versión: se documenta en `[Unreleased]` y el bump sigue el flujo de release habitual del repo.

---

## 4. Diseño por componente

### 4.1 Migración del modelo LLM, respaldo y comprobación de arranque (P0)

**Config (`app/config.py`)**

| Setting | Default nuevo | Antes |
|---|---|---|
| `groq_model` | `openai/gpt-oss-120b` | `meta-llama/llama-4-scout-17b-16e-instruct` |
| `groq_fallback_model` | `openai/gpt-oss-20b` (`""` desactiva) | — |
| `groq_reasoning_effort` | `low` (`""` no envía el parámetro) | — |
| `groq_max_tokens` | `8000` | `4000` |
| `groq_verify_model_on_startup` | `true` | — |

`groq_max_tokens` sube porque en gpt-oss los tokens de razonamiento cuentan como tokens de salida; con `low` son pocos, pero el informe puede superar 3.000 tokens y 4.000 dejaba poco margen. `reasoning_effort` solo se envía a modelos `openai/gpt-oss*` (Groq rechaza el parámetro en modelos que no lo soportan).

**Clientes (`app/main.py`)**

`_make_groq_client(model: str) -> ChatGroq` construye el cliente con los settings comunes y añade `reasoning_effort` cuando aplica. En `lifespan`: `app.state.groq_client` (principal) y `app.state.groq_fallback_client` (o `None`).

`_check_groq_model(api_key, model) -> bool | None` hace `GET https://api.groq.com/openai/v1/models/{model}` con timeout de 5 s: `200` → `True`; `404` → `False` y log **ERROR** con enlace a la página de deprecations; cualquier otra cosa (red caída, 401, 5xx) → `None` y log WARNING. **No se aborta el arranque**: un fallo de red en el boot no debe tumbar el servicio. El resultado se guarda en `app.state.groq_model_available` y se expone en `/health/deep`.

**Respaldo (`app/rag.py`)**

`_invoke_llm(state, messages) -> tuple[str, str]` devuelve `(texto, modelo_usado)`:

1. Invoca el cliente principal en un hilo.
2. Si lanza cualquier excepción y hay cliente de respaldo: log WARNING `llm_fallback` (evento, request_id, clase de error, modelo de respaldo), métrica `legaldev_llm_fallback_total{reason}`, e invoca el respaldo.
3. Si también falla (o no hay respaldo): log ERROR y `HTTPException(503)` como hoy.

Se hace fallback ante **cualquier** excepción del principal, no solo `NotFound`: Groq devuelve `400 model_decommissioned` para modelos retirados, `404` para desconocidos, `429` en límite de cuota y `5xx` en incidentes — todos casos donde el segundo modelo (con cuota independiente) puede responder. El SDK de Groq ya reintenta transitorios (`max_retries=2`) antes de que la excepción llegue aquí. El coste es que un timeout del principal puede duplicar la latencia en el peor caso; se prefiere a un 503.

`_content_to_text(content) -> str`: `response.content` puede llegar como lista de bloques en modelos con razonamiento; se concatenan los bloques de texto. Defensivo y trivial de testear.

**Respuesta**: `RAGResponse.llm_model: str` (default `"unknown"` para compatibilidad) con el modelo que generó el informe. `/health/deep` añade `groq_model`, `groq_fallback_model`, `groq_model_available_at_startup`.

**Errores**: sin cambios de contrato HTTP (503 cuando ambos fallan; 404/422/429 igual).

**Tests**: defaults de settings; `_make_groq_client` envía `reasoning_effort` solo a gpt-oss; `_check_groq_model` en 200/404/excepción; fallback usado cuando el principal falla (respuesta del segundo, métrica +1, evento en log); 503 si ambos fallan y si no hay respaldo; `llm_model` en la respuesta; `/health/deep` con los campos nuevos; `_content_to_text` con str y con lista de bloques.

Esto se entrega como **PR-A (hotfix)** independiente y pequeño para poder mergear y desplegar sin esperar al resto.

### 4.2 Unificación del retrieval y timeout global

Se elimina la duplicación: `_retrieve(inp, vs, threshold) -> RetrievalResult` es la única implementación (sync). `retrieve_docs_sync` queda como envoltorio que devuelve `RetrievalResult.docs` (misma firma que hoy: eval y tests no cambian). `run_pipeline` ejecuta `_retrieve` en un hilo con `asyncio.wait_for(timeout=settings.retrieval_timeout)`.

```python
@dataclass
class RetrievalResult:
    docs: list                  # contexto final ordenado (reranker + inyecciones)
    candidates: int             # candidatos de la búsqueda principal
    top_score: float | None     # mejor score de la búsqueda principal
    pre_rerank: int             # pares enviados al reranker
    injected_stems: list[str]   # normativas inyectadas
```

`retrieval_timeout: float = 60.0` sustituye a `chroma_timeout` (10 s por búsqueda). Motivo: el timeout por búsqueda no cubría el reranker (20+ s en producción), que es la parte lenta; un timeout global es lo que el cliente percibe. Al expirar: `HTTPException(503, "Retrieval timed out")`. Limitación conocida (igual que hoy): cancelar `to_thread` no interrumpe el hilo; el trabajo termina en segundo plano.

Se elimina `_search_with_timeout`. El test H2 de concurrencia (`/health` responde durante un análisis) sigue siendo válido porque todo el retrieval corre en hilo.

### 4.3 Asignación de plazas: exclusiones antes del reranker y tope por fuente

Nuevo orden dentro de `_retrieve`:

```
main (k=100, score ≥ umbral) → quitar excluidas → recorte reranker_top_k
aux (score ≥ umbral, dedupe)  → quitar excluidas
→ rerank de TODOS los candidatos (orden completo)
→ _select_diverse(orden, top_k_chunks, max_chunks_per_source)
→ inyecciones (sin cambios)
```

`_select_diverse(ranked, top_k, max_per_source)` recorre el orden del reranker, acepta como máximo `max_per_source` chunks de la misma fuente y, si al final quedan plazas libres, las rellena con los saltados (en su orden original). `max_chunks_per_source: int = 4` (0 desactiva). Con `top_k_chunks=12` garantiza al menos tres fuentes distintas cuando existen.

`rerank(query, docs, top_k)` conserva su firma; se llama con `top_k=len(docs)` para obtener el orden completo. Los mocks existentes (`docs[:top_k]`) siguen funcionando.

Criterio de aceptación medible: eval 13/13 con 0 FP (sin regresión) y, en el propio eval, la columna nueva **Fuentes** (nº de normativas distintas en el contexto final) no baja en ningún caso y sube en los casos de H3/H4. Ambas cifras se registran en el plan al ejecutar.

### 4.4 Verificación de citas (`app/citations.py`)

Módulo puro, sin dependencias:

- `extract_quotes(answer) -> list[str]`: en cada línea que empieza por `>`, captura el texto entre la primera comilla de apertura (`"`, `“`, `«`) y la última de cierre antes de un guion largo/corto. Si no hay guion, captura entre comillas.
- `normalize(text) -> str`: NFKC + `casefold`, elimina comillas, guiones, guiones blandos y **todo espacio en blanco**. Sin espacios, las citas coinciden aunque el PDF tenga artefactos de extracción ("tratamient o", "prot ecci ón") o saltos de línea con guion.
- `verify_citations(answer, docs) -> CitationStats`: divide cada cita por elipsis (`...`, `…`, `[...]`, `[…]`), normaliza los segmentos, ignora los de menos de 12 caracteres y exige que **todos** los segmentos restantes aparezcan en el corpus normalizado (los chunks normalizados unidos por `|`, separador que la normalización no puede producir). Una cita sin segmentos suficientemente largos cuenta como no verificada (conservador).

```python
class CitationStats(BaseModel):
    total: int
    verificadas: int
    no_verificadas: list[str]   # texto original truncado a 120 chars
```

`RAGResponse.citas: CitationStats` (default vacío). `run_pipeline` añade, después de "Cobertura del análisis", la sección:

```
## Verificación de citas
Se han verificado textualmente 7 de 8 citas contra los fragmentos recuperados.
Citas no verificadas (posible paráfrasis o interpolación; contrastar con la fuente oficial):
- "…"
```

Solo si hay al menos una cita. Métricas: histograma `legaldev_citations_verified_ratio` y contador `legaldev_citations_unverified_total`. Log: `citations_total`, `citations_verified`.

Por qué en código y no en el prompt: es determinista, gratis y verificable con tests; pedirle al LLM que se autoverifique no lo es.

### 4.5 Reranker: calentamiento en el arranque (cuantización int8 descartada con datos)

- `reranker.warmup()`: carga el modelo y ejecuta una predicción mínima. Se llama en `lifespan` tras cargar ChromaDB. La primera petición deja de pagar ~2 s de carga + compilación de kernels.
- **Cuantización dinámica int8: no se implementa.** Medida in place sobre las 74 capas `Linear` de `bge-reranker-base` (278 M parámetros), 5 queries del eval × 35 pares:

  | Hilos | fp32 s/query | int8 s/query | Aceleración | Top-12 idéntico |
  |---|---|---|---|---|
  | 6 | 6,53 | 6,50 | 1,0× | no (8/12, 8/12, 8/12, 7/12, 11/12) |
  | 2 | 17,58 | 11,06 | 1,6× | no (mismos solapes) |

  El orden del top-5 cambió en las 5 queries y la correlación entre puntuaciones fp32/int8 cayó hasta 0,23 en una de ellas (diferencia máxima de 0,83 en probabilidad). Ganar un 37 % de latencia en el tier gratuito a cambio de un ranking distinto no es aceptable para un sistema cuyo contexto lo decide ese ranking. Un flag "opcional" que degrada la calidad sería un footgun: no se añade código.

Tests: `warmup` carga el modelo y predice una vez; `lifespan` lo invoca (mockeado en las fixtures).

### 4.6 `/v1/feedback` endurecido

`FeedbackInput.request_id`: `min_length=1, max_length=64, pattern=^[A-Za-z0-9_-]+$` (el `X-Request-ID` generado es hex de 8 chars; se admite el formato UUID). `comment`: `max_length=2000`. El endpoint pasa a tener `@limiter.limit(settings.rate_limit)`. Tests: 422 en cada límite, 429 tras agotar el límite.

### 4.7 Ingesta robusta y trazable

**`app/corpus.py`**: `EMBEDDING_MODEL` pasa a definirse aquí (única fuente) y lo importan `main.py`, `ingest.py` y las herramientas.

**`app/legal_splitter.py`**: cada parte que empieza por el patrón de artículo recibe `metadata["article"] = "Artículo 5"` (el encabezado tal cual). Si la parte se subdivide por longitud, los sub-chunks a partir del segundo se prefijan con `"Artículo 5 (cont.): "`. Así cada chunk se describe a sí mismo para el embedding, el reranker y el LLM.

**`app/ingest.py`**:
- Lee PDFs con `pypdf.PdfReader` directamente (`_load_pages(pdf_path) -> list[Document]` con `source`, `page` 0-indexed y `total_pages`), eliminando `langchain-community`.
- Descarta chunks con menos de `MIN_CHUNK_CHARS = 40` caracteres tras `strip()` (el índice actual tiene 112 chunks así).
- Construye en `<CHROMA_DB_PATH>.building`, escribe `.corpus_version` y `.index_meta.json`, y solo entonces sustituye el directorio final (`_swap_dirs` con reintentos: ChromaDB en Windows puede mantener descriptores abiertos; si el rename falla tras los reintentos, deja `.building` intacto y termina con error e instrucciones). Nunca se destruye el índice viejo antes de tener uno nuevo completo.
- `.index_meta.json`: `embedding_model`, `corpus_version`, `chunks`, `documents`, `splitter_version` (2), `min_chunk_chars`, `created_at` (UTC ISO).

**`app/store.py`**: `read_index_meta(path) -> dict` (vacío si no existe).

**`app/main.py`**: en `lifespan`, si el índice declara un `embedding_model` distinto de `EMBEDDING_MODEL` → `RuntimeError` (arranque abortado: un índice incompatible produce scores sin sentido, mejor fallar alto que servir basura). Si no hay metadatos (índice anterior a este sprint) → WARNING.

**`app/rag.py`**: `_build_user_message` muestra el artículo cuando existe: `### Fuente 3: RGPD.pdf, Artículo 5, p. 36`.

El índice actual no tiene `article` ni `.index_meta.json`: el comportamiento en producción no cambia hasta reindexar. El test E2E pasa a usar `_load_pages` + `split_document` reales, con lo que la ruta de ingesta completa queda cubierta con PDFs sintéticos.

### 4.8 Evaluador fiel

`tools/eval_retrieval.py`:
- `--chroma-path` (default `settings.chroma_db_path`).
- Antes de cargar, lee `.index_meta.json`; si declara un modelo distinto de `--model`, aborta con mensaje claro (`--force` lo salta). Sin metadatos, avisa.
- Columna **Fuentes** (normativas distintas en el contexto final) en la tabla estándar.
- `--sweep` regenera `tools/eval_results.md` con el formato actual (recall, FP, ruido).
- `Makefile`: target `eval-sweep`.

### 4.9 Dependencias

`pyproject.toml`: se eliminan `langchain` y `langchain-community`; se añade `langchain-core` explícitamente (se importa directamente y hasta ahora llegaba de forma transitiva). `uv lock` regenera el lock. Verificación: `uv sync --frozen --extra dev`, suite completa y test E2E (slow) en verde; `grep` confirma que nada importa `langchain_community`.

### 4.10 Documentación

README (modelo LLM y respaldo, pipeline nuevo, verificación de citas, variables de entorno, tabla de tests, limitaciones: retirada de modelos, guardia débil con datos de H5, latencia), CHANGELOG `[Unreleased]`, CONTRIBUTING (runbook de reindexado y `.index_meta.json`), `.env.example` saneado, `README_hf.md` (modelo).

---

## 5. Flujo resultante

```
POST /v1/analyze
  ├─ cache HIT → respuesta
  ├─ _retrieve (hilo, timeout global 60 s)
  │    main k=100 ≥ umbral → −excluidas → top-25
  │    aux condicionales ≥ umbral → −excluidas
  │    rerank (orden completo) → _select_diverse(top 12, ≤ 4 por fuente)
  │    inyecciones por fuente (sin umbral)
  ├─ vacío → 404
  ├─ _invoke_llm: principal → (fallo) → respaldo → (fallo) → 503
  ├─ verify_citations(respuesta, docs)
  └─ RAGResponse(respuesta + Cobertura + Verificación de citas,
                 normativas_detectadas (≥2 chunks), citas, llm_model, corpus_version)
```

---

## 6. Estrategia de verificación

| Nivel | Qué | Cómo |
|---|---|---|
| Unitario | cada función nueva y cada regla | pytest, mocks (sin red, sin modelos); TDD en cada tarea |
| Integración API | endpoints, headers, códigos | `TestClient` con lifespan mockeado (fixture `client`) |
| Retrieval real | sin regresión y mejora de diversidad | `make eval` sobre el `chroma_db/` real antes/después de 4.3; cifras en el plan |
| Rendimiento | reranker int8 vs fp32 | medido antes de planificar (4.5): descartado; solo warm-up |
| E2E | ingesta real + pipeline | `pytest tests/test_e2e.py -m slow` (PDF sintético, Chroma real, LLM mock) |
| Lint | ruff check + format | como en CI |
| Producción | modelo vigente | tras desplegar: `/health/deep` → `groq: ok`; una petición real a `/v1/analyze` |

Cobertura mínima de CI: 80 % (sin cambios).

---

## 7. Entrega y pasos manuales

- **PR-A** (`fix/groq-model-decommissioned` → `main`): solo 4.1 + docs mínimas. Mergeable y desplegable de inmediato.
- **PR-B** (`sprint/3-rag-quality` → `main`, basada en PR-A): 4.2–4.10 + este documento y el plan. Cuando PR-A se mergee (squash), PR-B se rebasa sobre `main` para eliminar los commits duplicados.

Pasos que quedan en manos del mantenedor (requieren credenciales o decisión de producto):

1. Mergear PR-A → `make push-space` → comprobar `https://gustavintavo8-legaldev.hf.space/health/deep` devuelve `"groq":"ok"` y `groq_model: openai/gpt-oss-120b`.
2. Revisar el informe generado con el modelo nuevo (formato, español, citas) con un cuestionario real. Si el formato se degradara, el ajuste está acotado al `SYSTEM_PROMPT` (snapshot test) y a `groq_reasoning_effort`.
3. Mergear PR-B → `make push-space`.
4. Reindexar cuando se quiera activar las mejoras de ingesta (artículo en sub-chunks, filtro de ruido, metadatos):
   ```bash
   # con los 22 PDFs en docs/
   make ingest                      # construye en chroma_db.building y sustituye
   cat chroma_db/.index_meta.json   # comprobar embedding_model y chunks
   make eval                        # 13/13, 0 FP
   make eval-sweep                  # regenera tools/eval_results.md
   git add chroma_db/ tools/eval_results.md && git commit -m "chore: rebuild index (splitter v2)"
   git push && make push-space
   ```

---

## 8. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| gpt-oss-120b cambia el estilo del informe respecto a Llama 4 | temperatura 0 y prompt sin cambios; `reasoning_effort=low`; revisión manual post-deploy (paso 2). El respaldo gpt-oss-20b comparte familia y formato. |
| Groq no acepta `reasoning_effort` en algún modelo configurado por el usuario | solo se envía a `openai/gpt-oss*`. |
| Fallback duplica latencia en timeouts | aceptado frente a 503; el SDK ya reintenta transitorios; visible en `llm_model` y métrica. |
| Timeout global de 60 s demasiado corto en CPU compartida | configurable; el reranker mide ~20 s en 2 hilos; calentamiento elimina la carga en la primera petición. |
| Tope por fuente deja fuera un chunk relevante de una guía dominante | 4 chunks por fuente siguen superando el mínimo de 2 para abrir sección; eval sin regresión como criterio. |
| Falsos "no verificados" en citas por normalización insuficiente | normalización sin espacios ni guiones ni comillas; segmentos por elipsis; solo se informa, nunca se altera la respuesta. |
| Rename del índice falla en Windows por descriptores abiertos | reintentos con `gc.collect()`; si falla, `.building` queda intacto y se imprime el comando manual; el índice viejo nunca se borra antes. |
| Guardia de arranque por modelo rompe un despliegue | solo actúa si el índice **declara** un modelo distinto; los índices antiguos (sin metadatos) solo avisan. |
| Eliminar `langchain-community` rompe algo transitivo | `uv lock` + suite + E2E; `grep` de imports. |

---

## 9. Diferido, con evidencia

| Idea | Evidencia | Qué haría falta |
|---|---|---|
| Retrieval híbrido BM25+denso | tabla del spike: mejora RGPD/CCII/cookies, pierde EU AI Act, +250 ms | gold standard a nivel de chunk para medir calidad del contexto, no solo presencia de la normativa |
| Guardia anti-alucinación por score del reranker | H5: off-topic puntúa 0.37 y normativas correctas 0.05 | señal de aplicabilidad distinta de la similitud (campos nuevos en el cuestionario, p. ej. `es_plataforma_intermediaria` para DSA) |
| Modelo de embeddings orientado a retrieval (p. ej. `multilingual-e5-small`) | el modelo actual es de paráfrasis; RGPD en #44 del denso | PDFs fuente, reindexado, eval con `--chroma-path` A/B (habilitado en este sprint) |
| Reranker más pequeño/ONNX | H6: 20 s en 2 hilos; int8 dinámico cambia el ranking (4.5) | medir calidad con un eval de chunks |
| Campo `es_plataforma_intermediaria` (DSA como FP residual) | documentado en v0.3.0 | cambio de contrato con el frontend |

---

## 10. Métricas de éxito del sprint

- Producción: `/health/deep.groq == "ok"` y `POST /v1/analyze` devuelve 200 con `llm_model` informado.
- Código: cero duplicación de retrieval (un único `_retrieve`), suite completa verde, cobertura ≥ 80 %.
- Retrieval: eval 13/13, 0 FP, columna **Fuentes** ≥ baseline en todos los casos.
- Respuesta: `citas.total > 0` en informes reales y sección "Verificación de citas" presente.
- Operación: `warmup` en arranque (sin int8); `.index_meta.json` escrito por la ingesta; arranque aborta ante índice incompatible.
- Seguridad: `/v1/feedback` rechaza payloads fuera de límites y devuelve 429 al superar la cuota.
