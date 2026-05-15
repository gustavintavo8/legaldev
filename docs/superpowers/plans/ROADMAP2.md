# ROADMAP

Plan de mejoras para llevar LegalDev de un proyecto de portfolio competente a un proyecto que un senior pueda revisar sin objeciones. Las mejoras están priorizadas en tiers: **P0** son bugs o riesgos reales, **P1** son mejoras de calidad técnica que se notan en una entrevista, **P2** son refinamientos y nice-to-have.

Cada item lleva una estimación de esfuerzo (S/M/L) y un criterio de "hecho" verificable.

---

## P0 — Bugs y problemas reales

### 0.1 Validar `ALLOWED_ORIGINS` cuando contiene `*`

**Problema.** `Settings.cors_origins` hace un split por coma sin validación. Si alguien configura `ALLOWED_ORIGINS=*,https://foo.com` por error, FastAPI no falla pero el comportamiento es ambiguo y peligroso si en el futuro se activa `allow_credentials`.

**Solución.** Añadir un `@field_validator` en `Settings` que rechace combinaciones inválidas: si `*` aparece, debe ser el único valor.

**Hecho cuando.** Test que verifica que `ALLOWED_ORIGINS="*,https://foo.com"` levanta `ValidationError`.

Esfuerzo: S

---

### 0.2 Endurecer detección de IP real en rate limiting

**Problema.** `_get_real_ip` lee `X-Forwarded-For` sin verificar la procedencia. En local o si Railway no setea el header, un atacante puede mandar `X-Forwarded-For: <ip-aleatoria>` por cada request y bypassear el rate limit por IP trivialmente.

**Solución.** Añadir env var `TRUST_PROXY_HEADERS` (default `false`). Solo leer `X-Forwarded-For` cuando esté en `true`. Para Railway, documentar que se debe activar.

**Hecho cuando.** Tests cubren los dos modos (trust on/off) y los logs de arranque indican qué modo está activo.

Esfuerzo: S

---

### 0.3 Reemplazar `_collection` (API privada de Chroma)

**Problema.** `app.state.vectorstore._collection.count()` y `._collection.get(...)` usan API privada de Chroma (`_collection`). Esto puede romper en una actualización menor sin warning.

**Solución.** Encapsular el acceso en un wrapper `app/store.py` con métodos `count()` y `list_sources()`. Si Chroma cambia, se toca un solo sitio. Mantener un comentario en el wrapper indicando el uso de API privada y el motivo (no hay equivalente público en `langchain-chroma` 1.1).

**Hecho cuando.** `grep -r "_collection" app/` no devuelve nada fuera de `app/store.py`.

Esfuerzo: S

---

### 0.4 Calcular `INDEXED_NORMATIVAS` desde ChromaDB, no desde `REQUIRED_DOCS`

**Problema.** `INDEXED_NORMATIVAS` se calcula desde la lista canónica de archivos requeridos. Si la ingesta falla parcialmente o alguien borra un PDF sin actualizar `corpus.py`, hay drift entre lo que el código dice indexado y lo que realmente está en Chroma.

**Solución.** En el `lifespan` de `app/main.py`, leer las `source` únicas desde Chroma una vez al arranque y cachearlas en `app.state.indexed_normativas`. `rag.py` lee de ahí, no de `REQUIRED_DOCS`. Mantener `REQUIRED_DOCS` solo para validación en `ingest.py`.

**Hecho cuando.** El handler de `/normativas` y `INDEXED_NORMATIVAS` usan la misma fuente de verdad.

Esfuerzo: S

---

### 0.5 Timeout y manejo de errores en retrieval

**Problema.** `similarity_search_with_relevance_scores` no tiene timeout. Si Chroma se cuelga por I/O de disco, la request se queda colgada hasta el timeout de uvicorn.

**Solución.** Envolver la llamada en `asyncio.wait_for` (requiere refactorizar `run_pipeline` a async, o usar `concurrent.futures` con un timeout corto). Loggear y devolver 503 si excede.

**Hecho cuando.** Test simula un retrieval lento (mock con `sleep`) y verifica que devuelve 503 en lugar de colgarse.

Esfuerzo: M

---

### 0.6 Optimizar orden de capas en Dockerfile

**Problema.** Las layers están en un orden subóptimo. `COPY chroma_db/` después de `COPY app/` invalida la layer de `app/` cada vez que se reindexa.

**Solución.** Reordenar: `pyproject.toml/uv.lock` → install → embedding model download → `chroma_db/` → `app/`. Los cambios de código (más frecuentes) invalidan solo la última capa.

**Hecho cuando.** Cambiar un archivo en `app/` y reconstruir reusa la layer de `chroma_db/`.

Esfuerzo: S

---

### 0.7 Sanear logging de `descripcion_breve`

**Problema.** Actualmente loggeas `descripcion_length` y `descripcion_hash`, lo cual es correcto. Pero no hay una política documentada que prevenga que un cambio futuro meta `descripcion_breve` literal en logs. Logs con PII son un problema en cualquier auditoría.

**Solución.** Añadir una sección en `CONTRIBUTING.md` (o un comentario en `rag.py`) listando explícitamente qué campos del cuestionario nunca deben ir a logs en claro. Añadir un test que falle si el output de logs contiene la `descripcion_breve` original.

**Hecho cuando.** Test de logging que captura los logs de `run_pipeline` y verifica que la `descripcion_breve` original no aparece.

Esfuerzo: S

---

## P1 — Mejoras técnicas de calidad

### 1.1 Añadir un cross-encoder reranker

**Problema.** El retrieval actual es similaridad vectorial + threshold + slice. No hay reranking. Para 22 documentos legales con artículos parecidos entre sí, un reranker mejora la precisión del contexto que llega al LLM. Es la diferencia entre un RAG juguete y uno serio.

**Solución.** Añadir `BAAI/bge-reranker-base` (~80 MB en CPU) como paso entre overfetch y slice:

1. Overfetch a 100 candidatos
2. Filtrar por threshold de similaridad
3. Reranker sobre los top 30 supervivientes
4. Slice a top 12 por score del reranker

Métrica: comparar recall@k en `tools/eval_cases.yaml` antes y después. Documentar el delta en CHANGELOG y README.

**Hecho cuando.** `make eval` muestra recall ≥ actual y los casos `query-compleja-rgpd-colegiado-ia` y `cookies-webapp` pasan con menos chunks auxiliares (idealmente eliminando alguna `AuxSearch`).

Esfuerzo: M

---

### 1.2 Splitter consciente de estructura legal

**Problema.** `RecursiveCharacterTextSplitter(500/100)` parte artículos por la mitad. Un chunk legal ideal es un artículo completo (o un apartado de un artículo).

**Solución.** Custom splitter con regex que respete límites de artículos (`Artículo \d+`, `Art\. \d+`, `Considerando \d+` para normativa europea). Fallback a `RecursiveCharacterTextSplitter` cuando no encuentra patrones.

**Hecho cuando.** Inspección manual de 10 chunks aleatorios muestra que ≥80% empiezan con "Artículo" o "Considerando" y no cortan a mitad de frase.

Esfuerzo: M

---

### 1.3 Justificar empíricamente `MIN_RELEVANCE_SCORE`

**Problema.** El valor `0.35` está hardcodeado sin justificación visible. En una entrevista, "¿por qué 0.35?" es una pregunta esperable y la respuesta actual es "porque sí".

**Solución.** Extender `tools/eval_retrieval.py` con un sweep sobre el threshold (0.20, 0.25, 0.30, 0.35, 0.40, 0.45) reportando recall promedio y "ruido" (chunks de normativas no esperadas) para cada caso. Generar `tools/eval_results.md` con la tabla. Justificar el valor elegido.

**Hecho cuando.** `tools/eval_results.md` existe y el README enlaza a él en la sección "Decisiones técnicas".

Esfuerzo: M

---

### 1.4 Test E2E con ChromaDB real

**Problema.** Todos los tests están mockeados. No hay protección contra rupturas en la integración real Chroma/LangChain. Una actualización de versión menor puede romper el pipeline sin que los tests lo detecten.

**Solución.** Crear `tests/test_e2e.py` marcado con `@pytest.mark.slow`. Usa un PDF sintético pequeño (un .txt convertido o un PDF mínimo en `tests/fixtures/`), ingesta a un `chroma_db` temporal, corre `run_pipeline` con un Groq mockeado. CI ejecuta los slow tests solo en push a `main`, no en cada PR.

**Hecho cuando.** El test E2E pasa localmente y CI tiene un job `test-slow` separado.

Esfuerzo: M

---

### 1.5 Versionado del corpus

**Problema.** No hay forma de saber qué versión del corpus generó una respuesta. Si alguien reporta "esta respuesta es incorrecta", no puedes correlacionarla con el estado del corpus en ese momento.

**Solución.** En `ingest.py`, calcular un `corpus_version = sha256(sorted([(f.name, f.stat().st_size) for f in pdfs]))[:12]`, guardarlo en un archivo `chroma_db/.corpus_version`. Exponerlo en `/health` y en `RAGResponse`. Loggearlo en cada llamada.

**Hecho cuando.** `curl /health` devuelve `corpus_version`, y cada respuesta de `/v1/analyze` lo incluye.

Esfuerzo: S

---

### 1.6 Request ID y trazabilidad

**Problema.** Logs JSON estructurados pero sin correlación entre eventos de la misma request.

**Solución.** Middleware FastAPI que genera un UUID corto por request, lo añade al header `X-Request-ID` de la respuesta y lo inyecta en el contexto de logging (`contextvars`). Todo log dentro de `run_pipeline` lleva ese ID.

**Hecho cuando.** Una request genera ≥3 líneas de log y todas comparten `request_id`. El cliente puede recuperar ese ID del header.

Esfuerzo: S

---

### 1.7 Renderizar "Cobertura del análisis" programáticamente

**Problema.** El LLM tiene instrucciones de generar la sección "Cobertura del análisis" listando normativas no recuperadas. Si el modelo decide saltársela (pasa con prompts largos), no hay forma de detectarlo y la respuesta queda incompleta.

**Solución.** Quitar esa sección del system prompt. Renderizarla en código después de recibir la respuesta del LLM y concatenarla al `respuesta_completa`. Garantiza determinismo y libera tokens en el prompt.

**Hecho cuando.** El system prompt ya no menciona "Cobertura del análisis" y la respuesta final siempre incluye la sección cuando `not_retrieved` no está vacío.

Esfuerzo: S

---

### 1.8 Healthcheck profundo

**Problema.** `/health` solo cuenta chunks. No detecta si Groq está caído o si el modelo de embeddings se cargó mal.

**Solución.** `/health/deep` que ejecuta una query trivial contra Chroma y un ping a Groq (cacheado 60s vía `functools.lru_cache` con TTL). Devuelve un objeto con el estado de cada componente. `/health` sigue siendo el liveness probe ligero.

**Hecho cuando.** `curl /health/deep` devuelve `{groq: ok, chroma: ok, corpus_version: "..."}` y un test verifica que detecta fallos.

Esfuerzo: S

---

### 1.9 Caché de respuestas idénticas

**Problema.** Cuestionarios idénticos llaman a Groq cada vez. Es desperdicio de tokens (limitado en free tier) y latencia.

**Solución.** `lru_cache` (en memoria) o `cachetools.TTLCache` sobre el hash canónico del `QuestionnaireInput`. TTL configurable, default 1 hora. Marcar las respuestas cacheadas con un header `X-Cache: HIT/MISS`.

Documentar la decisión en el README: "no usamos Redis porque para un proyecto single-instance el LRU en memoria es suficiente; si pasa a multi-instance, hay que cambiar."

**Hecho cuando.** Dos requests idénticas seguidas: la segunda devuelve `X-Cache: HIT` y no incrementa el contador de llamadas a Groq.

Esfuerzo: S

---

### 1.10 Endpoint `/v1/feedback`

**Problema.** No hay loop de feedback. Un proyecto que se presenta como portfolio se beneficia mucho de demostrar mentalidad de producto.

**Solución.** `POST /v1/feedback` recibe `{request_id, rating: 1-5, comment?: str}` y lo persiste en un JSONL local (`feedback.jsonl`). En el README, mostrar cómo se usaría para iterar sobre el prompt.

**Hecho cuando.** Endpoint funciona, persiste a disco, y hay un test que verifica la persistencia.

Esfuerzo: S

---

### 1.11 Métricas Prometheus custom

**Problema.** `prometheus-fastapi-instrumentator` está instalado pero no se aprovecha. Solo expone métricas HTTP genéricas.

**Solución.** Añadir métricas custom:
- `legaldev_chunks_retrieved` (histograma)
- `legaldev_top_score` (histograma)
- `legaldev_retrieval_duration_seconds` (histograma)
- `legaldev_llm_duration_seconds` (histograma)
- `legaldev_404_no_coverage_total` (contador)
- `legaldev_aux_search_triggered_total{type}` (contador)

**Hecho cuando.** `/metrics` muestra estas métricas y el README incluye un screenshot de un dashboard Grafana (o al menos una query PromQL útil).

Esfuerzo: M

---

### 1.12 Frontend mínimo (Streamlit o Next.js)

**Problema.** Sin UI, el proyecto se demuestra con `curl`. Esto limita el "wow factor" en entrevistas.

**Solución.** Dos opciones:

- **Streamlit (rápido, M)**: `frontend/app.py` con formulario que mapea 1:1 al `QuestionnaireInput`, llama a la API local, renderiza el markdown.
- **Next.js (más profesional, L)**: app separada en `frontend/`, deploy en Vercel, llama a la API en Railway. Más esfuerzo pero infinitamente mejor para portfolio.

Elegir según tiempo disponible. La Streamlit puede vivir junto al backend; la Next.js merece su propio repo o subdirectorio con su propio CI.

**Hecho cuando.** Un usuario sin conocer `curl` puede usar el sistema. README enlaza al frontend.

Esfuerzo: M (Streamlit) / L (Next.js)

---

## P2 — Refinamientos

### 2.1 Modelo de embeddings: medir antes de cambiar

**Problema.** El README justifica `all-MiniLM-L6-v2` por RAM. Pero un plan Railway Hobby ($5/mes, 8 GB) caben holgadamente modelos multilingual.

**Solución.** En `tools/eval_retrieval.py`, añadir flag `--model` para probar:
- `all-MiniLM-L6-v2` (actual, ~80 MB)
- `paraphrase-multilingual-MiniLM-L12-v2` (~440 MB)
- `BAAI/bge-m3` (~2.3 GB, si cabe)

Reportar recall por caso. Si el multilingual gana por margen claro, cambiar y documentar el coste de RAM.

**Hecho cuando.** Tabla comparativa en `tools/eval_results.md` con números reales, no opiniones.

Esfuerzo: M

---

### 2.2 API keys básicas

**Problema.** Sin autenticación, el rate limit por IP es trivial de bypassear.

**Solución.** Header `X-API-Key` validado contra un set leído de env var `API_KEYS` (comma-separated). Endpoint público (`/`, `/health`, `/normativas`) sigue abierto; `/v1/analyze` requiere key. Default: si `API_KEYS` está vacío, el endpoint queda abierto (preserva DX local).

**Hecho cuando.** Tests cubren los dos modos y el README explica cómo generar/rotar keys.

Esfuerzo: S

---

### 2.3 GIF de demo en el README

**Problema.** El README es excelente en lo técnico pero no tiene demo visual. Para un recruiter que abre el repo durante 30 segundos, una demo visual decide si sigue leyendo.

**Solución.** Grabar un GIF de 10-15 segundos: usuario rellena el formulario (Streamlit/Next.js), aparece la respuesta con citas. Subir a `docs/demo.gif` y enlazar arriba del README.

**Hecho cuando.** El README abre con un GIF visible en GitHub.

Esfuerzo: S

---

### 2.4 Sección "Limitaciones conocidas" en el README

**Problema.** Toda herramienta seria reconoce sus limitaciones. La ausencia de esa sección sugiere falta de honestidad técnica.

**Solución.** Sección al final del README listando, sin endulzar:

- Embeddings inglés-céntrico afecta términos jurídicos en español
- Corpus estático; no detecta cambios normativos en tiempo real
- LLM puede alucinar incluso con grounding fuerte
- Cobertura solo de las 22 normativas indexadas; legislación autonómica no cubierta
- Rate limit por IP es spoofable sin proxy de confianza

**Hecho cuando.** La sección existe y es honesta.

Esfuerzo: S

---

### 2.5 Sección "Qué aprendí" en el README

**Problema.** Como proyecto de portfolio de estudiante, contar el aprendizaje multiplica el valor. Un recruiter quiere ver no solo qué hiciste, sino qué aprendiste haciéndolo.

**Solución.** Sección al final con 5-8 bullets honestos: el primer intento, qué falló, qué medición te hizo cambiar de opinión, qué decisión técnica fue una mala decisión que luego revertiste. La parte de las búsquedas auxiliares por dominio (saturación léxica con cookies) es exactamente el tipo de historia que va aquí.

**Hecho cuando.** La sección está escrita en primera persona y cuenta al menos una historia de iteración real.

Esfuerzo: S

---

### 2.6 Disciplina con CHANGELOG

**Problema.** El CHANGELOG solo tiene una entrada (v0.1.0) y la sección `[Unreleased]` está vacía. En un proyecto serio se actualiza por cada PR no trivial.

**Solución.** Convertir en hábito: cada PR que cambia comportamiento añade una entrada en `[Unreleased]`. Al hacer release, mover a una nueva versión.

**Hecho cuando.** En el siguiente release, `[Unreleased]` tiene al menos 5 entradas reales.

Esfuerzo: continuo

---

### 2.7 Detección defensiva de prompt injection

**Problema.** El sandboxing actual (`<descripcion_usuario>` + instrucción al LLM de ignorar el contenido) es buena defensa pero no detección. No sabes si alguien intenta inyectar.

**Solución.** Antes de pasar el input al pipeline, escanear `descripcion_breve` por patrones sospechosos: la propia etiqueta de cierre del sandbox, frases tipo "ignore previous instructions", "you are now", etc. No rechazar (sería intrusivo); loggear con un campo `suspected_injection: true` para análisis.

**Hecho cuando.** Test inyecta un patrón conocido, verifica que se loggea el flag y la respuesta sigue normal.

Esfuerzo: S

---

### 2.8 Política de versionado de dependencias

**Problema.** `pyproject.toml` pinea todo con `==`. Reproducible, sí, pero no recibe patches de seguridad sin trabajo manual.

**Solución.** Adoptar: `~=` para runtime (recibe patches), `==` solo para dependencias con incompatibilidades conocidas, `>=` para dev. Configurar Dependabot o Renovate para PRs automáticos. Mantener `uv.lock` para reproducibilidad exacta.

**Hecho cuando.** `.github/dependabot.yml` existe y al menos un PR de actualización se ha mergeado.

Esfuerzo: S

---

### 2.9 Aliasing de email en `SECURITY.md`

**Problema.** El email de contacto es una Gmail personal. Para un proyecto que se vende como serio, conviene un alias dedicado.

**Solución.** Registrar `security@<tu-dominio>` o usar un alias de Gmail (`gustavintavo1202+legaldev-security@gmail.com`). Generar y publicar una PGP key si quieres ir un paso más allá.

**Hecho cuando.** `SECURITY.md` apunta a un canal dedicado.

Esfuerzo: S

---

### 2.10 Refactor: `tipo_proyecto` y enums en `_build_user_message`

**Problema.** `StrEnum` se serializa correctamente en Python 3.11+ a su valor string, pero el código no lo testea explícitamente. Si en algún momento se cambia a `Enum` regular, el `f-string` imprime `TipoProyecto.APP_WEB` y nadie se entera.

**Solución.** Test parametrizado que llama a `_build_user_message` con cada enum y verifica que el output contiene el valor string, no el nombre de la clase.

**Hecho cuando.** El test existe y pasa.

Esfuerzo: S

---

## Orden sugerido de ejecución

Si solo dispones de tiempo limitado, este es el orden de mayor impacto/esfuerzo:

1. **Primera tanda (P0 bugs):** 0.1 → 0.2 → 0.3 → 0.4 → 0.6. Unas pocas horas en total. Cierra los problemas reales y deja el código defendible.
2. **Segunda tanda (P1 visibilidad):** 1.5 (corpus version) → 1.6 (request ID) → 1.7 (cobertura programática) → 1.8 (healthcheck profundo). Mejoras que demuestran madurez operacional.
3. **Tercera tanda (P1 RAG core):** 1.3 (justificar threshold) → 1.1 (reranker) → 1.4 (E2E). Aquí está la diferencia entre "lo monté" y "lo entendí".
4. **Cuarta tanda (presentación):** 1.12 (frontend) → 2.3 (GIF) → 2.4 (limitaciones) → 2.5 (aprendizajes). El proyecto pasa de impresionar a un compañero técnico a impresionar también a un recruiter no técnico.
5. **Resto en orden de oportunidad.**

---

## Notas para mantenimiento futuro

- Cada PR no trivial debería: actualizar `CHANGELOG.md` (sección `[Unreleased]`), correr `make eval` si toca retrieval, mantener coverage ≥ 80%.
- El `chroma_db/` commiteado es un trade-off consciente; si crece > 200 MB, evaluar Git LFS o regenerar en CI antes del build de Docker.
- La carpeta `docs/` con los PDFs nunca debe commitearse — son fuentes públicas y pesan mucho. El `.gitignore` ya lo cubre.
- Si el proyecto crece a multi-tenant o multi-instance, varios items cambian de "P2 nice-to-have" a "P0 blocker": caché (Redis), rate limit (Redis), auth (real), versionado de corpus por tenant.
