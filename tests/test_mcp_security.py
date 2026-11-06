"""Seguridad del punto de entrada /mcp (RNF-15, RNF-16, RNF-18, RNF-20 y RNF-21).

PP-07, PP-08, PP-16, PP-17 y el orden de las comprobaciones de app/mcp_guard.py. Las guardas
de producción (el servidor MCP está desactivado por defecto y /mcp no existe sin él) siguen
aquí. PP-14 está en tests/test_mcp_contract.py, con el resto del protocolo.
"""

import hashlib
import json
import logging
import re
import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from prometheus_client import REGISTRY

from app import config, mcp_guard, mcp_server
from app.config import Settings
from tests._mcp import message, rpc
from tests.conftest import MCP_TEST_KEYS, MCP_TEST_ORIGIN

CLIENTS_DIR = Path(__file__).resolve().parent.parent / "docs" / "mcp" / "clients"
# Referencias a un secreto que no se versiona: variable de entrada de VS Code
# (${input:id}), variable de entorno de Cursor (${env:NOMBRE}) o de Claude Code (${NOMBRE}).
_SECRET_REF = re.compile(
    r"^\$\{(?:input:[\w-]+|env:[A-Z_][A-Z0-9_]*|[A-Z_][A-Z0-9_]*)\}$"
)
LISTAR = {"name": "listar_normativas", "arguments": {}}


def _analizar(cuestionario):
    return {"name": "analizar_proyecto", "arguments": cuestionario}


def test_mcp_is_disabled_by_default():
    assert Settings(groq_api_key="x").mcp_enabled is False


def test_mcp_endpoint_is_not_mounted_while_disabled(client):
    assert not any(
        getattr(route, "path", "").startswith("/mcp") for route in client.app.routes
    )
    assert client.post("/mcp", json={}).status_code == 404


def test_mcp_allowed_origins_rejects_wildcard():
    with pytest.raises(ValueError, match="MCP_ALLOWED_ORIGINS"):
        Settings(groq_api_key="x", mcp_allowed_origins="*")


def test_client_examples_never_contain_a_literal_api_key():
    files = sorted(CLIENTS_DIR.glob("*.json"))
    assert len(files) == 3
    for path in files:
        config_json = json.loads(path.read_text(encoding="utf-8"))
        servers = config_json.get("servers") or config_json["mcpServers"]
        headers = servers["legaldev"]["headers"]
        assert _SECRET_REF.match(headers["X-API-Key"]), path.name
        url = servers["legaldev"]["url"]
        assert url.endswith("/mcp"), path.name  # ruta exacta: sin barra final ni 307


def test_guard_checks_follow_the_order_of_the_implementation():
    # Las tres primeras en McpGuard, las dos últimas en el SDK (23-detalle, «Capa de servicio
    # y traducción de errores»). 22-arquitectura y CU-07 deben unificarse con este orden.
    assert mcp_guard.CHECK_ORDER == (
        "origin",
        "api_key",
        "rate_limit",
        "headers",
        "protocol_version",
    )


def test_rnf21_rate_limit_covers_only_tools_that_consume_model_quota():
    # listar_normativas y consultar_obligaciones solo leen el índice local.
    assert mcp_guard.RATE_LIMITED_TOOLS == frozenset({"analizar_proyecto"})
    assert mcp_guard.RATE_LIMITED_TOOLS <= set(mcp_server.TOOL_NAMES)
    assert mcp_guard.is_rate_limited("tools/call", "analizar_proyecto")
    assert not mcp_guard.is_rate_limited("tools/call", "listar_normativas")
    assert not mcp_guard.is_rate_limited("tools/list", "analizar_proyecto")


# --------------------------------------------------------------------------- PP-07 (clave)


def test_pp07_without_api_keys_mcp_is_never_mounted(caplog):
    """Con MCP_ENABLED y API_KEYS vacía la ruta no existe: /mcp nunca queda abierto."""
    from fastapi import FastAPI

    app = FastAPI()
    with (
        patch.object(config.settings, "mcp_enabled", True),
        patch.object(config.settings, "api_keys", ""),
        caplog.at_level(logging.WARNING),
    ):
        assert mcp_server.mount_if_enabled(app) is False
    assert not mcp_server.is_mounted(app)
    assert "sin API_KEYS" in caplog.text


def test_pp07_mcp_requires_api_key(mcp_http):
    """401 sin X-API-Key (con desafío) y 403 con una clave desconocida; las dos claves
    configuradas pasan. A diferencia de /v1/analyze, nunca queda abierto."""
    sin_clave = rpc(mcp_http, "tools/call", LISTAR, key=None)
    assert sin_clave.status_code == 401
    assert sin_clave.headers["www-authenticate"] == 'ApiKey header="X-API-Key"'
    assert message(sin_clave)["id"] == 1

    desconocida = rpc(mcp_http, "tools/call", LISTAR, key="no-es-una-clave")
    assert desconocida.status_code == 403

    for key in MCP_TEST_KEYS:
        assert rpc(mcp_http, "tools/call", LISTAR, key=key).status_code == 200


def test_bad_origin_is_checked_before_the_api_key(mcp_http):
    r = rpc(
        mcp_http,
        "tools/call",
        LISTAR,
        key=None,
        headers={"Origin": "https://evil.example"},
    )
    assert r.status_code == 403


# ---------------------------------------------------------------- PP-16 (Origin y métodos)


def test_pp16_invalid_origin_is_rejected_with_403(mcp_http):
    """Con independencia de CORS (aunque ALLOWED_ORIGINS sea «*»); protección frente a DNS
    rebinding exigida por el transporte Streamable HTTP (RNF-18)."""
    assert config.settings.allowed_origins == "*"
    for origin in ("https://evil.example", "null", "http://localhost:8000"):
        r = rpc(mcp_http, "tools/call", LISTAR, headers={"Origin": origin})
        assert r.status_code == 403, origin


def test_pp16_allowed_or_missing_origin_is_accepted(mcp_http):
    """VS Code, Claude Code y Cursor no envían Origin; los navegadores sí."""
    assert rpc(mcp_http, "tools/call", LISTAR).status_code == 200
    con_origen = rpc(
        mcp_http, "tools/call", LISTAR, headers={"Origin": MCP_TEST_ORIGIN}
    )
    assert con_origen.status_code == 200


def test_pp16_get_and_delete_return_405_and_session_header_is_ignored(mcp_http):
    """La revisión elimina el flujo GET y las sesiones; nunca se emite Mcp-Session-Id. El
    GET de un cliente antiguo (que abriría un flujo SSE sin fin) responde al instante."""
    headers = {"Accept": "text/event-stream", "X-API-Key": MCP_TEST_KEYS[0]}
    estados: dict[str, int] = {}

    def _pedir():
        estados["GET"] = mcp_http.get("/mcp", headers=headers).status_code
        estados["DELETE"] = mcp_http.delete("/mcp", headers=headers).status_code

    hilo = threading.Thread(target=_pedir, daemon=True)
    hilo.start()
    hilo.join(10)
    assert not hilo.is_alive(), "GET o DELETE sobre /mcp no responden"
    assert estados == {"GET": 405, "DELETE": 405}

    r = rpc(mcp_http, "tools/call", LISTAR, headers={"Mcp-Session-Id": "abc123"})
    assert r.status_code == 200
    assert "mcp-session-id" not in r.headers


def test_post_mcp_is_served_without_redirect(mcp_http):
    r = rpc(mcp_http, "tools/list")
    assert r.status_code == 200
    assert "location" not in r.headers


def test_oversized_body_is_rejected_before_the_sdk(mcp_http):
    body = {
        "jsonrpc": "2.0",
        "id": 9,
        "method": "tools/list",
        "params": {"x": "y" * 300_000},
    }
    r = rpc(mcp_http, "tools/list", body=body)
    assert r.status_code == 413


# ------------------------------------------------------------------------- PP-17 (límite)


def test_pp17_rate_limit_applies_only_to_tools_call(mcp_http, sample_input_dict):
    """Tras agotar el cupo con tools/call de analizar_proyecto, server/discover, tools/list,
    listar_normativas y consultar_obligaciones siguen respondiendo."""
    with patch.object(config.settings, "rate_limit", "2/minute"):
        for _ in range(2):
            ok = rpc(mcp_http, "tools/call", _analizar(sample_input_dict))
            assert ok.status_code == 200
        limitado = rpc(mcp_http, "tools/call", _analizar(sample_input_dict))
        assert limitado.status_code == 429
        assert int(limitado.headers["retry-after"]) >= 1
        assert message(limitado)["error"]["code"] == -32000

        assert rpc(mcp_http, "server/discover").status_code == 200
        assert rpc(mcp_http, "tools/list").status_code == 200
        assert rpc(mcp_http, "tools/call", LISTAR).status_code == 200
        consulta = {
            "name": "consultar_obligaciones",
            "arguments": {"normativa": "RGPD", "contexto": "cookies"},
        }
        assert rpc(mcp_http, "tools/call", consulta).status_code == 200


def test_rnf21_rate_limit_key_is_api_key_then_ip(mcp_http, sample_input_dict):
    """Dos claves desde la misma IP tienen cupos distintos; la clave no se guarda en claro en
    el almacén del limitador."""
    assert mcp_guard.rate_limit_key("k", "1.2.3.4") != mcp_guard.rate_limit_key(
        "otra", "1.2.3.4"
    )
    assert mcp_guard.rate_limit_key(None, "1.2.3.4") == "mcp:ip:1.2.3.4"
    with patch.object(config.settings, "rate_limit", "1/minute"):
        primera, segunda = MCP_TEST_KEYS
        assert (
            rpc(
                mcp_http, "tools/call", _analizar(sample_input_dict), key=primera
            ).status_code
            == 200
        )
        assert (
            rpc(
                mcp_http, "tools/call", _analizar(sample_input_dict), key=primera
            ).status_code
            == 429
        )
        assert (
            rpc(
                mcp_http, "tools/call", _analizar(sample_input_dict), key=segunda
            ).status_code
            == 200
        )
    almacen = repr(vars(mcp_http.app.state.limiter._storage))
    assert "mcp:key:" in almacen
    assert primera not in almacen and segunda not in almacen


def test_legacy_client_without_headers_is_rate_limited_too(mcp_http, sample_input_dict):
    """La guarda lee método y herramienta del cuerpo: un cliente de la era antigua, sin
    Mcp-Method ni Mcp-Name, no se libra del límite."""
    with patch.object(config.settings, "rate_limit", "1/minute"):
        primera = rpc(
            mcp_http, "tools/call", _analizar(sample_input_dict), modern=False
        )
        assert primera.status_code == 200
        assert message(primera)["result"]["isError"] is False
        segunda = rpc(
            mcp_http, "tools/call", _analizar(sample_input_dict), modern=False
        )
        assert segunda.status_code == 429


def test_lying_mcp_name_does_not_dodge_the_limit(mcp_http, sample_input_dict):
    """Mcp-Name de una herramienta no limitada con el cuerpo de analizar_proyecto: la guarda
    cuenta la invocación (lee el cuerpo) y el SDK rechaza la incoherencia."""
    with patch.object(config.settings, "rate_limit", "1/minute"):
        mentira = rpc(
            mcp_http,
            "tools/call",
            _analizar(sample_input_dict),
            headers={"Mcp-Name": "listar_normativas"},
        )
        assert mentira.status_code == 400
        assert (
            rpc(mcp_http, "tools/call", _analizar(sample_input_dict)).status_code == 429
        )


# ------------------------------------------------------------ RNF-15 y PP-08 (privacidad)


def test_rnf15_tool_descriptions_snapshot():
    """Hash fijo de los textos estáticos que ve el asistente (descripciones, títulos,
    instrucciones y descripciones de campo), como test_system_prompt_snapshot fija el prompt."""
    textos = json.dumps(
        [
            mcp_server.TOOL_DESCRIPTIONS,
            mcp_server.TOOL_TITLES,
            mcp_server.SERVER_INSTRUCTIONS,
            mcp_server.DESCRIPCION_BREVE_FIELD,
            mcp_server.CAMPO_DESCRIPCIONES,
        ],
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha256(textos.encode()).hexdigest()
    assert (
        digest == "ff0ed5bad2005fbf7f3c1c660d85742283f1893233f37036f3eda1731fc3afde"
    ), (
        f"Textos estáticos del servidor MCP cambiados: revisa y actualiza el hash: {digest}"
    )


def test_pp08_mcp_logs_do_not_contain_descripcion_breve(
    mcp_http, sample_input_dict, caplog
):
    """Como test_run_pipeline_does_not_log_descripcion_breve, invocando por /mcp: camino
    válido, cuestionario inválido, modelo caído y excepción no prevista; incluye el
    argumento contexto de consultar_obligaciones. Todos los registradores, nivel DEBUG."""
    caplog.set_level(logging.DEBUG)
    centinela = "CENTINELA-PRIVADO-91c2"
    cuestionario = dict(sample_input_dict, descripcion_breve=f"App con {centinela}")

    assert rpc(mcp_http, "tools/call", _analizar(cuestionario)).status_code == 200
    invalido = dict(
        cuestionario, tipo_proyecto="nave_espacial", descripcion_breve=centinela * 40
    )
    r = rpc(mcp_http, "tools/call", _analizar(invalido))
    assert message(r)["result"]["isError"] is True
    assert centinela not in r.text

    otro = dict(cuestionario, ccaa="Madrid")  # otra entrada de caché
    llm = mcp_http.app.state.groq_client
    llm.invoke.side_effect = Exception("Groq caído")
    mcp_http.app.state.groq_fallback_client = llm
    r = rpc(mcp_http, "tools/call", _analizar(otro))
    assert message(r)["result"]["isError"] is True
    llm.invoke.side_effect = None

    with patch(
        "app.rag.run_pipeline_detailed", side_effect=RuntimeError("fallo interno")
    ):
        r = rpc(mcp_http, "tools/call", _analizar(dict(cuestionario, ccaa="Galicia")))
    assert message(r)["result"]["isError"] is True
    assert "fallo interno" not in r.text

    consulta = {
        "name": "consultar_obligaciones",
        "arguments": {"normativa": "RGPD", "contexto": f"registro {centinela}"},
    }
    assert rpc(mcp_http, "tools/call", consulta).status_code == 200

    assert caplog.records, "la prueba no ha capturado ningún registro"
    assert centinela not in caplog.text


@pytest.mark.skip(
    reason="TODO(PT2/RNF-20): saneado de la salida del modelo; PP-18 con LLM real"
)
def test_pp18_indirect_injection_payloads_are_not_reproduced():
    """Con 10 a 20 cargas en descripcion_breve (órdenes al asistente, peticiones de invocar
    herramientas, HTML y caracteres de control) y el LLM simulado que las repite, el
    resultado no reproduce la descripción, no contiene órdenes al asistente y llega saneado.
    La proporción de informes que obedecen alguna carga se informa con el LLM real. Hoy solo
    está hecha la parte estructural: structuredContent.cuestionario no incluye la descripción
    y los errores de validación no repiten los valores recibidos."""


def _metric(name, **labels):
    return REGISTRY.get_sample_value(name, labels) or 0.0


def test_cu07_metrics_are_labelled_by_access_path(mcp_http, sample_input_dict):
    """Una llamada por cada vía incrementa la serie con su etiqueta via."""
    rest_antes = _metric("legaldev_analyze_requests_total", via="rest")
    mcp_antes = _metric("legaldev_analyze_requests_total", via="mcp")

    rest = mcp_http.post(
        "/v1/analyze", json=sample_input_dict, headers={"X-API-Key": MCP_TEST_KEYS[0]}
    )
    assert rest.status_code == 200
    assert rpc(mcp_http, "tools/call", _analizar(sample_input_dict)).status_code == 200

    assert _metric("legaldev_analyze_requests_total", via="rest") == rest_antes + 1
    assert _metric("legaldev_analyze_requests_total", via="mcp") == mcp_antes + 1
