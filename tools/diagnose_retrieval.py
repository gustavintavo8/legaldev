"""
Pipeline diagnostic for patterns P2 (RGPD-no-section), P3 (INJECTION domain gap),
P4 (DSA inverted recall).

Run:
    python tools/diagnose_retrieval.py --p3
    python tools/diagnose_retrieval.py --p2
    python tools/diagnose_retrieval.py --p4
    python tools/diagnose_retrieval.py --all

Only vector retrieval + reranker -- no LLM calls.
Output saved to tools/probe_results/.
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("GROQ_API_KEY", "diag-no-llm")

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

from app import reranker as _reranker
from app.config import settings
from app.models import QuestionnaireInput
from app.rag import AUXILIARY_SEARCHES, EXCLUSIONS, INJECTIONS, _build_query

OUT_DIR = Path(__file__).parent / "probe_results"
OUT_DIR.mkdir(exist_ok=True)

MODEL = "paraphrase-multilingual-MiniLM-L12-v2"


def _stem(doc) -> str:
    return Path(doc.metadata.get("source", "?")).stem


def _load_vs() -> Chroma:
    print(f"Loading embeddings ({MODEL}) and ChromaDB...")
    return Chroma(
        persist_directory=settings.chroma_db_path,
        embedding_function=HuggingFaceEmbeddings(
            model_name=MODEL, encode_kwargs={"normalize_embeddings": True}
        ),
        collection_name="legaldev",
    )


def _make_input(**overrides) -> QuestionnaireInput:
    base = dict(
        tipo_proyecto="app_web",
        descripcion_breve="app de gestion de tareas",
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
    base.update(overrides)
    return QuestionnaireInput(**base)


# -----------------------------------------------------------------------------
# Shared pipeline tracing
# -----------------------------------------------------------------------------

def trace_pipeline(vs: Chroma, inp: QuestionnaireInput, label: str) -> dict:
    """Run the full retrieval pipeline and return a rich trace dict."""
    query = _build_query(inp)
    print(f"\n  Query ({len(query)} chars):")
    print(f"  {query[:200]}{'...' if len(query) > 200 else ''}")

    # -- 1. Main candidates (overfetch_k = 100) ------------------------------
    raw = vs.similarity_search_with_relevance_scores(query, k=settings.overfetch_k)
    candidates_all = [(doc, score) for doc, score in raw]

    above = [(doc, score) for doc, score in candidates_all if score >= settings.min_relevance_score]
    below = [(doc, score) for doc, score in candidates_all if score < settings.min_relevance_score]

    print(f"\n  [1] Candidates: {len(candidates_all)} total, "
          f"{len(above)} >= {settings.min_relevance_score}, "
          f"{len(below)} below threshold")

    # Per-stem score summary for main candidates
    from collections import defaultdict
    stem_scores: dict[str, list[float]] = defaultdict(list)
    for doc, score in candidates_all:
        stem_scores[_stem(doc)].append(score)
    stem_top = {s: max(v) for s, v in stem_scores.items()}
    stem_count = {s: len(v) for s, v in stem_scores.items()}

    print("\n  Top-score per source in candidates_all (sorted desc):")
    for s, top in sorted(stem_top.items(), key=lambda x: -x[1]):
        cnt = stem_count[s]
        above_threshold = sum(1 for v in stem_scores[s] if v >= settings.min_relevance_score)
        flag = "  <- BELOW threshold" if top < settings.min_relevance_score else ""
        print(f"    {s:<55} top={top:.4f}  n={cnt}  n>=thr={above_threshold}{flag}")

    # -- 2. docs = above-threshold from main ---------------------------------
    docs = [doc for doc, _ in above]
    main_n = len(docs)
    seen = {hashlib.md5(d.page_content.encode()).hexdigest() for d in docs}

    # -- 3. Auxiliary searches ------------------------------------------------
    aux_added: list[dict] = []
    for aux in AUXILIARY_SEARCHES:
        if not aux.condition(inp):
            continue
        aux_raw = vs.similarity_search_with_relevance_scores(aux.query, k=aux.k)
        new_from_aux = 0
        for doc, score in aux_raw:
            if score >= settings.min_relevance_score:
                h = hashlib.md5(doc.page_content.encode()).hexdigest()
                if h not in seen:
                    seen.add(h)
                    docs.append(doc)
                    new_from_aux += 1
                    aux_added.append({"aux": aux.name, "stem": _stem(doc), "score": round(score, 4)})
        print(f"\n  [2] Aux '{aux.name}': fetched {len(aux_raw)}, "
              f"new unique above thr: {new_from_aux}")
        for doc, score in aux_raw:
            flag = "  <- below thr" if score < settings.min_relevance_score else ""
            print(f"      {_stem(doc):<55} {score:.4f}{flag}")

    # -- 4. pre_rerank composition --------------------------------------------
    pre_rerank = docs[: min(settings.reranker_top_k, main_n)] + docs[main_n:]
    print(f"\n  [3] pre_rerank: {len(pre_rerank)} docs "
          f"(main[:{ settings.reranker_top_k}]={len(docs[:settings.reranker_top_k])} "
          f"+ aux={len(docs[main_n:])})")
    pre_stems = [_stem(d) for d in pre_rerank]
    from collections import Counter
    for s, c in Counter(pre_stems).most_common():
        print(f"      {s:<55} {c} chunk(s)")

    # -- 5. CrossEncoder rerank -----------------------------------------------
    docs_reranked = _reranker.rerank(query, pre_rerank, top_k=settings.top_k_chunks)
    print(f"\n  [4] After CrossEncoder top_k={settings.top_k_chunks}:")
    reranked_stems = [_stem(d) for d in docs_reranked]
    for s, c in Counter(reranked_stems).most_common():
        print(f"      {s:<55} {c} chunk(s)")
    dropped_from_pre = set(pre_stems) - set(reranked_stems)
    if dropped_from_pre:
        print(f"      Dropped by CrossEncoder: {sorted(dropped_from_pre)}")

    # -- 6. Exclusions --------------------------------------------------------
    excluded_stems = {exc.stem for exc in EXCLUSIONS if exc.condition(inp)}
    print(f"\n  [5] EXCLUSIONS active: {sorted(excluded_stems) if excluded_stems else 'none'}")
    docs_after_excl = [d for d in docs_reranked if _stem(d) not in excluded_stems]
    excl_removed = [_stem(d) for d in docs_reranked if _stem(d) in excluded_stems]
    if excl_removed:
        print(f"      Removed chunks: {excl_removed}")

    # -- 7. Injections --------------------------------------------------------
    print(f"\n  [6] INJECTIONS:")
    seen_inj = {hashlib.md5(d.page_content.encode()).hexdigest() for d in docs_after_excl}
    injection_log: list[dict] = []
    docs_final = list(docs_after_excl)
    for inj in INJECTIONS:
        fires = inj.condition(inp)
        blocked = inj.stem in excluded_stems
        print(f"      {inj.stem:<55} condition={fires}  blocked={blocked}", end="")
        if not fires or blocked:
            print()
            injection_log.append({"stem": inj.stem, "fires": fires, "blocked": blocked,
                                   "candidates_above_thr": 0, "injected": 0})
            continue
        # Find candidates above threshold for this stem
        target_candidates = [
            (doc, score) for doc, score in candidates_all
            if _stem(doc) == inj.stem and score >= settings.min_relevance_score
        ]
        # Also check how many exist below threshold (to show what's being missed)
        target_below = [
            (doc, score) for doc, score in candidates_all
            if _stem(doc) == inj.stem and score < settings.min_relevance_score
        ]
        target = target_candidates[: inj.k]
        added = 0
        for doc, _ in target:
            h = hashlib.md5(doc.page_content.encode()).hexdigest()
            if h not in seen_inj:
                seen_inj.add(h)
                docs_final.append(doc)
                added += 1
        print(f"  cands>=thr={len(target_candidates)}  cands<thr={len(target_below)}"
              f"  injected={added}")
        if target_below:
            print(f"        Best below-thr score for {inj.stem}: "
                  f"{max(s for _, s in target_below):.4f}  "
                  f"(threshold is {settings.min_relevance_score})")
        injection_log.append({
            "stem": inj.stem,
            "fires": fires,
            "blocked": blocked,
            "candidates_above_thr": len(target_candidates),
            "candidates_below_thr": len(target_below),
            "best_below_score": round(max((s for _, s in target_below), default=0.0), 4),
            "injected": added,
        })

    # -- 8. Final docs -> LLM -------------------------------------------------
    final_stems = [_stem(d) for d in docs_final]
    final_stem_counts = Counter(final_stems)
    retrieved_sources = set(final_stems)

    print(f"\n  [7] FINAL docs to LLM ({len(docs_final)} chunks):")
    for s, c in sorted(final_stem_counts.items(), key=lambda x: -x[1]):
        flag = "  <- ONLY 1 CHUNK -> NO section (prompt rule)" if c == 1 else ""
        print(f"      {s:<55} {c} chunk(s){flag}")

    print(f"\n  normativas_detectadas (from stems): {sorted(retrieved_sources)}")

    # Identify >=2 threshold issue (P2 root cause)
    one_chunk_sources = [s for s, c in final_stem_counts.items() if c == 1]
    if one_chunk_sources:
        print(f"\n  ! P2 SIGNAL -- sources with exactly 1 chunk (will be in normativas_detectadas "
              f"but LLM won't open section): {one_chunk_sources}")

    return {
        "label": label,
        "query_preview": query[:300],
        "threshold": settings.min_relevance_score,
        "candidates_total": len(candidates_all),
        "candidates_above_thr": len(above),
        "stem_top_scores": {s: round(v, 4) for s, v in sorted(stem_top.items(), key=lambda x: -x[1])},
        "aux_added": aux_added,
        "pre_rerank_size": len(pre_rerank),
        "pre_rerank_stems": Counter(pre_stems),
        "after_crossencoder_stems": Counter(reranked_stems),
        "dropped_by_crossencoder": sorted(dropped_from_pre),
        "excluded_stems": sorted(excluded_stems),
        "injection_log": injection_log,
        "final_stem_counts": dict(final_stem_counts),
        "normativas_detectadas": sorted(retrieved_sources),
        "one_chunk_sources": one_chunk_sources,
        "final_chunks": len(docs_final),
    }


# -----------------------------------------------------------------------------
# P3 -- INJECTION domain gap
# -----------------------------------------------------------------------------

def diag_p3(vs: Chroma):
    print("\n" + "=" * 72)
    print("P3 -- RGPD INJECTION gap for distant-domain queries")
    print("=" * 72)

    probes = [
        # (label, descripcion_breve, extra_overrides)
        ("plantas (probe 8 original)", "red social para amantes de las plantas donde la gente comparte fotos y consejos", {}),
        ("red social (generico)", "red social para compartir contenido", {}),
        ("app perfiles usuario", "app con perfiles de usuario y comunidad", {}),
        ("app gestion tareas (baseline)", "app de gestion de tareas", {}),
    ]

    results = []
    for label, desc, extra in probes:
        print(f"\n{'-'*60}")
        print(f"> {label}")
        inp = _make_input(
            descripcion_breve=desc,
            tipo_proyecto="app_web",
            tipos_datos_personales=["nombre", "email"],
            tiene_usuarios_registrados=True,
            acceso_publico=True,
            usa_cookies=True,
            **extra,
        )
        trace = trace_pipeline(vs, inp, label)
        results.append(trace)

    # Print RGPD boundary table
    print("\n" + "=" * 72)
    print("P3 SUMMARY -- RGPD scores across query domains")
    print(f"{'Label':<45} {'RGPD top score':>15}  {'>=0.40?':>6}  {'RGPD injected?':>14}")
    print("-" * 82)
    for r in results:
        top = r["stem_top_scores"].get("RGPD", 0.0)
        above = "YES" if top >= settings.min_relevance_score else "NO"
        inj = next((x for x in r["injection_log"] if x["stem"] == "RGPD"), {})
        injected = "YES" if inj.get("injected", 0) > 0 else "NO"
        print(f"  {r['label']:<43} {top:>15.4f}  {above:>6}  {injected:>14}")

    out = OUT_DIR / "diag_p3.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n  Saved: {out}")


# -----------------------------------------------------------------------------
# P2 -- RGPD detected but no section (chunk count vs prompt rule)
# -----------------------------------------------------------------------------

def diag_p2(vs: Chroma):
    print("\n" + "=" * 72)
    print("P2 -- RGPD in normativas_detectadas but no ## section in report")
    print("=" * 72)

    cases = [
        ("probe 5 -- cookies movil", dict(
            tipo_proyecto="app_movil",
            descripcion_breve="app de noticias con publicidad",
            tipos_datos_personales=["email"],
            usa_cookies=True,
            monetizacion="publicidad",
        )),
        ("probe 7 -- ecommerce marketplace", dict(
            tipo_proyecto="ecommerce",
            descripcion_breve="marketplace para vender ropa de segunda mano entre particulares",
            tipos_datos_personales=["nombre", "email", "ubicacion"],
            usa_cookies=True,
            acceso_publico=True,
            monetizacion="marketplace",
        )),
    ]

    results = []
    for label, overrides in cases:
        print(f"\n{'-'*60}")
        print(f"> {label}")
        inp = _make_input(**overrides)
        trace = trace_pipeline(vs, inp, label)
        results.append(trace)

    print("\n" + "=" * 72)
    print("P2 SUMMARY -- RGPD chunk count in final docs (prompt requires >=2 for section)")
    print(f"{'Case':<45} {'RGPD chunks':>12}  {'in normativas_det':>18}  {'section?':>9}")
    print("-" * 87)
    for r in results:
        n = r["final_stem_counts"].get("RGPD", 0)
        in_nd = "RGPD" in r["normativas_detectadas"]
        section = "YES" if n >= 2 else "NO (prompt rule: <2 chunks)"
        print(f"  {r['label']:<43} {n:>12}  {str(in_nd):>18}  {section:>9}")

    print("\n  PROMPT RULE (rag.py SYSTEM_PROMPT, line 225):")
    print("  'abre seccion propia para una normativa solo si tienes 2 o mas fragmentos'")
    print("  normativas_detectadas is computed from ANY chunk >= 1 -> mismatch when n=1")

    out = OUT_DIR / "diag_p2.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n  Saved: {out}")


# -----------------------------------------------------------------------------
# P4 -- DSA inverted recall (FP in cookies, absent in marketplace)
# -----------------------------------------------------------------------------

def diag_p4(vs: Chroma):
    print("\n" + "=" * 72)
    print("P4 -- DSA: FP in cookies context, absent in marketplace/social")
    print("=" * 72)

    DSA_STEM = "Digital Services Act (Reglamento UE 2022-2065)"

    # -- Part A: DSA scores across query types ------------------------------
    query_cases = [
        ("cookies/publicidad (FP context)", _make_input(
            tipo_proyecto="app_web",
            descripcion_breve="app de noticias con publicidad",
            tipos_datos_personales=["email"],
            usa_cookies=True,
            monetizacion="publicidad",
        )),
        ("marketplace C2C (probe 7, missing)", _make_input(
            tipo_proyecto="ecommerce",
            descripcion_breve="marketplace para vender ropa de segunda mano entre particulares",
            tipos_datos_personales=["nombre", "email", "ubicacion"],
            usa_cookies=True,
            acceso_publico=True,
            monetizacion="marketplace",
        )),
        ("red social UGC (probe 8, missing)", _make_input(
            tipo_proyecto="app_web",
            descripcion_breve="red social para amantes de las plantas donde la gente comparte fotos y consejos",
            tipos_datos_personales=["nombre", "email"],
            usa_cookies=True,
            acceso_publico=True,
        )),
        ("plataforma intermediacion directa", _make_input(
            tipo_proyecto="ecommerce",
            descripcion_breve="plataforma intermediaria de servicios digitales entre usuarios, marketplace de contenidos de terceros, moderacion de plataforma intermediaria",
            tipos_datos_personales=["nombre", "email"],
            usa_cookies=True,
            acceso_publico=True,
            monetizacion="marketplace",
        )),
    ]

    print("\n  Part A: DSA top score per query context")
    dsa_scores: list[dict] = []
    results_a = []
    for label, inp in query_cases:
        query = _build_query(inp)
        raw = vs.similarity_search_with_relevance_scores(query, k=settings.overfetch_k)
        dsa_hits = [(doc, score) for doc, score in raw if _stem(doc) == DSA_STEM]
        dsa_hits_above = [(d, s) for d, s in dsa_hits if s >= settings.min_relevance_score]
        top = max((s for _, s in dsa_hits), default=0.0)
        print(f"    {label:<50}  DSA top={top:.4f}  n_above_thr={len(dsa_hits_above)}")
        dsa_scores.append({
            "label": label,
            "dsa_top_score": round(top, 4),
            "dsa_chunks_above_thr": len(dsa_hits_above),
            "dsa_chunks_total_in_100": len(dsa_hits),
        })
        results_a.append({"label": label, "query": query, "dsa_hits": [
            {"stem": _stem(d), "score": round(s, 4), "page": d.metadata.get("page"),
             "preview": d.page_content[:200]}
            for d, s in dsa_hits
        ]})

    # -- Part B: DSA chunk content sample -----------------------------------
    print(f"\n  Part B: DSA chunk content sample (ALL chunks in DB)")
    # Use a neutral query to pull DSA chunks regardless of score
    neutral_raw = vs.similarity_search_with_relevance_scores(
        "plataforma intermediaria servicios digitales regulacion",
        k=settings.overfetch_k,
    )
    dsa_chunks = [(doc, score) for doc, score in neutral_raw if _stem(doc) == DSA_STEM]
    # Extend with more if possible
    broader_raw = vs.similarity_search_with_relevance_scores(
        "Digital Services Act obligaciones plataformas",
        k=settings.overfetch_k,
    )
    seen_h = {hashlib.md5(d.page_content.encode()).hexdigest() for d, _ in dsa_chunks}
    for doc, score in broader_raw:
        if _stem(doc) == DSA_STEM:
            h = hashlib.md5(doc.page_content.encode()).hexdigest()
            if h not in seen_h:
                seen_h.add(h)
                dsa_chunks.append((doc, score))

    print(f"  Found {len(dsa_chunks)} unique DSA chunks (sample first 6):")
    chunk_sample = []
    for i, (doc, score) in enumerate(sorted(dsa_chunks, key=lambda x: -x[1])[:6], 1):
        page = doc.metadata.get("page", "?")
        preview = doc.page_content[:300].replace("\n", " ")
        print(f"\n    Chunk {i} (p.{page}, score={score:.4f}):")
        print(f"    '{preview}...'")
        chunk_sample.append({
            "page": page,
            "score": round(score, 4),
            "preview": doc.page_content[:400],
        })

    out = OUT_DIR / "diag_p4.json"
    out_data = {"dsa_scores_by_query": dsa_scores, "query_details": results_a, "dsa_chunk_sample": chunk_sample}
    out.write_text(json.dumps(out_data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n  Saved: {out}")

    print("\n" + "=" * 72)
    print("P4 SUMMARY")
    print(f"{'Context':<50}  {'DSA top score':>14}  {'Above 0.40?':>11}")
    print("-" * 78)
    for d in dsa_scores:
        above = "YES" if d["dsa_top_score"] >= settings.min_relevance_score else "NO"
        print(f"  {d['label']:<50}  {d['dsa_top_score']:>14.4f}  {above:>11}")


# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Pipeline diagnostics for P2/P3/P4")
    parser.add_argument("--p2", action="store_true", help="Diagnose P2 (RGPD no section)")
    parser.add_argument("--p3", action="store_true", help="Diagnose P3 (INJECTION domain gap)")
    parser.add_argument("--p4", action="store_true", help="Diagnose P4 (DSA inverted)")
    parser.add_argument("--all", dest="all_", action="store_true", help="Run all diagnostics")
    args = parser.parse_args()

    if not any([args.p2, args.p3, args.p4, args.all_]):
        parser.print_help()
        sys.exit(0)

    vs = _load_vs()
    print(f"threshold={settings.min_relevance_score}  overfetch_k={settings.overfetch_k}"
          f"  reranker_top_k={settings.reranker_top_k}  top_k={settings.top_k_chunks}")

    if args.p3 or args.all_:
        diag_p3(vs)
    if args.p2 or args.all_:
        diag_p2(vs)
    if args.p4 or args.all_:
        diag_p4(vs)


if __name__ == "__main__":
    main()
