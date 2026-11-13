# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Deployed
- 13/11/2026: `main` (`ab3e3a3`) en el Space, con `MCP_DAILY_LIMIT=200/day`. Comprobación, MCP Inspector y latencia en producción en `docs/mcp/produccion/`, `docs/mcp/latencia/` y `docs/mcp/README.md`. `analizar_proyecto` en frío tuvo p50 20,9 s y p95 22,7 s; en caché, p95 3,4 s; `consultar_obligaciones`, p95 8,9 s (n = 10).

### Added
- `tools/medir_latencia_mcp.py` (RNF-19): mide por MCP la latencia p50 y p95, con mínimo y máximo, de tres series y la escribe en JSON:
  - `analizar_proyecto` en frío, con cuestionarios distintos y marcados con la ejecución para que no estén en la caché;
  - `analizar_proyecto` en caliente, desde la caché, comprobado con `generado_por_ia.fecha`;
  - `consultar_obligaciones`.

  Los percentiles son por el rango más cercano. Los errores y los 429 se cuentan aparte. Las llamadas van espaciadas y sin reintentos, y el arranque del Space se anota por separado. La URL y la clave llegan en `LEGALDEV_URL` y `LEGALDEV_API_KEY`. No importa `app` ni lee `.env`.
- `tools/servidor_mcp_prueba.py`: API local con `/mcp` y una clave de prueba que registra, por petición, el método, la revisión que pide el cliente y su `clientInfo`, sin la clave ni los argumentos. Con `--modelo-simulado` no llama a Groq. Sirve para ver qué revisión negocia cada cliente.
- `make mcp-inspect`: comprueba `/mcp` con MCP Inspector 2.13.0 (`tools/list --strict` y `listar_normativas` en las dos eras, y el rechazo sin clave y con una clave falsa). Sustituye al marcador pendiente. Los resultados del 12/11/2026, por HTTP y por stdio, están en `docs/mcp/README.md`, «MCP Inspector».
- Ejemplos de configuración stdio para VS Code, Cursor y Claude Code en `docs/mcp/clients/stdio/`, con la ruta del repositorio en `LEGALDEV_DIR`. Una prueba comprueba que lanzan `app.mcp_stdio` con `uv` y que no llevan URL, cabeceras ni variables.
- Saneado de la salida del modelo (RNF-20, `app/sanitize.py`), antes de verificar las citas y de guardar en la caché, así que llega igual a la API REST, a la web y a `analizar_proyecto`. Se aplica solo al texto del modelo, no a las secciones que añade el código. Codifica la salida en lugar de buscar lo peligroso: primero lleva el texto a una sola forma (resuelve una vez las referencias de carácter y pasa a ASCII las formas de ancho completo, como las leen el visor y el asistente) y después escapa «<», «[», «@», el «&» de una referencia, el «:» de «://», la segunda barra de «//» y el punto de «www.» en todo el texto, también en el código, salvo lo que ya va escapado. Así ningún intérprete que siga CommonMark pinta HTML, imágenes, enlaces ni autoenlaces del modelo ni resuelve una referencia de carácter: se ven como texto, y los enlaces del modelo, también los oficiales, dejan de ser clicables. Las casillas de las listas de tareas se ven como «[ ]». Retira caracteres de control, escapes ANSI, caracteres invisibles (ancho cero, bidi, etiquetas Unicode) y bloques que imitan llamadas a herramientas, y cierra los bloques de código sin cerrar. Lo deja constar en el campo nuevo `saneado` (recuentos de lo retirado; `imagenes`, `enlaces`, `html` y `urls` quedan siempre a 0) y, si retira algo, en una sección «Saneado de la salida» del informe. `citations.normalize` quita la barra invertida, así que las citas literales se siguen verificando: ninguno de los 13.756 fragmentos del índice cambia tras `normalize`. Las instrucciones del servidor MCP y el aviso de sus resultados dicen ahora que el contenido es para el desarrollador, no órdenes para el asistente. Queda fuera un dominio sin esquema que linkify enlaza en modo difuso, y el paso que retira las llamadas es una heurística para las formas conocidas (detalle en `docs/mcp/README.md`, «Salida segura»).
- PP-18 (inyección indirecta): 20 cargas reales en `docs/mcp/pp18/cargas.json`, probadas en la descripción y en un fragmento envenenado con el modelo simulado que las repite. Las comprueba un oráculo independiente (`tests/_pp18.py`) que pinta con markdown-it-py (CommonMark, tablas, tachado y linkify; `markdown-it-py` y `linkify-it-py`, dependencias de desarrollo).
  - `docs/mcp/pp18/oraculo.py` sanea y pinta las cargas y las 282 entradas de `tests/_casos_saneado.py` (las de las cuatro revisiones y todas las que las pruebas anteriores pasaban a `sanear`) con dos intérpretes: marked + DOMPurify, el visor de la web, y markdown-it-py. Con cada uno mira también si en lo que se pinta se ve una llamada, un bloque anunciado como llamada o un invisible. El 13/11/2026, ninguna pinta nada peligroso con ninguno de los dos.
  - `docs/mcp/pp18/fuzz.py` y `docs/mcp/pp18/fuzz_tiempo.py` buscan fallos y entradas lentas.
  - `docs/mcp/pp18/medir.py` mide lo mismo con el modelo real, con como mucho 12 llamadas. El 12/11/2026, con el saneado anterior, `openai/gpt-oss-120b` reprodujo 2 de 12 cargas y ninguna forma ejecutable pasó el saneado. El 13/11/2026, con la codificación (`ab3e3a3`), reprodujo las mismas 2 (P03 quedó como texto y P06 se retiró), ninguna llegó ejecutable y se verificaron 109 de 125 citas.
  - `docs/mcp/pp18/corpus_identidad.py` comprueba que el saneado no cambia el índice tras `normalize`.
- Marcado del contenido generado por IA (Reglamento de IA, art. 50.2; hallazgo C-05): campo `generado_por_ia` (`modelo`, `proveedor`, `fecha` en UTC) en la respuesta de `POST /v1/analyze` y en el `structuredContent` y el `outputSchema` de `analizar_proyecto`. Es nulo cuando no se llama al modelo. Los dos campos nuevos son opcionales: el contrato anterior no cambia.
- Servidor MCP en `POST /mcp` (`MCP_ENABLED`, desactivado por defecto; exige `API_KEYS`), sobre el SDK oficial `mcp==2.3.0`: herramientas `analizar_proyecto`, `listar_normativas` y `consultar_obligaciones`, con salida estructurada. Atiende la revisión 2026-07-28 y la era del `initialize`. Guarda propia de `Origin` (`MCP_ALLOWED_ORIGINS`), clave y límite. Claves propias opcionales (`MCP_API_KEYS`) para desplegarlo junto a la web pública sin cerrar `/v1/analyze`. El informe completo va también en `structuredContent.informe`. Detalles y decisiones en `docs/mcp/README.md`.
- Servidor MCP local por stdio (`uv run --directory <repositorio> python -m app.mcp_stdio`, o `make mcp-stdio`): las mismas tres herramientas y el mismo motor que `/mcp`, en las dos eras, sin clave ni límites (el proceso es del cliente y gasta su propia clave de Groq) y con los registros por stderr. El motor se carga con stdout ya desviado a stderr, para que lo que escriben las bibliotecas al cargar no corrompa el protocolo. Es un servidor local, no un puente al Space; la decisión está en `docs/mcp/README.md`, «Modo stdio».
- Tope diario por clave en `/mcp` (`MCP_DAILY_LIMIT`, por ejemplo `200/day`; vacío o 0, sin tope): cuenta las llamadas a `analizar_proyecto` de cada clave en el mismo almacén que el cupo por minuto, después de él, y al agotarse responde 429 con `Retry-After`. Cuentan también las que salen de la caché. Un valor que no sea un único límite por día impide arrancar.
- Capa de servicio común REST/MCP (`app/service.py`): una entrada de caché por cuestionario para las dos vías y métrica `legaldev_analyze_requests_total{via}`.
- El aviso de no asesoramiento abre y cierra `respuesta_completa`, además de ir en el campo `disclaimer`, para que acompañe al informe cuando se copia o cuando un cliente solo muestra ese texto.
- `NOTICE.md`: licencias y atribución de los textos de terceros del índice (guías de la AEPD con CC BY-NC-SA 4.0, BOE, EUR-Lex y CCII). Sección «Privacidad y datos» en el README con lo que trata hoy el servicio y lo que falta por publicar.
- Modelo de respaldo (`GROQ_FALLBACK_MODEL`, por defecto `openai/gpt-oss-20b`): si el principal falla por cualquier causa se reintenta con él; evento `llm_fallback` en logs y métrica `legaldev_llm_fallback_total{reason}`.
- Comprobación del modelo al arrancar (`GROQ_VERIFY_MODEL_ON_STARTUP`): log ERROR si Groq responde 404; resultado en `/health/deep` junto a `groq_model` y `groq_fallback_model`.
- `RAGResponse.llm_model`: modelo que generó cada informe.
- `GROQ_REASONING_EFFORT` (default `low`), enviado solo a modelos `openai/gpt-oss*`.
- Verificación determinista de citas (`app/citations.py`): cada cita del informe se busca literalmente en los fragmentos recuperados; `RAGResponse.citas` y sección "Verificación de citas" al final del informe; métricas `legaldev_citations_verified_ratio` y `legaldev_citations_unverified_total`.
- Tope de chunks por normativa en el contexto (`MAX_CHUNKS_PER_SOURCE`, default 4).
- INJECTION nueva: la "Guía sobre uso de cookies - AEPD" cuando `usa_cookies=True` (k=2). Medido en el eval: al dejar de gastar plazas del reranker en normativas excluidas, sus chunks caían a las posiciones 13-14 del CrossEncoder (fuera del top-12), así que se garantiza por regla como RGPD, LSSI y CCII.
- Reranker precargado en el arranque (`warmup` en `lifespan`). La cuantización int8 se midió y se descartó: 1,6× en 2 hilos pero altera el ranking.
- `.index_meta.json` escrito por la ingesta (modelo de embeddings, versión del corpus, nº de chunks, versión del splitter); el arranque aborta si el índice se construyó con otro modelo.
- Metadato `article` en los chunks y prefijo `Artículo N (cont.):` en sub-chunks de artículos largos (activo tras reindexar).
- `tools/eval_retrieval.py --chroma-path` y comprobación de modelo del índice; `make eval-sweep`.

### Changed
- `docs/mcp/README.md`: formatos de los clientes revisados el 12/11/2026. En VS Code, `.vscode/mcp.json` es el formato del arnés *Local*, que se retira en febrero de 2027. El formato portable (`.mcp.json` con `mcpServers`) es el mismo que el de Claude Code. El README tiene ahora los pasos para probar a mano cada cliente, la sección «Latencia» y una lista única de pendientes.
- La carga del motor (índice, embeddings, clientes de Groq y reordenador) sale del `lifespan` a `app.main.load_engine`, que comparten la API y el modo stdio.
- Documentación del corpus (`docs/CORPUS_SOURCES.md`, README): títulos y fechas oficiales de las guías de la AEPD, marca «EN REVISIÓN», versiones que no incorporan correcciones o modificaciones (RGPD, Reglamento de IA, Data Act, DGA), ámbito del ENS (sector público y proveedores por contrato), búsquedas auxiliares sin filtro por fuente y estado actual del DSA.
- Índice ChromaDB reconstruido (2026-09-12) con el splitter v2 a partir de los 22 documentos descargados de sus fuentes oficiales (EUR-Lex, BOE, AEPD, CCII; ver `docs/CORPUS_SOURCES.md`): 13.756 chunks, `corpus_version` `7a2029a4dfd8`, `.index_meta.json` presente (la guardia de arranque ya verifica el modelo de embeddings). La «Directiva de Responsabilidad por Productos con IA» corresponde a la Directiva (UE) 2024/2853 en vigor.
- `GROQ_MAX_TOKENS` por defecto 4000 → 8000 (en gpt-oss los tokens de razonamiento cuentan como salida).
- Retrieval unificado en `_retrieve` (API y eval ejecutan el mismo código); timeout global `RETRIEVAL_TIMEOUT` (60 s) sustituye a `CHROMA_TIMEOUT`.
- Las EXCLUSIONS se aplican antes del recorte y del reranker: las normativas excluidas ya no consumen plazas del contexto.
- `retrieval_duration` ahora incluye las búsquedas de inyección (antes se contabilizaban en `llm_duration`).
- La ingesta construye el índice en `chroma_db.building` y solo después sustituye el anterior; descarta chunks de menos de 40 caracteres; lee PDFs con `pypdf` directamente.
- Dependencias: eliminadas `langchain` y `langchain-community`; `langchain-core` explícita.

### Fixed
- Saneado de la salida (RNF-20): tres revisiones adversarias del 12/11/2026 encontraron 10, 19 y 7 huecos en el saneado que buscaba con expresiones regulares las imágenes, los enlaces, el HTML, las URL y el código imitando la gramática de marked y de CommonMark (corchetes anidados, definiciones en listas, espacios Unicode en el destino, URL oficiales seguidas de `'@otro`, vallas que solo cierra un intérprete, acentos que marked empareja de otra forma, coste cuadrático, una caché sin límite). Cada arreglo abría otros, y solo protegía frente a marked. Se sustituyó por la codificación de la salida (ver «Added»): `app/sanitize.py` pasa de 1.355 a 575 líneas. De los arreglos quedan los que no tratan de cómo se pinta el texto: el guion blando y CRLF, los objetos JSON de llamada escritos con escapes, `<function=…>` con cualquier nombre (también con espacio de nombres o comillas), `[TOOL_CALLS]nombre[ARGS]{…}`, los cierres de las etiquetas de llamada buscados una vez y agrupados por nombre (sin la caché que crecía con cada petición), las vallas que solo cierra un intérprete y el coste lineal, con una prueba que mide el bucle de eventos. Las líneas de un bloque de código ya no se sangran: estropeaba listas legítimas. Detalle y cifras en `docs/mcp/README.md`, «Salida segura».
- Saneado de la salida (RNF-20), revisión de la codificación del 13/11/2026 (7 hallazgos, todos de antes de la codificación salvo las casillas de tareas): una llamada a una herramienta escrita con referencias de carácter (`&lt;invoke&gt;`) o con formas de ancho completo (`＜invoke＞`) llegaba entera al asistente; una apertura de llamada sin ningún `>` detrás no se quitaba, ni las siguientes; los bloques que se anuncian como llamada detrás de un marcador de lista o de cita (`- ```tool_code`) no se retiraban; un objeto JSON de llamada con una línea en blanco dentro de un bloque de código, o con las claves en otra caja, llegaba entero; un invisible escrito como referencia (`&#x202E;`) aparecía en la página. Se arreglan dentro de la codificación: el texto se lleva antes a una sola forma y se escapa el «&» de las referencias. Las casillas de las listas de tareas quedan como cambio aceptado. El README vuelve a recoger el JSON partido por una línea en blanco fuera de un bloque, que la reescritura había perdido, y corrige el peor tiempo: el 0,12 s que daba era el peor de los textos de `fuzz_tiempo.py`, no una cota; el peor caso conocido, con las 21 pasadas y una cola de párrafos JSON, tarda unos 0,6 s con 32.000 caracteres (3,5 s con 200.000), sin parar el bucle de eventos. Los fuzzers, con piezas nuevas, encontraron más formas de la misma clase (vallas de llamada que el saneado tomaba por contenido de otro bloque, un «_» de énfasis pegado al nombre de una etiqueta, un «|» o una «/» escapados), arregladas igual.
- `make mcp-dev` arranca la API con `/mcp` (seguía diciendo que el servidor MCP no estaba implementado).
- Verificación de citas: se ignoran los guiones Unicode (U+2010, U+2011, U+2012, U+2212, U+2043) que el modelo escribe donde el PDF tiene «-»; antes una cita literal partida por un guion de corte de línea se daba por no verificada.
- «Cobertura del análisis» lista primero las normativas detectadas a las que el informe no dedica sección (encabezado con su nombre o cita verificada en sus fragmentos), y `analizar_proyecto` las devuelve en `normativas_sin_desarrollar`; `consultar_obligaciones` lleva el aviso también en `structuredContent`.
- «Cobertura del análisis» lista también las normativas con un solo fragmento recuperado, que el informe no desarrolla y antes no salían en ninguna parte, y aclara que «sin fragmentos» se refiere a ese análisis.
- `make ingest` ejecuta `python -m app.ingest` (con `python app/ingest.py` el paquete `app` no se resolvía y la ingesta fallaba al importar).
- Verificación de citas: se tolera hasta un 10 % de diferencia en cada extremo del segmento (punto final añadido por el LLM, palabra cortada en el borde del chunk). Medido en producción: 4 de 12 citas literales se marcaban como no verificadas; la cita ajena al contexto sigue detectándose.
- Producción devolvía 503 en todos los análisis desde el 17/07/2026: Groq retiró `meta-llama/llama-4-scout-17b-16e-instruct`. El modelo por defecto pasa a `openai/gpt-oss-120b` (sustituto recomendado por Groq).
- `/v1/feedback`: `request_id` acotado (1–64 chars, `[A-Za-z0-9_-]`), `comment` ≤ 2000 chars, rate limit.
- `tools/diagnose_ranking.py` usaba `all-MiniLM-L6-v2` contra un índice multilingüe.
- `tools/eval_results.md` regenerado con el formato actual.
- `make ingest` no podía completar el intercambio del índice en Windows (handles de SQLite retenidos por ChromaDB); ahora se liberan explícitamente.

## [0.4.0] - 2026-06-24

### Added
- INJECTIONS incondicionales: la normativa aplicable se garantiza aunque el proyecto sea de dominio lejano (RGPD ahora se recupera en casos donde antes no). [P3]
- 2 casos nuevos en la suite de evaluación (dominio lejano + 1-chunk).

### Changed
- normativas_detectadas usa umbral ≥2 chunks: coherencia entre la normativa del header y las secciones del cuerpo. [P2a]
- Retrieval unificado en retrieve_docs_sync: el eval ejecuta ahora la misma lógica que producción (elimina la divergencia eval↔producción).

### Fixed
- filter= en la búsqueda de Chroma (antes where=): las INJECTIONS habrían lanzado TypeError con Chroma real.

## [0.3.1] - 2026-06-16

### Security
- Cerrada vía de inyección de prompt en el campo `ccaa` (ahora enum cerrado de comunidades autónomas, validado por Pydantic).

### Fixed
- Eliminados chunks duplicados en `pre_rerank` en proyectos de baja señal.
- El reranker y la llamada a Groq ya no bloquean el event loop; el servidor responde a otras peticiones (incl. `/health`) durante un análisis.

## [0.3.0] - 2026-05-25

### Added
- INJECTIONS: garantía determinista de normativa aplicable post-reranker (RGPD, EU AI Act, LSSI, IA Agéntica) según campos del cuestionario.
- EXCLUSIONS condicionales para documentos de IA (Adecuación RGPD+IA, IA Agéntica) y LOPDGDD en proyectos sin datos ni usuarios.
- Gold standard de evaluación con precision (`negative_expected`) además de recall.
- Caso de evaluación `lssi-web-publica`.

### Changed
- El evaluador (`eval_retrieval.py`) ahora replica el pipeline completo de producción (recorte `reranker_top_k`, CrossEncoder, exclusiones), corrigiendo una fidelidad optimista que ocultaba misses de recall.

### Fixed
- Recall de normativa fundamental (RGPD, EU AI Act, LSSI): de 2/10 a 11/11.
- Falsos positivos de documentos de IA en proyectos sin IA: de 16 a 2 (2 residuales de DSA, documentados).

## [0.2.0] - 2026-05-15

### Added
- Cross-encoder reranker (`BAAI/bge-reranker-base`) between overfetch and top-k slice, improving multi-normativa query precision
- Article-boundary legal splitter (`app/legal_splitter.py`) — regex splits on `Artículo`/`Considerando`/`Art.` boundaries, falls back to `RecursiveCharacterTextSplitter`
- `GET /health/deep` endpoint — pings Chroma and Groq, TTL-cached 60 s
- `POST /v1/feedback` endpoint — persists `{request_id, rating, comment}` to `feedback.jsonl`
- TTL in-memory response cache for `/v1/analyze` with `X-Cache: HIT/MISS` header
- `X-Request-ID` header on every response; `request_id` injected into all structured logs via `contextvars`
- Corpus version hash (`chroma_db/.corpus_version`) exposed in `/health` and `RAGResponse`
- Prometheus custom metrics: `legaldev_chunks_retrieved`, `legaldev_top_score`, `legaldev_retrieval_duration_seconds`, `legaldev_llm_duration_seconds`, `legaldev_404_no_coverage_total`, `legaldev_aux_search_triggered_total{type}`
- `POST /v1/analyze` threshold sweep tool (`python tools/eval_retrieval.py --sweep`) with results in `tools/eval_results.md`
- E2E test against real ChromaDB (`tests/test_e2e.py`, `@pytest.mark.slow`), runs only on push to `main`
- `TRUST_PROXY_HEADERS` env var (default `false`) — only trusts `X-Forwarded-For` when explicitly enabled
- `ALLOWED_ORIGINS` validator — rejects `*,https://...` mixed configurations
- Retrieval timeout via `asyncio.wait_for` + `asyncio.to_thread` — returns 503 instead of hanging on ChromaDB I/O; `run_pipeline` is fully async
- `app/store.py` wrapper for Chroma private API (`_collection.count`, `_collection.get`) — isolates breakage to one file
- `indexed_normativas` populated from ChromaDB at startup, not from `REQUIRED_DOCS` list
- Dockerfile layer order optimized: deps → model download → `chroma_db/` → `app/`
- PII policy in logs: `descripcion_breve` logged as length + SHA-256 prefix, never raw
- `X-API-Key` header authentication for `/v1/analyze`; open by default when `API_KEYS` env var is unset
- Prompt injection detection: `descripcion_breve` scanned for suspicious patterns; logs `suspected_injection: true` without rejecting
- `Makefile push-space` target — creates/resets `hf-space` branch with `README_hf.md` swapped in as `README.md`, force-pushes to `space` remote; see README for full workflow
- `README_hf.md` — HF Spaces frontmatter file used only in the Space repo; `README.md` stays clean for GitHub
- Git LFS tracking for `chroma_db/` binaries (`.sqlite3`, `.bin`) — required by Hugging Face Hub's 10 MB per-file limit
- `HF_HOME`, `TRANSFORMERS_CACHE`, `SENTENCE_TRANSFORMERS_HOME` → `/tmp/huggingface` in Dockerfile — HF Spaces only allows writes to `/tmp` at runtime; baked model weights remain accessible without landing on a world-writable path

### Changed
- EMBEDDING_MODEL: `all-MiniLM-L6-v2` → `paraphrase-multilingual-MiniLM-L12-v2` — better recall on Spanish legal text; the switch was previously blocked by Railway's 512 MB RAM limit and became trivial once HF Spaces removed that constraint; see README for full rationale
- `encode_kwargs={"normalize_embeddings": True}` added to every `HuggingFaceEmbeddings` instantiation (`app/ingest.py`, `app/main.py`, `tools/eval_retrieval.py`, `tests/test_e2e.py`) — `paraphrase-multilingual-MiniLM-L12-v2` has no `Normalize` module in its pipeline; without this kwarg embeddings are not unit vectors, L2 distances exceed √2, and LangChain's score formula produces negative values that break the threshold entirely
- `MIN_RELEVANCE_SCORE` default raised from `0.35` to `0.40` — sweep with the new model confirmed 100% recall at all thresholds 0.20–0.45; 0.40 gives ~8% noise reduction at no recall cost
- Deploy target: Railway → Hugging Face Spaces — Railway free tier RAM (512 MB) is too tight for `paraphrase-multilingual-MiniLM-L12-v2` (~500 MB at runtime); HF Spaces provides the headroom needed; see README for `make push-space` workflow
- "Cobertura del análisis" section rendered in code (`_render_coverage_section`) rather than by LLM — deterministic, frees prompt tokens
- `app/ingest.py` uses `split_document` from `legal_splitter` instead of inline `RecursiveCharacterTextSplitter`

### Fixed
- Dockerfile `rm -rf /tmp/*` replaced with targeted `find` deletion of `.lock` and `.incomplete` files — broad cleanup was deleting baked model weights, forcing a re-download on every cold start
- `feedback.jsonl` removed from git tracking and added to `.gitignore` — file was committed with manual test entries from development

## [0.1.0] - 2026-05-09

### Added
- RAG pipeline over 22 Spanish/EU legal documents: 10 EU normativas (RGPD, EU AI Act, NIS2, DSA, CRA, DORA, ePrivacy, Data Act, DGA, Responsabilidad IA), 4 Spanish (LOPDGDD, ENS, LSSI, LPI), Código Ético CCII, and 7 AEPD guides
- `POST /analyze` endpoint: structured questionnaire → applicable regulations with technical implications
- `GET /health` endpoint with live document count from ChromaDB
- Score-based overfetch retrieval: fetch `OVERFETCH_K` candidates, filter by `MIN_RELEVANCE_SCORE`, keep top `TOP_K_CHUNKS`
- Page-level citations in retrieved chunks
- Rate limiting on `/analyze` (configurable, default 10 req/min)
- Configurable CORS origins via `ALLOWED_ORIGINS` env var
- Groq API timeout via `GROQ_TIMEOUT` env var
- Standalone `ingest.py` script to build the vector store from PDFs
- Docker + docker-compose support
- Railway deployment via pre-built `chroma_db/` baked into the Docker image
- Mandatory legal disclaimer on every response
