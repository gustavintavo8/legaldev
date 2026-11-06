"""Utilidades de las pruebas del servidor MCP: peticiones JSON-RPC en crudo y cliente en proceso."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp import Client

from app.mcp_server import PROTOCOL_VERSION, build_mcp_server

MODERN_META = {
    "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
    "io.modelcontextprotocol/clientCapabilities": {},
    "io.modelcontextprotocol/clientInfo": {"name": "pytest", "version": "1"},
}
ACCEPT = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def rpc_body(method: str, params: dict | None = None, *, id: int = 1, modern=True):
    params = dict(params or {})
    if modern:
        params["_meta"] = {**MODERN_META, **params.get("_meta", {})}
    return {"jsonrpc": "2.0", "id": id, "method": method, "params": params}


def rpc(
    http,
    method: str,
    params: dict | None = None,
    *,
    key: str | None = "test-key-1",
    modern: bool = True,
    headers: dict | None = None,
    body: dict | None = None,
    id: int = 1,
):
    """POST /mcp. ``modern`` añade ``_meta`` y las cabeceras de la revisión 2026-07-28;
    sin él la petición es de la era del initialize (sin cabeceras ni ``_meta``)."""
    h = dict(ACCEPT)
    if key is not None:
        h["X-API-Key"] = key
    if modern:
        h["MCP-Protocol-Version"] = PROTOCOL_VERSION
        h["Mcp-Method"] = method
        if method == "tools/call":
            h["Mcp-Name"] = (params or {}).get("name", "")
    h.update(headers or {})
    payload = (
        body if body is not None else rpc_body(method, params, id=id, modern=modern)
    )
    return http.post("/mcp", json=payload, headers=h, follow_redirects=False)


def message(response) -> dict[str, Any]:
    """Respuesta JSON-RPC, venga como JSON o como flujo SSE (el último mensaje con id)."""
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        datos = [
            json.loads(line[len("data:") :].strip())
            for line in response.text.splitlines()
            if line.startswith("data:")
        ]
        return [d for d in datos if "id" in d][-1]
    return response.json()


def call_in_process(state, tool: str, arguments: dict | None = None, **kwargs):
    """``tools/call`` con un cliente MCP en proceso sobre ``build_mcp_server(state)``."""

    async def _run():
        async with Client(build_mcp_server(state)) as c:
            return await c.call_tool(tool, arguments or {}, **kwargs)

    try:
        return asyncio.run(_run())
    except BaseExceptionGroup as group:
        # El cliente en proceso envuelve los errores del protocolo en grupos de anyio.
        leaf: BaseException = group
        while isinstance(leaf, BaseExceptionGroup) and len(leaf.exceptions) == 1:
            leaf = leaf.exceptions[0]
        raise leaf from group


def list_tools_in_process(state):
    async def _run():
        async with Client(build_mcp_server(state)) as c:
            return (await c.list_tools()).tools

    return asyncio.run(_run())


def text_of(result) -> str:
    return "".join(getattr(c, "text", "") for c in result.content)
