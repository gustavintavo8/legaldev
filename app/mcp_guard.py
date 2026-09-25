"""Controles de acceso del punto de entrada ``/mcp`` (esqueleto; no se usa en producción).

Requisitos: RNF-15 (mismas claves de API y mismo límite por IP que ``/v1/analyze``,
descripciones estáticas, registros sin la descripción libre) y las medidas de seguridad del
transporte Streamable HTTP de la revisión 2026-07-28. Pruebas: PP-07 y PP-08.

Orden previsto de las comprobaciones, antes de despachar el JSON-RPC:

1. ``Origin`` (protección frente a DNS rebinding): si la cabecera está presente y no es un
   origen permitido, 403. Los clientes MCP de escritorio no envían ``Origin``; los
   navegadores sí.
2. Clave de API: la misma semántica que ``app.main._verify_api_key`` (sin claves
   configuradas, abierto; sin cabecera, 401; clave desconocida, 403).
3. Cabeceras de la revisión (``MCP-Protocol-Version``, ``Mcp-Method``, ``Mcp-Name``) frente al
   cuerpo: 400 con ``HeaderMismatch`` (-32020) si faltan o no coinciden. Puede resolverlo el
   SDK si se adopta; si no, se implementa aquí.
4. Límite por IP (``settings.rate_limit``, la misma clave ``_get_real_ip``) aplicado solo a
   ``tools/call``: ``server/discover`` y ``tools/list`` son baratos y el cliente los repite,
   y no deben consumir el cupo de análisis. Es una concreción de RNF-15, que habla del
   «mismo límite»; al superarlo, 429 (PP-07).
5. Etiqueta ``via=mcp`` en ``request.state`` para métricas y registros (CU-07).
"""

from __future__ import annotations

from typing import Final

from app.service import Via

RATE_LIMITED_METHODS: Final[frozenset[str]] = frozenset({"tools/call"})


class GuardRejection(Exception):
    """Rechazo antes de despachar la petición; ``status`` es el código HTTP de la respuesta."""

    status: int = 400


class OriginRejected(GuardRejection):
    status = 403


class MissingApiKey(GuardRejection):
    status = 401


class InvalidApiKey(GuardRejection):
    status = 403


class HeaderMismatch(GuardRejection):
    status = 400
    jsonrpc_code = -32020


def validate_origin(origin: str | None, allowed_origins: list[str]) -> None:
    """Acepta la ausencia de ``Origin``; si está presente, exige que esté en la lista permitida."""
    # TODO(PT2/RNF-15): decidir la lista para /mcp. Con ALLOWED_ORIGINS="*" (valor por
    # defecto, pensado para CORS de la web) la validación no protegería de nada: /mcp debería
    # tener una lista explícita propia y no heredar "*". Añadir el ajuste cuando se implemente.
    raise NotImplementedError


def check_api_key(x_api_key: str | None, key_set: frozenset[str]) -> None:
    """Misma política que ``app.main._verify_api_key``, sin depender de FastAPI."""
    # TODO(PT2/PP-07): implementar y hacer que _verify_api_key reutilice esta función.
    raise NotImplementedError


def validate_request_headers(headers: dict[str, str], body: dict) -> None:
    """Coherencia de ``MCP-Protocol-Version``/``Mcp-Method``/``Mcp-Name`` con el cuerpo.

    ``Mcp-Name`` puede venir codificado como ``=?base64?...?=`` y se decodifica antes de
    comparar. Los nombres de cabecera se comparan sin distinguir mayúsculas; los valores, sí.
    """
    # TODO(PT2/RNF-16): implementar solo si el SDK elegido no lo hace ya.
    raise NotImplementedError


def is_rate_limited(method: str) -> bool:
    """``True`` si el método JSON-RPC consume cupo del limitador (solo ``tools/call``)."""
    # TODO(PT2/PP-07): implementar y conectar al limitador de app.main (misma instancia).
    raise NotImplementedError


def request_via(path: str) -> Via:
    """Vía de acceso según la ruta: ``Via.MCP`` bajo ``/mcp``, ``Via.REST`` en el resto."""
    # TODO(PT2/CU-07): implementar y añadir la etiqueta via a las métricas de app/metrics.py
    # (cambia las series de Prometheus: revisar paneles y alertas existentes).
    raise NotImplementedError
