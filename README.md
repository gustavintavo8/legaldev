# LegalDev

**API RAG de normativa legal para developers en España. Describe tu proyecto de software y obtén las normativas europeas y españolas que te aplican, con implicaciones técnicas concretas.**

> ⚠️ Esta herramienta es de orientación informativa y no constituye asesoramiento legal. Para decisiones con impacto legal, consulta con un abogado especializado en derecho digital.

[![Python](https://img.shields.io/badge/Python-3.11+-3776ab?logo=python&logoColor=white)](https://python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.136-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-1.5-ff6b35)](https://www.trychroma.com/)
[![Groq](https://img.shields.io/badge/Groq-Llama_4-f55036)](https://groq.com/)
[![HF Spaces](https://img.shields.io/badge/🤗_Space-LegalDev-yellow)](https://huggingface.co/spaces/gustavintavo8/legaldev)
[![Tests](https://img.shields.io/badge/Tests-69_passed-22c55e?logo=pytest)](./tests/)

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
          ├─ 2. ChromaDB retrieval
          │      similarity_search_with_relevance_scores(query, k=100)
          │      → filter chunks where score < 0.35 → take top 12
          │      → AUXILIARY_SEARCHES (conditional, deduped by content hash):
          │         if tipos_datos_personales: search RGPD/LOPDGDD (k=6)
          │         if usa_cookies: search cookies AEPD (k=6)
          │         if colegiado: search CCII (k=6)
          │      → EXCLUSIONS: ENS always removed; LPI if not contenido_digital
          │      → if no chunks pass: HTTP 404 (no coverage)
          │
          ├─ 3. LLM call (Groq · Llama 4 Scout · temperature=0)
          │      SystemPrompt: rules + mandatory citation format
          │      UserMessage: questionnaire context + retrieved chunks
          │
          └─ 4. RAGResponse
                 respuesta_completa  ← LLM output with inline citations
                 normativas_detectadas ← unique sources from retrieved chunks
                 chunks_utilizados
                 disclaimer
```

**Indexación offline** (una vez, antes del Docker build):
```
docs/*.pdf → PyPDFLoader → RecursiveCharacterTextSplitter(500/100)
           → HuggingFaceEmbeddings(paraphrase-multilingual-MiniLM-L12-v2)
           → ChromaDB(./chroma_db)
```

---

## 🛠️ Tech Stack

```
API framework      FastAPI 0.136 + uvicorn
Vector store       ChromaDB 1.5 (local, SQLite-backed)
Embeddings         sentence-transformers · paraphrase-multilingual-MiniLM-L12-v2 (~500 MB)
LLM                Groq API · meta-llama/llama-4-scout-17b-16e-instruct
Prompt framework   LangChain (loaders, splitters, Chroma wrapper)
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

La solución: la query principal no menciona "cookies" — describe el proyecto, sus datos y sus señales regulatorias generales. El mismo problema se detectó para RGPD/LOPDGDD (posición #29 con `overfetch_k=100` en queries complejas) y para el Código Ético CCII. El patrón se generalizó a `AUXILIARY_SEARCHES`: una lista de búsquedas condicionales que se activan cuando su condición es verdadera, deduplicando por hash de contenido. Todas aplican el mismo umbral `MIN_RELEVANCE_SCORE=0.35`.

| Aux search | Condición | Query |
|------------|-----------|-------|
| RGPD/LOPDGDD | `tipos_datos_personales != ["ninguno"]` | `"protección datos personales responsable tratamiento..."` |
| Cookies AEPD | `usa_cookies=True` | `"cookies consentimiento banner rastreo..."` |
| CCII | `colegiado=True` | `"código deontológico ingeniero informático..."` |

Complementario a esto, `EXCLUSIONS` elimina chunks de normativas estructuralmente no aplicables antes de pasar el contexto al LLM: ENS (sector público, campo no disponible en el cuestionario) y LPI (solo cuando `contenido_digital=False`). "Menores", "salud" y "biométricos" fueron verificados y no presentan el mismo problema de saturación léxica.

### Groq en vez de OpenAI

Groq ofrece un Developer Plan gratuito con 500.000 tokens/día y latencias de ~200ms por respuesta gracias a su hardware LPU. Para un proyecto open source dirigido a developers individuales, el coste cero en inferencia es fundamental. El modelo elegido (`llama-4-scout-17b-16e-instruct`) tiene context window de 128k tokens y function calling fiable — más que suficiente para el tamaño de los prompts generados (cuestionario + 12-18 chunks ≈ ~5.000 tokens).

---

## 📂 Estructura del proyecto

```
legaldev/
├── app/
│   ├── main.py        # FastAPI app, lifespan, endpoints, rate limiting
│   ├── rag.py         # Pipeline: query building, retrieval, score filter, LLM call
│   ├── ingest.py      # Script de indexación offline (no importado por la app)
│   ├── models.py      # QuestionnaireInput, RAGResponse (Pydantic)
│   ├── config.py      # Settings desde .env (pydantic-settings)
│   └── corpus.py      # REQUIRED_DOCS: lista canónica de documentos indexados
├── docs/              # PDFs legales (no commiteados — solo en local)
├── tests/
│   ├── conftest.py    # Fixtures y mocks (sin llamadas reales)
│   ├── test_api.py    # Tests de endpoints HTTP
│   ├── test_rag.py    # Tests del pipeline RAG y construcción de queries
│   ├── test_ingest.py # Tests del mapeo doc_type por documento
│   └── test_models.py # Tests de validación Pydantic
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
make test   # pytest -v (69 tests, sin Groq ni ChromaDB reales)
```

---

## 🔑 Variables de entorno

```env
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
GROQ_TIMEOUT=30
GROQ_TEMPERATURE=0.0
GROQ_MAX_TOKENS=4000
CHROMA_DB_PATH=./chroma_db
DOCS_PATH=./docs
TOP_K_CHUNKS=12
COOKIES_K=6
RGPD_K=6
COLEGIADO_K=6
OVERFETCH_K=100
MIN_RELEVANCE_SCORE=0.35
RATE_LIMIT=10/minute
ALLOWED_ORIGINS=*
```

| Variable | Descripción | Default |
|----------|-------------|---------|
| `GROQ_API_KEY` | API key de [GroqCloud](https://console.groq.com) | — |
| `GROQ_MODEL` | Modelo de Groq a usar | `llama-4-scout-17b-16e-instruct` |
| `GROQ_TEMPERATURE` | Temperatura del LLM (0 = determinista) | `0.0` |
| `GROQ_MAX_TOKENS` | Límite de tokens en la respuesta del LLM | `4000` |
| `MIN_RELEVANCE_SCORE` | Umbral mínimo de relevancia para chunks | `0.35` |
| `TOP_K_CHUNKS` | Chunks de la query principal a incluir en el prompt | `12` |
| `COOKIES_K` | Chunks de la búsqueda auxiliar de cookies | `6` |
| `RGPD_K` | Chunks de la búsqueda auxiliar de RGPD/LOPDGDD | `6` |
| `COLEGIADO_K` | Chunks de la búsqueda auxiliar del CCII | `6` |
| `OVERFETCH_K` | Candidatos a recuperar antes de filtrar por score | `100` |
| `RATE_LIMIT` | Límite de requests en `/v1/analyze` | `10/minute` |
| `ALLOWED_ORIGINS` | CORS origins (coma-separados) | `*` |

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
  "disclaimer": "⚠️ Esta información es orientativa..."
}
```

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
# Solo si cambias PDFs o modelo (requiere re-indexación):
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

- **Modelo de embeddings pesado.** `paraphrase-multilingual-MiniLM-L12-v2` ocupa ~500 MB de RAM en runtime. En entornos con menos de 700 MB disponibles el startup puede fallar o ser muy lento. Ajusta el plan de hosting o usa `all-MiniLM-L6-v2` (~80 MB) si la memoria es crítica (requiere re-indexar el `chroma_db/`).

- **Corpus estático.** Las 22 normativas están indexadas a una fecha fija. LegalDev no detecta nuevas directivas, reglamentos delegados, ni modificaciones publicadas en el BOE o DOUE posteriores a la indexación. Siempre contrasta con fuentes oficiales actualizadas.

- **El LLM puede alucinar pese al grounding.** El sistema obliga a citar textualmente fragmentos recuperados, pero un modelo a temperatura 0 puede interpolar o extrapolar más allá de lo que el chunk dice. Toda respuesta debe ser revisada por un profesional antes de actuar sobre ella.

- **Cobertura limitada.** Solo están indexadas las 22 normativas de la base de conocimiento. Legislación autonómica específica, convenios colectivos sectoriales, circulares de la AEPD posteriores a 2024, o normativa de países fuera de la UE no están cubiertas.

- **Rate limit spoofeable sin proxy de confianza.** El límite de 10 req/min se aplica por IP. Sin `TRUST_PROXY_HEADERS=true` y un proxy de confianza configurado, un atacante puede enviar headers `X-Forwarded-For` arbitrarios y bypassear el límite. Actívalo solo en entornos con proxy verificado (Railway, etc.).

---

## 📓 Qué aprendí construyendo esto

- **Splitter vs. retrieval: el orden importa.** Empecé con `RecursiveCharacterTextSplitter(500/100)` y los resultados parecían aceptables. Al inspeccionar chunks reales, vi que partía artículos por la mitad: un chunk terminaba con "...el responsable del trata-" y el siguiente empezaba con "miento deberá...". El reranker mejoraba eso pero no lo resolvía. Escribir el `legal_splitter.py` con regex por límites de artículo subió el recall en los casos de evaluación más que cualquier otro cambio individual.

- **Saturación léxica en retrieval multidocumento.** Para un proyecto con `tipos_datos_personales=["nombre","email"]` y `usa_cookies=true`, la query principal siempre recuperaba chunks de cookies bien rankeados, desplazando a RGPD/LOPDGDD. No era un fallo del modelo: era dilución semántica por vocabulario compartido. La solución fue añadir búsquedas auxiliares por dominio (query especializada + k propio). Aprendí que en RAG sobre corpus heterogéneos, una sola query generalmente no basta.

- **El threshold de 0.35 no era arbitrario — pero tampoco lo sabía.** Antes del sweep, ese número era una intuición. Implementar `--sweep` y ver la tabla de recall vs. ruido para 0.20–0.45 me confirmó que 0.35 estaba en el knee de la curva: por debajo hay mucho ruido sin ganancia real de recall, por encima se pierde cobertura en normativas de nicho. Ahora tengo datos que lo justifican.

- **Las APIs privadas de librerías son una trampa silenciosa.** `vectorstore._collection.count()` y `._collection.get(...)` funcionaban perfectamente. El problema era que podían romperse en cualquier minor release sin warning. Encapsularlas en `app/store.py` no fue un refactor de diseño — fue seguro de mantenimiento. Si ChromaDB cambia la API interna, hay exactamente un lugar para arreglarlo.

- **Los tests aislados del rate limiter son más difíciles de lo que parecen.** Añadir la caché de respuestas al test suite hizo que tests de middleware anteriores empezaran a fallar con 429. El problema era que los tests extra de caché agotaban el límite de 10 req/min antes de que corrieran los tests de middleware. La solución fue un fixture `autouse` que resetea el storage del limiter tras cada test. Aprendí que los efectos globales de estado (rate limiter, caché, registry de Prometheus) necesitan cleanup explícito en cada test, no solo al principio de la sesión.

- **Windows y ChromaDB en tests temporales: los archivos se niegan a borrarse.** En el test E2E, el `TemporaryDirectory` fallaba con `PermissionError` al limpiarse porque SQLite y HNSWLIB (el motor de índices de Chroma) mantenían file handles abiertos. `ignore_cleanup_errors=True` (Python 3.12+) resuelve el síntoma, pero el origen es que ChromaDB no cierra todos sus handles en `__del__`. Es el tipo de bug que solo aparece en Windows y que no encontrarás en la documentación — lo encontré inspeccionando el traceback completo del error.

---

## 📄 Licencia

MIT © 2026 gustavintavo8
