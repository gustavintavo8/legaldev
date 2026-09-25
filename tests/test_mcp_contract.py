"""Pruebas de contrato del servidor MCP (PP-01 a PP-04 y PP-06; RF-22 a RF-25; RNF-16).

Se ejecutarán con un cliente MCP en proceso sobre TestClient (sin red), conforme a la
revisión 2026-07-28. Hoy solo corren las guardas de las constantes del contrato.
"""

import pytest

from app import mcp_server


def test_contract_constants_match_the_memoria():
    assert mcp_server.PROTOCOL_VERSION == "2026-07-28"
    assert mcp_server.TOOL_NAMES == (
        "analizar_proyecto",
        "listar_normativas",
        "consultar_obligaciones",
    )
    assert set(mcp_server.TOOL_DESCRIPTIONS) == set(mcp_server.TOOL_NAMES)
    assert mcp_server.TOOLS_LIST_CACHE_SCOPE in ("public", "private")


@pytest.mark.skip(
    reason="TODO(PT2/PP-01): server/discover declara 2026-07-28 y la capacidad tools"
)
def test_pp01_server_discover_declares_revision_and_tools_capability():
    """supportedVersions contiene 2026-07-28, capabilities.tools existe, resultType complete.

    PP-01 habla de «inicialización de la sesión»; la revisión 2026-07-28 ya no tiene
    initialize: su equivalente es server/discover.
    """


@pytest.mark.skip(
    reason="TODO(PT2/PP-02): tools/list devuelve exactamente tres herramientas"
)
def test_pp02_tools_list_returns_exactly_three_tools_with_valid_schemas():
    """Nombre, descripción e inputSchema válido como JSON Schema 2020-12; orden determinista."""


@pytest.mark.skip(
    reason="TODO(PT2/PP-02): tools/list incluye ttlMs, cacheScope y resultType"
)
def test_pp02_tools_list_is_cacheable_result():
    """ttlMs entero >= 0, cacheScope en {public, private}, resultType == complete."""


@pytest.mark.skip(
    reason="TODO(PT2/PP-02): inputSchema de analizar_proyecto == QuestionnaireInput"
)
def test_pp02_analizar_proyecto_input_schema_is_generated_from_questionnaire():
    """El esquema se obtiene de QuestionnaireInput.model_json_schema(), no se duplica a mano."""


@pytest.mark.skip(
    reason="TODO(PT2/PP-03): analizar_proyecto devuelve texto y structuredContent"
)
def test_pp03_analizar_proyecto_returns_report_and_structured_content():
    """Informe en content[0].text; structuredContent con normativas, fragmentos, modelo,
    versión del corpus, citas y aviso; isError false; resultType complete."""


@pytest.mark.skip(
    reason="TODO(PT2/PP-04): cuestionario inválido -> isError con los campos erróneos"
)
def test_pp04_invalid_questionnaire_is_tool_error_not_protocol_error():
    """Respuesta JSON-RPC con result (no error), isError true y los campos que fallan."""


@pytest.mark.skip(
    reason="TODO(PT2/PP-06): normativa desconocida -> error con las disponibles"
)
def test_pp06_consultar_obligaciones_unknown_normativa_lists_available():
    """isError true y la lista de normativas de listar_normativas en el texto del error."""


@pytest.mark.skip(
    reason="TODO(PT2/RF-23): sin cobertura -> resultado sin obligaciones (CU-07, 4d)"
)
def test_rf23_no_coverage_is_tool_result_not_http_404():
    """El equivalente MCP del 404 de /v1/analyze es un resultado, no un error de transporte."""


@pytest.mark.skip(
    reason="TODO(PT2/RNF-16): resultType presente en todos los resultados"
)
def test_rnf16_every_result_carries_result_type():
    """server/discover, tools/list y tools/call llevan resultType; nunca input_required."""


@pytest.mark.skip(
    reason="TODO(PT2/RNF-16): versión no soportada -> 400 y error -32022 con supported"
)
def test_rnf16_unsupported_protocol_version_returns_32022():
    """data.supported lista las versiones del servidor y data.requested la pedida."""


@pytest.mark.skip(
    reason="TODO(PT2/RNF-16): Mcp-Method/Mcp-Name distintos del cuerpo -> 400 y -32020"
)
def test_rnf16_header_body_mismatch_returns_header_mismatch_error():
    """También si falta MCP-Protocol-Version, Mcp-Method o, en tools/call, Mcp-Name."""


@pytest.mark.skip(
    reason="TODO(PT2/RNF-16): GET y DELETE sobre /mcp -> 405; Mcp-Session-Id se ignora"
)
def test_rnf16_get_and_delete_return_405_and_session_header_is_ignored():
    """La revisión elimina el flujo GET y las sesiones; no se emite Mcp-Session-Id."""


@pytest.mark.skip(reason="TODO(PT2/RNF-16): método desconocido -> 404 y -32601")
def test_rnf16_unknown_method_returns_404_method_not_found():
    """Incluye ping (y initialize, salvo que el spike decida un servidor dual-era)."""
