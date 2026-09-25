"""Servidor MCP de LegalDev (esqueleto; NO se monta en la aplicación).

Requisitos: RF-22 a RF-25, RNF-15 y RNF-16; caso de uso CU-07; pruebas PP-01 a PP-08.

Revisión objetivo de la especificación: **2026-07-28**
(https://modelcontextprotocol.io/specification/2026-07-28/changelog). Lo que obliga a
diferencia de las revisiones anteriores:

* **Sin estado.** No hay sesiones ni cabecera ``Mcp-Session-Id``, ni handshake
  ``initialize``/``notifications/initialized``, ni ``ping``. Cada petición lleva en ``_meta``
  su versión (``io.modelcontextprotocol/protocolVersion``) y las capacidades del cliente
  (``io.modelcontextprotocol/clientCapabilities``); el cliente DEBERÍA identificarse con
  ``io.modelcontextprotocol/clientInfo`` y el servidor con
  ``io.modelcontextprotocol/serverInfo`` en el ``_meta`` de cada resultado. Una versión no
  soportada responde ``UnsupportedProtocolVersionError`` (-32022, ``data.supported``).
* **``server/discover`` obligatorio**: versiones soportadas, capacidades e identidad.
* **Streamable HTTP**: un único endpoint (``/mcp``) que acepta POST; GET y DELETE -> 405.
  Cada POST lleva ``MCP-Protocol-Version``, ``Mcp-Method`` y, en ``tools/call``, ``Mcp-Name``;
  si no coinciden con el cuerpo: 400 con ``HeaderMismatch`` (-32020). La respuesta es un
  objeto JSON o un flujo SSE propio de esa petición; no hay reanudación (``Last-Event-ID``).
* **``resultType`` obligatorio** en todos los resultados: ``"complete"`` o
  ``"input_required"``.
* **``tools/list`` cacheable**: ``ttlMs`` y ``cacheScope`` (``"public"``/``"private"``)
  obligatorios; las herramientas DEBERÍAN listarse en orden determinista.
* **MRTR** (``InputRequiredResult`` con ``inputRequests``; el cliente reintenta con
  ``inputResponses``) sustituye a las peticiones iniciadas por el servidor
  (``elicitation/create``, ``sampling/createMessage``, ``roots/list``). LegalDev no lo
  necesita: las tres herramientas reciben todos sus datos como argumentos y, si faltan, es el
  asistente quien los pide al desarrollador (CU-07, paso 3). Todos sus resultados son
  ``"complete"``.
* **Obsoletos**: Sampling, Roots y Logging. La migración recomendada para Sampling es
  llamar directamente a la API del proveedor del LLM, que es lo que ya hace LegalDev con Groq.
* ``inputSchema``/``outputSchema`` admiten cualquier palabra clave de JSON Schema 2020-12.

**Discrepancia con la memoria.** RF-22, RNF-16, PP-01, CA-09 y el paso 1 de CU-07 describen
todavía una «inicialización de la sesión» (``initialize``) que esta revisión elimina; el
equivalente es ``server/discover`` más la versión en ``_meta`` de cada petición.

El soporte de la revisión 2026-07-28 en el SDK oficial de Python está sin comprobar: lo
decide el spike de PT2, y hasta entonces no se añade la dependencia ``mcp``.
"""

from __future__ import annotations

from typing import Any, Final, Literal

PROTOCOL_VERSION: Final = "2026-07-28"
# TODO(PT2/RNF-16): comprobar qué revisión hablan hoy VS Code, Claude Code y Cursor. Un
# servidor solo «moderno» rechaza el initialize de un cliente «legacy» (matriz de
# compatibilidad de la revisión), así que puede hacer falta servir también 2025-11-25
# (servidor dual-era) para que CU-07 funcione con los asistentes reales.
SUPPORTED_VERSIONS: Final[tuple[str, ...]] = (PROTOCOL_VERSION,)
SERVER_NAME: Final = "legaldev"
MCP_PATH: Final = "/mcp"

# Códigos de error JSON-RPC de la revisión (rango -32020..-32099 reservado a la especificación).
ERROR_HEADER_MISMATCH: Final = -32020
ERROR_MISSING_REQUIRED_CLIENT_CAPABILITY: Final = -32021
ERROR_UNSUPPORTED_PROTOCOL_VERSION: Final = -32022
ERROR_METHOD_NOT_FOUND: Final = -32601  # por HTTP, con 404

ResultType = Literal["complete", "input_required"]
CacheScope = Literal["public", "private"]

# Orden determinista (la revisión lo recomienda para cachés y prompt caching del cliente).
TOOL_NAMES: Final[tuple[str, ...]] = (
    "analizar_proyecto",
    "listar_normativas",
    "consultar_obligaciones",
)

# Descripciones estáticas (RNF-15): nunca incorporan texto del usuario y se fijarán con una
# prueba de instantánea, como el SYSTEM_PROMPT. Texto de 23-detalle.tex, lst:det-mcp-tools.
TOOL_DESCRIPTIONS: Final[dict[str, str]] = {
    "analizar_proyecto": (
        "Identifica la normativa española y europea aplicable a un proyecto software "
        "descrito por un cuestionario y devuelve obligaciones con citas literales "
        "verificadas. Orientativo; no es asesoramiento legal."
    ),
    "listar_normativas": (
        "Devuelve las normativas indexadas (nombre, tipo, nivel) y la versión del corpus."
    ),
    "consultar_obligaciones": (
        "Devuelve las obligaciones de una normativa concreta para el contexto indicado, "
        "con citas verificadas."
    ),
}

# TODO(PT2/RF-22): fijar ttlMs y cacheScope de tools/list. Propuesta: la lista es estática y
# no depende de quién pregunta, así que "public"; 1 h, como la caché de respuestas, porque el
# corpus solo cambia con un redespliegue. Confirmar que "public" es aceptable cuando /mcp
# exige clave de API (un intermediario compartido serviría la lista sin comprobarla).
TOOLS_LIST_TTL_MS: Final = 3_600_000
TOOLS_LIST_CACHE_SCOPE: Final[CacheScope] = "public"


def server_discover() -> dict[str, Any]:
    """Resultado de ``server/discover`` (``DiscoverResult``).

    Forma prevista: ``resultType: "complete"``, ``supportedVersions: ["2026-07-28"]``,
    ``capabilities: {"tools": {}}``, ``_meta["io.modelcontextprotocol/serverInfo"]`` con
    nombre y versión del servicio, ``instructions`` opcional (texto estático) y, como
    operación cacheable, ``ttlMs`` y ``cacheScope``.
    """
    # TODO(PT2/PP-01): implementar. PP-01 («inicialización de la sesión») se reinterpreta
    # como: server/discover declara la revisión 2026-07-28 y la capacidad de herramientas.
    raise NotImplementedError


def tools_list() -> dict[str, Any]:
    """Resultado de ``tools/list``: las tres herramientas en el orden de ``TOOL_NAMES``.

    El ``inputSchema`` de ``analizar_proyecto`` se genera con
    ``QuestionnaireInput.model_json_schema()`` (el mismo que publica ``/openapi.json``), no se
    escribe a mano; su ``outputSchema`` cubre el contenido estructurado de RF-23. Incluye
    ``resultType``, ``ttlMs`` y ``cacheScope``.
    """
    # TODO(PT2/PP-02): implementar; comprobar que el esquema generado por Pydantic (con $defs
    # y $ref) cumple los requisitos de resolución de $ref de la revisión.
    raise NotImplementedError


async def analizar_proyecto(arguments: dict[str, Any], state) -> dict[str, Any]:
    """Herramienta ``analizar_proyecto`` (RF-23).

    Valida ``arguments`` con ``QuestionnaireInput``; si falla, devuelve un resultado con
    ``isError: true`` y el detalle de los campos (PP-04), no un error del protocolo. Si
    valida, delega en ``app.service.analyze(..., via=Via.MCP)`` y devuelve el informe como
    contenido de texto y, como ``structuredContent``, normativas detectadas, fragmentos,
    modelo, versión del corpus, estadísticas de citas, controles (cuando exista el mapeo,
    RF-26) y aviso. Los errores de dominio se traducen a resultados de error (CU-07, 4d y 4e).
    """
    # TODO(PT2/RF-23): implementar sobre app.service.analyze.
    raise NotImplementedError


def listar_normativas(state) -> dict[str, Any]:
    """Herramienta ``listar_normativas`` (RF-24): sin argumentos; delega en ``app.service``."""
    # TODO(PT2/RF-24): implementar sobre app.service.list_normativas.
    raise NotImplementedError


async def consultar_obligaciones(arguments: dict[str, Any], state) -> dict[str, Any]:
    """Herramienta ``consultar_obligaciones`` (RF-25).

    Argumentos ``normativa`` (nombre devuelto por ``listar_normativas``) y ``contexto``
    (máx. 500 caracteres). Una normativa desconocida produce un resultado de error con la
    lista de las disponibles (PP-06).
    """
    # TODO(PT2/RF-25): implementar sobre app.service.consultar_obligaciones.
    raise NotImplementedError


def tool_error_result(message: str) -> dict[str, Any]:
    """Resultado de herramienta con ``isError: true`` y ``resultType: "complete"``.

    El mensaje es estático o enumera campos del esquema; nunca repite texto libre del usuario.
    """
    # TODO(PT2/PP-04): implementar.
    raise NotImplementedError


def build_mcp_app(state):
    """Aplicación ASGI que ``app/main.py`` montará en ``MCP_PATH`` si ``settings.mcp_enabled``.

    Comparte proceso, caché, limitador y claves de API con la API REST (RF-22) y aplica
    ``app.mcp_guard`` antes de despachar cada petición.
    """
    # TODO(PT2/RF-22): decidir en el spike entre el SDK oficial de Python (si soporta la
    # revisión 2026-07-28; fijar la versión en pyproject) y un transporte propio sobre
    # FastAPI. Montarlo en main.py solo cuando settings.mcp_enabled sea verdadero.
    raise NotImplementedError
