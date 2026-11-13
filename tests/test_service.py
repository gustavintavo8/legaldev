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


def _index_state(docs):
    """Estado con un vectorstore simulado que contiene ``docs``."""
    state = MagicMock()
    state.vectorstore._collection.get.return_value = {
        "metadatas": [d.metadata for d in docs]
    }
    state.vectorstore.similarity_search_with_relevance_scores.return_value = [
        (d, 0.5) for d in docs
    ]
    state.indexed_normativas = frozenset(
        d.metadata["source"].removesuffix(".pdf") for d in docs
    )
    state.corpus_version = "v-test"
    return state


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
        # Metadatos como los guarda el índice: el encabezado, no el número.
        _doc(
            "Artículo 6. Licitud del tratamiento.",
            "RGPD.pdf",
            page=35,
            article="Artículo 6",
        ),
        _doc(
            "Artículo 22. Cookies y comunicaciones.",
            "LSSI.pdf",
            page=16,
            article="Artículo 22",
        ),
        _doc(
            "Considerando 32. Consentimiento.",
            "RGPD.pdf",
            page=5,
            article="Considerando 32",
        ),
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
    assert (considerando.articulo, considerando.considerando) == (None, "32")


def test_rf24_list_normativas_returns_id_type_pages_and_corpus_version():
    """Una entrada por documento indexado, identificada por la raíz del nombre de fichero."""
    state = _index_state(
        [
            _doc("a", "RGPD.pdf", page=0),
            _doc("b", "RGPD.pdf", page=87),
            _doc("c", "LSSI.pdf", page=40, doc_type="normativa_española"),
        ]
    )
    state.vectorstore._collection.get.return_value["metadatas"].append(
        {"source": "Guia.pdf"}  # sin doc_type ni page
    )

    listado = service.list_normativas(state)

    assert listado.corpus_version == "v-test"
    assert [n.model_dump() for n in listado.normativas] == [
        {"identificador": "Guia", "tipo": "desconocido", "paginas": 0},
        {"identificador": "LSSI", "tipo": "normativa_española", "paginas": 41},
        {"identificador": "RGPD", "tipo": "normativa_europea", "paginas": 88},
    ]


def test_rf25_retrieve_for_source_only_returns_chunks_of_that_source(mock_reranker):
    """Todos los fragmentos devueltos tienen metadata['source'] igual al documento pedido."""
    vs = MagicMock()
    vs.similarity_search_with_relevance_scores.return_value = [
        (_doc("rgpd 1", "RGPD.pdf"), 0.9),
        (
            _doc("lssi 1", "LSSI.pdf"),
            0.8,
        ),  # el filtro de Chroma no debería dejarlo pasar
        (_doc("rgpd 1", "RGPD.pdf"), 0.7),  # duplicado
        (_doc("rgpd 2", "RGPD.pdf"), 0.1),  # sin umbral: también vale
    ]

    docs = rag.retrieve_for_source(
        "registro de usuarios", vs, "RGPD", fetch_k=30, top_k=6
    )

    assert [d.page_content for d in docs] == ["rgpd 1", "rgpd 2"]
    kwargs = vs.similarity_search_with_relevance_scores.call_args.kwargs
    assert kwargs == {"k": 30, "filter": {"source": "RGPD.pdf"}}


@pytest.mark.parametrize("normativa", ["rgpd", "RGPD.pdf", "XYZ", ""])
def test_rf25_unknown_normativa_lists_available_sources(normativa):
    """El error lleva la lista de normativas indexadas para que el asistente corrija."""
    state = _index_state([_doc("a", "RGPD.pdf"), _doc("b", "LSSI.pdf")])

    with pytest.raises(service.UnknownNormativaError) as exc_info:
        asyncio.run(
            service.consultar_obligaciones(
                normativa, "cookies", state, via=service.Via.MCP
            )
        )

    assert exc_info.value.normativa == normativa
    assert exc_info.value.disponibles == ["LSSI", "RGPD"]
    state.vectorstore.similarity_search_with_relevance_scores.assert_not_called()


def test_rf25_consultar_obligaciones_is_deterministic_and_does_not_call_the_llm(
    mock_reranker, caplog
):
    """Dos llamadas iguales devuelven los mismos fragmentos en el mismo orden; el LLM simulado
    no recibe ninguna llamada y el contexto no aparece en los registros."""
    caplog.set_level("DEBUG")
    sentinel = "CONTEXTO-CENTINELA-7f3a"
    state = _index_state(
        [
            _doc("Artículo 22. Cookies.", "LSSI.pdf", page=16, article="Artículo 22"),
            _doc(
                "Artículo 21. Comunicaciones.",
                "LSSI.pdf",
                page=15,
                article="Artículo 21",
            ),
        ]
    )

    first = asyncio.run(
        service.consultar_obligaciones("LSSI", sentinel, state, via=service.Via.MCP)
    )
    second = asyncio.run(
        service.consultar_obligaciones("LSSI", sentinel, state, via=service.Via.MCP)
    )

    assert first == second
    assert first.normativa == "LSSI"
    assert [(f.articulo, f.pagina) for f in first.fragmentos] == [
        ("22", 17),
        ("21", 16),
    ]
    assert all(f.texto and f.normativa == "LSSI" for f in first.fragmentos)
    state.groq_client.invoke.assert_not_called()
    assert sentinel not in caplog.text
    assert '"event": "consulta_normativa"' in caplog.text


@pytest.mark.skip(
    reason="TODO(PT5/PI2): _retrieve(config=RetrievalConfig()) idéntico a producción"
)
def test_pi2_retrieve_with_default_config_matches_current_retrieve():
    """Con la configuración por defecto (S), mismos docs y mismo orden que rag._retrieve hoy."""
