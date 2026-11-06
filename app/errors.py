"""Errores de dominio del motor (ErrorDominio en fig:det-mcp-clases).

El motor (``app/rag.py``) los lanza en lugar de ``fastapi.HTTPException`` y cada vía de
acceso los traduce a su formato: la API REST con ``HTTP_STATUS`` (mismos códigos y textos que
antes del cambio) y el servidor MCP con un resultado de herramienta (tab:det-mcp-errores). No
dependen de FastAPI ni de la biblioteca MCP.
"""

from __future__ import annotations


class LegalDevError(Exception):
    """Base de los errores de dominio; ``detail`` es el texto que ve el cliente REST."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class NoCoverageError(LegalDevError):
    """``SinCobertura``: ningún fragmento supera el umbral.

    Por REST es un 404; por MCP no es un error, sino un resultado con ``isError: false`` y
    sin normativas (CU-07, flujo 5c).
    """


class LLMUnavailableError(LegalDevError):
    """``ModeloNoDisponible``: fallan el modelo principal y el de respaldo (REST 503)."""


class RetrievalTimeoutError(LegalDevError):
    """``TiempoAgotado``: la recuperación supera ``settings.retrieval_timeout`` (REST 503)."""


class UnknownNormativaError(LegalDevError):
    """``NormativaDesconocida``: ``consultar_obligaciones`` recibe una normativa que no está
    en el índice (RF-25, PP-06). Solo existe por MCP."""

    def __init__(self, normativa: str, disponibles: list[str]) -> None:
        super().__init__(f"Normativa desconocida: {normativa!r}")
        self.normativa = normativa
        self.disponibles = disponibles


class InvalidMappingError(LegalDevError):
    """``TablaMapeoInvalida``: la tabla de mapeo o el catálogo no validan al arrancar.

    ``POST /v1/evidence`` responde 503; ``analizar_proyecto`` devuelve el resultado sin
    obligaciones tipificadas y ``/health/deep`` señala el fallo (tab:det-mcp-errores).
    """


# Traducción a la API REST (tab:det-mcp-errores). Los tres primeros reproducen los códigos que
# devolvía run_pipeline con HTTPException. UnknownNormativaError no tiene equivalente REST.
HTTP_STATUS: dict[type[LegalDevError], int] = {
    NoCoverageError: 404,
    LLMUnavailableError: 503,
    RetrievalTimeoutError: 503,
    InvalidMappingError: 503,
}
