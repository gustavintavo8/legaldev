# Única fuente de verdad del modelo de embeddings. Cambiarlo exige reindexar: los vectores
# de un modelo no son comparables con los de otro (el arranque lo comprueba vía .index_meta.json).
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
# El Dockerfile pre-descarga este mismo modelo por nombre (paso RUN con SentenceTransformer(...)); si cambias EMBEDDING_MODEL, actualiza también el Dockerfile o el arranque fallará en offline (HF_HUB_OFFLINE=1).

REQUIRED_DOCS: frozenset[str] = frozenset(
    {
        "RGPD.pdf",
        "EU AI Act.pdf",
        "Directiva NIS2.pdf",
        "Directiva de Responsabilidad por Productos con IA.pdf",
        "Digital Services Act (Reglamento UE 2022-2065).pdf",
        "Cyber Resilience Act (Reglamento UE 2024-2847).pdf",
        "Directiva ePrivacy (2002-58-CE consolidada).pdf",
        "Data Act (Reglamento UE 2023-2854).pdf",
        "Data Governance Act (Reglamento UE 2022-868).pdf",
        "DORA (Reglamento UE 2022-2554).pdf",
        "LOPDGDD.pdf",
        "Real Decreto 311-2022 ENS.pdf",
        "LSSI.pdf",
        "Ley de Propiedad Intelectual.pdf",
        "Guía para el cumplimiento del deber de informar - AEPD.pdf",
        "Guía de Análisis de Riesgos para tratamientos de datos personales - AEPD.pdf",
        "Guía de Privacidad desde el Diseño - AEPD.pdf",
        "Guía sobre uso de cookies - AEPD.pdf",
        "Adecuación al RGPD de tratamientos que incorporan IA - AEPD.pdf",
        "IA Agentica desde la perspectiva de proteccion de datos - AEPD.pdf",
        "Guía de Anonimización - AEPD.pdf",
        "Código Ético y Deontológico CCII.pdf",
    }
)
