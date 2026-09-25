"""Pruebas de contrato del servidor MCP (RF-22 a RF-25; RNF-16).

PP-01 a PP-04, PP-06, PP-13 a PP-15 y los errores de protocolo de tab:ana-errores-mcp. Se
ejecutarán con un cliente MCP en proceso sobre TestClient (sin red), conforme a la revisión
2026-07-28. Hoy solo corren las guardas de las constantes del contrato.
"""

import pytest

from app import mcp_server


def test_contract_constants_match_the_memoria():
    assert mcp_server.PROTOCOL_VERSION == "2026-07-28"
    assert mcp_server.PROTOCOL_VERSION in mcp_server.SUPPORTED_VERSIONS
    assert mcp_server.TOOL_NAMES == (
        "analizar_proyecto",
        "listar_normativas",
        "consultar_obligaciones",
    )
    assert set(mcp_server.TOOL_DESCRIPTIONS) == set(mcp_server.TOOL_NAMES)
    assert mcp_server.TOOLS_LIST_CACHE_SCOPE in ("public", "private")


def test_tool_annotations_match_the_memoria():
    # 22-arquitectura, «Esquema de las herramientas», y tab:det-mcp-herramientas.
    annotations = mcp_server.TOOL_ANNOTATIONS
    assert set(annotations) == set(mcp_server.TOOL_NAMES)
    assert all(a["readOnlyHint"] is True for a in annotations.values())
    # Solo analizar_proyecto sale del índice local (envía la descripción al proveedor):
    # conserva openWorldHint por defecto (verdadero).
    assert "openWorldHint" not in annotations["analizar_proyecto"]
    assert annotations["listar_normativas"]["openWorldHint"] is False
    assert annotations["consultar_obligaciones"]["openWorldHint"] is False


@pytest.mark.skip(
    reason="TODO(PT2/PP-01): versión y capacidades en cada petición, sin petición previa"
)
def test_pp01_tools_call_without_prior_request_carries_version_in_meta():
    """Un tools/call sin ninguna petición previa se atiende; una versión no soportada en _meta
    recibe 400 con UnsupportedProtocolVersionError (-32022) y data.supported; si
    MCP-Protocol-Version no coincide con la de _meta, 400 con HeaderMismatch (-32020)."""


@pytest.mark.skip(
    reason="TODO(PT2/PP-13): server/discover declara 2026-07-28, tools e identidad"
)
def test_pp13_server_discover_declares_revision_and_tools_capability():
    """supportedVersions contiene 2026-07-28, capabilities.tools existe, serverInfo en _meta
    y resultType complete."""


@pytest.mark.skip(
    reason="TODO(PT2/PP-02): tools/list devuelve las tres herramientas en orden estable"
)
def test_pp02_tools_list_returns_exactly_three_tools_with_valid_schemas():
    """Mismo orden en llamadas repetidas; inputSchema y outputSchema válidos como JSON Schema
    2020-12; anotaciones de TOOL_ANNOTATIONS."""


@pytest.mark.skip(
    reason="TODO(PT2/PP-02): esquema publicado y QuestionnaireInput aceptan y rechazan lo mismo"
)
def test_pp02_published_schema_and_model_accept_and_reject_the_same_questionnaires():
    """Cuestionarios de ejemplo válidos e inválidos (enumeración, longitud, usa_ia sin
    tipo_ia): el esquema posprocesado (validado con jsonschema) y el modelo Pydantic dan el
    mismo veredicto en cada uno. No se exige igualdad con model_json_schema(): el esquema
    publicado resuelve los $ref y expresa la dependencia con if/then."""


@pytest.mark.skip(
    reason="TODO(PT2/PP-02): listar_normativas devuelve lo mismo que GET /normativas"
)
def test_pp02_listar_normativas_matches_get_normativas():
    """Mismos documentos (por su identificador, sin .pdf) y versión del corpus."""


@pytest.mark.skip(
    reason="TODO(PT2/PP-15): resultType en todo resultado; tools/list con ttlMs y cacheScope"
)
def test_pp15_every_result_is_complete_and_tools_list_is_cacheable():
    """server/discover, tools/list y tools/call (también con isError) llevan resultType
    complete; tools/list lleva ttlMs entero >= 0 y cacheScope en {public, private}."""


@pytest.mark.skip(
    reason="TODO(PT2/PP-03): analizar_proyecto devuelve texto y structuredContent"
)
def test_pp03_analizar_proyecto_returns_report_and_structured_content():
    """Informe y serialización JSON en el texto; structuredContent conforme al outputSchema
    (normativas, identificadores de fragmentos, modelo, versión del corpus, citas); isError
    false; resultType complete."""


@pytest.mark.skip(
    reason="TODO(PT2/PP-04): cuestionario inválido -> isError con los campos erróneos"
)
def test_pp04_invalid_questionnaire_is_tool_error_not_protocol_error():
    """Respuesta JSON-RPC con result (no error), isError true y los campos que fallan."""


@pytest.mark.skip(
    reason="TODO(PT2/PP-04): herramienta desconocida -> error del protocolo -32602"
)
def test_pp04_unknown_tool_is_protocol_error():
    """tools/call con un name fuera de TOOL_NAMES: error JSON-RPC -32602, no isError."""


@pytest.mark.skip(
    reason="TODO(PT2/PP-06): normativa desconocida -> error con las disponibles"
)
def test_pp06_consultar_obligaciones_unknown_normativa_lists_available():
    """isError true y la lista de normativas de listar_normativas en el texto del error."""


@pytest.mark.skip(
    reason="TODO(PT2/RF-25): consultar_obligaciones devuelve fragmentos sin llamar al modelo"
)
def test_rf25_consultar_obligaciones_returns_located_fragments_without_llm():
    """Todos los fragmentos son de la normativa pedida, con identificador, página, artículo y
    texto, en el orden del reordenador; el LLM simulado no se invoca."""


@pytest.mark.skip(
    reason="TODO(PT2/RF-23): sin cobertura -> resultado sin obligaciones (CU-07, 5c)"
)
def test_rf23_no_coverage_is_tool_result_not_http_404():
    """El equivalente MCP del 404 de /v1/analyze es un resultado con isError false."""


@pytest.mark.skip(
    reason="TODO(PT2/RNF-16): initialize de un cliente 2025-11-25 -> 400 por cabeceras"
)
def test_rnf16_legacy_initialize_is_rejected_for_missing_headers():
    """Un initialize sin MCP-Protocol-Version ni Mcp-Method recibe 400, y el mensaje nombra
    las versiones soportadas (tab:ana-errores-mcp). Si la prueba de concepto decide un
    servidor de doble era, esta prueba cambia: initialize se atiende con la semántica
    2025-11-25."""


@pytest.mark.skip(
    reason="TODO(PT2/RNF-16): método no implementado con cabeceras válidas -> 404 y -32601"
)
def test_rnf16_unknown_method_with_valid_headers_returns_404_method_not_found():
    """Por ejemplo ping, que la revisión 2026-07-28 elimina, enviado con MCP-Protocol-Version
    2026-07-28 y Mcp-Method ping coherentes con el cuerpo. Sin esas cabeceras es 400
    (HeaderMismatch), no 404."""
