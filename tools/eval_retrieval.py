"""
Retrieval evaluation script — P1.4.

Ejecutar: python tools/eval_retrieval.py
          make eval
Requiere: ChromaDB generado (make ingest) y GROQ_API_KEY en .env (o env var).
Solo hace retrieval — no llama al LLM.

Casos definidos en tools/eval_cases.yaml. Para añadir un caso nuevo, edita ese
archivo: añade label, overrides sobre base_input, la lista expected de stems
(nombre de archivo sin .pdf) que deben aparecer en los resultados, y
opcionalmente negative_expected con stems que NO deben aparecer.
"""

import argparse
import datetime
import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("GROQ_API_KEY", "eval-no-llm")

import yaml
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

from app import reranker as _reranker
from app.config import settings
from app.models import QuestionnaireInput
from app.rag import AUXILIARY_SEARCHES, EXCLUSIONS, INJECTIONS, _build_query

_SUPPORTED_MODELS = [
    "all-MiniLM-L6-v2",
    "paraphrase-multilingual-MiniLM-L12-v2",
    "BAAI/bge-m3",
]


def _load_cases(yaml_path: Path) -> tuple[dict, list[dict]]:
    with yaml_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["base_input"], data["cases"]


def _make_input(base: dict, overrides: dict) -> QuestionnaireInput:
    return QuestionnaireInput(**{**base, **(overrides or {})})


def _retrieve(vs, query: str, k: int, threshold: float) -> list:
    return [
        doc
        for doc, score in vs.similarity_search_with_relevance_scores(query, k=k)
        if score >= threshold
    ]


def run_case(case: dict, base_input: dict, vs, threshold: float) -> dict:
    inp = _make_input(base_input, case.get("overrides"))
    expected: list[str] = case.get("expected", [])
    negative_expected: list[str] = case.get("negative_expected", [])
    query = _build_query(inp)

    # Main query — keep raw candidates for injection (mirrors run_pipeline)
    candidates = vs.similarity_search_with_relevance_scores(query, k=settings.overfetch_k)
    docs = [doc for doc, score in candidates if score >= threshold]
    main_n = len(docs)
    seen = {hashlib.md5(d.page_content.encode()).hexdigest() for d in docs}

    for aux in AUXILIARY_SEARCHES:
        if aux.condition(inp):
            for doc in _retrieve(vs, aux.query, aux.k, threshold):
                h = hashlib.md5(doc.page_content.encode()).hexdigest()
                if h not in seen:
                    seen.add(h)
                    docs.append(doc)

    # Mirror production: pre_rerank slicing + CrossEncoder (same as run_pipeline)
    pre_rerank = docs[:settings.reranker_top_k] + docs[main_n:]
    docs = _reranker.rerank(query, pre_rerank, top_k=settings.top_k_chunks)

    # Mirror production: apply EXCLUSIONS post-reranker (same as run_pipeline)
    excluded = {exc.stem for exc in EXCLUSIONS if exc.condition(inp)}
    if excluded:
        docs = [d for d in docs if Path(d.metadata.get("source", "")).stem not in excluded]

    # Mirror production: INJECTIONS (uses candidates from main query)
    seen_inj = {hashlib.md5(d.page_content.encode()).hexdigest() for d in docs}
    for inj in INJECTIONS:
        if not inj.condition(inp):
            continue
        if inj.stem in excluded:
            continue
        target = [
            doc
            for doc, score in candidates
            if Path(doc.metadata.get("source", "")).stem == inj.stem
            and score >= threshold
        ][: inj.k]
        for doc in target:
            h = hashlib.md5(doc.page_content.encode()).hexdigest()
            if h not in seen_inj:
                seen_inj.add(h)
                docs.append(doc)

    retrieved_stems = {
        Path(d.metadata["source"]).stem for d in docs if "source" in d.metadata
    }
    found = [e for e in expected if e in retrieved_stems]
    missing = [e for e in expected if e not in retrieved_stems]
    false_positives = [n for n in negative_expected if n in retrieved_stems]
    recall = len(found) / len(expected) if expected else None

    return {
        "label": case["label"],
        "off_topic": case.get("off_topic", False),
        "expected": expected,
        "negative_expected": negative_expected,
        "found": found,
        "missing": missing,
        "false_positives": false_positives,
        "recall": recall,
        "chunks": len(docs),
    }


def _compute_noise(docs: list, expected: list[str]) -> int:
    retrieved_stems = {
        Path(d.metadata["source"]).stem for d in docs if "source" in d.metadata
    }
    return len(retrieved_stems - set(expected))


def sweep(vs, base_input: dict, cases: list[dict]) -> list[tuple]:
    thresholds = [0.20, 0.25, 0.30, 0.35, 0.40, 0.45]
    rows = []
    for t in thresholds:
        recalls, fps, noises = [], [], []
        for case in cases:
            r = run_case(case, base_input, vs, t)
            if r["recall"] is not None:
                recalls.append(r["recall"])
            fps.append(len(r["false_positives"]))
            inp = _make_input(base_input, case.get("overrides"))
            docs = _retrieve(vs, _build_query(inp), settings.overfetch_k, t)
            noises.append(_compute_noise(docs, case.get("expected", [])))
        avg_recall = sum(recalls) / len(recalls) if recalls else 0.0
        avg_fp = sum(fps) / len(fps) if fps else 0.0
        avg_noise = sum(noises) / len(noises) if noises else 0.0
        rows.append((t, avg_recall, avg_fp, avg_noise))
    return rows


def _write_eval_results(rows: list[tuple], path: Path) -> None:
    lines = [
        "# Retrieval Threshold Sweep Results",
        "",
        "| Threshold | Avg Recall | Avg FP | Avg Noise (unexpected stems) |",
        "|-----------|-----------|--------|------------------------------|",
    ]
    for t, recall, avg_fp, noise in rows:
        lines.append(
            f"| {t:.2f}      | {recall:.0%}       | {avg_fp:.1f}    | {noise:.1f}                         |"
        )
    lines += [
        "",
        f"**Chosen threshold:** `{settings.min_relevance_score}` — best recall/noise tradeoff.",
        "",
        f"_Generated by `python tools/eval_retrieval.py --sweep` on {datetime.date.today()}_",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Results written to {path}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LegalDev retrieval evaluator")
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="Sweep thresholds 0.20–0.45 and write tools/eval_results.md",
    )
    parser.add_argument(
        "--model",
        default="paraphrase-multilingual-MiniLM-L12-v2",
        choices=_SUPPORTED_MODELS,
        help="Embedding model to evaluate (default: paraphrase-multilingual-MiniLM-L12-v2)",
    )
    return parser


def main():
    args = _build_parser().parse_args()

    cases_path = Path(__file__).parent / "eval_cases.yaml"
    base_input, cases = _load_cases(cases_path)

    print(f"Cargando embeddings ({args.model}) y ChromaDB...")
    vs = Chroma(
        persist_directory=settings.chroma_db_path,
        embedding_function=HuggingFaceEmbeddings(
            model_name=args.model, encode_kwargs={"normalize_embeddings": True}
        ),
        collection_name="legaldev",
    )

    if args.sweep:
        rows = sweep(vs, base_input, cases)
        print(f"\n{'Threshold':>10}  {'Avg Recall':>10}  {'Avg FP':>8}  {'Avg Noise':>10}")
        print("-" * 46)
        for t, recall, avg_fp, noise in rows:
            print(f"{t:>10.2f}  {recall:>10.0%}  {avg_fp:>8.1f}  {noise:>10.1f}")
        results_path = Path(__file__).parent / "eval_results.md"
        _write_eval_results(rows, results_path)
        return

    threshold = settings.min_relevance_score

    print(
        f"\nRetrieval eval — model={args.model}  threshold={threshold}"
        f"  overfetch_k={settings.overfetch_k}  casos={len(cases)}\n"
    )

    _run_standard_eval(cases, base_input, vs, threshold)


def _run_standard_eval(cases, base_input, vs, threshold):
    print(f"{'':4} {'Caso':<32} {'Recall':>7}  {'FP':>4}  {'Chunks':>6}  Problemas")
    print("-" * 80)

    all_passed = True
    results = []
    for case in cases:
        r = run_case(case, base_input, vs, threshold)
        results.append(r)

        if r["recall"] is None:
            recall_ok = True
            recall_str = "  N/A "
        else:
            recall_ok = r["recall"] == 1.0
            recall_str = f"{r['recall']:>6.0%} "

        ok = recall_ok and not r["false_positives"]

        if not ok:
            all_passed = False

        status = "OK " if ok else "NOK"
        fp_count = len(r["false_positives"])

        problems = []
        if r["missing"]:
            miss_str = ", ".join(r["missing"])
            if len(miss_str) > 30:
                miss_str = miss_str[:27] + "..."
            problems.append(f"miss: {miss_str}")
        if r["false_positives"]:
            fp_str = ", ".join(r["false_positives"])
            if len(fp_str) > 30:
                fp_str = fp_str[:27] + "..."
            problems.append(f"fp: {fp_str}")
        problems_str = " | ".join(problems)

        print(
            f"{status}  {r['label']:<32} {recall_str} {fp_count:>4}  {r['chunks']:>6}  {problems_str}"
        )

    print()
    if all_passed:
        print("OK — todos los casos pasaron.")
    else:
        print("FAIL — algún caso falló.")
        for r in results:
            if r["missing"]:
                print(f"  [{r['label']}] miss: {r['missing']}")
            if r["false_positives"]:
                print(f"  [{r['label']}] fp:   {r['false_positives']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
