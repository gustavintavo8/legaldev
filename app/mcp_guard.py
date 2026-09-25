"""Controles de acceso del punto de entrada ``/mcp`` (esqueleto; no se usa en producción).

Requisitos: RNF-15 (clave de API siempre obligatoria, del mismo conjunto que la API REST;
descripciones estáticas; registros sin la descripción libre), RNF-16 (cabeceras y versión de
la revisión 2026-07-28), RNF-18 (validación de ``Origin``) y RNF-21 (límite por invocación).
Pruebas: PP-01 (versión), PP-07 (clave), PP-08 (registros), PP-14 (cabeceras), PP-16
(``Origin`` y 405) y PP-17 (límite); criterio CA-09. Errores: tab:ana-errores-mcp.

Orden de las comprobaciones antes de despachar el JSON-RPC (``CHECK_ORDER``), el de
22-arquitectura («Flujo sin estado de una invocación», paso 3) y de CU-07 (paso 5):

1. ``Origin`` (RNF-18, protección frente a DNS rebinding): si la cabecera está presente y no
   es un origen permitido, 403, con independencia de CORS. Los clientes MCP de escritorio no
   envían ``Origin``; los navegadores sí.
2. Cabeceras (RNF-16, PP-14): ``MCP-Protocol-Version``, ``Mcp-Method`` y, en ``tools/call``,
   ``Mcp-Name`` deben existir y coincidir con el cuerpo; si no, 400 con ``HeaderMismatch``
   (-32020). Un ``initialize`` de un cliente de la revisión 2025-11-25 cae aquí: no trae esas
   cabeceras, y el mensaje debería nombrar las revisiones admitidas (21-analisis).
3. Versión (RNF-16, PP-01): una revisión no soportada en ``_meta``, 400 con
   ``UnsupportedProtocolVersionError`` (-32022) y ``data.supported``.
4. Clave de API (RNF-15, PP-07): sin cabecera, 401; clave desconocida, 403. A diferencia de
   ``app.main._verify_api_key``, que deja la API abierta si no hay claves configuradas,
   ``/mcp`` nunca queda abierto: sin ``API_KEYS`` la ruta no se monta (22-arquitectura,
   «Despliegue»; ver ``settings.mcp_enabled``).
5. Límite (RNF-21, PP-17): solo ``tools/call`` de las herramientas que consumen cuota del
   modelo (``RATE_LIMITED_TOOLS``); al superarlo, 429. ``server/discover``, ``tools/list`` y
   las herramientas que solo leen el índice no se limitan. Usa ``Mcp-Name`` ya validado en el
   paso 2 para saber qué herramienta se invoca.
6. Argumentos: los valida cada herramienta y un fallo es un resultado con ``isError``, no
   un rechazo del transporte (PP-04). No se hace aquí.

Después, la etiqueta ``via=mcp`` en ``request.state`` para métricas y registros (CU-07).
GET y DELETE sobre ``/mcp`` responden 405 y ``Mcp-Session-Id`` se ignora (PP-16).

Comprobar las cabeceras y la versión antes que la clave hace que un cliente sin clave reciba
primero los errores del protocolo; no revela nada que no diga ya la especificación.
23-detalle («Capa de servicio y traducción de errores») describe otro reparto: un middleware
ASGI anterior al SDK comprueba ``Origin``, la clave y el límite (con ``Mcp-Method`` aún sin
validar) y el SDK valida después las cabeceras. Se sigue 22-arquitectura, que coincide con
CU-07; la memoria debe unificar 23-detalle con ellos.
"""

from __future__ import annotations

from typing import Final

from app.service import Via

CHECK_ORDER: Final[tuple[str, ...]] = (
    "origin",
    "headers",
    "protocol_version",
    "api_key",
    "rate_limit",
)

# Herramientas que consumen cuota del proveedor del modelo (RNF-21). listar_normativas y
# consultar_obligaciones solo leen el índice local (RF-24, RF-25; openWorldHint falso en
# app/mcp_server.py) y no se limitan.
RATE_LIMITED_TOOLS: Final[frozenset[str]] = frozenset({"analizar_proyecto"})


class GuardRejection(Exception):
    """Rechazo antes de despachar la petición; ``status`` es el código HTTP de la respuesta."""

    status: int = 400


class OriginRejected(GuardRejection):
    status = 403


class HeaderMismatch(GuardRejection):
    status = 400
    jsonrpc_code = -32020


class UnsupportedProtocolVersion(GuardRejection):
    status = 400
    jsonrpc_code = -32022


class MissingApiKey(GuardRejection):
    status = 401


class InvalidApiKey(GuardRejection):
    status = 403


def validate_origin(origin: str | None, allowed_origins: list[str]) -> None:
    """Acepta la ausencia de ``Origin``; si está presente, exige que esté en la lista permitida."""
    # TODO(PT2/RNF-18): decidir la lista para /mcp. Con ALLOWED_ORIGINS="*" (valor por
    # defecto, pensado para CORS de la web) la validación no protegería de nada: /mcp debe
    # tener una lista explícita propia, independiente de CORS (tab:arq-mcp-amenazas), y no
    # heredar "*". Añadir el ajuste cuando se implemente.
    raise NotImplementedError


def validate_request_headers(headers: dict[str, str], body: dict) -> None:
    """Coherencia de ``MCP-Protocol-Version``/``Mcp-Method``/``Mcp-Name`` con el cuerpo (PP-14).

    ``Mcp-Name`` puede venir codificado como ``=?base64?...?=`` y se decodifica antes de
    comparar. Los nombres de cabecera se comparan sin distinguir mayúsculas; los valores, sí.
    """
    # TODO(PT2/RNF-16): implementar solo si el SDK elegido no lo hace ya.
    raise NotImplementedError


def check_protocol_version(requested: str, supported: tuple[str, ...]) -> None:
    """Versión de ``_meta`` frente a las soportadas; si no está, ``UnsupportedProtocolVersion``.

    El error lleva ``data.supported`` (las de ``mcp_server.SUPPORTED_VERSIONS``) y
    ``data.requested``, para que el cliente reintente con una común (PP-01).
    """
    # TODO(PT2/RNF-16): implementar solo si el SDK elegido no lo hace ya.
    raise NotImplementedError


def check_api_key(x_api_key: str | None, key_set: frozenset[str]) -> None:
    """RNF-15: 401 sin cabecera y 403 con clave desconocida; ``key_set`` nunca está vacío.

    Con ``key_set`` vacío ``/mcp`` no se monta, así que aquí es un error de configuración y
    no una invitación a dejar pasar la petición.
    """
    # TODO(PT2/PP-07): implementar compartiendo con app.main._verify_api_key la comparación
    # de claves, pero no su política de «abierto sin claves», que solo vale para la API REST.
    raise NotImplementedError


def is_rate_limited(method: str, tool_name: str | None) -> bool:
    """``True`` solo para ``tools/call`` de una herramienta de ``RATE_LIMITED_TOOLS`` (RNF-21)."""
    # TODO(PT2/RNF-21): implementar y conectar al limitador de app.main (settings.rate_limit).
    raise NotImplementedError


def rate_limit_key(api_key: str | None, client_ip: str) -> str:
    """Clave del limitador en ``/mcp`` (RNF-21): la clave de API y, si no la hay, la IP.

    Es la regla de tab:ana-errores-mcp («por clave o, si no la hay, por IP»). La IP es la de
    ``app.main._get_real_ip``. La clave de API no se guarda en claro en el almacén del
    limitador: se usa un resumen (p. ej. ``"key:" + sha256(clave)[:16]``).
    """
    # TODO(PT2/RNF-21): implementar. slowapi fija key_func al crear el Limiter; /mcp necesita
    # otra función de clave (o un segundo Limiter con el mismo almacén). Como RNF-15 hace la
    # clave siempre obligatoria, la rama por IP solo se alcanzaría si se relajara RNF-15.
    # RNF-21, 22-arquitectura y 23-detalle dicen «por clave e IP»; unificar la redacción con
    # tab:ana-errores-mcp. Falta también el «tope diario por clave» de tab:arq-mcp-amenazas.
    raise NotImplementedError


def request_via(path: str, headers: dict[str, str]) -> Via:
    """Vía de acceso: ``Via.MCP`` bajo ``/mcp``; en el resto, ``Via.REST`` o ``Via.CI``."""
    # TODO(PT2/CU-07): implementar y añadir la etiqueta via a las métricas de app/metrics.py
    # (cambia las series de Prometheus: revisar paneles y alertas existentes). La señal de
    # Via.CI la fija PT6 (ver Via en app/service.py).
    raise NotImplementedError
