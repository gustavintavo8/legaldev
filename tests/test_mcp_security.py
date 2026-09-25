"""Seguridad del punto de entrada /mcp (PP-07, PP-08; RNF-15).

Las guardas que corren hoy comprueban que el andamiaje no cambia producción: el servidor MCP
está desactivado por defecto y /mcp no existe en la aplicación.
"""

import pytest

from app import mcp_guard
from app.config import Settings


def test_mcp_is_disabled_by_default():
    assert Settings(groq_api_key="x").mcp_enabled is False


def test_rate_limit_policy_covers_only_tools_call():
    assert mcp_guard.RATE_LIMITED_METHODS == frozenset({"tools/call"})


def test_mcp_endpoint_is_not_mounted_while_disabled(client):
    assert not any(
        getattr(route, "path", "").startswith("/mcp") for route in client.app.routes
    )
    assert client.post("/mcp", json={}).status_code == 404


@pytest.mark.skip(
    reason="TODO(PT2/PP-07): /mcp con API_KEYS: 401 sin clave y 403 con clave errónea"
)
def test_pp07_mcp_requires_api_key_when_configured():
    """Misma semántica que /v1/analyze (tests/test_api_keys.py)."""


@pytest.mark.skip(reason="TODO(PT2/PP-07): tools/call por encima de RATE_LIMIT -> 429")
def test_pp07_tools_call_over_rate_limit_returns_429():
    """Mismo limitador e igual clave de IP (_get_real_ip) que /v1/analyze."""


@pytest.mark.skip(
    reason="TODO(PT2/RNF-15): server/discover y tools/list no consumen cupo del limitador"
)
def test_rnf15_rate_limit_applies_only_to_tools_call():
    """Tras agotar el cupo con tools/call, server/discover y tools/list siguen respondiendo."""


@pytest.mark.skip(reason="TODO(PT2/RNF-15): Origin presente y no permitido -> 403")
def test_rnf15_invalid_origin_is_rejected_with_403():
    """Protección frente a DNS rebinding exigida por el transporte Streamable HTTP."""


@pytest.mark.skip(
    reason="TODO(PT2/RNF-15): sin cabecera Origin (cliente de escritorio) se acepta"
)
def test_rnf15_missing_origin_is_accepted():
    """VS Code, Claude Code y Cursor no envían Origin; los navegadores sí."""


@pytest.mark.skip(
    reason="TODO(PT2/RNF-15): las descripciones de las herramientas son estáticas (instantánea)"
)
def test_rnf15_tool_descriptions_snapshot():
    """Hash fijo de TOOL_DESCRIPTIONS, como test_system_prompt_snapshot fija el prompt."""


@pytest.mark.skip(
    reason="TODO(PT2/PP-08): ningún registro del servidor MCP contiene la descripción libre"
)
def test_pp08_mcp_logs_do_not_contain_descripcion_breve(caplog):
    """Como test_run_pipeline_does_not_log_descripcion_breve, invocando por /mcp; incluye
    el argumento contexto de consultar_obligaciones."""


@pytest.mark.skip(
    reason="TODO(PT2/CU-07): las métricas distinguen la vía de acceso (via=rest|mcp)"
)
def test_cu07_metrics_are_labelled_by_access_path():
    """Una llamada por cada vía incrementa la serie con su etiqueta via."""
