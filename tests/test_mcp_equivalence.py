"""Equivalencia entre analizar_proyecto (MCP) y POST /v1/analyze (PP-05; PI6; CA-09).

Es la prueba más importante de la extensión: fija como invariante que el servidor MCP es una
capa fina sobre el motor. Cualquier divergencia entre lo que ve un asistente y lo que ve un
integrador de la API es un defecto. Compara solo las partes deterministas del resultado: el
texto del informe depende del modelo y, con el modelo simulado y la caché común, su igualdad
sería trivial (20-requisitos, comentario de CA-09). La parte de CA-09 sobre
listar_normativas y GET /normativas está en PP-02 (tests/test_mcp_contract.py).

El índice simulado devuelve fragmentos distintos según la consulta (puntuación derivada de un
resumen de consulta y texto), con varias normativas, páginas y artículos, de modo que cada
caso recorre de verdad las exclusiones, las búsquedas auxiliares, el tope por normativa y las
inyecciones.
"""

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from langchain_core.documents import Document

from app import cache, rag
from app.fragments import fragment_id
from tests._mcp import message, rpc
from tests.conftest import MCP_TEST_KEYS

ROOT = Path(__file__).resolve().parent.parent
# Raíces reales de las reglas de app/rag.py (inyecciones y exclusiones), para que se activen.
FUENTES = (
    "RGPD",
    "LOPDGDD",
    "LSSI",
    "EU AI Act",
    "Guía sobre uso de cookies - AEPD",
    "IA Agentica desde la perspectiva de proteccion de datos - AEPD",
    "Adecuación al RGPD de tratamientos que incorporan IA - AEPD",
    "Código Ético y Deontológico CCII",
    "Real Decreto 311-2022 ENS",
)
POOL = [
    Document(
        page_content=f"{fuente}, artículo {n}: obligación número {n} de {fuente}.",
        metadata={"source": f"{fuente}.pdf", "page": n * 3, "article": str(n)},
    )
    for fuente in FUENTES
    for n in range(1, 7)
]


def _puntuacion(query: str, texto: str) -> float:
    return int(hashlib.md5(f"{query}|{texto}".encode()).hexdigest()[:4], 16) / 0xFFFF


def _buscar(query, k, filter=None):
    docs = [
        d for d in POOL if filter is None or d.metadata["source"] == filter["source"]
    ]
    puntuados = sorted(
        ((d, _puntuacion(query, d.page_content)) for d in docs), key=lambda x: -x[1]
    )
    return puntuados[:k]


def _reordenar(query, docs, top_k):
    return sorted(docs, key=lambda d: -_puntuacion("rerank|" + query, d.page_content))[
        :top_k
    ]


def _casos():
    datos = yaml.safe_load(
        (ROOT / "tools" / "eval_cases.yaml").read_text(encoding="utf-8")
    )
    casos = [
        (c["label"], {**datos["base_input"], **c.get("overrides", {})})
        for c in datos["cases"]
    ]
    # Conjunto de prueba (PT4): un YAML por caso con el cuestionario completo.
    for path in sorted((ROOT / "eval" / "cases" / "acotado").glob("*.yaml")):
        caso = yaml.safe_load(path.read_text(encoding="utf-8"))
        casos.append((caso["id"], caso["cuestionario"]))
    return casos


CASOS = _casos()


@pytest.fixture
def indice(mcp_http):
    """El índice simulado y un espía de los fragmentos que recibe el modelo."""
    mcp_http.app.state.vectorstore.similarity_search_with_relevance_scores.side_effect = _buscar
    vistos: list[list[str]] = []
    real = rag._build_user_message

    def espia(inp, docs, not_retrieved):
        vistos.append([fragment_id(d.page_content) for d in docs])
        return real(inp, docs, not_retrieved)

    with (
        patch("app.reranker.rerank", side_effect=_reordenar),
        patch("app.rag._build_user_message", side_effect=espia),
    ):
        yield vistos


def _rest(http, cuestionario):
    return http.post(
        "/v1/analyze", json=cuestionario, headers={"X-API-Key": MCP_TEST_KEYS[0]}
    )


def _mcp(http, cuestionario):
    r = rpc(
        http,
        "tools/call",
        {"name": "analizar_proyecto", "arguments": cuestionario},
    )
    assert r.status_code == 200
    return message(r)["result"]


def test_casos_de_regresion_cargados():
    assert len(CASOS) >= 13


@pytest.mark.parametrize(("label", "cuestionario"), CASOS, ids=[c[0] for c in CASOS])
def test_pp05_analizar_proyecto_matches_post_v1_analyze(
    mcp_http, indice, label, cuestionario
):
    """Para cada caso de la batería de regresión (tools/eval_cases.yaml) y del conjunto de
    prueba (eval/cases/acotado), con la caché vaciada entre vías y el LLM simulado: la lista
    de fragment_id de los fragmentos que recibe el modelo es idéntica, en el mismo orden, por
    las dos vías, y coincide con structuredContent.fragmentos; coinciden también
    normativas_detectadas y corpus_version. No basta con comparar recuentos."""
    cache.clear()
    rest = _rest(mcp_http, cuestionario)
    cache.clear()
    mcp = _mcp(mcp_http, cuestionario)

    if rest.status_code == 404:
        assert mcp["isError"] is False
        assert mcp["structuredContent"]["sin_cobertura"] is True
        assert indice == []
        return
    assert rest.status_code == 200, label
    assert mcp["isError"] is False, label
    assert len(indice) == 2, label
    por_rest, por_mcp = indice
    assert por_rest, label
    assert por_rest == por_mcp, label
    data = mcp["structuredContent"]
    assert [f["identificador"] for f in data["fragmentos"]] == por_mcp
    assert data["normativas_detectadas"] == rest.json()["normativas_detectadas"]
    assert data["corpus_version"] == rest.json()["corpus_version"]
    assert data["llm_model"] == rest.json()["llm_model"]
    assert data["citas"] == rest.json()["citas"]


def test_pp05_the_simulated_index_exercises_several_normativas(mcp_http, indice):
    """Control de la prueba anterior: casi todos los casos tienen cobertura, el contexto
    mezcla normativas y cambia de un caso a otro."""
    estados = []
    for _label, cuestionario in CASOS:
        cache.clear()
        mcp_http.app.state.limiter._storage.reset()  # 13 peticiones REST en una prueba
        estados.append(_rest(mcp_http, cuestionario).status_code)
    # Los casos sin cobertura (404) también se comparan: MCP devuelve sin_cobertura.
    assert estados.count(200) >= len(CASOS) * 2 // 3
    assert estados.count(404) + estados.count(200) == len(CASOS)
    assert len({tuple(c) for c in indice}) > len(indice) // 2
    por_id = {fragment_id(d.page_content): d.metadata["source"] for d in POOL}
    assert all(len({por_id[i] for i in contexto}) > 1 for contexto in indice)


def test_pp05_mcp_call_after_rest_call_is_a_cache_hit(
    mcp_http, indice, sample_input_dict
):
    """Con la caché activa, el LLM simulado se invoca una sola vez para el mismo cuestionario
    por las dos vías."""
    llm = mcp_http.app.state.groq_client
    antes = llm.invoke.call_count
    rest = _rest(mcp_http, sample_input_dict)
    assert rest.headers["X-Cache"] == "MISS"
    mcp = _mcp(mcp_http, sample_input_dict)

    assert llm.invoke.call_count == antes + 1
    assert len(indice) == 1
    assert [
        f["identificador"] for f in mcp["structuredContent"]["fragmentos"]
    ] == indice[0]
    again = _rest(mcp_http, sample_input_dict)
    assert again.headers["X-Cache"] == "HIT"
