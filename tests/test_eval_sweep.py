"""Unit tests for the eval sweep — runs against mock data, no real ChromaDB."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_sweep_returns_one_row_per_threshold():
    from tools.eval_retrieval import sweep

    vs = MagicMock()
    vs.similarity_search_with_relevance_scores.return_value = []
    base_input = {
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
    cases = [
        {"label": "test-off-topic", "off_topic": True, "overrides": {}, "expected": []}
    ]

    rows = sweep(vs, base_input, cases)
    assert len(rows) == 6  # 0.20, 0.25, 0.30, 0.35, 0.40, 0.45
    for threshold, avg_recall, avg_fp, avg_noise in rows:
        assert 0.0 <= threshold <= 1.0
