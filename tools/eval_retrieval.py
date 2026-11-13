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
import os
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("GROQ_API_KEY", "eval-no-llm")

import yaml
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

from app import reranker, store
from app.config import settings
from app.corpus import EMBEDDING_MODEL
from app.models import QuestionnaireInput
from app.rag import AUXILIARY_SEARCHES, EXCLUSIONS, INJECTIONS, retrieve_docs_sync

THRESHOLDS: tuple[float, ...] = (0.20, 0.25, 0.30, 0.35, 0.40, 0.45)
# Criterio del producto: una normativa entra en normativas_detectadas (y el informe le abre
# sección) con dos fragmentos o más (app/rag.py, run_pipeline_detailed).
MIN_CHUNKS_PRODUCTO = 2

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


def rule_guaranteed(inp: QuestionnaireInput) -> set[str]:
    """Normativas que una INJECTION garantiza para este cuestionario.

    Las mismas que inyecta ``rag._retrieve``: la condición de la regla se cumple y ninguna
    EXCLUSION retira la normativa. Se decide caso a caso, no por tener regla en general (la
    guía de IA agéntica solo con agentes, el RGPD solo con datos personales).
    """
    excluded = {exc.stem for exc in EXCLUSIONS if exc.condition(inp)}
    return {
        inj.stem
        for inj in INJECTIONS
        if inj.condition(inp) and inj.stem not in excluded
    }


def run_case(case: dict, base_input: dict, vs, threshold: float) -> dict:
    inp = _make_input(base_input, case.get("overrides"))
    expected: list[str] = case.get("expected", [])
    negative_expected: list[str] = case.get("negative_expected", [])

    docs = retrieve_docs_sync(inp, vs, threshold)

    chunks_per_stem = Counter(
        Path(d.metadata["source"]).stem for d in docs if "source" in d.metadata
    )
    retrieved_stems = set(chunks_per_stem)
    found = [e for e in expected if e in retrieved_stems]
    missing = [e for e in expected if e not in retrieved_stems]
    false_positives = [n for n in negative_expected if n in retrieved_stems]
    recall = len(found) / len(expected) if expected else None
    found_product = [e for e in expected if chunks_per_stem[e] >= MIN_CHUNKS_PRODUCTO]
    garantizadas = rule_guaranteed(inp)

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
        "sources": len(retrieved_stems),
        "retrieved_stems": retrieved_stems,
        "chunks_per_stem": chunks_per_stem,
        "found_product": found_product,
        "rule_expected": [e for e in expected if e in garantizadas],
        "search_expected": [e for e in expected if e not in garantizadas],
    }


def _compute_noise(retrieved_stems: set[str], expected: list[str]) -> int:
    return len(retrieved_stems - set(expected))


@dataclass(frozen=True)
class SweepRow:
    """Una fila del barrido.

    Las cuatro primeras son las columnas históricas: medias por caso, y una normativa cuenta
    como recuperada con un solo fragmento. Las tres últimas son recuentos ``(recuperadas,
    esperadas)`` de pares (caso, normativa esperada) con el criterio del producto (dos
    fragmentos o más): todas, las que garantiza una INJECTION y las que dependen de la
    búsqueda. Con 13 casos, un recuento dice más que una media.
    """

    threshold: float
    avg_recall: float
    avg_fp: float
    avg_noise: float
    producto: tuple[int, int]
    regla: tuple[int, int]
    busqueda: tuple[int, int]


def sweep(
    vs, base_input: dict, cases: list[dict], thresholds=THRESHOLDS
) -> list[SweepRow]:
    rows = []
    for t in thresholds:
        recalls, fps, noises = [], [], []
        producto = regla = busqueda = (0, 0)
        for case in cases:
            r = run_case(case, base_input, vs, t)
            if r["recall"] is not None:
                recalls.append(r["recall"])
            fps.append(len(r["false_positives"]))
            noises.append(
                _compute_noise(r["retrieved_stems"], case.get("expected", []))
            )
            ok = set(r["found_product"])
            producto = _sumar(producto, ok, r["expected"])
            regla = _sumar(regla, ok, r["rule_expected"])
            busqueda = _sumar(busqueda, ok, r["search_expected"])
        avg_recall = sum(recalls) / len(recalls) if recalls else 0.0
        avg_fp = sum(fps) / len(fps) if fps else 0.0
        avg_noise = sum(noises) / len(noises) if noises else 0.0
        rows.append(
            SweepRow(t, avg_recall, avg_fp, avg_noise, producto, regla, busqueda)
        )
    return rows


def _sumar(
    total: tuple[int, int], ok: set[str], esperadas: list[str]
) -> tuple[int, int]:
    return total[0] + sum(e in ok for e in esperadas), total[1] + len(esperadas)


def _coma(x: float, decimales: int = 2) -> str:
    return f"{x:.{decimales}f}".replace(".", ",")


def _ratio(par: tuple[int, int]) -> float:
    return par[0] / par[1] if par[1] else 1.0


def conclusion(rows: list[SweepRow], chosen: float) -> str:
    """Lo que dice la tabla, sacado de los datos.

    Si el recall (con dos fragmentos y el histórico) y los FP no cambian con el umbral, lo
    dice, y dice qué cambia (el ruido) y si el configurado es el de menos ruido. Si cambian,
    da el mejor por recall, FP y ruido, en ese orden, y si coincide con el configurado. Antes
    se escribía siempre «best recall/noise tradeoff», aunque la tabla dijera otra cosa
    (revisión externa del 13/11/2026).
    """
    if not rows:
        return "Sin filas: no hay nada que concluir."
    calidad = {(r.producto, round(r.avg_recall, 4), round(r.avg_fp, 1)) for r in rows}
    if len(calidad) > 1:
        mejor = min(
            rows,
            key=lambda r: (
                -_ratio(r.producto),
                -round(r.avg_recall, 4),
                round(r.avg_fp, 1),
                round(r.avg_noise, 1),
                r.threshold,
            ),
        )
        texto = (
            "Por recall (con dos fragmentos y el histórico), FP y ruido, en ese orden, el "
            f"mejor es {_coma(mejor.threshold)}"
        )
        if mejor.threshold == chosen:
            return texto + ", que coincide con el configurado."
        return texto + f", que no coincide con el configurado ({_coma(chosen)})."

    r = rows[0]
    rango = f"{_coma(rows[0].threshold)} y {_coma(rows[-1].threshold)}"
    frases = [
        f"Entre {rango}, el recall (histórico {r.avg_recall:.0%}; con dos fragmentos, "
        f"{r.producto[0]}/{r.producto[1]}) y los FP ({_coma(r.avg_fp, 1)}) no cambian: en "
        "estos casos el umbral no decide qué normativas esperadas llegan al contexto."
    ]
    ruidos = [round(x.avg_noise, 1) for x in rows]
    menos_ruido = min(rows, key=lambda x: (round(x.avg_noise, 1), x.threshold))
    if max(ruidos) != min(ruidos):
        frases.append(
            f"Solo cambia el ruido, entre {_coma(max(ruidos), 1)} y "
            f"{_coma(min(ruidos), 1)}; el de menos ruido es "
            f"{_coma(menos_ruido.threshold)} ({_coma(menos_ruido.avg_noise, 1)})."
        )
    configurado = next((x for x in rows if x.threshold == chosen), None)
    if configurado is None:
        frases.append(f"El configurado ({_coma(chosen)}) no está en la tabla.")
    elif round(configurado.avg_noise, 1) > round(menos_ruido.avg_noise, 1):
        frases.append(
            f"El configurado ({_coma(chosen)}) no es el de menos ruido: este barrido no lo "
            "respalda por sí solo."
        )
    else:
        frases.append(f"El configurado ({_coma(chosen)}) es el de menos ruido.")
    return " ".join(frases)


def _fmt_par(par: tuple[int, int]) -> str:
    return f"{_ratio(par):.0%} ({par[0]}/{par[1]})" if par[1] else "— (0/0)"


def _write_eval_results(
    rows: list[SweepRow], path: Path, procedencia: dict, *, chosen: float
) -> None:
    lines = [
        "# Retrieval Threshold Sweep Results",
        "",
        "Barrido del umbral de relevancia (`MIN_RELEVANCE_SCORE`) sobre los casos de "
        "`tools/eval_cases.yaml`, solo con la recuperación (sin LLM).",
        "",
        "| Procedencia | Valor |",
        "|---|---|",
        *(f"| {k} | {v} |" for k, v in procedencia.items()),
        "",
        "Columnas: las cuatro primeras son las históricas (medias por caso; una normativa "
        "cuenta como recuperada con un solo fragmento). Las tres últimas cuentan pares (caso, "
        "normativa esperada) con el criterio del producto, dos fragmentos o más, como "
        "`normativas_detectadas`: todas, las que garantiza una INJECTION en ese caso y las "
        "que dependen de la búsqueda.",
        "",
        "| Threshold | Avg Recall | Avg FP | Avg Noise (unexpected stems) "
        "| Recall ≥2 fragmentos | Garantizadas por regla | Dependen de la búsqueda |",
        "|-----------|-----------|--------|------------------------------|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r.threshold:.2f}      | {r.avg_recall:.0%}       | {r.avg_fp:.1f}    "
            f"| {r.avg_noise:.1f}                         "
            f"| {_fmt_par(r.producto)} | {_fmt_par(r.regla)} | {_fmt_par(r.busqueda)} |"
        )
    lines += [
        "",
        f"**Umbral configurado:** `{chosen}`. {conclusion(rows, chosen)}",
        "",
        f"_Generated by `python tools/eval_retrieval.py --sweep` on {datetime.date.today()}_",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Results written to {path}")


def _commit() -> str:
    """Commit del código evaluado y, si los hay, los ficheros con cambios sin commit."""
    raiz = Path(__file__).resolve().parent.parent
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=raiz,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        sucios = subprocess.run(
            ["git", "diff", "HEAD", "--name-only"],
            cwd=raiz,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        return "desconocido"
    if not sucios:
        return sha
    return f"{sha}, con cambios sin commit en {', '.join(sucios)}"


def procedencia(chroma_path: str, model: str, n_cases: int) -> dict:
    """Con qué se generó el barrido: código, índice, modelos y ajustes efectivos."""
    meta = store.read_index_meta(chroma_path)
    return {
        "commit": _commit(),
        "corpus_version": store.read_corpus_version(chroma_path),
        "índice": (
            f"{meta.get('chunks', '?')} fragmentos, construido el "
            f"{meta.get('created_at', '?')}"
        ),
        "embeddings": model,
        "reordenador": reranker._MODEL_NAME,
        "casos": n_cases,
        "overfetch_k / reranker_top_k": (
            f"{settings.overfetch_k} / {settings.reranker_top_k}"
        ),
        "top_k_chunks": settings.top_k_chunks,
        "tope por fuente (max_chunks_per_source)": settings.max_chunks_per_source,
        "k de las búsquedas auxiliares": ", ".join(
            f"{a.name} {a.k}" for a in AUXILIARY_SEARCHES
        ),
        "k de las inyecciones": ", ".join(f"{i.stem} {i.k}" for i in INJECTIONS),
    }


def _check_index_model(meta: dict, model: str, force: bool) -> None:
    indexed = meta.get("embedding_model")
    if indexed is None:
        print(
            "Aviso: el índice no tiene .index_meta.json; no se puede comprobar el modelo."
        )
        return
    if indexed != model and not force:
        raise SystemExit(
            f"El índice fue construido con '{indexed}' pero --model es '{model}': los vectores no son "
            "comparables y el eval sería basura. Usa el mismo modelo o --chroma-path a un índice "
            "construido con ese modelo (o --force si sabes lo que haces)."
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LegalDev retrieval evaluator")
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="Sweep thresholds 0.20–0.45 and write tools/eval_results.md",
    )
    parser.add_argument(
        "--model",
        default=EMBEDDING_MODEL,
        choices=_SUPPORTED_MODELS,
        help=f"Embedding model to evaluate (default: {EMBEDDING_MODEL})",
    )
    parser.add_argument(
        "--chroma-path",
        default=settings.chroma_db_path,
        help="Directorio del índice ChromaDB a evaluar (default: CHROMA_DB_PATH)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Evaluar aunque .index_meta.json declare otro modelo de embeddings (resultados NO comparables)",
    )
    return parser


def main():
    args = _build_parser().parse_args()

    cases_path = Path(__file__).parent / "eval_cases.yaml"
    base_input, cases = _load_cases(cases_path)

    _check_index_model(store.read_index_meta(args.chroma_path), args.model, args.force)

    print(f"Cargando embeddings ({args.model}) y ChromaDB...")
    vs = Chroma(
        persist_directory=args.chroma_path,
        embedding_function=HuggingFaceEmbeddings(
            model_name=args.model, encode_kwargs={"normalize_embeddings": True}
        ),
        collection_name="legaldev",
    )

    if args.sweep:
        rows = sweep(vs, base_input, cases)
        print(
            f"\n{'Threshold':>10}  {'Avg Recall':>10}  {'Avg FP':>8}  {'Avg Noise':>10}"
            f"  {'>=2 frag.':>9}  {'Regla':>7}  {'Busqueda':>8}"
        )
        print("-" * 76)
        for r in rows:
            print(
                f"{r.threshold:>10.2f}  {r.avg_recall:>10.0%}  {r.avg_fp:>8.1f}"
                f"  {r.avg_noise:>10.1f}  {r.producto[0]:>4}/{r.producto[1]:<4}"
                f"  {r.regla[0]:>3}/{r.regla[1]:<3}  {r.busqueda[0]:>3}/{r.busqueda[1]:<4}"
            )
        results_path = Path(__file__).parent / "eval_results.md"
        _write_eval_results(
            rows,
            results_path,
            procedencia(args.chroma_path, args.model, len(cases)),
            chosen=settings.min_relevance_score,
        )
        return

    threshold = settings.min_relevance_score

    print(
        f"\nRetrieval eval — model={args.model}  threshold={threshold}"
        f"  overfetch_k={settings.overfetch_k}  casos={len(cases)}\n"
    )

    _run_standard_eval(cases, base_input, vs, threshold)


def _run_standard_eval(cases, base_input, vs, threshold):
    print(
        f"{'':4} {'Caso':<32} {'Recall':>7}  {'FP':>4}  {'Chunks':>6}  {'Fuentes':>7}  Problemas"
    )
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
            f"{status}  {r['label']:<32} {recall_str} {fp_count:>4}  {r['chunks']:>6}  {r['sources']:>7}  {problems_str}"
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
