"""Capa de servicio común REST/MCP (app/service.py). Pendiente de PT2 salvo las guardas."""

import pytest
from fastapi import HTTPException

from app import service


def test_domain_errors_do_not_depend_on_fastapi_and_map_to_current_status_codes():
    # Los códigos reproducen los que devuelve hoy run_pipeline por la API REST.
    assert not any(issubclass(e, HTTPException) for e in service.HTTP_STATUS)
    assert service.HTTP_STATUS[service.NoCoverageError] == 404
    assert service.HTTP_STATUS[service.LLMUnavailableError] == 503
    assert service.HTTP_STATUS[service.RetrievalTimeoutError] == 503


def test_retrieval_config_default_is_production_system_s():
    assert all(vars(service.RetrievalConfig()).values())


@pytest.mark.skip(
    reason="TODO(PT2/RF-22): analyze() comparte la entrada de caché entre REST y MCP"
)
def test_rf22_analyze_shares_cache_entry_between_rest_and_mcp():
    """Mismo cuestionario por /v1/analyze y por service.analyze(via=MCP): un solo MISS."""


@pytest.mark.skip(
    reason="TODO(PT2/RF-22): el motor lanza errores de dominio en lugar de HTTPException"
)
def test_rf22_no_coverage_raises_domain_error_not_http_exception():
    """Sin fragmentos sobre el umbral: NoCoverageError; la API REST sigue devolviendo 404."""


@pytest.mark.skip(
    reason="TODO(PT2/RF-22): los dos modelos caídos producen LLMUnavailableError"
)
def test_rf22_llm_unavailable_raises_domain_error():
    """Principal y respaldo fallan: LLMUnavailableError; REST 503, MCP resultado de error."""


@pytest.mark.skip(
    reason="TODO(PT2/RF-24): list_normativas() con nombre, tipo, nivel y corpus_version"
)
def test_rf24_list_normativas_returns_name_type_tier_and_corpus_version():
    """Una entrada por documento indexado; el nivel coincide con los tiers del SYSTEM_PROMPT."""


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
    reason="TODO(PT5/PI2): _retrieve(config=RetrievalConfig()) idéntico a producción"
)
def test_pi2_retrieve_with_default_config_matches_current_retrieve():
    """Con la configuración por defecto (S), mismos docs y mismo orden que rag._retrieve hoy."""
