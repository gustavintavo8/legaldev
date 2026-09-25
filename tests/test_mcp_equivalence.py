"""Equivalencia entre analizar_proyecto (MCP) y POST /v1/analyze (PP-05; PI6; CA-09).

Es la prueba más importante de la extensión: fija como invariante que el servidor MCP es una
capa fina sobre el motor. Cualquier divergencia entre lo que ve un asistente y lo que ve un
integrador de la API es un defecto.
"""

import pytest


@pytest.mark.skip(
    reason="TODO(PT2/PP-05): misma salida por MCP y por REST en los casos del gold standard"
)
def test_pp05_analizar_proyecto_matches_post_v1_analyze_on_gold_standard():
    """Para cada caso de tools/eval_cases.yaml, con el LLM simulado: mismas
    normativas_detectadas, mismo chunks_utilizados y mismas estadísticas de citas."""


@pytest.mark.skip(
    reason="TODO(PT2/PP-05): el informe Markdown es idéntico por las dos vías"
)
def test_pp05_report_text_is_identical_across_access_paths():
    """content[0].text del resultado MCP == respuesta_completa de la API REST."""


@pytest.mark.skip(
    reason="TODO(PT2/CU-07): una petición por MCP tras otra igual por REST es HIT de caché"
)
def test_cu07_mcp_call_after_rest_call_is_a_cache_hit():
    """El LLM simulado se invoca una sola vez para el mismo cuestionario por las dos vías."""
