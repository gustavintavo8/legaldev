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

### Desarrollo

```bash
make dev        # uvicorn app.main:app --reload
make test       # pytest -v
make ingest     # python app/ingest.py
```

API disponible en http://localhost:8000. Documentación interactiva en http://localhost:8000/docs.

### Docker Compose

```bash
# Genera chroma_db/ primero, luego:
docker-compose up --build
```

---

## Uso de la API

### POST /v1/analyze

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

Respuesta:

```json
{
  "respuesta_completa": "## RGPD\n\nDado que tu plataforma trata datos financieros...",
  "normativas_detectadas": ["RGPD", "LOPDGDD", "EU AI Act"],
  "chunks_utilizados": 8,
  "disclaimer": "⚠️ Esta información es orientativa y no constituye asesoramiento legal..."
}
```

### GET /normativas

```bash
curl http://localhost:8000/normativas
# {"normativas": ["RGPD.pdf", "LOPDGDD.pdf", ...], "total": 22}
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
| Guías AEPD (×7) | Guías oficiales AEPD |
| Código Ético y Deontológico CCII | Deontología |

---

## Aviso legal

LegalDev es una herramienta de orientación informativa. La información proporcionada no constituye asesoramiento legal y no debe utilizarse como sustituto de la consulta con un abogado especializado en derecho digital o tecnológico.
