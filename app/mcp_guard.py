"""Controles de acceso del punto de entrada ``/mcp`` (guarda ASGI delante del SDK).

Requisitos: RNF-15 (clave de API siempre obligatoria: ``MCP_API_KEYS`` o, si está vacía,
las de la API REST),
RNF-16 (cabeceras y versión, que valida el SDK), RNF-18 (validación de ``Origin``) y RNF-21
(límite por invocación). Pruebas: PP-07 (clave), PP-08 (registros), PP-14 (cabeceras), PP-16
(``Origin`` y 405) y PP-17 (límite); criterio CA-09. Errores: tab:ana-errores-mcp.

Orden de las comprobaciones (``CHECK_ORDER``). Las tres primeras las hace ``McpGuard`` antes
de entregar la petición al SDK; las dos últimas, el SDK:

1. ``Origin`` (RNF-18, DNS rebinding): si la cabecera está presente y no está en
   ``MCP_ALLOWED_ORIGINS``, 403, con independencia de CORS. Los clientes MCP de escritorio
   no envían ``Origin``; los navegadores sí.
2. Clave de API (RNF-15, PP-07): sin cabecera, 401; clave desconocida, 403. Las claves son
   las de ``MCP_API_KEYS`` o, si no hay, las de ``API_KEYS`` (``settings.mcp_key_set``). A
   diferencia de ``app.main._verify_api_key``, que deja la API abierta si no hay claves,
   ``/mcp`` nunca queda abierto: sin claves la ruta no se monta.
3. Límite (RNF-21, PP-17): solo ``tools/call`` de las herramientas que consumen cuota del
   modelo (``RATE_LIMITED_TOOLS``); al superarlo, 429 con ``Retry-After``. Primero el cupo
   por minuto (``RATE_LIMIT``) y después, si ``MCP_DAILY_LIMIT`` lo fija, el tope diario
   por clave, en el mismo almacén. Método y herramienta se leen **del cuerpo**, no de
   ``Mcp-Name``: un cliente de la era del ``initialize`` no envía esa cabecera y no debe
   librarse del límite. Mentir en ``Mcp-Name`` tampoco sirve: el SDK rechaza después la
   incoherencia con el cuerpo. Se cuentan todas las llamadas que pasan la guarda, también
   las que acaban saliendo de la caché, las de un cuestionario inválido y las que no tienen
   cobertura: la guarda decide antes de validar y de mirar la caché (``docs/mcp/README.md``,
   «Tope diario por clave»).
4. Cabeceras (RNF-16, PP-14): el SDK compara ``Mcp-Method``/``Mcp-Name`` con el cuerpo
   (400, ``HeaderMismatch``, -32020) cuando la petición es de la era sin estado.
5. Versión (RNF-16, PP-01): el SDK rechaza una revisión no soportada en ``_meta`` (400,
   ``UnsupportedProtocolVersionError``, -32022, con ``data.supported``).

Es el reparto de 23-detalle («Capa de servicio y traducción de errores»). 22-arquitectura y
CU-07 ponían las cabeceras y la versión antes que la clave; con el SDK no es posible sin
duplicar su validación, y que un cliente sin clave reciba 401 antes que un error de protocolo
no revela nada. Este es el orden que rige; el cambio que necesita la memoria está anotado en
``docs/mcp/README.md``, «Cambios que necesita la memoria».

Antes del límite, la guarda exige un único objeto JSON-RPC legible (sin lotes ni claves
duplicadas): lo que no puede leer no lo deja pasar. Los argumentos los valida cada
herramienta, y un fallo es un resultado con ``isError``, no un rechazo del transporte (PP-04). GET y DELETE sobre ``/mcp`` responden 405 desde la ruta
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

# Identificador del contador del tope diario (MCP_DAILY_LIMIT) en el almacén del limitador.
# limits nombra cada contador por identificadores y límite («LIMITER/<ids>/200/1/day»): si
# RATE_LIMIT incluyera el mismo límite («10/minute;200/day»), sin este identificador los dos
# compartirían contador y cada llamada contaría dos veces.
DAILY_LIMIT_SCOPE: Final = "tope_diario"

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


class DailyLimitExceeded(RateLimited):
    """Tope diario de la clave agotado (``MCP_DAILY_LIMIT``): 429 como el cupo por minuto,
    con otro mensaje y otro ``reason`` en el registro."""


class BodyTooLarge(GuardRejection):
    status = 413


class InvalidJson(GuardRejection):
    """Cuerpo que no se puede analizar (JSON roto, anidamiento excesivo, enteros de más de
    4300 cifras, claves duplicadas). Se rechaza aquí y no se deja al SDK: si los dos
    analizadores discreparan, la guarda podría no ver una invocación que el SDK sí ejecuta."""

    jsonrpc_code = -32700


class InvalidMessage(GuardRejection):
    """Un JSON que no es un único objeto JSON-RPC (lotes incluidos, que ninguna de las dos
    eras admite ya)."""


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
    # En bytes: compare_digest no admite str con caracteres no ASCII (y Starlette decodifica
    # las cabeceras como latin-1, así que pueden llegar). latin-1 devuelve los bytes que envió
    # el cliente; las claves configuradas se comparan en UTF-8.
    candidata = x_api_key.encode("latin-1", errors="replace")
    if not any(hmac.compare_digest(candidata, k.encode("utf-8")) for k in key_set):
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


class _DuplicateKey(ValueError):
    pass


def _sin_duplicados(pares: list[tuple[str, Any]]) -> dict[str, Any]:
    objeto: dict[str, Any] = {}
    for clave, valor in pares:
        if clave in objeto:
            # Con «name» repetido, dos analizadores podrían quedarse con valores distintos.
            raise _DuplicateKey(clave)
        objeto[clave] = valor
    return objeto


def _parse(body: bytes) -> tuple[dict[str, Any] | None, GuardRejection | None]:
    """El mensaje JSON-RPC, o el rechazo que corresponde si no es un único objeto válido."""
    try:
        payload = json.loads(body, object_pairs_hook=_sin_duplicados)
    except (ValueError, RecursionError):
        return None, InvalidJson("El cuerpo no es un JSON válido")
    if not isinstance(payload, dict):
        return None, InvalidMessage("Se espera un único mensaje JSON-RPC (sin lotes)")
    return payload, None


def _invocation(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    """``(method, params.name)`` del mensaje."""
    params = payload.get("params")
    name = params.get("name") if isinstance(params, dict) else None
    method = payload.get("method")
    return (
        method if isinstance(method, str) else None,
        name if isinstance(name, str) else None,
    )


def _request_id(payload: Any) -> Any:
    if isinstance(payload, dict) and isinstance(payload.get("id"), str | int):
        return payload["id"]
    return None


def _client_ip(request: Request) -> str:
    from app.main import _get_real_ip  # importación tardía: app.main monta esta guarda

    return _get_real_ip(request)


def _retry_after(strategy, item: limits.RateLimitItem, *identifiers: str) -> int:
    """Segundos hasta que se renueva la ventana (al menos 1), para ``Retry-After``."""
    reset_at = strategy.get_window_stats(item, *identifiers)[0]
    return max(1, int(reset_at - time.time()))


def _hit_rate_limit(scope: Scope, key: str) -> None:
    """Cuenta una invocación en el limitador de la API (mismo almacén y mismo cupo).

    ``RATE_LIMIT`` admite varios límites («10/minute;100/day»), como en slowapi: se cuentan
    todos y basta con que se agote uno.
    """
    strategy = scope["app"].state.limiter._limiter
    for item in limits.parse_many(config.settings.rate_limit):
        if not strategy.hit(item, key):
            raise RateLimited(
                "Límite de peticiones superado", _retry_after(strategy, item, key)
            )


def _hit_daily_limit(scope: Scope, key: str) -> None:
    """Cuenta una invocación en el tope diario de la clave (``MCP_DAILY_LIMIT``), si lo hay.

    Mismo almacén que el cupo por minuto, con un identificador propio
    (``DAILY_LIMIT_SCOPE``). Ventana fija de 24 h desde la primera llamada contada de cada
    clave, no desde medianoche; el almacén es la memoria del proceso, así que un reinicio la
    vacía.
    """
    item = config.settings.mcp_daily_limit_item
    if item is None:
        return
    strategy = scope["app"].state.limiter._limiter
    if not strategy.hit(item, key, DAILY_LIMIT_SCOPE):
        retry_after = _retry_after(strategy, item, key, DAILY_LIMIT_SCOPE)
        raise DailyLimitExceeded(
            f"Tope diario de analizar_proyecto agotado para esta clave ({item.amount} "
            f"al día). Se renueva dentro de {retry_after} s; listar_normativas y "
            "consultar_obligaciones siguen disponibles.",
            retry_after,
        )


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
        payload: dict[str, Any] | None = None
        try:
            body = await _read_body(receive)
            # Se analiza antes de autenticar solo para devolver el id en los rechazos; un
            # cuerpo ilegible se rechaza después de comprobar el origen y la clave.
            payload, invalido = _parse(body)
            validate_origin(
                request.headers.get("origin"), config.settings.mcp_origin_set
            )
            api_key = request.headers.get("x-api-key")
            check_api_key(api_key, config.settings.mcp_key_set)
            if invalido is not None:
                raise invalido
            if is_rate_limited(*_invocation(payload)):
                clave = rate_limit_key(api_key, _client_ip(request))
                # Primero el cupo por minuto: una ráfaga frenada no gasta el tope diario.
                _hit_rate_limit(scope, clave)
                _hit_daily_limit(scope, clave)
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
        await self.handler(scope, _replay(body, receive), send)
