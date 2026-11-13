"""Unit tests for the eval sweep — runs against mock data, no real ChromaDB.

El barrido publica ``tools/eval_results.md``: una tabla por umbral, una conclusión que sale de
los datos (antes era una frase fija, «best recall/noise tradeoff», que la tabla contradecía) y
una cabecera de procedencia. Además de las columnas históricas cuenta el recall con el criterio
del producto (una normativa cuenta con dos fragmentos o más, como ``normativas_detectadas`` en
``app/rag.py``) y lo separa entre las normativas que garantiza una regla (INJECTION) y las que
dependen de la búsqueda.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from langchain_core.documents import Document

sys.path.insert(0, str(Path(__file__).parent.parent))

BASE_INPUT = {
    "tipo_proyecto": "app_web",
    "descripcion_breve": "test",
    "tiene_usuarios_registrados": True,
    "acceso_publico": False,
    "tipos_datos_personales": ["ninguno"],
    "usuarios_menores": False,
    "usuarios_ue": False,
    "transferencia_datos_terceros": False,
    "usa_ia": False,
    "tipo_ia": None,
    "usa_cookies": False,
    "monetizacion": None,
    "contenido_digital": False,
    "ccaa": "Madrid",
    "es_empresa": False,
    "colegiado": None,
}


def test_sweep_returns_one_row_per_threshold():
    from tools.eval_retrieval import THRESHOLDS, SweepRow, sweep

    vs = MagicMock()
    vs.similarity_search_with_relevance_scores.return_value = []
    cases = [
        {"label": "test-off-topic", "off_topic": True, "overrides": {}, "expected": []}
    ]

    rows = sweep(vs, BASE_INPUT, cases)
    assert [r.threshold for r in rows] == list(THRESHOLDS)
    assert list(THRESHOLDS) == [0.20, 0.25, 0.30, 0.35, 0.40, 0.45]
    for row in rows:
        assert isinstance(row, SweepRow)
        assert 0.0 <= row.threshold <= 1.0
        # Sin normativas esperadas no hay nada que recuperar: 0 de 0.
        assert row.producto == row.regla == row.busqueda == (0, 0)


def _doc(texto: str, stem: str) -> Document:
    return Document(page_content=texto, metadata={"source": f"{stem}.pdf", "page": 0})


@pytest.fixture
def vs_rgpd_3_lopdgdd_1():
    """Índice con tres fragmentos del RGPD, uno de la LOPDGDD y dos de una guía."""
    docs = [
        _doc("rgpd 1", "RGPD"),
        _doc("rgpd 2", "RGPD"),
        _doc("rgpd 3", "RGPD"),
        _doc("lopdgdd 1", "LOPDGDD"),
        _doc("guia 1", "Guía X"),
        _doc("guia 2", "Guía X"),
    ]

    def buscar(query, k, filter=None):
        elegidos = [
            d
            for d in docs
            if filter is None or d.metadata["source"] == filter["source"]
        ]
        return [(d, 0.9) for d in elegidos][:k]

    vs = MagicMock()
    vs.similarity_search_with_relevance_scores.side_effect = buscar
    return vs


def test_run_case_counts_with_the_product_criterion_and_splits_rule_and_search(
    vs_rgpd_3_lopdgdd_1, mock_reranker
):
    """La LOPDGDD llega con un solo fragmento: cuenta en el recall histórico (≥ 1) pero no
    en el del producto (≥ 2). El RGPD lo garantiza la INJECTION de datos personales; la
    LOPDGDD depende de la búsqueda."""
    from tools.eval_retrieval import run_case

    case = {
        "label": "rgpd-lopdgdd",
        "overrides": {"tipos_datos_personales": ["email"]},
        "expected": ["RGPD", "LOPDGDD"],
        "negative_expected": ["Guía X"],
    }
    r = run_case(case, BASE_INPUT, vs_rgpd_3_lopdgdd_1, 0.40)

    assert r["recall"] == 1.0
    assert r["found_product"] == ["RGPD"]
    assert r["rule_expected"] == ["RGPD"]
    assert r["search_expected"] == ["LOPDGDD"]
    assert r["chunks_per_stem"]["LOPDGDD"] == 1
    assert r["false_positives"] == ["Guía X"]


def test_sweep_aggregates_product_rule_and_search_recall_as_counts(
    vs_rgpd_3_lopdgdd_1, mock_reranker
):
    from tools.eval_retrieval import sweep

    cases = [
        {
            "label": "rgpd-lopdgdd",
            "overrides": {"tipos_datos_personales": ["email"]},
            "expected": ["RGPD", "LOPDGDD"],
        },
        {"label": "off-topic", "off_topic": True, "overrides": {}, "expected": []},
    ]
    row = sweep(vs_rgpd_3_lopdgdd_1, BASE_INPUT, cases, thresholds=(0.40,))[0]

    assert row.avg_recall == 1.0  # columna histórica: media por caso con ≥ 1 fragmento
    assert row.producto == (1, 2)  # pares (caso, normativa esperada) con ≥ 2 fragmentos
    assert row.regla == (1, 1)
    assert row.busqueda == (0, 1)


def test_rule_guaranteed_follows_the_injection_conditions_and_exclusions():
    from app.models import QuestionnaireInput
    from tools.eval_retrieval import rule_guaranteed

    con_datos = QuestionnaireInput(
        **{**BASE_INPUT, "tipos_datos_personales": ["email"]}
    )
    assert "RGPD" in rule_guaranteed(con_datos)
    assert "LOPDGDD" not in rule_guaranteed(con_datos)  # no tiene INJECTION
    # La guía de IA agéntica tiene INJECTION y EXCLUSION: solo con agentes.
    agentes = QuestionnaireInput(**{**BASE_INPUT, "usa_ia": True, "tipo_ia": "agentes"})
    generativa = QuestionnaireInput(
        **{**BASE_INPUT, "usa_ia": True, "tipo_ia": "generativa"}
    )
    guia = "IA Agentica desde la perspectiva de proteccion de datos - AEPD"
    assert guia in rule_guaranteed(agentes)
    assert guia not in rule_guaranteed(generativa)


def _row(t, recall=1.0, fp=0.0, noise=5.0, producto=(20, 20)):
    from tools.eval_retrieval import SweepRow

    return SweepRow(t, recall, fp, noise, producto, (17, 17), (3, 3))


def test_conclusion_says_what_a_flat_table_shows():
    """Recall y FP iguales en todos los umbrales: la tabla no respalda ninguno; se dice qué
    cambia (el ruido) y cuál tiene menos, sin afirmar que el configurado sea el mejor."""
    from tools.eval_retrieval import conclusion

    rows = [
        _row(t, noise=n) for t, n in zip((0.20, 0.30, 0.40, 0.45), (5.2, 5.2, 5.1, 4.9))
    ]
    texto = conclusion(rows, 0.40)

    assert "best recall/noise tradeoff" not in texto
    assert "no cambian" in texto
    assert "0,45" in texto  # el de menos ruido
    assert "0,40" in texto
    assert "no es el de menos ruido" in texto


def test_conclusion_names_the_best_threshold_when_the_table_discriminates():
    from tools.eval_retrieval import conclusion

    rows = [
        _row(0.30, recall=1.0, fp=0.4, noise=6.0, producto=(20, 20)),
        _row(0.40, recall=1.0, fp=0.0, noise=5.0, producto=(20, 20)),
        _row(0.45, recall=0.9, fp=0.0, noise=4.0, producto=(18, 20)),
    ]
    texto = conclusion(rows, 0.40)

    assert "no cambian" not in texto
    assert "el mejor es 0,40" in texto
    assert "coincide con el configurado" in texto
    assert conclusion(rows, 0.45).count("0,40") >= 1
    assert "no coincide con el configurado (0,45)" in conclusion(rows, 0.45)


def test_write_eval_results_has_provenance_new_columns_and_no_fixed_claim(tmp_path):
    from tools.eval_retrieval import _write_eval_results

    procedencia = {"commit": "abc1234", "corpus_version": "7a2029a4dfd8"}
    path = tmp_path / "eval_results.md"
    _write_eval_results([_row(0.40)], path, procedencia, chosen=0.40)
    texto = path.read_text(encoding="utf-8")

    assert "best recall/noise tradeoff" not in texto
    assert "| commit | abc1234 |" in texto
    assert "| corpus_version | 7a2029a4dfd8 |" in texto
    # Las columnas históricas siguen, con su formato, y se añaden las nuevas.
    assert "| Threshold | Avg Recall | Avg FP | Avg Noise (unexpected stems) |" in texto
    assert "| 0.40      | 100%       | 0.0    | 5.0" in texto
    assert "20/20" in texto and "17/17" in texto and "3/3" in texto
