"""Equivalencia entre analizar_proyecto (MCP) y POST /v1/analyze (PP-05; PI6; CA-09).

Es la prueba más importante de la extensión: fija como invariante que el servidor MCP es una
capa fina sobre el motor. Cualquier divergencia entre lo que ve un asistente y lo que ve un
integrador de la API es un defecto. Compara solo las partes deterministas del resultado: el
texto del informe depende del modelo y, con el modelo simulado y la caché común, su igualdad
sería trivial (20-requisitos, comentario de CA-09). La parte de CA-09 sobre
listar_normativas y GET /normativas está en PP-02 (tests/test_mcp_contract.py).
"""

import pytest


@pytest.mark.skip(
    reason="TODO(PT2/PP-05): mismos fragmentos, en el mismo orden, por MCP y por REST"
)
def test_pp05_analizar_proyecto_matches_post_v1_analyze():
    """Para cada caso de la batería de regresión (tools/eval_cases.yaml) y del conjunto de
    prueba (eval/cases/acotado), con la caché desactivada y el LLM simulado: la lista de
    service.fragment_id de los fragmentos que recibe el modelo es idéntica, en el mismo
    orden, por las dos vías; y coinciden normativas_detectadas y corpus_version. No basta con
    comparar recuentos (chunks_utilizados)."""


@pytest.mark.skip(
    reason="TODO(PT2/PP-05): una llamada MCP tras la misma petición REST es HIT de caché"
)
def test_pp05_mcp_call_after_rest_call_is_a_cache_hit():
    """Con la caché activa, el LLM simulado se invoca una sola vez para el mismo cuestionario
    por las dos vías."""
