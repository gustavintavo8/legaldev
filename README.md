# LegalDev

**API RAG de normativa legal para developers en España. Describe tu proyecto de software y obtén las normativas europeas y españolas que te aplican, con implicaciones técnicas concretas.**

> ⚠️ Esta herramienta es de orientación informativa y no constituye asesoramiento legal. Para decisiones con impacto legal, consulta con un abogado especializado en derecho digital.

[![Python](https://img.shields.io/badge/Python-3.11+-3776ab?logo=python&logoColor=white)](https://python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.136-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-1.5-ff6b35)](https://www.trychroma.com/)
[![Groq](https://img.shields.io/badge/Groq-gpt--oss--120b-f55036?logo=groq)](https://groq.com/)
[![HF Spaces](https://img.shields.io/badge/🤗_Space-LegalDev-yellow)](https://huggingface.co/spaces/gustavintavo8/legaldev)
[![Tests](https://img.shields.io/badge/Tests-288_passed-22c55e?logo=pytest)](./tests/)

[Highlights](#-highlights-técnicos) · [Cómo funciona](#-cómo-funciona) · [Tech Stack](#️-tech-stack) · [Decisiones técnicas](#-decisiones-técnicas) · [Instalación](#-instalación) · [API](#-api) · [Deploy](#-deploy)

---

## ⚡ Highlights técnicos

- **RAG sobre 22 documentos legales** — 10 normativas europeas (RGPD, EU AI Act, NIS2, DSA, CRA, DORA, ePrivacy, Data Act, DGA, Responsabilidad IA), 4 españolas (LOPDGDD, ENS, LSSI, LPI), Código Ético CCII y 7 guías oficiales de la AEPD, indexados en ChromaDB con embeddings locales.
- **Score threshold anti-alucinación** — Si ningún chunk supera el umbral de relevancia, devuelve 404 en vez de inventar normativas con contexto basura.
- **Temperatura 0 + citas forzadas** — El LLM no "improvisa" en dominio legal: temperatura 0 para determinismo y prompt que exige citar textualmente el fragmento que justifica cada obligación.
- **Cuestionario estructurado como query semántica** — 16 campos del formulario se mapean a términos legales que dirigen el retrieval exactamente hacia las normativas relevantes para ese proyecto.
- **Vector store pre-generado en la imagen Docker** — El `chroma_db/` se bake en el build, eliminando 30s de indexación en cold start. La API arranca en ~3s.
- **Chunks de 500 chars para documentos legales** — Artículos atómicos para retrieval preciso, frente a los típicos 1000 chars que mezclan artículos distintos.

---

## 🔍 Cómo funciona

```
POST /v1/analyze (QuestionnaireInput)
          │
          ├─ 1. Build semantic query
          │      descripcion_breve + tipo_proyecto + datos_personales + usa_ia + ccaa + ...
          │
          ├─ 2. Retrieval (_retrieve — única implementación, la usan API y eval; corre en
          │      un hilo bajo un timeout global RETRIEVAL_TIMEOUT=60s)
          │      similarity_search_with_relevance_scores(query, k=100) → score ≥ 0.40
          │      → EXCLUSIONS (5, aplicadas ANTES del recorte, no después): ENS always;
          │         LPI if !contenido_digital; Adecuación RGPD+IA and IA Agéntica AEPD
          │         if !usa_ia / !agentes; LOPDGDD if no data and no users
          │      → recorte a RERANKER_TOP_K (25)
          │      → AUXILIARY_SEARCHES (condicionales, score ≥ 0.40, sin excluidas,
          │         deduped by content hash):
          │         if tipos_datos_personales: search RGPD/LOPDGDD (k=6)
          │         if usa_cookies: search cookies AEPD (k=6)
          │         if colegiado: search CCII (k=6)
          │      → Cross-encoder rerank (BAAI/bge-reranker-base) sobre TODOS los candidatos
          │         (no solo el top-k final)
          │      → _select_diverse: top TOP_K_CHUNKS=12, máx. MAX_CHUNKS_PER_SOURCE=4
          │         chunks por normativa (evita que 1-2 guías AEPD acaparen el contexto)
          │      → INJECTIONS (6, búsqueda filtrada por fuente, sin umbral — una garantía,
          │         no una sugerencia): RGPD if personal data; EU AI Act if usa_ia; LSSI if
          │         cookies or public web; guía de cookies AEPD if usa_cookies; IA Agéntica
          │         AEPD if agentes; Código Ético CCII if colegiado
          │      → if no chunks pass: HTTP 404 (no coverage)
          │
          ├─ 3. LLM call (Groq · openai/gpt-oss-120b · temperature=0 · reasoning_effort=low)
          │      SystemPrompt: rules + mandatory citation format
          │      UserMessage: questionnaire context + retrieved chunks (con artículo si
          │      el chunk proviene de uno)
          │      → fallback: openai/gpt-oss-20b si el principal falla (modelo retirado, 429, 5xx)
          │
          ├─ 4. Verificación de citas (app/citations.py)
          │      cada cita del informe se busca literalmente (normalizada) en los chunks
          │      recuperados — determinista, no altera la respuesta del LLM
          │
          └─ 5. RAGResponse
                 respuesta_completa  ← LLM output + "## Cobertura del análisis"
                                        + "## Verificación de citas"
                 normativas_detectadas ← unique sources con ≥ 2 chunks recuperados
                 chunks_utilizados · citas {total, verificadas, no_verificadas}
                 disclaimer · llm_model · corpus_version
```

**Indexación offline** (una vez, antes del Docker build):
```
docs/*.pdf → pypdf → legal_splitter (Artículo/Art./Considerando boundaries, metadato
           →          "article", sub-chunks largos con prefijo "Artículo N (cont.): "
           →          → fallback RecursiveCharacterTextSplitter)
           → filtro ≥ MIN_CHUNK_CHARS=40 (se conservan los chunks con artículo aunque
           →          sean más cortos — solo se descarta ruido de cabecera/pie de página)
           → HuggingFaceEmbeddings(paraphrase-multilingual-MiniLM-L12-v2)
           → ChromaDB en chroma_db.building/ → .corpus_version + .index_meta.json
           → swap atómico a chroma_db/ (nunca se borra el índice viejo antes de tener el nuevo)
```

---

## 🛠️ Tech Stack

```
API framework      FastAPI 0.136 + uvicorn
Vector store       ChromaDB 1.5 (local, SQLite-backed)
Embeddings         sentence-transformers · paraphrase-multilingual-MiniLM-L12-v2 (~500 MB)
Reranker           CrossEncoder BAAI/bge-reranker-base (precargado en el arranque)
PDF loading        pypdf (lectura directa; ya no depende de LangChain para cargar PDFs)
LLM                Groq API · openai/gpt-oss-120b (respaldo openai/gpt-oss-20b)
Prompt framework   LangChain (langchain-core, langchain-chroma, langchain-groq, langchain-text-splitters)
Rate limiting      slowapi (token bucket por IP)
Validation         Pydantic v2 + pydantic-settings
Testing            pytest · unittest.mock (sin llamadas reales a Groq ni ChromaDB)
Packaging          pyproject.toml + uv.lock · dev/runtime separados
Deploy             Hugging Face Spaces (Docker SDK) · chroma_db baked en imagen
```

---

## 🧠 Decisiones técnicas

### RAG en vez de fine-tuning

Fine-tuning modifica el comportamiento del modelo; RAG le da acceso a información que no tiene. Los documentos legales son extensos (el RGPD tiene 88 páginas, el EU AI Act 144) y se actualizan con cierta frecuencia — nuevas guías de la AEPD, actualizaciones de normativas. Con RAG, añadir un documento nuevo es cuestión de copiarlo en `docs/` y re-ejecutar `ingest.py`. Fine-tuning requeriría re-entrenar, lo que es inviable en términos de coste y tiempo para un proyecto open source.

### ChromaDB local en vez de Pinecone o Qdrant

Para un corpus de 22 documentos con ~14.300 chunks fijos que no cambian en runtime, una base vectorial en disco es suficiente y tiene latencia de consulta < 10ms. Pinecone añadiría latencia de red (~80-150ms por query), coste mensual y una dependencia de servicio externo. ChromaDB persiste en SQLite con su propio formato binario y se copia directamente al Docker image sin configuración adicional.

### Embeddings pre-generados, no en startup

La indexación de 22 PDFs tarda ~45 segundos e implica descargar el modelo de sentence-transformers (~80 MB) la primera vez. Ejecutar `ingest.py` en startup de la API añadiría ese overhead a cada cold start en Railway. La solución es generar el `chroma_db/` localmente, commitearlo al repo, y bakearlo en la imagen Docker. La API solo hace retrieval — carga el modelo de embeddings para las queries (~2s) y ya está. El `chroma_db/` pesa ~100 MB en el repo (vectores HNSW + SQLite); es el trade-off consciente que hacemos a cambio de cold starts < 3s sin infraestructura adicional.

### paraphrase-multilingual-MiniLM-L12-v2 en vez de all-MiniLM-L6-v2

Originalmente usábamos `all-MiniLM-L6-v2` (~80 MB): el modelo multilingual (~500 MB) crasheaba en el free tier de Railway (512 MB de RAM). Al migrar a Hugging Face Spaces, ese límite dejó de ser el cuello de botella, y el cambio de modelo pasó de bloqueado a trivial.

`paraphrase-multilingual-MiniLM-L12-v2` fue entrenado en 50+ idiomas con texto nativo en español — mejora el recall en consultas con terminología jurídica española ("responsable del tratamiento", "bases legitimadoras", "interés legítimo"). `all-MiniLM-L6-v2` funcionaba gracias al overlap léxico español-inglés en su corpus, pero las representaciones de pares como "protección de datos" / "data protection" eran subóptimas para búsqueda semántica estricta. El cambio es una sola línea en `EMBEDDING_MODEL` — y exige re-indexar el `chroma_db/` porque los vectores generados por un modelo no son compatibles con los del otro.

### Score threshold como guardia anti-alucinación

Sin umbral, el retriever siempre devuelve `k` chunks aunque la query tenga poca cobertura en la base de documentos. El LLM, ante chunks poco relevantes, tiende a completar con conocimiento paramétrico — inventando obligaciones plausibles pero no fundamentadas. El umbral de 0.40 (configurable vía `MIN_RELEVANCE_SCORE`) hace que si ningún chunk supera ese score, la API devuelva HTTP 404 con "no se encontraron normativas aplicables" en vez de pasarle contexto basura al modelo.

> **Prerrequisito: embeddings normalizados.** La escala del score `[-0.41, 1]` solo es válida cuando los embeddings son vectores unitarios. LangChain-Chroma calcula el score con la fórmula `1 - d/√2`, donde `d` es la distancia L2. Para vectores de norma 1, `d ∈ [0, 2]` y el score queda acotado en `[-0.41, 1]`. Sin normalización, `d` puede superar `√2` y el score se vuelve indefinidamente negativo — cualquier threshold falla y el retrieval devuelve vacío.
>
> No todos los modelos de `sentence-transformers` incluyen un módulo `Normalize` al final de su pipeline: `all-MiniLM-L6-v2` sí lo lleva; `paraphrase-multilingual-MiniLM-L12-v2` no. Por eso **todo `HuggingFaceEmbeddings` instanciado en este proyecto debe incluir `encode_kwargs={"normalize_embeddings": True}`**. Quien añada un modelo nuevo debe verificar si su pipeline termina en `Normalize` — si no, el kwarg es obligatorio o los scores serán inútiles.

### Temperatura 0 para respuestas legales

La creatividad del LLM es un defecto en dominio legal. Temperatura 0 selecciona siempre el token más probable en cada paso, produciendo respuestas deterministas y pegadas al texto de los documentos. Una misma consulta con temperatura 0.7 puede generar respuestas distintas en cada llamada — inaceptable cuando el output se presenta como interpretación de normativas.

### Citas textuales forzadas en el prompt

El system prompt no solo dice "no inventes normativas". Exige que cada obligación técnica vaya acompañada de la cita literal del fragmento que la justifica:
```
> "[cita textual del fragmento]" — {Nombre normativa}
```
Esto ancla cada afirmación del modelo a texto real de los documentos. Si el modelo no puede citar, no puede incluir la obligación. Es el mecanismo de grounding más efectivo sin necesidad de un reranker o un paso de verificación adicional.

### Chunk size 500 en vez de 1000

Los documentos legales tienen artículos cortos y bien delimitados. Un chunk de 1000 chars a menudo captura partes de dos artículos distintos — un artículo sobre consentimiento y otro sobre datos de menores, por ejemplo. Al hacer retrieval, ese chunk aparece en queries sobre ambos temas pero no es específico en ninguno de los dos. Chunks de 500 chars con overlap de 100 producen fragmentos atómicos (un artículo o parte de él) que el retriever puede posicionar con más precisión.

### Cuestionario estructurado como interfaz de entrada

En vez de texto libre ("tengo una app de salud para menores"), el cuestionario extrae campos específicos que se mapean directamente a términos legales en `_build_query()`. `descripcion_breve` encabeza la query — el texto del developer define el contexto base, y los campos estructurados añaden términos legales específicos a continuación. `usuarios_menores=True` → añade "usuarios menores de edad" a la query semántica, que dirigirá el retrieval hacia artículos del RGPD sobre menores y la guía AEPD correspondiente. `usa_ia=True + tipo_ia="generativa"` → "inteligencia artificial generativa", que apunta al EU AI Act. Esta traducción estructurada produce queries semánticamente ricas sin depender de que el usuario sepa qué palabras clave usar.

### Query descriptiva + búsqueda auxiliar por dominio

El retrieval usa una sola query semántica construida desde el cuestionario. El problema: las guías operativas de la AEPD (cookies, análisis de riesgos, privacidad por diseño) tienen centenares de chunks muy específicos que repiten sus términos clave en cada uno. Cuando el cuestionario incluye `usa_cookies=True`, la palabra "cookies" en la query hacía que la *Guía sobre uso de cookies* ocupara las primeras 100+ posiciones del ranking por densidad léxica — desplazando RGPD a la posición #142 y EU AI Act fuera del top 200, aunque ambos sean directamente aplicables.

Medición sobre 5 cuestionarios representativos:

| Query | RGPD (antes) | RGPD (después) | EU AI Act (antes) | Cookies AEPD |
|-------|-------------|----------------|-------------------|--------------|
| SaaS B2B con cookies + IA | #142 | #2 | no aparece | #98 |
| Ecommerce con cookies | #52 | #5 | #30 | #57 |
| App de salud con IA (sin cookies) | #6 | #6 | #30 | sin cambio |

La solución: la query principal no menciona "cookies" — describe el proyecto, sus datos y sus señales regulatorias generales. El mismo problema se detectó para RGPD/LOPDGDD (posición #29 con `overfetch_k=100` en queries complejas) y para el Código Ético CCII. El patrón se generalizó a `AUXILIARY_SEARCHES`: una lista de búsquedas condicionales que se activan cuando su condición es verdadera, deduplicando por hash de contenido. Todas aplican el mismo umbral `MIN_RELEVANCE_SCORE=0.40`.

| Aux search | Condición | Query |
|------------|-----------|-------|
| RGPD/LOPDGDD | `tipos_datos_personales != ["ninguno"]` | `"protección datos personales responsable tratamiento..."` |
| Cookies AEPD | `usa_cookies=True` | `"cookies consentimiento banner rastreo..."` |
| CCII | `colegiado=True` | `"código deontológico ingeniero informático..."` |

### Filtrado por reglas: EXCLUSIONS e INJECTIONS

El reranker (CrossEncoder) selecciona los fragmentos más accionables para el developer, pero esa optimización tiene un efecto colateral: prefiere las guías explicativas de la AEPD sobre el texto legal puro de los reglamentos, porque son más útiles para responder "¿qué tengo que cumplir?". El resultado es que la propia normativa que aplica puede no llegar a la respuesta, y que documentos temáticamente cercanos se cuelan aunque no apliquen al proyecto.

Para resolverlo, dos capas de reglas deterministas —condicionadas por los campos del cuestionario— rodean al reranker: **EXCLUSIONS** actúa antes (ver "Exclusiones antes del reranker y tope por fuente" más abajo) y **INJECTIONS** después.

**EXCLUSIONS** (5 reglas) eliminan documentos que no aplican al proyecto: el ENS (siempre — regula sector público, dato no capturado), la Ley de Propiedad Intelectual (salvo contenido digital), los dos documentos de IA de la AEPD (salvo que el proyecto use IA, y en el caso de IA Agéntica, salvo que sea específicamente de tipo agentes), y la LOPDGDD en proyectos sin datos personales ni usuarios registrados.

**INJECTIONS** (6 reglas) garantizan la normativa que sí aplica, inyectando sus mejores fragmentos (búsqueda filtrada por fuente, sin umbral) después del reranker: el RGPD cuando hay datos personales, el EU AI Act cuando se usa IA, la LSSI en webs públicas o con cookies, la guía de cookies de la AEPD cuando el proyecto usa cookies, la guía de IA Agéntica cuando el proyecto es de agentes, y el Código Ético CCII cuando el responsable es colegiado.

La distinción de fondo: **qué leyes aplican es una cuestión de reglas, no de similitud semántica.** El reranker decide qué fragmentos son útiles; las reglas de dominio deciden qué normativa es obligatoria.

### Evaluación: gold standard con precision y fidelidad a producción

El retrieval se evalúa contra un gold standard de 13 casos que cubren las combinaciones representativas del cuestionario (datos personales, IA, cookies, colegiación, proyectos fuera de dominio). Cada caso define no solo qué normativas deben aparecer (recall) sino cuáles no deben aparecer (precision, vía `negative_expected`).

La decisión de diseño más importante de esta evaluación fue hacerla fiel a producción. Una primera versión medía el recall sobre los ~100 candidatos del retrieval vectorial, pero producción aplica un recorte (`reranker_top_k=25`), el CrossEncoder y las exclusiones antes de construir la respuesta. Ese desfase hacía que el eval reportara como "recuperados" documentos que producción descartaba silenciosamente. Al alinear el eval con el pipeline real, salió a la luz que el RGPD —la normativa más básica del sistema— solo llegaba a la respuesta en 2 de 10 casos: rankeaba en posiciones 46-90 del retrieval vectorial y el reranker lo descartaba en favor de las guías. El problema no era visible porque el instrumento de medida no replicaba el sistema medido.

Esto motivó la arquitectura de EXCLUSIONS + INJECTIONS. Resultados, medidos sobre el eval ya fiel:

| Métrica | Antes | Después |
|---|---|---|
| Recall (normativa aplicable presente) | 2/10 | 11/11 |
| Falsos positivos | 16 | 2 |

Los falsos positivos se redujeron mediante las EXCLUSIONS condicionales; el recall se garantizó mediante las INJECTIONS. La lección: un sistema de evaluación que no replica producción no solo es incompleto, es activamente engañoso, porque genera confianza falsa.

### Groq en vez de OpenAI

Groq ofrece un Developer Plan gratuito con 500.000 tokens/día y latencias de ~200ms por respuesta gracias a su hardware LPU. Para un proyecto open source dirigido a developers individuales, el coste cero en inferencia es fundamental.

El modelo por defecto es `openai/gpt-oss-120b` (131k de contexto, 65k de salida). Groq retira modelos con pocos meses de aviso —`llama-4-scout`, el modelo original de LegalDev, dejó de existir el 17/07/2026 y la API estuvo devolviendo 503 hasta detectarlo—, así que el sistema (1) comprueba al arrancar que `GROQ_MODEL` existe (`GET /openai/v1/models/{model}`) y lo registra en `/health/deep`, (2) mantiene un segundo modelo (`GROQ_FALLBACK_MODEL`, por defecto `openai/gpt-oss-20b`) al que recurre si el principal falla por cualquier causa, y (3) informa en cada respuesta qué modelo la generó (`llm_model`). En gpt-oss los tokens de razonamiento cuentan como salida: `GROQ_REASONING_EFFORT=low` y `GROQ_MAX_TOKENS=8000`.

### Un solo retrieval para API y eval

El retrieval vivía por duplicado: `run_pipeline` (la ruta async de producción, con timeouts por búsqueda) y `retrieve_docs_sync` (la ruta síncrona que usa el evaluador) implementaban la misma secuencia —construir la query, buscar, aplicar auxiliares, rerankear, excluir, inyectar— en dos sitios distintos, sujetos solo por tres comentarios `keep in sync` y un único test de sincronía. Cualquier cambio en el retrieval, como los de este mismo sprint, había que hacerlo dos veces y confiar en que no divergieran.

Ahora `_retrieve(inp, vs, threshold) -> RetrievalResult` es la única implementación. Es síncrona porque tanto ChromaDB como el CrossEncoder son bloqueantes; `run_pipeline` la ejecuta con `asyncio.to_thread` bajo un único `asyncio.wait_for(timeout=settings.retrieval_timeout)` — un timeout global (`RETRIEVAL_TIMEOUT=60`) que sustituye al timeout por búsqueda que había antes (`CHROMA_TIMEOUT=10`), porque el cuello de botella real es el reranker (hasta ~20 s en el tier gratuito de HF Spaces), no una consulta individual a Chroma. `retrieve_docs_sync` queda como un envoltorio de una línea que devuelve `RetrievalResult.docs`, así que `tools/eval_retrieval.py` ejecuta exactamente el mismo código que `/v1/analyze`: la columna **Fuentes** que reporta el evaluador (número de normativas distintas en el contexto final) es la misma cuenta que decide qué secciones abre el informe.

### Exclusiones antes del reranker y tope por fuente

El reranker devolvía un top-12 y las EXCLUSIONS se aplicaban después, sobre ese top-12 ya cerrado: una normativa que sabíamos que no aplicaba (el ENS sin sector público, la Ley de Propiedad Intelectual sin contenido digital, las guías de IA sin IA) ya había ocupado una plaza del recorte a 25 candidatos y del top-12 del CrossEncoder, desplazando a normativas que sí aplican. Medido sobre los 13 casos del eval con el CrossEncoder real:

| Caso | Excluidos tras el recorte (antes) | Contexto del reranker (antes) |
|---|---|---|
| datos-sensibles-salud | 2 (Adecuación RGPD+IA, ENS) | 10 |
| ia-agente | 1 (ENS) | 11 |
| ccii-ingeniero-colegiado | 1 (ENS) | 11 |
| query-compleja-rgpd-colegiado-ia | 3 (IA Agéntica, ENS ×2) | 9 |
| sin-datos-personales | 3 (LPI, ENS ×2) | 9 |

El orden nuevo aplica las EXCLUSIONS justo después de la búsqueda principal, antes del recorte a `RERANKER_TOP_K` (25) y antes de las auxiliares: una normativa excluida ya no compite por una plaza. El CrossEncoder rankea siempre el conjunto completo de candidatos (`rerank(query, docs, top_k=len(docs))`, no solo los 12 finales) y `_select_diverse` recorre ese orden completo aceptando como máximo `MAX_CHUNKS_PER_SOURCE` (4) fragmentos de la misma normativa, rellenando las plazas sobrantes con lo que quedó fuera del tope — antes de este cambio, el top-12 solía estar compuesto por 5-6 chunks de una sola guía AEPD (p. ej. "Privacidad desde el Diseño") más 5 de LOPDGDD, como en menores-datos-personales o ia-generativa.

El efecto combinado de ambos cambios (exclusiones antes del recorte + tope de 4 por fuente) sobre el eval completo, manteniendo recall 13/13 y 0 falsos positivos:

| Caso | Chunks antes | Fuentes antes | Chunks después | Fuentes después |
|---|---|---|---|---|
| rgpd-lopdgdd-basico | 14 | 5 | 15 | 7 |
| datos-sensibles-salud | 13 | 5 | 15 | 6 |
| ia-generativa | 18 | 5 | 18 | 8 |
| ia-agente | 19 | 6 | 20 | 9 |
| menores-datos-personales | 15 | 4 | 15 | 7 |
| cookies-webapp | 16 | 7 | 19 | 7 |
| ccii-ingeniero-colegiado | 16 | 5 | 17 | 5 |
| query-compleja-rgpd-colegiado-ia | 19 | 9 | 24 | 10 |
| lssi-web-publica | 16 | 6 | 17 | 6 |
| sin-datos-personales | 9 | 3 | 12 | 4 |
| off-topic-recetas | 5 | 2 | 5 | 2 |
| probe-8-plantas-dominio-lejano | 16 | 7 | 19 | 7 |
| sin-ia-sin-cookies-app-basica | 14 | 5 | 15 | 5 |

"Fuentes" no baja en ningún caso y sube en la mayoría. Este mismo eval, corriendo con el nuevo orden, sacó a la luz un efecto colateral útil: al dejar de gastar plazas del reranker en normativas excluidas, la guía de cookies de la AEPD pasó a caer en las posiciones 13-14 del CrossEncoder —justo fuera del top-12— en los proyectos con `usa_cookies=True`. La solución fue tratarla como una garantía más: se añadió como INJECTION, igual que RGPD, LSSI o el Código CCII.

### Verificación de citas en código

El `SYSTEM_PROMPT` exige que cada obligación vaya acompañada de una cita textual entre comillas, con normativa y página — es el mecanismo de grounding que este documento lleva describiendo desde el principio. Pero hasta este sprint nadie comprobaba que esas citas fueran reales: un modelo a temperatura 0 puede parafrasear o interpolar dentro de las comillas con total naturalidad, y no había forma de saberlo sin abrir el PDF al lado.

`app/citations.py` es un módulo puro (sin red, sin LangChain) que hace esa comprobación de forma determinista. `extract_quotes` recorre las líneas de blockquote (`> "..." — Normativa, p. X`) del informe y captura el texto entre comillas; `verify_citations` normaliza cada cita y cada chunk recuperado con NFKC + `casefold` y elimina **todo el espacio en blanco**, además de comillas y guiones, antes de comparar. Ese nivel de normalización —no solo minúsculas, también espacios— existe porque el texto extraído de los PDFs trae artefactos de extracción ("tratamient o", "prot ecci ón") y saltos de línea con guion que el LLM corrige de forma natural al citar; comparando cadena a cadena con esos espacios de por medio, citas perfectamente reales se habrían marcado como no verificadas. Las citas con elipsis (`...`, `…`) se dividen en segmentos, y cada segmento de 12 o más caracteres debe aparecer en el corpus recuperado; una cita sin segmentos suficientemente largos cuenta como no verificada — es una guardia conservadora, no optimista.

El resultado se expone en `RAGResponse.citas` (`total`, `verificadas`, `no_verificadas`) y, cuando hay al menos una cita, en una sección final del informe, "## Verificación de citas". Qué NO hace este módulo: no bloquea ni reescribe la respuesta del LLM, y no decide si el informe se sirve o no — es información añadida para que quien lo lea sepa cuánto confiar en cada cita, no un filtro. Verificarlo en código es determinista, gratis en latencia de LLM y trivial de testear; pedirle al propio modelo que se autoverifique no tiene ninguna de esas tres propiedades.

### Medir antes de construir: BM25, guardia por reranker e int8

Tres ideas que sonaban razonables sobre el papel se midieron antes de escribir código de producción, y las tres se descartaron con datos:

- **Retrieval híbrido BM25 + denso (RRF, k=60).** BM25 rescata normativas que el retrieval denso entierra (RGPD pasa de la posición #44 a la #10, Código CCII de #76 a #5, la guía de cookies de #100 a #25), pero pierde por completo el EU AI Act (#18 en denso, fuera del top-100 en BM25 puro, #39 tras la fusión) y cuesta +200–270 ms/query en Python puro. Sin un gold standard a nivel de chunk no hay forma de demostrar que el contexto final mejora, solo que cambia — queda diferido (spec, sección 9).
- **Guardia anti-alucinación sobre la puntuación del reranker**, pensada para sustituir el umbral de similitud casi inútil (ver "Limitaciones conocidas"). Descartada: en `off-topic-recetas` el CrossEncoder puntúa "Privacidad desde el Diseño" con 0,37 y "Deber de informar" con 0,20, mientras que en `ccii-ingeniero-colegiado` los chunks correctos del Código CCII puntúan 0,05–0,07. El reranker ordena por género textual (guías explicativas por encima del texto legal plano), no por aplicabilidad, así que un umbral que filtrase ese ruido off-topic filtraría también normativa correcta.
- **Cuantización dinámica int8 del reranker**, para bajar la latencia en CPU (ver "Limitaciones conocidas"). Con 2 hilos gana 1,6×, pero el top-12 solo coincide con el de fp32 en 8, 8, 8, 7 y 11 de 12 fragmentos según la query, y el orden del top-5 cambia en las 5 queries probadas.

Ninguna de las tres llegó a `main`. El único cambio que sí se implementó en el reranker fue precargarlo en el arranque (`warmup()` en `lifespan`), que no toca el ranking.

---

## 📂 Estructura del proyecto

```
legaldev/
├── app/
│   ├── main.py        # FastAPI app, lifespan, endpoints, rate limiting
│   ├── rag.py         # Pipeline: query building, retrieval, score filter, LLM call
│   ├── citations.py   # Verificación determinista de citas (extract_quotes, verify_citations)
│   ├── ingest.py      # Script de indexación offline (no importado por la app)
│   ├── models.py      # QuestionnaireInput, RAGResponse (Pydantic)
│   ├── config.py      # Settings desde .env (pydantic-settings)
│   └── corpus.py      # REQUIRED_DOCS y EMBEDDING_MODEL: fuente canónica del corpus
├── docs/              # PDFs legales (no commiteados — solo en local)
├── tests/
│   ├── conftest.py              # Fixtures y mocks (sin llamadas reales)
│   ├── test_api.py               # Tests de endpoints HTTP
│   ├── test_rag.py               # Tests del pipeline RAG y construcción de queries
│   ├── test_retrieval_selection.py # Exclusiones pre-reranker y tope por fuente
│   ├── test_citations.py         # Extracción y verificación de citas
│   ├── test_llm_fallback.py      # Factoría de cliente Groq, comprobación de modelo, respaldo
│   ├── test_lifespan_guard.py    # Guardia de arranque ante índice/modelo incompatibles
│   ├── test_ingest.py            # Tests del mapeo doc_type por documento
│   ├── test_ingest_build.py      # Carga con pypdf, filtro de chunks, swap atómico del índice
│   └── test_models.py            # Tests de validación Pydantic
├── chroma_db/         # Vector store generado por ingest.py (commiteado)
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── pyproject.toml     # Dependencias runtime + dev; lockfile en uv.lock
├── uv.lock
└── .env.example
```

---

## 🚀 Instalación

### Requisitos

- Python 3.11+
- Cuenta en [Groq](https://console.groq.com) (gratuita)
- Docker + Docker Compose (opcional)

### Setup

```bash
git clone https://github.com/gustavintavo8/legaldev
cd legaldev
uv sync                # instala runtime + dev (pytest, ruff)
cp .env.example .env   # añade tu GROQ_API_KEY
```

### Añadir los PDFs

Copia los 22 documentos en `docs/` (ver lista completa en [Normativas indexadas](#-normativas-indexadas)). Los documentos de la UE se descargan desde [EUR-Lex](https://eur-lex.europa.eu) y los españoles desde el [BOE](https://boe.es).

### Indexar

```bash
make ingest   # python app/ingest.py
```

Genera `chroma_db/`. Si falta alguno de los 22 PDFs, el script aborta con un error explícito antes de tocar el índice existente.

### Arrancar

```bash
make dev    # uvicorn app.main:app --reload → http://localhost:8000
make test   # pytest -v (288 tests, sin Groq ni ChromaDB reales)
```

---

## 🔑 Variables de entorno

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
MAX_CHUNKS_PER_SOURCE=4
MIN_RELEVANCE_SCORE=0.40
RETRIEVAL_TIMEOUT=60
RATE_LIMIT=10/minute
ALLOWED_ORIGINS=*
```

| Variable | Descripción | Default |
|----------|-------------|---------|
| `GROQ_API_KEY` | API key de [GroqCloud](https://console.groq.com) | — |
| `GROQ_MODEL` | Modelo de Groq a usar | `openai/gpt-oss-120b` |
| `GROQ_FALLBACK_MODEL` | Modelo de respaldo si el principal falla; vacío lo desactiva | `openai/gpt-oss-20b` |
| `GROQ_REASONING_EFFORT` | Esfuerzo de razonamiento (solo modelos `openai/gpt-oss*`) | `low` |
| `GROQ_VERIFY_MODEL_ON_STARTUP` | Comprueba al arrancar que `GROQ_MODEL` existe en Groq | `true` |
| `GROQ_TEMPERATURE` | Temperatura del LLM (0 = determinista) | `0.0` |
| `GROQ_MAX_TOKENS` | Límite de tokens en la respuesta del LLM | `8000` |
| `MIN_RELEVANCE_SCORE` | Umbral mínimo de relevancia para chunks | `0.40` |
| `RERANKER_TOP_K` | Candidatos de la búsqueda principal que llegan al reranker tras el recorte | `25` |
| `MAX_CHUNKS_PER_SOURCE` | Tope de chunks de una misma normativa en el contexto final (`0` desactiva) | `4` |
| `TOP_K_CHUNKS` | Tamaño del contexto final (tras reranker + tope por fuente) enviado al LLM | `12` |
| `COOKIES_K` | Chunks de la búsqueda auxiliar de cookies | `6` |
| `RGPD_K` | Chunks de la búsqueda auxiliar de RGPD/LOPDGDD | `6` |
| `COLEGIADO_K` | Chunks de la búsqueda auxiliar del CCII | `6` |
| `OVERFETCH_K` | Candidatos a recuperar antes de filtrar por score | `100` |
| `RETRIEVAL_TIMEOUT` | Timeout global del retrieval (búsquedas ChromaDB + reranker CPU), en segundos | `60` |
| `RATE_LIMIT` | Límite de requests en `/v1/analyze` | `10/minute` |
| `ALLOWED_ORIGINS` | CORS origins (coma-separados) | `*` |

Cualquier clave de `.env` que no coincida con un setting conocido se ignora (`extra="ignore"` en `Settings`) — un `.env` con una variable renombrada o retirada no rompe el arranque.

---

## 📡 API

### `POST /v1/analyze`

Recibe un cuestionario sobre el proyecto y devuelve las normativas aplicables.

```bash
curl -X POST http://localhost:8000/v1/analyze \
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

```json
{
  "respuesta_completa": "## RGPD\n\n**Consentimiento explícito** ...\n> \"El tratamiento solo será lícito si...\" — RGPD",
  "normativas_detectadas": ["RGPD", "LOPDGDD", "EU AI Act"],
  "chunks_utilizados": 8,
  "disclaimer": "⚠️ Esta información es orientativa...",
  "corpus_version": "858b81eb27fe",
  "llm_model": "openai/gpt-oss-120b",
  "citas": {"total": 8, "verificadas": 7, "no_verificadas": ["…"]}
}
```

`respuesta_completa` puede terminar con hasta dos secciones generadas en código, no por el LLM: `## Cobertura del análisis` (normativas indexadas sin fragmentos relevantes para este proyecto) y, si hay al menos una cita, `## Verificación de citas` (resume `citas.verificadas`/`citas.total` y lista las citas de `citas.no_verificadas`; ver "Verificación de citas en código" más abajo).

**Errores:**
- `404` — Ningún chunk supera el umbral de relevancia. El proyecto descrito no tiene cobertura en la base de documentos.
- `422` — Input inválido (campos obligatorios ausentes, `descripcion_breve` > 500 chars).
- `429` — Rate limit superado.
- `503` — Groq API no disponible.

### `GET /normativas`

Lista los documentos indexados en ChromaDB.

```bash
curl http://localhost:8000/normativas
# {"normativas": ["RGPD.pdf", "LOPDGDD.pdf", ...], "total": 22}
```

### `GET /health`

```bash
curl http://localhost:8000/health
# {"status": "ok", "docs_indexed": 8247}
```

### `GET /health/deep`

Comprueba ChromaDB y Groq con una llamada real (`ping`), no solo el estado de arranque.

```bash
curl http://localhost:8000/health/deep
# {"chroma": "ok", "groq": "ok", "groq_model": "openai/gpt-oss-120b", "groq_fallback_model": "openai/gpt-oss-20b", "groq_model_available_at_startup": true, "corpus_version": "858b81eb27fe"}
```

El resultado se cachea 60 segundos, así que llamadas repetidas dentro de esa ventana no vuelven a golpear Groq ni ChromaDB.

---

## 🚢 Deploy en Hugging Face Spaces

El `chroma_db/` está commiteado y el Dockerfile lo copia a la imagen. HF Spaces nunca ejecuta `ingest.py` — el vector store ya está listo en el build.

> ⚠️ El `chroma_db/` debe coincidir con el `EMBEDDING_MODEL` configurado. Tras cambiar el modelo de embeddings, re-indexar es obligatorio.

### Estrategia dos READMEs

HF Spaces requiere frontmatter YAML en `README.md` del Space. GitHub y HF son repos distintos (remotes separados), así que mantenemos dos ficheros:

- `README.md` — este fichero, para GitHub (sin frontmatter).
- `README_hf.md` — frontmatter + descripción breve, solo para el Space.

El truco: una rama local `hf-space` = `main` + un commit de intercambio de README. `make push-space` la regenera y la empuja al remote `space`. El `README.md` original y el `README_hf.md` nunca llegan tal cual al Space — solo el `README.md` ya swappeado.

### Primer despliegue

```bash
# 1. Crea el Space en https://huggingface.co/spaces (SDK: Docker, puerto: 8000)
#    Añade el repo del Space como remote:
git remote add space https://huggingface.co/spaces/<username>/legaldev

# 2. Genera el índice localmente (necesitas los 22 PDFs en docs/ y GROQ_API_KEY):
make ingest

# 3. Verifica tamaño antes de commitear (ningún archivo debe superar 50 MB):
du -sh chroma_db/
find chroma_db -size +50M   # si hay salida, NO continuar

# 4. Evalúa el retrieval con el nuevo modelo y revisa tools/eval_results.md:
python tools/eval_retrieval.py --sweep --model paraphrase-multilingual-MiniLM-L12-v2

# 5. Commitea el índice:
git add chroma_db/ && git commit -m "chore: rebuild ChromaDB index with multilingual model"
git push   # GitHub main

# 6. Añade GROQ_API_KEY como Secret en la UI del Space (Settings → Secrets)

# 7. Push al Space (swap automático de README):
make push-space
```

### Actualizaciones posteriores

```bash
# Solo si cambias PDFs o modelo (requiere re-indexación). Runbook completo,
# con verificación de .index_meta.json y del eval, en CONTRIBUTING.md
# ("Re-indexing the corpus"):
make ingest
git add chroma_db/ && git commit -m "chore: rebuild index"
git push            # GitHub main
make push-space     # HF Space (re-genera hf-space sobre el main actualizado)
```

### Qué hace make push-space

1. Verifica que no haya cambios sin commitear.
2. Sitúa la rama `hf-space` exactamente en `main` (descartando el swap commit anterior).
3. Copia `README_hf.md` → `README.md` y crea el commit de intercambio.
4. Empuja `hf-space` como `main` del remote `space` con `--force-with-lease`.
5. Vuelve a la rama original.

El `README.md` de GitHub nunca se toca; `README_hf.md` no llega al Space (solo se usa como fuente del copy).

---

## 📚 Normativas indexadas

| Documento | Tipo |
|-----------|------|
| RGPD | Normativa europea |
| EU AI Act | Normativa europea |
| Directiva NIS2 | Normativa europea |
| Directiva de Responsabilidad por Productos con IA | Normativa europea |
| Digital Services Act (Reglamento UE 2022/2065) | Normativa europea |
| Cyber Resilience Act (Reglamento UE 2024/2847) | Normativa europea |
| Directiva ePrivacy (2002/58/CE consolidada) | Normativa europea |
| Data Act (Reglamento UE 2023/2854) | Normativa europea |
| Data Governance Act (Reglamento UE 2022/868) | Normativa europea |
| DORA (Reglamento UE 2022/2554) | Normativa europea |
| LOPDGDD | Normativa española |
| Real Decreto 311/2022 ENS | Normativa española |
| LSSI | Normativa española |
| Ley de Propiedad Intelectual | Normativa española |
| Guía para el cumplimiento del deber de informar | Guía AEPD |
| Guía de Análisis de Riesgos para tratamientos de datos | Guía AEPD |
| Guía de Privacidad desde el Diseño | Guía AEPD |
| Guía sobre uso de cookies | Guía AEPD |
| Guía de Anonimización | Guía AEPD |
| Adecuación al RGPD de tratamientos que incorporan IA | Guía AEPD |
| IA Agéntica desde la perspectiva de protección de datos | Guía AEPD |
| Código Ético y Deontológico CCII | Deontología |

---

---

## ⚠️ Limitaciones conocidas

- **Los modelos de Groq se retiran.** Groq da de baja modelos con solo unos meses de aviso: `llama-4-scout`, el modelo original de LegalDev, dejó de existir el 17/07/2026 y produjo cerca de dos meses de 503 en producción hasta detectarlo. Por eso el sistema comprueba `GROQ_MODEL` al arrancar (`GROQ_VERIFY_MODEL_ON_STARTUP`), mantiene un modelo de respaldo (`GROQ_FALLBACK_MODEL`) para cuando el principal falla, e informa en cada respuesta qué modelo la generó (`llm_model`). Conviene vigilar [console.groq.com/docs/deprecations](https://console.groq.com/docs/deprecations) para anticiparse a la próxima retirada.

- **Modelo de embeddings pesado.** `paraphrase-multilingual-MiniLM-L12-v2` ocupa ~500 MB de RAM en runtime. En entornos con menos de 700 MB disponibles el startup puede fallar o ser muy lento. Ajusta el plan de hosting o usa `all-MiniLM-L6-v2` (~80 MB) si la memoria es crítica (requiere re-indexar el `chroma_db/`).

- **Corpus estático.** Las 22 normativas están indexadas a una fecha fija. LegalDev no detecta nuevas directivas, reglamentos delegados, ni modificaciones publicadas en el BOE o DOUE posteriores a la indexación. Siempre contrasta con fuentes oficiales actualizadas.

- **El LLM puede alucinar pese al grounding.** El sistema obliga a citar textualmente fragmentos recuperados, pero un modelo a temperatura 0 puede interpolar o extrapolar más allá de lo que el chunk dice. Toda respuesta debe ser revisada por un profesional antes de actuar sobre ella.

- **Cobertura limitada.** Solo están indexadas las 22 normativas de la base de conocimiento. Legislación autonómica específica, convenios colectivos sectoriales, circulares de la AEPD posteriores a 2024, o normativa de países fuera de la UE no están cubiertas.

- **Rate limit spoofeable sin proxy de confianza.** El límite de 10 req/min se aplica por IP. Sin `TRUST_PROXY_HEADERS=true` y un proxy de confianza configurado, un atacante puede enviar headers `X-Forwarded-For` arbitrarios y bypassear el límite. Actívalo solo en entornos con proxy verificado (Railway, etc.).

- **DSA como falso positivo residual.** En dos casos (web con cookies, y una plataforma de gestión con seguimiento de usuarios), el retrieval trae el Digital Services Act por proximidad semántica —vocabulario de "monitorización", "plataforma", "usuarios"— aunque jurídicamente no aplica: el DSA regula la intermediación entre terceros, no la recogida de datos en sistemas cerrados. No se excluye por regla porque el proxy disponible (`acceso_publico=False`) suprimiría también marketplaces B2B privados donde el DSA sí aplica. Cerrarlo correctamente requeriría un campo explícito `es_plataforma_intermediaria` en el cuestionario. Es una decisión consciente, no un descuido.

- **Latencia del reranking.** El CrossEncoder corre sobre CPU. Medido sobre 35 pares (query de ~740 caracteres + chunk de ~460, mediana 253 tokens, máximo 393): 6,5–8,3 s con 6 hilos (portátil de desarrollo) y 17,6–20,5 s con 2 hilos (aprox. el tier gratuito de HF Spaces). La carga del modelo desde disco cuesta otros ~2 s; desde este sprint se precarga en el arranque (`warmup()` en `lifespan`), así que ya no se paga en la primera petición real. Se evaluó acelerar con cuantización dinámica int8 y se descartó con datos: con 2 hilos gana 1,6× (17,58 → 11,06 s/query), pero el top-12 resultante solo coincide con el de fp32 en 8, 8, 8, 7 y 11 de 12 fragmentos según la query, y el orden del top-5 cambia en las 5 queries probadas (correlación de puntuaciones fp32/int8 hasta 0,23). Un contexto distinto a cambio de latencia no es aceptable cuando ese contexto decide el informe. Las vías de mejora que quedan —un reranker más pequeño, o migrar a CPU dedicada— siguen pendientes.

- **La guardia por umbral es débil, y el reranker no la sustituye.** Con el modelo multilingüe, el score de relevancia (`1 - d/√2`) vive en un rango muy comprimido: de los 100 candidatos de la búsqueda principal, pasan el umbral de 0,40 el 100 % en proyectos con vocabulario legal normal, el 49 % en un proyecto sin datos personales, el 17 % en una consulta off-topic (una app de recetas) y solo el 4 % en un dominio muy lejano (una consulta sobre plantas). El umbral solo filtra en dominios muy alejados; en cualquier proyecto con vocabulario legal pasan los 100 candidatos, así que el 404 por falta de cobertura solo es alcanzable si además no se activa ninguna INJECTION. Se evaluó sustituirlo por una guardia sobre la puntuación del CrossEncoder y se descartó con datos: en `off-topic-recetas` (una app de recetas sin usuarios ni datos) la guía "Privacidad desde el Diseño" puntúa 0,37 y "Deber de informar" 0,20, mientras que en `ccii-ingeniero-colegiado` los chunks correctos del Código CCII puntúan 0,05–0,07 — un umbral que eliminase ese ruido eliminaría también normativa correcta, porque el reranker ordena por género textual (guías explicativas por encima de texto legal), no por aplicabilidad. La aplicabilidad la siguen decidiendo EXCLUSIONS/INJECTIONS —reglas deterministas sobre el cuestionario—, no la similitud semántica.

---

## 📓 Qué aprendí construyendo esto

- **Splitter vs. retrieval: el orden importa.** Empecé con `RecursiveCharacterTextSplitter(500/100)` y los resultados parecían aceptables. Al inspeccionar chunks reales, vi que partía artículos por la mitad: un chunk terminaba con "...el responsable del trata-" y el siguiente empezaba con "miento deberá...". El reranker mejoraba eso pero no lo resolvía. Escribir el `legal_splitter.py` con regex por límites de artículo subió el recall en los casos de evaluación más que cualquier otro cambio individual.

- **Saturación léxica en retrieval multidocumento.** Para un proyecto con `tipos_datos_personales=["nombre","email"]` y `usa_cookies=true`, la query principal siempre recuperaba chunks de cookies bien rankeados, desplazando a RGPD/LOPDGDD. No era un fallo del modelo: era dilución semántica por vocabulario compartido. La solución fue añadir búsquedas auxiliares por dominio (query especializada + k propio). Aprendí que en RAG sobre corpus heterogéneos, una sola query generalmente no basta.

- **El threshold de 0.35 no era arbitrario — pero tampoco lo sabía.** Antes del sweep, ese número era una intuición. Implementar `--sweep` y ver la tabla de recall vs. ruido para 0.20–0.45 me confirmó que 0.35 estaba en el knee de la curva: por debajo hay mucho ruido sin ganancia real de recall, por encima se pierde cobertura en normativas de nicho. Ahora tengo datos que lo justifican.

- **Las APIs privadas de librerías son una trampa silenciosa.** `vectorstore._collection.count()` y `._collection.get(...)` funcionaban perfectamente. El problema era que podían romperse en cualquier minor release sin warning. Encapsularlas en `app/store.py` no fue un refactor de diseño — fue seguro de mantenimiento. Si ChromaDB cambia la API interna, hay exactamente un lugar para arreglarlo.

- **Los tests aislados del rate limiter son más difíciles de lo que parecen.** Añadir la caché de respuestas al test suite hizo que tests de middleware anteriores empezaran a fallar con 429. El problema era que los tests extra de caché agotaban el límite de 10 req/min antes de que corrieran los tests de middleware. La solución fue un fixture `autouse` que resetea el storage del limiter tras cada test. Aprendí que los efectos globales de estado (rate limiter, caché, registry de Prometheus) necesitan cleanup explícito en cada test, no solo al principio de la sesión.

- **Windows y ChromaDB en tests temporales: los archivos se niegan a borrarse.** En el test E2E, el `TemporaryDirectory` fallaba con `PermissionError` al limpiarse porque SQLite y HNSWLIB (el motor de índices de Chroma) mantenían file handles abiertos. `ignore_cleanup_errors=True` (Python 3.12+) resuelve el síntoma, pero el origen es que ChromaDB no cierra todos sus handles en `__del__`. Es el tipo de bug que solo aparece en Windows y que no encontrarás en la documentación — lo encontré inspeccionando el traceback completo del error.

- **Un modelo puede desaparecer sin que nadie te avise.** Groq retiró `llama-4-scout-17b`, el modelo con el que arrancó este proyecto, el 17/07/2026, y durante casi dos meses `POST /v1/analyze` devolvió 503 en producción sin que yo lo supiera — nada monitorizaba el modelo en sí, solo si el proceso seguía vivo. Lo encontré revisando `/health/deep` a mano, por casualidad. Ahora el arranque comprueba que `GROQ_MODEL` existe en Groq (`GROQ_VERIFY_MODEL_ON_STARTUP`), hay un `GROQ_FALLBACK_MODEL` para cuando el principal falla por cualquier motivo, y cada respuesta declara qué modelo la generó (`llm_model`). La próxima retirada se verá en `/health/deep` el mismo día, no dos meses después.

- **Medir antes de construir ahorra construir cosas que no sirven.** Antes de tocar el retrieval de este sprint medí tres ideas que sonaban bien sobre el papel — retrieval híbrido BM25+denso, una guardia anti-alucinación basada en la puntuación del reranker, y cuantización int8 del reranker — y las tres tenían datos que las descartaban (detalle en "Decisiones técnicas"): la primera pierde el EU AI Act por completo, la segunda puntúa el ruido off-topic por encima de normativa correcta, la tercera cambia el ranking para ganar velocidad. Ninguna llegó a `main`. Y el propio eval, corriendo con los cambios que sí se implementaron, encontró algo que no estaba buscando: en cuanto dejé de desperdiciar plazas del reranker en normativas excluidas, la guía de cookies de la AEPD cayó justo fuera del top-12 en vez de dentro — tuvo que convertirse en una INJECTION más, como RGPD o LSSI. Medir con el sistema real, no con la intuición, sigue siendo la parte del trabajo que más se salta y la que más rápido se paga.

---

## 📄 Licencia

MIT © 2026 gustavintavo8
