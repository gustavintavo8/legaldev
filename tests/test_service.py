"""Capa de servicio común REST/MCP (app/service.py; RF-22, RF-24, RF-25, CU-07)."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from langchain_core.documents import Document
from prometheus_client import REGISTRY

from app import rag, service
from app.models import QuestionnaireInput

NO_COVERAGE_DETAIL = (
    "No se encontraron normativas aplicables a este tipo de proyecto en la base de "
    "conocimiento."
)


def _doc(texto, source, page=0, article=None, doc_type="normativa_europea"):
    meta = {"source": source, "page": page, "doc_type": doc_type}
    if article is not None:
        meta["article"] = article
    return Document(page_content=texto, metadata=meta)


def _no_injection_input(sample_input_dict):
    # Sin datos personales, IA ni cookies no se dispara ninguna inyección, así que un umbral
    # no superado deja el contexto vacío (como test_run_pipeline_no_relevant_docs_raises_404).
    return dict(
        sample_input_dict,
        tipos_datos_personales=["ninguno"],
        usa_ia=False,
        tipo_ia=None,
        usa_cookies=False,
        colegiado=None,
    )


def _metric(name, **labels):
    return REGISTRY.get_sample_value(name, labels) or 0.0


def test_domain_errors_do_not_depend_on_fastapi_and_map_to_current_status_codes():
    # Los códigos reproducen los que devuelve hoy run_pipeline por la API REST
    # (tab:det-mcp-errores); NormativaDesconocida no tiene equivalente REST.
    assert not any(issubclass(e, HTTPException) for e in service.HTTP_STATUS)
    assert service.HTTP_STATUS[service.NoCoverageError] == 404
    assert service.HTTP_STATUS[service.LLMUnavailableError] == 503
    assert service.HTTP_STATUS[service.RetrievalTimeoutError] == 503
    assert service.HTTP_STATUS[service.InvalidMappingError] == 503
    assert service.UnknownNormativaError not in service.HTTP_STATUS


def test_access_paths_are_the_three_of_the_memoria():
    # 23-detalle, «Capa de servicio y traducción de errores»: rest, mcp o ci.
    assert [v.value for v in service.Via] == ["rest", "mcp", "ci"]


def test_fragment_id_is_the_deduplication_hash_truncated_to_12(mock_doc):
    # 23-detalle, «Herramientas, identificadores y resultado»: el identificador que compara
    # PP-05 es el mismo resumen con el que rag._retrieve deduplica los candidatos.
    from app.rag import _content_hash

    fid = service.fragment_id(mock_doc.page_content)
    assert fid == _content_hash(mock_doc)[:12]
    assert len(fid) == 12 and all(c in "0123456789abcdef" for c in fid)


def test_retrieval_config_default_is_production_system_s():
    assert all(vars(service.RetrievalConfig()).values())


def test_rf22_analyze_shares_cache_entry_between_rest_and_mcp(
    client, sample_input_dict
):
    """Mismo cuestionario por /v1/analyze y por service.analyze(via=MCP): un solo MISS."""
    llm = client.app.state.groq_client
    r = client.post("/v1/analyze", json=sample_input_dict)
    assert r.status_code == 200
    assert r.headers["X-Cache"] == "MISS"
    calls = llm.invoke.call_count

    analysis = asyncio.run(
        service.analyze(
            QuestionnaireInput(**sample_input_dict),
            client.app.state,
            via=service.Via.MCP,
        )
    )

    assert analysis.cache_hit is True
    assert llm.invoke.call_count == calls
    assert analysis.result.response.model_dump(mode="json") == r.json()


def test_rf22_no_coverage_raises_domain_error_not_http_exception(
    client, mock_doc, sample_input_dict
):
    """Sin fragmentos sobre el umbral: NoCoverageError; la API REST sigue devolviendo 404."""
    payload = _no_injection_input(sample_input_dict)
    vs = client.app.state.vectorstore
    vs.similarity_search_with_relevance_scores.return_value = [(mock_doc, 0.05)]

    with pytest.raises(service.NoCoverageError) as exc_info:
        asyncio.run(
            service.analyze(
                QuestionnaireInput(**payload), client.app.state, via=service.Via.MCP
            )
        )
    assert not isinstance(exc_info.value, HTTPException)
    assert exc_info.value.detail == NO_COVERAGE_DETAIL

    r = client.post("/v1/analyze", json=payload)
    assert r.status_code == 404
    assert r.json() == {"detail": NO_COVERAGE_DETAIL}


def test_rf22_llm_unavailable_raises_domain_error(client, sample_input_dict):
    """Principal y respaldo fallan: LLMUnavailableError; REST 503 con el mismo texto."""
    # En el fixture client los dos clientes de Groq son el mismo objeto simulado.
    client.app.state.groq_client.invoke.side_effect = Exception("Groq caído")
    client.app.state.groq_fallback_client = client.app.state.groq_client

    with pytest.raises(service.LLMUnavailableError):
        asyncio.run(
            service.analyze(
                QuestionnaireInput(**sample_input_dict),
                client.app.state,
                via=service.Via.MCP,
            )
        )

    r = client.post("/v1/analyze", json=sample_input_dict)
    assert r.status_code == 503
    assert r.json() == {"detail": "LLM service unavailable. Please try again later."}


def test_cu07_analyze_counts_requests_by_access_path(client, sample_input_dict):
    rest_before = _metric("legaldev_analyze_requests_total", via="rest")
    mcp_before = _metric("legaldev_analyze_requests_total", via="mcp")

    client.post("/v1/analyze", json=sample_input_dict)
    asyncio.run(
        service.analyze(
            QuestionnaireInput(**sample_input_dict),
            client.app.state,
            via=service.Via.MCP,
        )
    )

    assert _metric("legaldev_analyze_requests_total", via="rest") == rest_before + 1
    assert _metric("legaldev_analyze_requests_total", via="mcp") == mcp_before + 1


def test_fragmentos_follow_llm_order_and_have_no_text(sample_input, mock_reranker):
    docs = [
        _doc("Artículo 6. Licitud del tratamiento.", "RGPD.pdf", page=35, article="6"),
        _doc(
            "Artículo 22. Cookies y comunicaciones.", "LSSI.pdf", page=16, article="22"
        ),
        _doc("Considerando 32. Consentimiento.", "RGPD.pdf", page=5),
    ]
    state = MagicMock()
    state.vectorstore.similarity_search_with_relevance_scores.return_value = [
        (d, 0.9) for d in docs
    ]
    state.groq_client.invoke.return_value = MagicMock(content="Informe")
    state.groq_fallback_client = None
    state.indexed_normativas = frozenset({"RGPD", "LSSI"})
    state.corpus_version = "v-test"
    seen: list[list] = []
    real = rag._build_user_message

    def spy(inp, ctx_docs, not_retrieved):
        seen.append(list(ctx_docs))
        return real(inp, ctx_docs, not_retrieved)

    with patch("app.rag._build_user_message", side_effect=spy):
        analysis = asyncio.run(
            service.analyze(sample_input, state, via=service.Via.REST)
        )

    fragmentos = analysis.result.fragmentos
    assert [f.identificador for f in fragmentos] == [
        service.fragment_id(d.page_content) for d in seen[0]
    ]
    assert all(f.texto is None for f in fragmentos)
    art6 = next(f for f in fragmentos if f.articulo == "6")
    assert (art6.normativa, art6.pagina) == ("RGPD", 36)
    considerando = next(f for f in fragmentos if f.pagina == 6)
    assert considerando.articulo is None


@pytest.mark.skip(
    reason="TODO(PT2/RF-24): list_normativas() con identificador, tipo, páginas y corpus_version"
)
def test_rf24_list_normativas_returns_id_type_pages_and_corpus_version():
    """Una entrada por documento indexado, identificada por la raíz del nombre de fichero."""


@pytest.mark.skip(
    reason="TODO(PT2/RF-25): _retrieve_for_source filtra por documento con el mismo reordenador"
)
def test_rf25_retrieve_for_source_only_returns_chunks_of_that_source():
    """Todos los fragmentos devueltos tienen metadata['source'] igual al documento pedido."""


@pytest.mark.skip(
    reason="TODO(PT2/RF-25): normativa desconocida -> UnknownNormativaError con las disponibles"
)
def test_rf25_unknown_normativa_lists_available_sources():
    """El error lleva la lista de normativas indexadas para que el asistente corrija."""


@pytest.mark.skip(
    reason="TODO(PT2/RF-25): consultar_obligaciones no invoca al modelo de lenguaje"
)
def test_rf25_consultar_obligaciones_is_deterministic_and_does_not_call_the_llm():
    """Dos llamadas iguales devuelven los mismos fragmentos en el mismo orden; el LLM simulado
    no recibe ninguna llamada y el contexto no aparece en los registros."""


@pytest.mark.skip(
    reason="TODO(PT5/PI2): _retrieve(config=RetrievalConfig()) idéntico a producción"
)
def test_pi2_retrieve_with_default_config_matches_current_retrieve():
    """Con la configuración por defecto (S), mismos docs y mismo orden que rag._retrieve hoy."""
