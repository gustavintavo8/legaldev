"""Registro de peticiones del servidor de prueba de clientes MCP (tools/servidor_mcp_prueba.py).

Comprueba que cada fila dice qué revisión pide el cliente en las dos eras y que nunca lleva la
clave ni los argumentos de la herramienta.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tests._mcp import ACCEPT, MODERN_META, rpc  # noqa: E402
from tools import servidor_mcp_prueba as prueba  # noqa: E402


def test_row_of_a_legacy_initialize():
    cuerpo = {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "inspector-cli", "version": "2.13.0", "extra": "x"},
        },
    }
    fila = prueba.fila(
        "POST", {"x-api-key": "secreta"}, json.dumps(cuerpo).encode(), 200, 3
    )
    assert fila == {
        "http": "POST",
        "status": 200,
        "ms": 3,
        "metodo": "initialize",
        "herramienta": None,
        "cabecera_version": None,
        "version_pedida": "2025-11-25",
        "cliente": {"name": "inspector-cli", "version": "2.13.0"},
        "con_clave": True,
    }
    assert "secreta" not in json.dumps(fila)


def test_row_of_a_broken_body_or_a_get():
    assert prueba.fila("POST", {}, b"{no es json", 400, 1)["metodo"] is None
    fila = prueba.fila("GET", {"mcp-protocol-version": "2025-11-25"}, b"", 405, 1)
    assert fila["cabecera_version"] == "2025-11-25" and fila["con_clave"] is False


def test_wrapped_app_logs_each_mcp_request_without_key_or_arguments(
    mcp_http, sample_input_dict
):
    from fastapi.testclient import TestClient

    filas: list[dict] = []
    # Sin «with»: el lifespan ya lo ha ejecutado mcp_http y el estado está cargado.
    envuelta = TestClient(prueba.con_registro(mcp_http.app, filas.append))
    assert envuelta.get("/health").status_code == 200
    rpc(envuelta, "server/discover")
    rpc(
        envuelta,
        "tools/call",
        {"name": "analizar_proyecto", "arguments": sample_input_dict},
    )
    rpc(envuelta, "tools/list", key=None)
    envuelta.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "1"},
            },
        },
        headers={**ACCEPT, "X-API-Key": "test-key-1"},
    )
    assert [(f["metodo"], f["status"]) for f in filas] == [
        ("server/discover", 200),
        ("tools/call", 200),
        ("tools/list", 401),
        ("initialize", 200),
    ]
    assert filas[0]["cabecera_version"] == filas[0]["version_pedida"] == "2026-07-28"
    assert filas[0]["cliente"] == MODERN_META["io.modelcontextprotocol/clientInfo"]
    assert filas[1]["herramienta"] == "analizar_proyecto"
    assert filas[3]["version_pedida"] == "2025-11-25"
    serializado = json.dumps(filas, ensure_ascii=False)
    assert "test-key-1" not in serializado
    assert sample_input_dict["descripcion_breve"] not in serializado


def test_main_requires_a_test_key(monkeypatch, capsys):
    monkeypatch.delenv("LEGALDEV_API_KEY", raising=False)
    assert prueba.main([]) == 2
    assert "LEGALDEV_API_KEY" in capsys.readouterr().err
