"""Servidor MCP de LegalDev (esqueleto; NO se monta en la aplicación).

Requisitos: RF-22 a RF-25, RNF-15, RNF-16 y RNF-18 a RNF-21; caso de uso CU-07; pruebas
PP-01 a PP-08 y PP-13 a PP-18; criterio CA-09; pregunta PI6. Controles de acceso en
``app/mcp_guard.py``; casos de uso en ``app/service.py``.

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
  necesita en la primera versión: las tres herramientas reciben todos sus datos como
  argumentos y, si faltan, es el asistente quien los pide al desarrollador (CU-07, paso 3;
  se revisará con PI7). Todos sus resultados son ``"complete"``.
* **Obsoletos**: Sampling, Roots y Logging. La migración recomendada para Sampling es
  llamar directamente a la API del proveedor del LLM, que es lo que ya hace LegalDev con Groq.
* ``inputSchema``/``outputSchema`` admiten cualquier palabra clave de JSON Schema 2020-12.

La memoria (04-alternativas y 23-detalle) elige el SDK oficial de Python, cuya línea 2.x
declara soporte de la revisión 2026-07-28 y de las anteriores. La versión concreta, las
revisiones que atiende de verdad y los clientes de la demostración los fija la prueba de
concepto de PT2; hasta entonces no se añade la dependencia ``mcp``. Las diferencias que
quedan entre este esqueleto y la memoria, y las de la memoria consigo misma, están en
``docs/mcp/README.md``.
"""

from __future__ import annotations

from typing import Any, Final, Literal

PROTOCOL_VERSION: Final = "2026-07-28"
# TODO(PT2/RNF-16): comprobar qué revisión hablan hoy VS Code, Claude Code y Cursor. Un
# servidor solo «moderno» rechaza con 400 el initialize de un cliente de la revisión
# 2025-11-25, que no trae las cabeceras (tab:ana-errores-mcp; 21-analisis lo deja como
# decisión abierta), así que puede hacer falta servir también 2025-11-25 (servidor de doble
# era) para que CU-07 funcione con los asistentes reales. Si se sirve solo 2026-07-28, ese
# error 400 debe nombrar las versiones soportadas, porque el cliente no puede adaptarse.
SUPPORTED_VERSIONS: Final[tuple[str, ...]] = (PROTOCOL_VERSION,)
SERVER_NAME: Final = "legaldev"
MCP_PATH: Final = "/mcp"

# Códigos de error JSON-RPC (tab:ana-errores-mcp y tab:det-mcp-errores). El rango
# -32020..-32099 lo reserva la revisión 2026-07-28.
ERROR_HEADER_MISMATCH: Final = -32020
ERROR_MISSING_REQUIRED_CLIENT_CAPABILITY: Final = -32021
ERROR_UNSUPPORTED_PROTOCOL_VERSION: Final = -32022
ERROR_METHOD_NOT_FOUND: Final = -32601  # por HTTP, con 404
ERROR_INVALID_PARAMS: Final = -32602  # herramienta desconocida o tools/call mal formado
ERROR_INTERNAL: Final = -32603  # excepción no prevista, sin detalle interno

ResultType = Literal["complete", "input_required"]
CacheScope = Literal["public", "private"]

# Orden determinista (la revisión lo recomienda para cachés y prompt caching del cliente).
TOOL_NAMES: Final[tuple[str, ...]] = (
    "analizar_proyecto",
    "listar_normativas",
    "consultar_obligaciones",
)

# Descripciones estáticas (RNF-15): nunca incorporan texto del usuario y se fijarán con una
# prueba de instantánea, como el SYSTEM_PROMPT. Contenido según tab:det-mcp-herramientas
# (23-detalle); la redacción es propia.
TOOL_DESCRIPTIONS: Final[dict[str, str]] = {
    "analizar_proyecto": (
        "Identifica la normativa española y europea aplicable a un proyecto software "
        "descrito por un cuestionario y devuelve obligaciones con citas literales "
        "verificadas. Orientativo; no es asesoramiento legal."
    ),
    "listar_normativas": (
        "Devuelve las normativas indexadas (identificador, tipo de documento y páginas) y "
        "la versión del corpus."
    ),
    "consultar_obligaciones": (
        "Devuelve los fragmentos más pertinentes de una normativa indexada para un contexto "
        "breve, con su localización (página y artículo). Solo consulta el índice: no redacta "
        "ni interpreta. Orientativo; no es asesoramiento legal."
    ),
}

# Descripción del único campo libre (22-arquitectura, «Esquema de las herramientas», y
# 20-requisitos, restricción de minimización): una o dos frases, sin código, credenciales ni
# datos personales. Entra en la misma instantánea que TOOL_DESCRIPTIONS.
DESCRIPCION_BREVE_FIELD: Final = (
    "Funcionalidad del proyecto en una o dos frases. No incluyas código, credenciales, "
    "secretos ni datos personales."
)

# Anotaciones (22-arquitectura, «Esquema de las herramientas»; tab:det-mcp-herramientas): las
# tres son de solo lectura; listar_normativas y consultar_obligaciones solo leen el índice
# local y declaran openWorldHint falso; analizar_proyecto lo deja en su valor por defecto
# (verdadero) porque envía la descripción al proveedor del modelo. Son orientativas: el
# cliente no debe fiarse de ellas salvo que confíe en el servidor.
TOOL_ANNOTATIONS: Final[dict[str, dict[str, bool]]] = {
    "analizar_proyecto": {"readOnlyHint": True},
    "listar_normativas": {"readOnlyHint": True, "openWorldHint": False},
    "consultar_obligaciones": {"readOnlyHint": True, "openWorldHint": False},
}

# TODO(PT2/RF-22): fijar ttlMs de tools/list. La memoria (21-analisis y 22-arquitectura) la
# declara "public" y de validez larga porque no depende de quién pregunta y solo cambia con
# una versión nueva; propuesta: 1 h, como la caché de respuestas. Confirmar que "public" es
# aceptable cuando /mcp exige clave de API (un intermediario compartido serviría la lista sin
# comprobarla).
TOOLS_LIST_TTL_MS: Final = 3_600_000
TOOLS_LIST_CACHE_SCOPE: Final[CacheScope] = "public"


def server_discover() -> dict[str, Any]:
    """Resultado de ``server/discover`` (``DiscoverResult``; PP-13).

    Forma prevista: ``resultType: "complete"``, ``supportedVersions: ["2026-07-28"]``,
    ``capabilities: {"tools": {}}``, ``_meta["io.modelcontextprotocol/serverInfo"]`` con
    nombre y versión del servicio, ``instructions`` opcional (texto estático) y, como
    operación cacheable, ``ttlMs`` y ``cacheScope``.
    """
    # TODO(PT2/PP-13): implementar.
    raise NotImplementedError


def tools_list() -> dict[str, Any]:
    """Resultado de ``tools/list``: las tres herramientas en el orden de ``TOOL_NAMES``.

    El ``inputSchema`` de ``analizar_proyecto`` se deriva de
    ``QuestionnaireInput.model_json_schema()`` y se posprocesa (22-arquitectura, «Esquema de
    las herramientas»; tab:det-mcp-herramientas): ``$ref`` resueltos en línea, la dependencia
    entre ``usa_ia`` y ``tipo_ia`` expresada con ``if``/``then`` y descripciones por campo
    (``DESCRIPCION_BREVE_FIELD`` para el texto libre). El modelo Pydantic sigue siendo la
    fuente de verdad: el servidor revalida con él, y PP-02 comprueba que el esquema publicado
    y el modelo aceptan y rechazan los mismos cuestionarios de ejemplo. El ``inputSchema`` de
    ``consultar_obligaciones`` enumera los identificadores del índice en ``normativa``. Cada
    herramienta lleva sus ``TOOL_ANNOTATIONS`` y su ``outputSchema``; el resultado incluye
    ``resultType``, ``ttlMs`` y ``cacheScope`` (PP-15).
    """
    # TODO(PT2/PP-02): implementar el posprocesado. 20-requisitos (tercera precisión de la
    # tabla de requisitos funcionales) dice aún que el esquema publicado «no expresa» la
    # regla de tipo_ia, contra 22-arquitectura y 23-detalle (if/then): corregir la memoria.
    raise NotImplementedError


async def analizar_proyecto(arguments: dict[str, Any], state) -> dict[str, Any]:
    """Herramienta ``analizar_proyecto`` (RF-23; PP-03).

    Valida ``arguments`` con ``QuestionnaireInput``; si falla, devuelve un resultado con
    ``isError: true`` y el detalle de los campos (PP-04; CU-07, flujo 5b), no un error del
    protocolo. Si valida, delega en ``app.service.analyze(..., via=Via.MCP)`` y devuelve:

    * como texto, el informe en Markdown seguido de la serialización JSON del contenido
      estructurado (para los clientes que no leen ``structuredContent``);
    * como ``structuredContent``, conforme a su ``outputSchema`` (tab:det-mcp-herramientas y
      CU-07, paso 6): el cuestionario interpretado, ``normativas_detectadas``, ``fragmentos``
      (``service.FragmentoRef`` sin texto), ``llm_model``, ``corpus_version``, ``citas`` y,
      con OE2, ``obligaciones`` y ``sin_tipificar`` (RF-27), además del aviso.

    Los errores de dominio se traducen según tab:det-mcp-errores (CU-07, flujos 5c y 5d): sin
    cobertura es un resultado válido sin obligaciones; tiempo agotado y modelo no disponible,
    ``isError`` con un código estable reintentable.
    """
    # TODO(PT2/RF-23): implementar sobre app.service.analyze.
    # TODO(PT2/RNF-19): responder con SSE y, si la petición trae progressToken, emitir
    # notifications/progress al terminar cada etapa (recuperación, generación, verificación)
    # para que el cliente reinicie su tiempo de espera. Si el cliente cierra el flujo, tratarlo
    # como cancelación: no enviar más mensajes y abandonar la petición al terminar la etapa en
    # curso (el hilo de recuperación, que no se puede interrumpir, termina en segundo plano;
    # CU-07, flujo 5e). Medir p95 en caliente y en frío frente al timeout de los clientes.
    # TODO(PT2/RNF-20): salida segura (PP-18): no reproducir descripcion_breve; separar cita,
    # interpretación y acción; sin órdenes al asistente ni peticiones de invocar herramientas;
    # sanear caracteres de control, HTML y enlaces en el texto y en structuredContent.
    raise NotImplementedError


def listar_normativas(state) -> dict[str, Any]:
    """Herramienta ``listar_normativas`` (RF-24): sin argumentos; delega en ``app.service``.

    ``structuredContent``: ``normativas`` (identificador, tipo de documento, páginas) y
    ``corpus_version``; PP-02 y CA-09 la comparan con ``GET /normativas``.
    """
    # TODO(PT2/RF-24): implementar sobre app.service.list_normativas.
    raise NotImplementedError


async def consultar_obligaciones(arguments: dict[str, Any], state) -> dict[str, Any]:
    """Herramienta ``consultar_obligaciones`` (RF-25).

    Argumentos ``normativa`` (identificador devuelto por ``listar_normativas``) y ``contexto``
    (máx. 500 caracteres). ``structuredContent``: los ``fragmentos`` de esa normativa
    (identificador, página, artículo y texto) en el orden del reordenador. No llama al
    modelo. Una normativa desconocida produce un resultado de error con la lista de las
    disponibles (PP-06).
    """
    # TODO(PT2/RF-25): implementar sobre app.service.consultar_obligaciones.
    raise NotImplementedError


def tool_error_result(codigo: str, mensaje: str) -> dict[str, Any]:
    """Resultado de herramienta con ``isError: true`` y ``resultType: "complete"``.

    Solo contenido de texto, que empieza por el código estable entre corchetes
    (``[TIEMPO_AGOTADO]``, ``[MODELO_NO_DISPONIBLE]``...) y sin ``structuredContent``, que
    debe ajustarse al esquema de salida (23-detalle, «Capa de servicio y traducción de
    errores»). El mensaje es estático o enumera campos del esquema; nunca repite texto libre
    del usuario.
    """
    # TODO(PT2/PP-04): implementar.
    raise NotImplementedError


def build_mcp_app(state):
    """Aplicación ASGI que ``app/main.py`` montará en ``MCP_PATH`` si ``settings.mcp_enabled``.

    Comparte proceso, caché, limitador y claves de API con la API REST (RF-22) y aplica
    ``app.mcp_guard`` antes de despachar cada petición.
    """
    # TODO(PT2/RF-22): implementar con el SDK oficial de Python (versión fijada en pyproject
    # tras la prueba de concepto). Montarlo en main.py solo si settings.mcp_enabled es
    # verdadero y hay API_KEYS (RNF-15: /mcp nunca queda abierto).
    raise NotImplementedError


def run_stdio() -> None:
    """Transporte stdio para uso local (RF-22: «y por stdio en local»).

    En stdio no hay capa HTTP: no se aplican ``Origin``, cabeceras ni clave, y solo quedan los
    errores de protocolo y de herramienta (21-analisis, «Errores de la interfaz MCP»).
    """
    # TODO(PT2/RF-22): implementar. La memoria no fija qué se ejecuta en local: 22-arquitectura
    # («Despliegue») y 30-manual-instalacion describen un puente que reenvía al servidor
    # remoto sin ejecutar el motor, mientras RF-22, la precondición de CU-07 y el riesgo de
    # latencia de 05-metodologia («ejecución local por stdio») suponen el servidor en local.
    # Decidir en la prueba de concepto y alinear la memoria.
    raise NotImplementedError
