"""Pruebas de contrato del servidor MCP (RF-22 a RF-25; RNF-16).

PP-01 a PP-04, PP-06, PP-13 y PP-15, y los errores de protocolo de tab:ana-errores-mcp. Las
herramientas se prueban con el cliente MCP del SDK en proceso; el protocolo HTTP, con
peticiones JSON-RPC en crudo contra /mcp montado en la aplicación (TestClient, sin red).
"""

import base64

import jsonschema
import pytest
from mcp.shared.exceptions import MCPError

from app import mcp_server
from app.fragments import fragment_id
from tests._mcp import (
    call_in_process,
    list_tools_in_process,
    message,
    rpc,
    rpc_body,
    text_of,
)


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


# ----------------------------------------------------------------------- protocolo (HTTP)


def test_pp01_tools_call_without_prior_request_carries_version_in_meta(mcp_http):
    """Un tools/call sin ninguna petición previa se atiende; una versión no soportada en _meta
    recibe 400 con UnsupportedProtocolVersionError (-32022) y data.supported; sin las
    capacidades del cliente, 400 con -32602; si MCP-Protocol-Version no coincide con la de
    _meta, 400 con HeaderMismatch (-32020)."""
    ok = rpc(mcp_http, "tools/call", {"name": "listar_normativas", "arguments": {}})
    assert ok.status_code == 200
    assert message(ok)["result"]["isError"] is False

    body = rpc_body("tools/list")
    body["params"]["_meta"]["io.modelcontextprotocol/protocolVersion"] = "2099-01-01"
    bad = rpc(
        mcp_http,
        "tools/list",
        body=body,
        headers={"MCP-Protocol-Version": "2099-01-01"},
    )
    assert bad.status_code == 400
    error = message(bad)["error"]
    assert error["code"] == mcp_server.ERROR_UNSUPPORTED_PROTOCOL_VERSION
    assert error["data"]["supported"] == list(mcp_server.SUPPORTED_VERSIONS)
    assert error["data"]["requested"] == "2099-01-01"

    body = rpc_body("tools/list")
    del body["params"]["_meta"]["io.modelcontextprotocol/clientCapabilities"]
    sin_capacidades = rpc(mcp_http, "tools/list", body=body)
    assert sin_capacidades.status_code == 400
    assert message(sin_capacidades)["error"]["code"] == mcp_server.ERROR_INVALID_PARAMS

    # Cabecera 2026-07-28 y _meta de otra revisión. (Al revés, una cabecera 2025-11-25 envía
    # la petición a la era antigua, que no lee _meta: es la doble era, no un error.)
    body = rpc_body("tools/list")
    body["params"]["_meta"]["io.modelcontextprotocol/protocolVersion"] = "2025-11-25"
    distinta = rpc(mcp_http, "tools/list", body=body)
    assert distinta.status_code == 400
    assert message(distinta)["error"]["code"] == mcp_server.ERROR_HEADER_MISMATCH


def test_pp13_server_discover_declares_revision_and_tools_capability(mcp_http):
    """supportedVersions contiene 2026-07-28, capabilities.tools existe, serverInfo en _meta
    y resultType complete."""
    r = rpc(mcp_http, "server/discover")
    assert r.status_code == 200
    result = message(r)["result"]
    assert result["supportedVersions"] == ["2026-07-28"]
    assert "tools" in result["capabilities"]
    assert result["_meta"]["io.modelcontextprotocol/serverInfo"]["name"] == "legaldev"
    assert result["resultType"] == "complete"
    assert result["instructions"] == mcp_server.SERVER_INSTRUCTIONS


def test_pp15_every_result_is_complete_and_tools_list_is_cacheable(mcp_http):
    """server/discover, tools/list y tools/call (también con isError) llevan resultType
    complete; tools/list lleva ttlMs entero >= 0 y cacheScope en {public, private}."""
    tools_list = message(rpc(mcp_http, "tools/list"))["result"]
    assert tools_list["ttlMs"] == mcp_server.TOOLS_LIST_TTL_MS
    assert tools_list["cacheScope"] == mcp_server.TOOLS_LIST_CACHE_SCOPE
    resultados = [
        message(rpc(mcp_http, "server/discover"))["result"],
        tools_list,
        message(
            rpc(mcp_http, "tools/call", {"name": "listar_normativas", "arguments": {}})
        )["result"],
        message(
            rpc(
                mcp_http,
                "tools/call",
                {"name": "consultar_obligaciones", "arguments": {"normativa": "XYZ"}},
            )
        )["result"],
    ]
    assert resultados[-1]["isError"] is True
    assert all(r["resultType"] == "complete" for r in resultados)


def test_rnf16_legacy_initialize_is_served_with_2025_11_25_semantics(mcp_http):
    """Servidor de doble era (decisión de la prueba de concepto): el initialize de un
    cliente 2025-11-25, sin cabeceras ni _meta, se atiende con la semántica de su revisión
    y sin Mcp-Session-Id (el servidor no guarda estado)."""
    r = rpc(
        mcp_http,
        "initialize",
        {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "cliente-antiguo", "version": "1"},
        },
        modern=False,
    )
    assert r.status_code == 200
    result = message(r)["result"]
    assert result["protocolVersion"] == "2025-11-25"
    assert result["serverInfo"]["name"] == "legaldev"
    assert "mcp-session-id" not in r.headers

    legacy_list = rpc(mcp_http, "tools/list", modern=False)
    assert [t["name"] for t in message(legacy_list)["result"]["tools"]] == list(
        mcp_server.TOOL_NAMES
    )


def test_rnf16_unknown_method_with_valid_headers_returns_404_method_not_found(mcp_http):
    """ping, que la revisión 2026-07-28 elimina, con cabeceras coherentes: 404 y -32601."""
    r = rpc(mcp_http, "ping")
    assert r.status_code == 404
    assert message(r)["error"]["code"] == mcp_server.ERROR_METHOD_NOT_FOUND


def test_pp14_header_body_mismatch_returns_header_mismatch_error(mcp_http):
    """400 con HeaderMismatch (-32020) si Mcp-Method o Mcp-Name no coinciden con el cuerpo;
    un valor en Base64 se decodifica antes de comparar. Sin las cabeceras, la petición es de
    la era antigua y se atiende (doble era), así que solo la incoherencia es un error."""
    params = {"name": "listar_normativas", "arguments": {}}
    nombre = rpc(mcp_http, "tools/call", params, headers={"Mcp-Name": "otra"})
    assert nombre.status_code == 400
    assert message(nombre)["error"]["code"] == mcp_server.ERROR_HEADER_MISMATCH

    metodo = rpc(mcp_http, "tools/call", params, headers={"Mcp-Method": "tools/list"})
    assert metodo.status_code == 400
    assert message(metodo)["error"]["code"] == mcp_server.ERROR_HEADER_MISMATCH

    b64 = base64.b64encode(b"listar_normativas").decode()
    codificado = rpc(
        mcp_http, "tools/call", params, headers={"Mcp-Name": f"=?base64?{b64}?="}
    )
    assert codificado.status_code == 200


def test_pp04_unknown_tool_is_protocol_error_over_http(mcp_http):
    r = rpc(mcp_http, "tools/call", {"name": "borrar_todo", "arguments": {}})
    assert r.status_code == 400
    error = message(r)["error"]
    assert error["code"] == mcp_server.ERROR_INVALID_PARAMS
    assert error["data"]["disponibles"] == list(mcp_server.TOOL_NAMES)


# ------------------------------------------------------------------ herramientas (en proceso)


def test_pp02_tools_list_returns_exactly_three_tools_with_valid_schemas(client):
    """Mismo orden en llamadas repetidas; inputSchema y outputSchema válidos como JSON Schema
    2020-12; anotaciones de TOOL_ANNOTATIONS."""
    tools = list_tools_in_process(client.app.state)
    again = list_tools_in_process(client.app.state)
    assert [t.name for t in tools] == list(mcp_server.TOOL_NAMES)
    assert [t.name for t in again] == list(mcp_server.TOOL_NAMES)
    for tool in tools:
        jsonschema.Draft202012Validator.check_schema(tool.input_schema)
        assert tool.output_schema is not None
        jsonschema.Draft202012Validator.check_schema(tool.output_schema)
        assert tool.description == mcp_server.TOOL_DESCRIPTIONS[tool.name]
        assert tool.title == mcp_server.TOOL_TITLES[tool.name]
        anotaciones = tool.annotations.model_dump(by_alias=True, exclude_none=True)
        assert anotaciones == mcp_server.TOOL_ANNOTATIONS[tool.name]
    analizar, listar, consultar = tools
    assert "$ref" not in str(analizar.input_schema)
    assert listar.input_schema == {"type": "object", "additionalProperties": False}
    assert consultar.input_schema["properties"]["normativa"]["enum"] == [
        "LOPDGDD",
        "RGPD",
    ]


def _cuestionarios(sample_input_dict):
    base = dict(sample_input_dict)
    sin_ia = dict(base, usa_ia=False, tipo_ia=None, monetizacion=None, colegiado=None)
    minimo = {k: v for k, v in sin_ia.items() if v is not None}
    return [
        ("completo", base, True),
        ("sin IA y opcionales nulos", sin_ia, True),
        ("sin los opcionales", minimo, True),
        ("enumeración inválida", dict(base, tipo_proyecto="nave_espacial"), False),
        ("descripción demasiado larga", dict(base, descripcion_breve="x" * 501), False),
        (
            "usa_ia sin tipo_ia",
            {k: v for k, v in base.items() if k != "tipo_ia"},
            False,
        ),
        ("usa_ia con tipo_ia nulo", dict(base, tipo_ia=None), False),
        ("falta ccaa", {k: v for k, v in base.items() if k != "ccaa"}, False),
        ("lista como cadena", dict(base, tipos_datos_personales="email"), False),
        ("booleano como cadena", dict(base, usa_cookies="true"), False),
        (
            "dato personal desconocido",
            dict(base, tipos_datos_personales=["adn"]),
            False,
        ),
        # El SDK convertiría estas cadenas en lista y en nulo antes de llamar a la herramienta
        # (pre_parse_json); la herramienta valida los argumentos tal como llegan.
        (
            "lista dentro de una cadena",
            dict(base, tipos_datos_personales='["email"]'),
            False,
        ),
        ("descripción que parece JSON", dict(base, descripcion_breve="null"), True),
    ]


def test_pp02_published_schema_and_model_accept_and_reject_the_same_questionnaires(
    client, sample_input_dict
):
    """Cuestionarios de ejemplo válidos e inválidos: el esquema publicado (validado con
    jsonschema) y la herramienta (que valida con el modelo Pydantic) dan el mismo veredicto
    en cada uno."""
    validator = jsonschema.Draft202012Validator(mcp_server.published_input_schema())
    for nombre, cuestionario, valido in _cuestionarios(sample_input_dict):
        assert validator.is_valid(cuestionario) is valido, nombre
        result = call_in_process(client.app.state, "analizar_proyecto", cuestionario)
        assert result.is_error is (not valido), nombre


def test_pp02_listar_normativas_matches_get_normativas(client):
    """Mismos documentos (por su identificador, sin .pdf) y versión del corpus."""
    result = call_in_process(client.app.state, "listar_normativas")
    assert result.is_error is False
    listado = result.structured_content
    rest = client.get("/normativas").json()
    assert [n["identificador"] for n in listado["normativas"]] == [
        s.removesuffix(".pdf") for s in rest["normativas"]
    ]
    assert listado["corpus_version"] == client.get("/health").json()["corpus_version"]


def test_pp03_analizar_proyecto_returns_report_and_structured_content(
    client, mock_doc, sample_input_dict
):
    """Informe y serialización JSON en el texto; structuredContent conforme al outputSchema
    (normativas, identificadores de fragmentos, modelo, versión del corpus, citas); isError
    false."""
    tools = {t.name: t for t in list_tools_in_process(client.app.state)}
    result = call_in_process(client.app.state, "analizar_proyecto", sample_input_dict)

    assert result.is_error is False
    data = result.structured_content
    jsonschema.validate(data, tools["analizar_proyecto"].output_schema)
    assert data["fragmentos"] == [
        {
            "identificador": fragment_id(mock_doc.page_content),
            "normativa": "RGPD",
            "pagina": 0,
            "articulo": None,
            "texto": None,
        }
    ]
    assert data["corpus_version"] == "abc123def456"
    assert data["llm_model"]
    assert data["sin_cobertura"] is False
    # El informe va también en structuredContent: hay clientes (Claude Code) que solo pasan
    # al modelo el contenido estructurado cuando la herramienta declara outputSchema.
    assert "Respuesta de prueba sobre RGPD" in data["informe"]
    assert data["informe"].startswith("> ⚠️")
    assert data["informe"].count("no constituye asesoramiento legal") == 2
    assert "descripcion_breve" not in data["cuestionario"]
    assert data["cuestionario"]["tipo_proyecto"] == sample_input_dict["tipo_proyecto"]
    texto = text_of(result)
    assert texto.startswith(data["informe"])
    assert '"corpus_version": "abc123def456"' in texto
    assert '"informe"' not in texto  # el JSON del texto no repite el informe


def test_pp04_invalid_questionnaire_is_tool_error_not_protocol_error(
    client, sample_input_dict
):
    """Resultado (no error JSON-RPC) con isError true y los campos que fallan, sin repetir
    los valores recibidos."""
    malo = {k: v for k, v in sample_input_dict.items() if k != "tipo_ia"}
    malo["tipo_proyecto"] = "nave_espacial"
    result = call_in_process(client.app.state, "analizar_proyecto", malo)

    assert result.is_error is True
    texto = text_of(result)
    assert texto.startswith("[CUESTIONARIO_INVALIDO]")
    assert "- tipo_proyecto:" in texto
    assert "- tipo_ia:" in texto
    assert "nave_espacial" not in texto
    assert result.structured_content is None
    client.app.state.groq_client.invoke.assert_not_called()


def test_pp04_unknown_tool_is_protocol_error(client):
    """tools/call con un name fuera de TOOL_NAMES: error JSON-RPC -32602, no isError."""
    with pytest.raises(MCPError) as exc_info:
        call_in_process(client.app.state, "borrar_todo")
    assert exc_info.value.code == mcp_server.ERROR_INVALID_PARAMS


@pytest.mark.parametrize("normativa", ["XYZ", "rgpd", "RGPD.pdf"])
def test_pp06_consultar_obligaciones_unknown_normativa_lists_available(
    client, normativa
):
    """isError true y la lista de normativas de listar_normativas en el texto del error."""
    result = call_in_process(
        client.app.state,
        "consultar_obligaciones",
        {"normativa": normativa, "contexto": "cookies analíticas"},
    )
    assert result.is_error is True
    texto = text_of(result)
    assert texto.startswith("[NORMATIVA_DESCONOCIDA]")
    assert texto.endswith("LOPDGDD, RGPD")


@pytest.mark.parametrize(
    "argumentos",
    [
        {"normativa": "RGPD"},
        {"normativa": "RGPD", "contexto": ""},
        {"normativa": "RGPD", "contexto": "x" * 501},
        {"normativa": 7, "contexto": "registro"},
    ],
)
def test_consultar_obligaciones_invalid_arguments_are_tool_errors(client, argumentos):
    result = call_in_process(client.app.state, "consultar_obligaciones", argumentos)
    assert result.is_error is True
    assert text_of(result).startswith("[ARGUMENTOS_INVALIDOS]")
    assert "xxxx" not in text_of(result)


def test_rf25_consultar_obligaciones_returns_located_fragments_without_llm(
    client, mock_doc
):
    """Todos los fragmentos son de la normativa pedida, con identificador, página y texto, en
    el orden del reordenador; el LLM simulado no se invoca."""
    result = call_in_process(
        client.app.state,
        "consultar_obligaciones",
        {"normativa": "RGPD", "contexto": "registro de usuarios con email"},
    )
    assert result.is_error is False
    data = result.structured_content
    assert data["normativa"] == "RGPD"
    assert data["fragmentos"] == [
        {
            "identificador": fragment_id(mock_doc.page_content),
            "normativa": "RGPD",
            "pagina": 0,
            "articulo": None,
            "texto": mock_doc.page_content,
        }
    ]
    client.app.state.groq_client.invoke.assert_not_called()
    assert mock_doc.page_content in text_of(result)


def test_rf23_no_coverage_is_tool_result_not_http_404(
    client, mock_doc, sample_input_dict
):
    """El equivalente MCP del 404 de /v1/analyze es un resultado con isError false."""
    sin_inyecciones = dict(
        sample_input_dict,
        tipos_datos_personales=["ninguno"],
        usa_ia=False,
        tipo_ia=None,
        usa_cookies=False,
        colegiado=None,
    )
    client.app.state.vectorstore.similarity_search_with_relevance_scores.return_value = [
        (mock_doc, 0.05)
    ]
    result = call_in_process(client.app.state, "analizar_proyecto", sin_inyecciones)

    assert result.is_error is False
    data = result.structured_content
    assert data["sin_cobertura"] is True
    assert "LOPDGDD, RGPD" in data["informe"]
    assert data["normativas_detectadas"] == []
    assert data["fragmentos"] == []
    assert "LOPDGDD, RGPD" in text_of(result)
    client.app.state.groq_client.invoke.assert_not_called()


def test_analizar_proyecto_llm_down_and_timeout_are_retryable_tool_errors(
    client, sample_input_dict
):
    from app import errors

    client.app.state.groq_client.invoke.side_effect = Exception("Groq caído")
    client.app.state.groq_fallback_client = client.app.state.groq_client
    caido = call_in_process(client.app.state, "analizar_proyecto", sample_input_dict)
    assert caido.is_error is True
    assert text_of(caido).startswith("[MODELO_NO_DISPONIBLE]")

    from unittest.mock import patch

    with patch(
        "app.rag.run_pipeline_detailed",
        side_effect=errors.RetrievalTimeoutError("Retrieval timed out."),
    ):
        lento = call_in_process(
            client.app.state, "analizar_proyecto", sample_input_dict
        )
    assert lento.is_error is True
    assert text_of(lento).startswith("[TIEMPO_AGOTADO]")


def test_analizar_proyecto_reports_progress_when_the_client_asks(
    client, sample_input_dict, monkeypatch
):
    """RNF-19: con progressToken, notificaciones de progreso mientras se genera el informe."""
    import time

    monkeypatch.setattr(mcp_server, "PROGRESS_INTERVAL_S", 0.05)
    real_invoke = client.app.state.groq_client.invoke

    def lento(*args, **kwargs):
        time.sleep(0.3)
        return real_invoke(*args, **kwargs)

    monkeypatch.setattr(client.app.state.groq_client, "invoke", lento)
    avisos: list[tuple] = []

    async def on_progress(progress, total, msg):
        avisos.append((progress, total, msg))

    result = call_in_process(
        client.app.state,
        "analizar_proyecto",
        sample_input_dict,
        progress_callback=on_progress,
    )
    assert result.is_error is False
    assert avisos[0] == (0, None, "Recuperando la normativa aplicable")
    assert len(avisos) >= 3
    assert all(m == "Generando el informe" for _, _, m in avisos[1:])


def test_consultar_obligaciones_keeps_a_contexto_that_looks_like_json(client, mock_doc):
    """Un contexto «[]» es texto, no una lista: se consulta con él tal cual."""
    result = call_in_process(
        client.app.state,
        "consultar_obligaciones",
        {"normativa": "RGPD", "contexto": "[]"},
    )
    assert result.is_error is False
    assert result.structured_content["fragmentos"][0]["texto"] == mock_doc.page_content
