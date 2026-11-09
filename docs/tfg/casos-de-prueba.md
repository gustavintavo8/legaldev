# Casos de prueba y organización de la suite

> Procede del capítulo de pruebas de la memoria del TFG (etiqueta `pre-recorte-2026-11` del repositorio de la memoria, `capitulos/24-pruebas.tex`). Los Documentos técnicos de la memoria conservan la estrategia, la batería de regresión y su circularidad, el barrido del umbral, las citas, los descartes, el rendimiento, el incidente y las pruebas PP del servidor MCP. Aquí queda el detalle de la suite del punto de partida: dobles de prueba, organización por componente, casos representativos, prueba de integración, desglose de las pruebas de citas y puntuaciones de la búsqueda.

Las cifras son de `main@9f173ce`, ejecutadas el 18 de septiembre de 2026 (`pytest -m 'not slow'`): 248 funciones de prueba en 23 ficheros, 295 casos superados y la prueba lenta deseleccionada, en 15,6 s. La cobertura de líneas de `app/` fue del 93 % (26 de septiembre de 2026). Las salidas están en `datos/pytest.txt`, `datos/pytest_cov.txt` y `datos/pytest_slow.txt` del repositorio de la memoria.

En `832ac33`, con el servidor MCP, pasan 420 pruebas de la suite rápida y la prueba lenta, se omiten 22 (las de PT3, PT5, PT10 y PP-18) y la cobertura es del 95 %. Los ficheros del servidor MCP son `test_mcp_contract.py` (27 pruebas con sus parametrizaciones), `test_mcp_security.py` (36, de las que 35 pasan y se omite PP-18), `test_mcp_equivalence.py` (16) y `test_service.py` (17, de las que 16 pasan y se omite PI2), con utilidades comunes en `tests/_mcp.py`. También son posteriores al punto de partida `test_obligations.py`, `test_controls.py` y `test_evidence.py`, de los esqueletos de OE2, y `test_list_todos.py`.

## Componentes reales y simulados en cada nivel

Los componentes deterministas se prueban de forma exhaustiva y barata, con dobles en lugar de los modelos y de la base vectorial. Los no deterministas o caros se prueban con menos frecuencia, contra el sistema real. Ningún nivel repite lo que prueba el inferior: las pruebas HTTP no vuelven a probar la lógica de la caché, ni la de integración los códigos de error.

| Componente | Unitarias / HTTP | Integración | Regresión | Producción |
|---|---|---|---|---|
| Modelo de embeddings | simulado | real | real | real |
| Índice ChromaDB | simulado | real (temporal) | real | real |
| Reordenador (*cross-encoder*) | simulado (identidad) | simulado (identidad) | real | real |
| Modelo de lenguaje (Groq) | simulado | simulado | no interviene | real |
| Reglas y consulta | reales | reales | reales | reales |
| Verificación de citas | real | real | no interviene | real |
| Caché de respuestas | real | no interviene | no interviene | real |
| Capa HTTP (FastAPI) | real | no interviene | no interviene | real |

## Infraestructura de la suite (`tests/conftest.py`)

`conftest.py` concentra los dobles y el aislamiento entre casos.

- **`client`.** Arranca la aplicación con su ciclo de vida y sustituye el modelo de embeddings, Chroma, el cliente de Groq, la comprobación del modelo, el calentamiento del reordenador y la lectura de los metadatos del índice. Con esos dobles, las pruebas HTTP recorren `/v1/analyze` sin disco ni red. El índice simulado devuelve siempre un fragmento del RGPD con puntuación 0,85.
- **`mock_reranker`.** Sustituye el reordenador por la identidad truncada. Fuera de `client` hay que pedirlo de forma explícita, para que ninguna prueba unitaria cargue el modelo real por accidente.
- **`_isolate_global_state`.** De uso automático. Vacía la caché antes y después de cada caso y reinicia el limitador al terminar cada uno. Sin él, un caso que agotaba el límite de 10 peticiones por minuto hacía fallar con 429 a otros posteriores, y una respuesta cacheada por un caso aparecía como `X-Cache: HIT` en otro.

## Organización por componente

Agrupa los ficheros `tests/test_<nombre>.py` de `main@9f173ce` y señala los requisitos no funcionales que verifican. La relación de cada requisito funcional con sus pruebas está en [trazabilidad.md](trazabilidad.md).

| Ficheros (`test_*.py`) | Funciones | RNF | Qué fijan |
|---|---|---|---|
| `rag` | 54 | 01, 04 | Consulta y mensaje al modelo; búsquedas auxiliares, exclusiones e inyecciones; sección de cobertura; tiempo máximo de la recuperación; instantánea del *prompt*; registros sin la descripción; misma recuperación en la API y en el evaluador. |
| `retrieval_selection`, `reranker` | 13 | — | Exclusiones antes del reordenador; tope por normativa; orden, truncado y calentamiento del reordenador. |
| `citations` | 43 | — | Extracción, normalización y verificación literal de citas (desglose más abajo). |
| `api`, `api_keys` | 37 | 06 | Puntos de entrada; códigos 401, 403, 404, 422, 429 y 503; caché `HIT`/`MISS`; límite; IP real tras un proxy de confianza. |
| `models`, `build_user_message`, `injection` | 18 | 05 | Validación del cuestionario y enumeraciones cerradas; detección y registro de patrones de inyección. |
| `llm_fallback`, `lifespan_guard`, `config` | 25 | 02, 06 | Respaldo del modelo; comprobación al arrancar; índice de otro modelo; valores por defecto y `ALLOWED_ORIGINS`. |
| `ingest_build`, `legal_splitter`, `ingest`, `store` | 30 | 08 | Carga y segmentación; metadatos del índice; intercambio atómico y sus fallos. |
| `cache` | 10 | — | Caducidad, desalojo y claves deterministas. |
| `middleware`, `metrics`, `concurrency` | 9 | 01, 10 | `X-Request-ID`; métricas; `/health` responde durante un análisis. |
| `eval_model_flag`, `eval_sweep` | 8 | 08 | Opciones del evaluador y rechazo de un índice construido con otro modelo. |
| `e2e` | 1 | — | Integración con índice real (lenta). |
| **Total** | **248** | | 2.896 líneas de prueba frente a 1.637 de aplicación (líneas no vacías). |

La suite tiene más líneas que la aplicación porque cada corrección se desarrolló con una prueba que reproducía el fallo antes de escribir el código. Cada incidente dejó además sus propios casos: el modelo retirado, los descriptores abiertos en Windows y las citas literales marcadas como no verificadas. `test_system_prompt_snapshot` (`tests/test_rag.py`) fija el *hash* del *prompt* del sistema. Cualquier cambio, aunque sea de una coma, obliga a actualizar la instantánea a propósito, porque el *prompt* especifica el formato que el resto del sistema da por supuesto: citas en bloque y dos fragmentos por normativa para abrir sección.

## Casos de prueba representativos (CP-01 a CP-12)

Un caso por requisito o grupo de requisitos, con el nombre real de la función de prueba. Todas existen en `832ac33`.

| Id | Objetivo | Entrada y resultado esperado | Prueba (fichero) | Req. |
|---|---|---|---|---|
| CP-01 | Análisis completo por HTTP | Cuestionario válido; 200 con informe, normativas, fragmentos y aviso de no asesoramiento. | `test_v1_analyze_returns_rag_response` (`test_api.py`) | RF-01, RF-08 |
| CP-02 | Validación de la entrada | Sin campos, descripción de 501 caracteres o IA sin `tipo_ia`; 422 o error de validación. | `test_analyze_invalid_input_missing_fields` y dos más (`test_api.py`) | RF-02 |
| CP-03 | Sin cobertura | Ningún fragmento supera el umbral y no hay inyecciones; 404 «sin cobertura». | `test_analyze_no_relevant_docs_returns_404` (`test_api.py`) | RF-04 |
| CP-04 | Respaldo del modelo | El principal falla y el respaldo responde, declarado en `llm_model`; si fallan ambos, 503. | `test_fallback_used_when_primary_fails`; `test_503_when_both_models_fail` (`test_llm_fallback.py`) | RF-19 |
| CP-05 | Caché de respuestas | Dos peticiones idénticas; la segunda lleva `X-Cache: HIT` y no invoca al modelo. | `test_cache_hit_does_not_call_llm_again` (`test_api.py`) | RF-15 |
| CP-06 | Límite y claves | Más de diez valoraciones en un minuto, 429; con `API_KEYS`, 401 sin clave y 403 con clave errónea. | `test_feedback_is_rate_limited` (`test_api.py`); `test_analyze_rejects_wrong_key` (`test_api_keys.py`) | RF-16, RF-17 |
| CP-07 | Inyección directa | Descripción con «ignore previous instructions»; se registra el evento y la petición se atiende. | `test_injection_logged_but_not_rejected` (`test_injection.py`) | RNF-05 |
| CP-08 | Privacidad de los registros | Ningún registro contiene la descripción, solo su longitud y su *hash*. | `test_run_pipeline_does_not_log_descripcion_breve` (`test_rag.py`) | RNF-04 |
| CP-09 | Exclusiones antes del reordenador | Fragmentos del ENS entre los candidatos; no llegan al reordenador ni ocupan plazas. | `test_excluded_docs_never_reach_the_reranker` (`test_retrieval_selection.py`) | RF-05 |
| CP-10 | Inyección garantizada | Todos los candidatos bajo el umbral, pero hay datos personales; el RGPD llega al contexto. | `test_injection_delivers_rgpd_even_when_all_scores_below_threshold` (`test_rag.py`) | RF-06 |
| CP-11 | Verificación literal | Cita limpia frente a un fragmento con «dat os» y «líc ita», verificada; una palabra cambiada en el interior, rechazada. | `test_verify_tolerates_pdf_extraction_spacing`; `…rejects_difference_in_the_middle_of_the_quote` (`test_citations.py`) | RF-10 |
| CP-12 | División por artículos | Texto con «Artículo 1» y «Artículo 2»; dos fragmentos con metadato `article`. | `test_splits_on_articulo_boundary` (`test_legal_splitter.py`) | RF-18 |

CP-12 muestra el límite de las pruebas con datos sintéticos. Su texto escribe «Artículo» sin los artefactos de extracción de los PDF reales («Ar tículo»), y por eso la suite pasa aunque el metadato de artículo falte en 9 de las 10 normas de la UE del índice.

## Prueba de integración con índice real (`test_e2e.py`)

`test_e2e_pipeline_retrieves_from_real_chroma` cubre lo que los dobles no pueden: la integración de `pypdf`, el segmentador, el modelo de embeddings, ChromaDB y el *pipeline* con las versiones fijadas.

1. Genera con `fpdf2` un PDF de siete artículos sintéticos y lo carga y segmenta con las funciones de la ingesta real.
2. Construye un índice temporal con `paraphrase-multilingual-MiniLM-L12-v2` y vectores normalizados.
3. Ejecuta `run_pipeline` con el reordenador sustituido por la identidad y el modelo de lenguaje simulado. El umbral se pone a 0, porque las puntuaciones de un corpus de siete frases no son comparables con las del real.
4. Comprueba que el contexto no está vacío, que la normativa sintética figura entre las detectadas y que `llm_model` indica el modelo principal.

No es una prueba de extremo a extremo en sentido estricto, porque el reordenador y el modelo son simulados; ese papel lo cumple la verificación en producción. Se ejecuta en el trabajo `test-slow` de la integración continua. Esta prueba descubrió que ChromaDB mantenía abiertos en Windows los descriptores de SQLite y de HNSWLIB (solución en [modulos.md](modulos.md), apartado de la ingesta). Comparte el límite de CP-12, porque su PDF también escribe «Artículo» sin artefactos.

## Pruebas de la verificación de citas (`test_citations.py`)

En `main@9f173ce` el fichero tenía 43 funciones de prueba, en cuatro grupos:

| Grupo | Pruebas | Qué cubren |
|---|---|---|
| Extracción | 9 | Tipos de comillas, citas partidas por el ajuste de línea del modelo y líneas que no son cita. |
| Normalización y verificación | 20 | Artefactos como «dat os», guiones de fin de línea, CRLF, caracteres de anchura cero, NFD frente a NFC; rechazo de paráfrasis y de citas que abarcan dos fragmentos. |
| Tolerancia en los extremos | 7 | Llegaron con `BOUNDARY_TOLERANCE`, tras comprobar en producción que se rechazaban citas reales por un punto final o una palabra en el borde del fragmento. |
| Rendimiento e integración | 7 | Entre ellas, la que fija la complejidad lineal de la extracción: la primera implementación era cuadrática y tardaba minutos ante una respuesta con miles de comillas sueltas. |

En `832ac33` el fichero tiene 49 funciones. Las nuevas cubren los arreglos del 6 de noviembre de 2026, entre ellos que la verificación ignore los guiones Unicode que escribe el modelo.

## Puntuaciones de la búsqueda principal

Puntuaciones de relevancia de los candidatos de la búsqueda principal en cinco casos de la batería, medidas el 11 de septiembre de 2026 sobre el índice anterior (13.873 fragmentos):

| Caso | Puntuaciones 1.ª–3.ª | Puntuación 100.ª | Superan 0,40 |
|---|---|---|---|
| C01 rgpd-lopdgdd-basico | 0,562 / 0,554 / 0,550 | 0,428 | 100 de 100 |
| C08 query-compleja | 0,714 / 0,694 / 0,688 | 0,600 | 100 de 100 |
| C10 sin-datos-personales | 0,510 / 0,501 / 0,495 | 0,357 | 49 de 100 |
| C11 off-topic-recetas | 0,471 / 0,471 / 0,469 | 0,330 | 17 de 100 |
| C12 plantas (dominio lejano) | 0,443 / 0,423 / 0,416 | 0,299 | 4 de 100 |

Con vocabulario jurídico pasan los cien candidatos, y el umbral solo recorta en dominios lejanos. Ocurre porque el umbral de 0,40 equivale a un coseno de unos 0,58 (s = 1 − √2 · (1 − cos θ)) y, con el modelo multilingüe, las puntuaciones caen en un rango estrecho. El barrido del umbral y su justificación están en el capítulo de pruebas de los Documentos técnicos.
