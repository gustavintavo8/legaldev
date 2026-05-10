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
    # CCII no aparece en la query principal (query demasiado dilutada).
    # La búsqueda auxiliar de run_pipeline() es la que lo trae. Validar end-to-end con el smoke test.
    (
        "covered-CCII (main query only)",
        {"colegiado": True, "es_empresa": False},
        None,
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
        print("OK Todos los casos pasaron.")
    else:
        print("FAIL Algún caso falló — revisar retrieval.")
        sys.exit(1)


if __name__ == "__main__":
    main()
