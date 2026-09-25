"""Seguridad del punto de entrada /mcp (RNF-15, RNF-16, RNF-18, RNF-20 y RNF-21).

PP-07, PP-08, PP-14, PP-16, PP-17 y PP-18. Las guardas que corren hoy comprueban que el
andamiaje no cambia producción (el servidor MCP está desactivado por defecto y /mcp no existe
en la aplicación) y fijan la política ya decidida en la memoria.
"""

import json
import re
from pathlib import Path

import pytest

from app import mcp_guard, mcp_server
from app.config import Settings

CLIENTS_DIR = Path(__file__).resolve().parent.parent / "docs" / "mcp" / "clients"
# Referencias a un secreto que no se versiona: variable de entrada de VS Code
# (${input:id}), variable de entorno de Cursor (${env:NOMBRE}) o de Claude Code (${NOMBRE}).
_SECRET_REF = re.compile(
    r"^\$\{(?:input:[\w-]+|env:[A-Z_][A-Z0-9_]*|[A-Z_][A-Z0-9_]*)\}$"
)


def test_mcp_is_disabled_by_default():
    assert Settings(groq_api_key="x").mcp_enabled is False


def test_mcp_endpoint_is_not_mounted_while_disabled(client):
    assert not any(
        getattr(route, "path", "").startswith("/mcp") for route in client.app.routes
    )
    assert client.post("/mcp", json={}).status_code == 404


def test_client_examples_never_contain_a_literal_api_key():
    files = sorted(CLIENTS_DIR.glob("*.json"))
    assert len(files) == 3
    for path in files:
        config = json.loads(path.read_text(encoding="utf-8"))
        servers = config.get("servers") or config["mcpServers"]
        headers = servers["legaldev"]["headers"]
        assert _SECRET_REF.match(headers["X-API-Key"]), path.name


def test_guard_checks_follow_the_order_of_the_architecture():
    # 22-arquitectura, «Flujo sin estado de una invocación», paso 3; CU-07, paso 5.
    assert mcp_guard.CHECK_ORDER == (
        "origin",
        "headers",
        "protocol_version",
        "api_key",
        "rate_limit",
    )


def test_rnf21_rate_limit_covers_only_tools_that_consume_model_quota():
    # listar_normativas y consultar_obligaciones solo leen el índice local.
    assert mcp_guard.RATE_LIMITED_TOOLS == frozenset({"analizar_proyecto"})
    assert mcp_guard.RATE_LIMITED_TOOLS <= set(mcp_server.TOOL_NAMES)


@pytest.mark.skip(
    reason="TODO(PT2/PP-07): sin API_KEYS /mcp no se activa; con ellas, 401 y 403"
)
def test_pp07_mcp_requires_api_key():
    """Con MCP_ENABLED y API_KEYS vacía la ruta no existe; con claves, 401 sin X-API-Key y 403
    con una clave desconocida. A diferencia de /v1/analyze, nunca queda abierto."""


@pytest.mark.skip(
    reason="TODO(PT2/PP-17): agotado el cupo de una clave, analizar_proyecto recibe 429"
)
def test_pp17_rate_limit_applies_only_to_tools_call():
    """Tras agotar el cupo con tools/call de analizar_proyecto, server/discover, tools/list,
    listar_normativas y consultar_obligaciones siguen respondiendo."""


@pytest.mark.skip(
    reason="TODO(PT2/RNF-21): el cupo se cuenta por clave de API y, sin clave, por IP"
)
def test_rnf21_rate_limit_key_is_api_key_then_ip():
    """rate_limit_key: dos claves desde la misma IP tienen cupos distintos; la clave no se
    guarda en claro en el almacén del limitador."""


@pytest.mark.skip(
    reason="TODO(PT2/PP-14): Mcp-Method/Mcp-Name ausentes o distintos del cuerpo -> 400"
)
def test_pp14_header_body_mismatch_returns_header_mismatch_error():
    """400 con HeaderMismatch (-32020) si faltan o no coinciden con method y params.name; un
    valor en Base64 se decodifica antes de comparar."""


@pytest.mark.skip(reason="TODO(PT2/PP-16): Origin presente y no permitido -> 403")
def test_pp16_invalid_origin_is_rejected_with_403():
    """Con independencia de CORS (aunque ALLOWED_ORIGINS sea «*»); protección frente a DNS
    rebinding exigida por el transporte Streamable HTTP (RNF-18)."""


@pytest.mark.skip(
    reason="TODO(PT2/PP-16): Origin permitido o ausente (cliente de escritorio) se atiende"
)
def test_pp16_allowed_or_missing_origin_is_accepted():
    """VS Code, Claude Code y Cursor no envían Origin; los navegadores sí."""


@pytest.mark.skip(
    reason="TODO(PT2/PP-16): GET y DELETE sobre /mcp -> 405; Mcp-Session-Id se ignora"
)
def test_pp16_get_and_delete_return_405_and_session_header_is_ignored():
    """La revisión elimina el flujo GET y las sesiones; nunca se emite Mcp-Session-Id."""


@pytest.mark.skip(
    reason="TODO(PT2/RNF-15): descripciones de herramientas y campos estáticas (instantánea)"
)
def test_rnf15_tool_descriptions_snapshot():
    """Hash fijo de TOOL_DESCRIPTIONS y DESCRIPCION_BREVE_FIELD, como
    test_system_prompt_snapshot fija el prompt."""


@pytest.mark.skip(
    reason="TODO(PT2/PP-08): ningún registro del servidor MCP contiene la descripción libre"
)
def test_pp08_mcp_logs_do_not_contain_descripcion_breve(caplog):
    """Como test_run_pipeline_does_not_log_descripcion_breve, invocando por /mcp; incluye
    el argumento contexto de consultar_obligaciones."""


@pytest.mark.skip(
    reason="TODO(PT2/PP-18): cargas de inyección en la descripción no llegan a la salida"
)
def test_pp18_indirect_injection_payloads_are_not_reproduced():
    """Con 10 a 20 cargas en descripcion_breve (órdenes al asistente, peticiones de invocar
    herramientas, HTML y caracteres de control) y el LLM simulado que las repite, el
    resultado no reproduce la descripción, no contiene órdenes al asistente y llega saneado.
    La proporción de informes que obedecen alguna carga se informa con el LLM real."""


@pytest.mark.skip(
    reason="TODO(PT2/CU-07): las métricas distinguen la vía de acceso (via=rest|mcp|ci)"
)
def test_cu07_metrics_are_labelled_by_access_path():
    """Una llamada por cada vía incrementa la serie con su etiqueta via."""
