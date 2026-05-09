# LegalDev

**API RAG de normativa legal para developers en España. Describe tu proyecto de software y obtén las normativas europeas y españolas que te aplican, con implicaciones técnicas concretas.**

> ⚠️ Esta herramienta es de orientación informativa y no constituye asesoramiento legal. Para decisiones con impacto legal, consulta con un abogado especializado en derecho digital.

[![Python](https://img.shields.io/badge/Python-3.11+-3776ab?logo=python&logoColor=white)](https://python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.136-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-1.5-ff6b35)](https://www.trychroma.com/)
[![Groq](https://img.shields.io/badge/Groq-Llama_4-f55036)](https://groq.com/)
[![Railway](https://img.shields.io/badge/Deploy-Railway-0b0d0e?logo=railway)](https://railway.app/)
[![Tests](https://img.shields.io/badge/Tests-49_passed-22c55e?logo=pytest)](./tests/)

[Highlights](#-highlights-técnicos) · [Cómo funciona](#-cómo-funciona) · [Tech Stack](#️-tech-stack) · [Decisiones técnicas](#-decisiones-técnicas) · [Instalación](#-instalación) · [API](#-api) · [Deploy](#-deploy)

---

## ⚡ Highlights técnicos

- **RAG sobre 22 documentos legales** — RGPD, EU AI Act, DSA, CRA, DORA, LOPDGDD, ENS, LSSI y 7 guías oficiales de la AEPD, indexados en ChromaDB con embeddings locales.
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
          │      tipo_proyecto + datos_personales + usa_ia + cookies + ccaa + ...
          │
          ├─ 2. ChromaDB retrieval
          │      similarity_search_with_relevance_scores(query, k=24)
          │      → filter chunks where score < 0.2
          │      → if no chunks pass: HTTP 404 (no coverage)
          │      → take top 8
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
           → HuggingFaceEmbeddings(all-MiniLM-L6-v2)
           → ChromaDB(./chroma_db)
```

---

## 🛠️ Tech Stack

```
API framework      FastAPI 0.136 + uvicorn
Vector store       ChromaDB 1.5 (local, SQLite-backed)
Embeddings         sentence-transformers · all-MiniLM-L6-v2 (~80 MB)
LLM                Groq API · meta-llama/llama-4-scout-17b-16e-instruct
Prompt framework   LangChain (loaders, splitters, Chroma wrapper)
Rate limiting      slowapi (token bucket por IP)
Validation         Pydantic v2 + pydantic-settings
Testing            pytest · unittest.mock (sin llamadas reales a Groq ni ChromaDB)
Deploy             Railway via Dockerfile · chroma_db baked en imagen
```

---

## 🧠 Decisiones técnicas

### RAG en vez de fine-tuning

Fine-tuning modifica el comportamiento del modelo; RAG le da acceso a información que no tiene. Los documentos legales son extensos (el RGPD tiene 88 páginas, el EU AI Act 144) y se actualizan con cierta frecuencia — nuevas guías de la AEPD, actualizaciones de normativas. Con RAG, añadir un documento nuevo es cuestión de copiarlo en `docs/` y re-ejecutar `ingest.py`. Fine-tuning requeriría re-entrenar, lo que es inviable en términos de coste y tiempo para un proyecto open source.

### ChromaDB local en vez de Pinecone o Qdrant

Para un corpus de 22 documentos con ~8.000 chunks fijos que no cambian en runtime, una base vectorial en disco es suficiente y tiene latencia de consulta < 10ms. Pinecone añadiría latencia de red (~80-150ms por query), coste mensual y una dependencia de servicio externo. ChromaDB persiste en SQLite con su propio formato binario y se copia directamente al Docker image sin configuración adicional.

### Embeddings pre-generados, no en startup

La indexación de 22 PDFs tarda ~45 segundos e implica descargar el modelo de sentence-transformers (~80 MB) la primera vez. Ejecutar `ingest.py` en startup de la API añadiría ese overhead a cada cold start en Railway. La solución es generar el `chroma_db/` localmente, commitearlo al repo, y bakearlo en la imagen Docker. La API solo hace retrieval — carga el modelo de embeddings para las queries (~2s) y ya está.

### all-MiniLM-L6-v2 en vez de paraphrase-multilingual-MiniLM-L12-v2

El modelo multilingual daría mejores embeddings para texto en español, pero ocupa ~500 MB de RAM. El free tier de Railway tiene 512 MB — crasheaba en startup. `all-MiniLM-L6-v2` ocupa ~80 MB y funciona suficientemente bien en español gracias al overlap léxico entre idiomas en su corpus de entrenamiento. Es un trade-off consciente: calidad de embeddings vs viabilidad en free tier. Si el proyecto escala a un plan con más RAM, el cambio de modelo es una línea en `EMBEDDING_MODEL`.

### Score threshold como guardia anti-alucinación

Sin umbral, el retriever siempre devuelve `k` chunks aunque la query tenga poca cobertura en la base de documentos. El LLM, ante chunks poco relevantes, tiende a completar con conocimiento paramétrico — inventando obligaciones plausibles pero no fundamentadas. El umbral de 0.2 (configurable vía `MIN_RELEVANCE_SCORE`) hace que si ningún chunk supera ese score, la API devuelva HTTP 404 con "no se encontraron normativas aplicables" en vez de pasarle contexto basura al modelo.

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

En vez de texto libre ("tengo una app de salud para menores"), el cuestionario extrae campos específicos que se mapean directamente a términos legales en `_build_query()`. `usuarios_menores=True` → añade "usuarios menores de edad" a la query semántica, que dirigirá el retrieval hacia artículos del RGPD sobre menores y la guía AEPD correspondiente. `usa_ia=True + tipo_ia="generativa"` → "inteligencia artificial generativa", que apunta al EU AI Act. Esta traducción estructurada produce queries semánticamente ricas sin depender de que el usuario sepa qué palabras clave usar.

### Groq en vez de OpenAI

Groq ofrece un Developer Plan gratuito con 500.000 tokens/día y latencias de ~200ms por respuesta gracias a su hardware LPU. Para un proyecto open source dirigido a developers individuales, el coste cero en inferencia es fundamental. El modelo elegido (`llama-4-scout-17b-16e-instruct`) tiene context window de 128k tokens y function calling fiable — más que suficiente para el tamaño de los prompts generados (cuestionario + 8 chunks ≈ ~3.000 tokens).

---

## 📂 Estructura del proyecto

```
legaldev/
├── app/
│   ├── main.py        # FastAPI app, lifespan, endpoints, rate limiting
│   ├── rag.py         # Pipeline: query building, retrieval, score filter, LLM call
│   ├── ingest.py      # Script de indexación offline (no importado por la app)
│   ├── models.py      # QuestionnaireInput, RAGResponse (Pydantic)
│   └── config.py      # Settings desde .env (pydantic-settings)
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
├── requirements.txt
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
pip install -r requirements.txt
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
make test   # pytest -v (49 tests, sin Groq ni ChromaDB reales)
```

---

## 🔑 Variables de entorno

```env
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
GROQ_TIMEOUT=30
GROQ_TEMPERATURE=0.0
CHROMA_DB_PATH=./chroma_db
DOCS_PATH=./docs
TOP_K_CHUNKS=8
MMR_FETCH_K=24
MIN_RELEVANCE_SCORE=0.2
RATE_LIMIT=10/minute
ALLOWED_ORIGINS=*
```

| Variable | Descripción | Default |
|----------|-------------|---------|
| `GROQ_API_KEY` | API key de [GroqCloud](https://console.groq.com) | — |
| `GROQ_MODEL` | Modelo de Groq a usar | `llama-4-scout-17b-16e-instruct` |
| `GROQ_TEMPERATURE` | Temperatura del LLM (0 = determinista) | `0.0` |
| `MIN_RELEVANCE_SCORE` | Umbral mínimo de relevancia para chunks | `0.2` |
| `TOP_K_CHUNKS` | Chunks a incluir en el prompt | `8` |
| `MMR_FETCH_K` | Candidatos a recuperar antes de filtrar | `24` |
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

## 🚢 Deploy en Railway

El `chroma_db/` está commiteado y el Dockerfile lo copia a la imagen. Railway nunca ejecuta `ingest.py` — el vector store ya está listo en el build.

```bash
# 1. Generar el índice localmente (con todos los PDFs en docs/)
make ingest

# 2. Commitear el chroma_db actualizado
git add chroma_db/ && git commit -m "chore: rebuild index"
git push
```

En Railway:
1. Conecta el repo → Railway detecta el `Dockerfile` automáticamente
2. Añade `GROQ_API_KEY` en Settings → Variables
3. Deploy automático en cada push a `main`

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

## 📄 Licencia

MIT © 2026 gustavintavo8
