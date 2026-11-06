"""Controles de acceso del punto de entrada ``/mcp`` (guarda ASGI delante del SDK).

Requisitos: RNF-15 (clave de API siempre obligatoria, del mismo conjunto que la API REST),
RNF-16 (cabeceras y versión, que valida el SDK), RNF-18 (validación de ``Origin``) y RNF-21
(límite por invocación). Pruebas: PP-07 (clave), PP-08 (registros), PP-14 (cabeceras), PP-16
(``Origin`` y 405) y PP-17 (límite); criterio CA-09. Errores: tab:ana-errores-mcp.

Orden de las comprobaciones (``CHECK_ORDER``). Las tres primeras las hace ``McpGuard`` antes
de entregar la petición al SDK; las dos últimas, el SDK:

1. ``Origin`` (RNF-18, DNS rebinding): si la cabecera está presente y no está en
   ``MCP_ALLOWED_ORIGINS``, 403, con independencia de CORS. Los clientes MCP de escritorio
   no envían ``Origin``; los navegadores sí.
2. Clave de API (RNF-15, PP-07): sin cabecera, 401; clave desconocida, 403. A diferencia de
   ``app.main._verify_api_key``, que deja la API abierta si no hay claves configuradas,
   ``/mcp`` nunca queda abierto: sin ``API_KEYS`` la ruta no se monta.
3. Límite (RNF-21, PP-17): solo ``tools/call`` de las herramientas que consumen cuota del
   modelo (``RATE_LIMITED_TOOLS``); al superarlo, 429. Método y herramienta se leen **del
   cuerpo**, no de ``Mcp-Name``: un cliente de la era del ``initialize`` no envía esa
   cabecera y no debe librarse del límite. Mentir en ``Mcp-Name`` tampoco sirve: el SDK
   rechaza después la incoherencia con el cuerpo.
4. Cabeceras (RNF-16, PP-14): el SDK compara ``Mcp-Method``/``Mcp-Name`` con el cuerpo
   (400, ``HeaderMismatch``, -32020) cuando la petición es de la era sin estado.
5. Versión (RNF-16, PP-01): el SDK rechaza una revisión no soportada en ``_meta`` (400,
   ``UnsupportedProtocolVersionError``, -32022, con ``data.supported``).

Es el reparto de 23-detalle («Capa de servicio y traducción de errores»). 22-arquitectura y
CU-07 ponían las cabeceras y la versión antes que la clave; con el SDK no es posible sin
duplicar su validación, y que un cliente sin clave reciba 401 antes que un error de protocolo
no revela nada. La memoria debe unificarse con este orden.

Los argumentos los valida cada herramienta, y un fallo es un resultado con ``isError``, no un
rechazo del transporte (PP-04). GET y DELETE sobre ``/mcp`` responden 405 desde la ruta
(``mcp_server.mount``), y ``Mcp-Session-Id`` se ignora (PP-16).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any, Final

import limits
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send

from app import config
from app.service import Via

logger = logging.getLogger(__name__)

CHECK_ORDER: Final[tuple[str, ...]] = (
    "origin",
    "api_key",
    "rate_limit",
    "headers",
    "protocol_version",
)

# Herramientas que consumen cuota del proveedor del modelo (RNF-21). listar_normativas y
# consultar_obligaciones solo leen el índice local (RF-24, RF-25; openWorldHint falso en
# app/mcp_server.py) y no se limitan.
RATE_LIMITED_TOOLS: Final[frozenset[str]] = frozenset({"analizar_proyecto"})

# Un cuestionario ocupa unos 2 KB; el SDK admitiría 4 MiB.
MAX_BODY_BYTES: Final = 256 * 1024

# JSON-RPC: los rechazos del transporte no tienen código propio en la especificación.
_INVALID_REQUEST: Final = -32600
_SERVER_ERROR: Final = -32000


class GuardRejection(Exception):
    """Rechazo antes de despachar la petición; ``status`` es el código HTTP de la respuesta."""

    status: int = 400
    jsonrpc_code: int = _INVALID_REQUEST
    headers: dict[str, str] = {}

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class OriginRejected(GuardRejection):
    status = 403


class MissingApiKey(GuardRejection):
    status = 401
    headers = {"WWW-Authenticate": 'ApiKey header="X-API-Key"'}


class InvalidApiKey(GuardRejection):
    status = 403


class RateLimited(GuardRejection):
    status = 429
    jsonrpc_code = _SERVER_ERROR

    def __init__(self, message: str, retry_after: int) -> None:
        super().__init__(message)
        self.headers = {"Retry-After": str(retry_after)}


class BodyTooLarge(GuardRejection):
    status = 413


def validate_origin(origin: str | None, allowed: frozenset[str]) -> None:
    """Acepta la ausencia de ``Origin``; si está presente, exige que esté en ``allowed``."""
    if origin is None:
        return
    if origin.rstrip("/") not in allowed:
        raise OriginRejected("Origin no permitido")


def check_api_key(x_api_key: str | None, key_set: frozenset[str]) -> None:
    """RNF-15: 401 sin cabecera y 403 con clave desconocida; ``key_set`` nunca está vacío.

    Con ``key_set`` vacío ``/mcp`` no se monta, así que aquí es un error de configuración y
    no una invitación a dejar pasar la petición.
    """
    if not key_set:
        raise InvalidApiKey("El servidor MCP no tiene claves de API configuradas")
    if not x_api_key:
        raise MissingApiKey("Falta la cabecera X-API-Key")
    if not any(hmac.compare_digest(x_api_key, k) for k in key_set):
        raise InvalidApiKey("Clave de API no válida")


def is_rate_limited(method: str | None, tool_name: str | None) -> bool:
    """``True`` solo para ``tools/call`` de una herramienta de ``RATE_LIMITED_TOOLS`` (RNF-21)."""
    return method == "tools/call" and tool_name in RATE_LIMITED_TOOLS


def rate_limit_key(api_key: str | None, client_ip: str) -> str:
    """Clave del limitador en ``/mcp`` (RNF-21): la clave de API y, si no la hay, la IP.

    La clave de API no se guarda en claro en el almacén del limitador: se usa un resumen.
    Como RNF-15 hace la clave siempre obligatoria, la rama por IP solo se alcanzaría si se
    relajara RNF-15.
    """
    if api_key:
        return "mcp:key:" + hashlib.sha256(api_key.encode()).hexdigest()[:16]
    return "mcp:ip:" + client_ip


def request_via(path: str, headers: dict[str, str] | None = None) -> Via:
    """Vía de acceso: ``Via.MCP`` bajo ``/mcp``; en el resto, ``Via.REST``."""
    # TODO(PT6/RF-28): Via.CI necesita una señal propia de la acción de CI (cabecera o
    # User-Agent); ver Via en app/service.py.
    if path == "/mcp" or path.startswith("/mcp/"):
        return Via.MCP
    return Via.REST


def _invocations(payload: Any) -> list[tuple[str | None, str | None]]:
    """``(method, params.name)`` de cada mensaje (la era antigua admitía lotes)."""
    mensajes = payload if isinstance(payload, list) else [payload]
    out = []
    for msg in mensajes:
        if not isinstance(msg, dict):
            continue
        params = msg.get("params")
        name = params.get("name") if isinstance(params, dict) else None
        method = msg.get("method")
        out.append(
            (
                method if isinstance(method, str) else None,
                name if isinstance(name, str) else None,
            )
        )
    return out


def _request_id(payload: Any) -> Any:
    if isinstance(payload, dict) and isinstance(payload.get("id"), str | int):
        return payload["id"]
    return None


def _client_ip(request: Request) -> str:
    from app.main import _get_real_ip  # importación tardía: app.main monta esta guarda

    return _get_real_ip(request)


def _hit_rate_limit(scope: Scope, key: str) -> None:
    """Cuenta una invocación en el limitador de la API (mismo almacén y mismo cupo)."""
    limiter = scope["app"].state.limiter
    item = limits.parse(config.settings.rate_limit)
    if not limiter._limiter.hit(item, key):
        reset_at = limiter._limiter.get_window_stats(item, key)[0]
        retry_after = max(1, int(reset_at - time.time()))
        raise RateLimited("Límite de peticiones superado", retry_after)


async def _read_body(receive: Receive) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            break
        chunk = message.get("body", b"")
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise BodyTooLarge("Cuerpo de la petición demasiado grande")
        chunks.append(chunk)
        if not message.get("more_body", False):
            break
    return b"".join(chunks)


def _replay(body: bytes, receive: Receive) -> Receive:
    """``receive`` que entrega primero el cuerpo ya leído y después delega en el original
    (para que el SDK detecte la desconexión del cliente y cancele la petición)."""
    sent = False

    async def _receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await receive()

    return _receive


class McpGuard:
    """Aplicación ASGI que aplica ``origin``, ``api_key`` y ``rate_limit`` y entrega la
    petición, con el cuerpo intacto, a ``handler`` (el gestor del SDK)."""

    def __init__(self, handler) -> None:
        self.handler = handler

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope)
        payload: Any = None
        try:
            body = await _read_body(receive)
            try:
                payload = json.loads(body) if body else None
            except ValueError:
                payload = None  # el SDK responde el error de análisis JSON-RPC
            validate_origin(
                request.headers.get("origin"), config.settings.mcp_origin_set
            )
            api_key = request.headers.get("x-api-key")
            check_api_key(api_key, config.settings.api_key_set)
            if any(is_rate_limited(m, t) for m, t in _invocations(payload)):
                _hit_rate_limit(scope, rate_limit_key(api_key, _client_ip(request)))
        except GuardRejection as rej:
            logger.info(
                json.dumps(
                    {
                        "event": "mcp_rejected",
                        "status": rej.status,
                        "reason": type(rej).__name__,
                    }
                )
            )
            response = JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": _request_id(payload),
                    "error": {"code": rej.jsonrpc_code, "message": rej.message},
                },
                status_code=rej.status,
                headers=rej.headers,
            )
            await response(scope, receive, send)
            return
        scope.setdefault("state", {})["via"] = request_via(scope["path"]).value
        await self.handler(scope, _replay(body, receive), send)
