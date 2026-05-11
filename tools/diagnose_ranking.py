"""
Diagnóstico de posiciones reales en el ranking para la query problemática.

Ejecutar: python tools/diagnose_ranking.py
Requiere: ChromaDB generado (make ingest) y GROQ_API_KEY en .env (o env var).
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("GROQ_API_KEY", "diag-no-llm")

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

from app.config import settings
from app.models import QuestionnaireInput
from app.rag import _build_query

WATCHLIST = {
    "RGPD",
    "LOPDGDD",
    "Ley de Propiedad Intelectual",
    "Real Decreto 311-2022 ENS",
    "IA Agéntica desde la perspectiva de proteccion de datos - AEPD",
}

PROBLEMATIC_INPUT = QuestionnaireInput(
    tipo_proyecto="app_web",
    descripcion_breve="App de gestión de equipos de fútbol con seguimiento de jugadores",
    tiene_usuarios_registrados=True,
    acceso_publico=True,
    tipos_datos_personales=["nombre", "email", "telefono", "ubicacion"],
    usuarios_menores=False,
    usuarios_ue=True,
    transferencia_datos_terceros=False,
    usa_ia=True,
    tipo_ia="recomendacion",
    usa_cookies=True,
    monetizacion=None,
    contenido_digital=False,
    ccaa="Asturias",
    es_empresa=False,
    colegiado=True,
)


def main():
    query = _build_query(PROBLEMATIC_INPUT)
    print(f"Query ({len(query)} chars):\n{query}\n")
    print("Cargando ChromaDB...")

    vs = Chroma(
        persist_directory=settings.chroma_db_path,
        embedding_function=HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2"),
        collection_name="legaldev",
    )

    results = vs.similarity_search_with_relevance_scores(query, k=100)
    print(f"\nTotal candidatos: {len(results)}")
    print(f"Threshold activo: {settings.min_relevance_score}")
    print(f"top_k_chunks (slice principal): {settings.top_k_chunks}\n")

    print(f"{'Pos':>4}  {'Score':>6}  {'Pass':>5}  {'Top12':>5}  Fuente")
    print("-" * 75)

    watchlist_hits: dict[str, list] = {}

    for i, (doc, score) in enumerate(results, 1):
        source = doc.metadata.get("source", "?")
        stem = Path(source).stem
        passes = score >= settings.min_relevance_score
        in_top12 = i <= settings.top_k_chunks

        flag = ""
        for w in WATCHLIST:
            if w.lower() in stem.lower():
                flag = " <<<"
                watchlist_hits.setdefault(w, []).append((i, score))

        marker = "YES" if passes else "no"
        top12_marker = "YES" if in_top12 else "-"
        print(
            f"{i:>4}  {score:>6.4f}  {marker:>5}  {top12_marker:>5}  {stem[:55]}{flag}"
        )

    print("\n--- Resumen watchlist ---")
    for name in WATCHLIST:
        hits = watchlist_hits.get(name)
        if hits:
            positions = ", ".join(
                f"#{p} (score={s:.4f}, {'PASS' if s >= settings.min_relevance_score else 'FAIL'})"
                for p, s in hits
            )
            print(f"  {name}: {positions}")
        else:
            print(f"  {name}: NO APARECE en top-100")


if __name__ == "__main__":
    main()
