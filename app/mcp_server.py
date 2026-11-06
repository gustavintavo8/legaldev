"""Servidor MCP de LegalDev (RF-22 a RF-25; RNF-15, RNF-16, RNF-18 a RNF-21; CU-07).

Expone el motor como tres herramientas de solo lectura sobre el SDK oficial de Python
(``mcp==2.3.0``, ``MCPServer``), en ``POST /mcp`` dentro del mismo proceso que la API REST.
Es una capa fina: las herramientas llaman a ``app.service`` (la misma caché, el mismo motor y
los mismos errores de dominio que ``POST /v1/analyze``) y solo traducen entradas y salidas.

Revisión objetivo: **2026-07-28** (sin estado, ``server/discover``, cabeceras
``MCP-Protocol-Version``/``Mcp-Method``/``Mcp-Name``, ``resultType`` y ``tools/list``
cacheable). El SDK sirve además la era del ``initialize`` (2025-11-25 y anteriores): la
primera petición de cada cliente decide la era, así que los asistentes que aún no hablan
2026-07-28 también funcionan (servidor de doble era; decisión de la prueba de concepto,
``docs/mcp/README.md``). LegalDev no usa MRTR, Sampling, Roots ni Logging: las tres
herramientas reciben todos sus datos como argumentos y todos sus resultados son ``complete``.

Reparto del trabajo en una petición HTTP (``CHECK_ORDER`` en ``app/mcp_guard.py``):

1. ``McpGuard`` (propia): ``Origin``, clave de API y límite por invocación.
2. SDK: cabeceras frente al cuerpo (-32020), versión (-32022), ``_meta`` (-32602), métodos
   inexistentes (-32601, 404) y validación JSON-RPC.
3. ``reject_unknown_tools`` (middleware del SDK): herramienta desconocida -> -32602.
4. Cada herramienta: valida sus argumentos con el modelo Pydantic en modo estricto y devuelve
   los fallos como resultado con ``isError`` (PP-04), nunca como error del protocolo.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import inspect
import json
import logging
from collections.abc import AsyncIterator, Mapping
from typing import Annotated, Any, Final, Literal

from mcp.server import MCPServer
from mcp.server.caching import CacheHint
from mcp.server.mcpserver import Context
from mcp.server.transport_security import TransportSecuritySettings
from mcp.shared.exceptions import MCPError
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, Field, ValidationError
from starlette.routing import Route

from app import config, service
from app.models import CitationStats, QuestionnaireInput
from app.service import ConsultaNormativa, FragmentoRef, ListadoNormativas, Via

logger = logging.getLogger(__name__)

PROTOCOL_VERSION: Final = "2026-07-28"
# Revisiones de la era sin estado que se atienden. La era del initialize (2025-11-25 y
# anteriores) la sirve el SDK aparte y no figura en server/discover.
SUPPORTED_VERSIONS: Final[tuple[str, ...]] = (PROTOCOL_VERSION,)
SERVER_NAME: Final = "legaldev"
MCP_PATH: Final = "/mcp"

# Códigos de error JSON-RPC (tab:ana-errores-mcp y tab:det-mcp-errores). El rango
# -32020..-32099 lo reserva la revisión 2026-07-28; los de cabeceras y versión los emite el SDK.
ERROR_HEADER_MISMATCH: Final = -32020
ERROR_MISSING_REQUIRED_CLIENT_CAPABILITY: Final = -32021
ERROR_UNSUPPORTED_PROTOCOL_VERSION: Final = -32022
ERROR_METHOD_NOT_FOUND: Final = -32601  # por HTTP, con 404
ERROR_INVALID_PARAMS: Final = -32602  # herramienta desconocida o tools/call mal formado
ERROR_INTERNAL: Final = -32603  # excepción no prevista, sin detalle interno

CacheScope = Literal["public", "private"]

# Orden determinista (la revisión lo recomienda para cachés y prompt caching del cliente).
TOOL_NAMES: Final[tuple[str, ...]] = (
    "analizar_proyecto",
    "listar_normativas",
    "consultar_obligaciones",
)

TOOL_TITLES: Final[dict[str, str]] = {
    "analizar_proyecto": "Analizar proyecto",
    "listar_normativas": "Listar normativas",
    "consultar_obligaciones": "Consultar obligaciones",
}

# Textos estáticos (RNF-15): nunca incorporan texto del usuario y los fija una prueba de
# instantánea (test_rnf15_tool_descriptions_snapshot), como test_system_prompt_snapshot fija
# el prompt. Contenido según tab:det-mcp-herramientas (23-detalle); la redacción es propia.
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

SERVER_INSTRUCTIONS: Final = (
    "LegalDev identifica la normativa española y europea que afecta a un proyecto software. "
    "Usa listar_normativas para ver los documentos indexados, consultar_obligaciones para "
    "leer los fragmentos de una normativa concreta y analizar_proyecto para el informe "
    "completo a partir del cuestionario. Si falta algún dato del cuestionario, pregúntalo al "
    "desarrollador en lugar de suponerlo. Orientativo; no es asesoramiento legal."
)

# Descripción del único campo libre (22-arquitectura, «Esquema de las herramientas», y
# 20-requisitos, restricción de minimización): una o dos frases, sin código, credenciales ni
# datos personales.
DESCRIPCION_BREVE_FIELD: Final = (
    "Funcionalidad del proyecto en una o dos frases. No incluyas código, credenciales, "
    "secretos ni datos personales."
)

# Descripción de cada campo del cuestionario en el inputSchema publicado; las preguntas son
# las del formulario de la web (legaldev-web, src/components/Demo.tsx).
CAMPO_DESCRIPCIONES: Final[dict[str, str]] = {
    "tipo_proyecto": "Tipo de proyecto.",
    "descripcion_breve": DESCRIPCION_BREVE_FIELD,
    "tiene_usuarios_registrados": "¿Tiene usuarios registrados?",
    "acceso_publico": "¿Es de acceso público?",
    "tipos_datos_personales": (
        'Tipos de datos personales que trata; ["ninguno"] si no trata ninguno.'
    ),
    "usuarios_menores": "¿Tiene usuarios menores de edad?",
    "usuarios_ue": "¿Tiene usuarios en la UE?",
    "transferencia_datos_terceros": "¿Transfiere datos a terceros?",
    "usa_ia": "¿Usa inteligencia artificial?",
    "tipo_ia": "Tipo de IA. Obligatorio si usa_ia es verdadero.",
    "usa_cookies": "¿Usa cookies?",
    "monetizacion": "Modelo de monetización, si lo hay.",
    "contenido_digital": "¿Publica contenido digital?",
    "ccaa": "Comunidad autónoma.",
    "es_empresa": "¿Es una empresa?",
    "colegiado": (
        "¿Ingeniero informático colegiado (CCII)? Solo para personas físicas; "
        "falso o nulo si es_empresa es verdadero."
    ),
}

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

# tools/list no depende de quién pregunta y solo cambia con una versión nueva o un índice
# nuevo (la enumeración de normativas): una hora, como la caché de respuestas. «public» es
# aceptable aunque /mcp exija clave: la lista no contiene nada propio del cliente.
TOOLS_LIST_TTL_MS: Final = 3_600_000
TOOLS_LIST_CACHE_SCOPE: Final[CacheScope] = "public"

# Intervalo de las notificaciones de progreso mientras se genera el informe (RNF-19): solo se
# envían si la petición trae progressToken, y reinician el tiempo de espera del cliente.
PROGRESS_INTERVAL_S: Final = 5.0

CONTEXTO_MAX: Final = 500

# Códigos estables al principio del texto de los resultados de error (tab:det-mcp-errores).
CODIGO_CUESTIONARIO_INVALIDO: Final = "CUESTIONARIO_INVALIDO"
CODIGO_ARGUMENTOS_INVALIDOS: Final = "ARGUMENTOS_INVALIDOS"
CODIGO_NORMATIVA_DESCONOCIDA: Final = "NORMATIVA_DESCONOCIDA"
CODIGO_TIEMPO_AGOTADO: Final = "TIEMPO_AGOTADO"
CODIGO_MODELO_NO_DISPONIBLE: Final = "MODELO_NO_DISPONIBLE"

AVISO: Final = (
    "Información orientativa; no constituye asesoramiento legal. Para decisiones con "
    "impacto legal, consulta con un abogado especializado en derecho digital."
)


# --------------------------------------------------------------------------------------
# Modelos de salida (outputSchema)
# --------------------------------------------------------------------------------------


class AnalisisProyecto(BaseModel):
    """``structuredContent`` de ``analizar_proyecto`` (tab:det-mcp-herramientas).

    Incluye el informe completo: hay clientes (Claude Code, por ejemplo) que, si la
    herramienta declara ``outputSchema``, solo pasan al modelo el contenido estructurado y no
    el texto, así que sin este campo el asistente vería las normativas y los fragmentos pero
    no las obligaciones ni las citas (prueba con Claude Code del 06/11/2026).
    """

    informe: str = Field(
        description=(
            "Informe en Markdown: por normativa, cita literal con su localización, "
            "interpretación y acciones de implementación; abre y cierra con el aviso."
        )
    )
    # El cuestionario validado, con los valores por defecto aplicados y sin descripcion_breve:
    # el resultado no refleja el texto libre del usuario (RNF-20, PP-18).
    cuestionario: dict[str, Any]
    normativas_detectadas: list[str]
    normativas_sin_desarrollar: list[str] = Field(
        default_factory=list,
        description=(
            "Detectadas a las que el informe no dedica sección: consúltalas con "
            "consultar_obligaciones."
        ),
    )
    fragmentos: list[FragmentoRef]  # sin texto, en el orden en que los recibe el modelo
    llm_model: str | None = None
    corpus_version: str
    citas: CitationStats | None = None
    # Sin fragmentos sobre el umbral: no es un error (CU-07, flujo 5c).
    sin_cobertura: bool = False
    aviso: str = AVISO


class ConsultaObligaciones(ConsultaNormativa):
    """``structuredContent`` de ``consultar_obligaciones``: los fragmentos y el aviso.

    El aviso va también aquí por la misma razón que el ``informe`` de ``analizar_proyecto``:
    hay clientes que solo pasan al modelo el contenido estructurado.
    """

    aviso: str = AVISO


class _ConsultaArgs(BaseModel):
    normativa: str
    contexto: str = Field(min_length=1, max_length=CONTEXTO_MAX)


# --------------------------------------------------------------------------------------
# Esquemas publicados
# --------------------------------------------------------------------------------------


def _inline_refs(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        if "$ref" in node:
            target = copy.deepcopy(defs[node["$ref"].rsplit("/", 1)[-1]])
            extra = {k: v for k, v in node.items() if k != "$ref"}
            return _inline_refs({**target, **extra}, defs)
        return {k: _inline_refs(v, defs) for k, v in node.items() if k != "$defs"}
    if isinstance(node, list):
        return [_inline_refs(item, defs) for item in node]
    return node


def published_input_schema() -> dict[str, Any]:
    """``inputSchema`` de ``analizar_proyecto``: ``QuestionnaireInput`` posprocesado.

    Con los ``$ref`` resueltos en línea (algunos clientes no los siguen), una descripción por
    campo y la regla ``usa_ia`` -> ``tipo_ia`` expresada con ``if``/``then`` (22-arquitectura,
    «Esquema de las herramientas»). El modelo Pydantic sigue siendo la fuente de verdad: la
    herramienta revalida con él, y PP-02 comprueba que el esquema y el modelo aceptan y
    rechazan los mismos cuestionarios.
    """
    raw = QuestionnaireInput.model_json_schema()
    schema = _inline_refs(raw, raw.get("$defs", {}))
    schema.pop("title", None)
    for name, prop in schema["properties"].items():
        prop.pop("title", None)
        prop["description"] = CAMPO_DESCRIPCIONES[name]
    schema["allOf"] = [
        {
            "if": {"properties": {"usa_ia": {"const": True}}, "required": ["usa_ia"]},
            "then": {
                "required": ["tipo_ia"],
                "properties": {"tipo_ia": {"not": {"type": "null"}}},
            },
        }
    ]
    return schema


def consultar_input_schema(normativas: list[str]) -> dict[str, Any]:
    """``inputSchema`` de ``consultar_obligaciones``: ``normativa`` enumera el índice."""
    return {
        "type": "object",
        "properties": {
            "normativa": {
                "type": "string",
                "enum": sorted(normativas),
                "description": "Identificador devuelto por listar_normativas (p. ej. «RGPD»).",
            },
            "contexto": {
                "type": "string",
                "minLength": 1,
                "maxLength": CONTEXTO_MAX,
                "description": (
                    "Situación concreta sobre la que se consulta, en una o dos frases "
                    "(p. ej. «registro de usuarios con email»). Sin datos personales."
                ),
            },
        },
        "required": ["normativa", "contexto"],
        "additionalProperties": False,
    }


LISTAR_INPUT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
}


# --------------------------------------------------------------------------------------
# Resultados
# --------------------------------------------------------------------------------------


def tool_error_result(codigo: str, mensaje: str) -> CallToolResult:
    """Resultado de herramienta con ``isError: true`` (``resultType`` lo añade el SDK).

    Solo texto, que empieza por el código estable entre corchetes y sin
    ``structuredContent`` (que tendría que ajustarse al esquema de salida). El mensaje es
    estático o enumera campos del esquema: nunca repite texto libre del usuario.
    """
    return CallToolResult(
        content=[TextContent(type="text", text=f"[{codigo}] {mensaje}")],
        is_error=True,
    )


def _structured_result(texto: str, estructurado: BaseModel) -> CallToolResult:
    """Texto legible seguido del JSON del contenido estructurado (sin repetir ``informe``,
    que ya es el texto), y el contenido estructurado completo."""
    data = estructurado.model_dump(mode="json")
    serializado = json.dumps(
        {k: v for k, v in data.items() if k != "informe"}, ensure_ascii=False, indent=2
    )
    return CallToolResult(
        content=[
            TextContent(type="text", text=f"{texto}\n\n```json\n{serializado}\n```")
        ],
        structured_content=data,
    )


_TIPO_IA_OBLIGATORIO: Final = "obligatorio cuando usa_ia es verdadero"


def _campos_invalidos(
    exc: ValidationError, argumentos: dict[str, Any] | None = None
) -> list[str]:
    """``campo: mensaje`` por error, sin ``input_value`` (no repite lo que envió el cliente).

    Pydantic no ejecuta el validador de modelo (``usa_ia`` -> ``tipo_ia``) si ya falla algún
    campo, así que esa regla se comprueba aquí también: el asistente recibe todos los fallos
    de una vez y no tiene que reintentar varias veces.
    """
    lineas = []
    campos: set[str] = set()
    for err in exc.errors(
        include_url=False, include_input=False, include_context=False
    ):
        campo = ".".join(str(p) for p in err["loc"])
        if (
            not campo
        ):  # validador de modelo: la única regla cruzada es usa_ia -> tipo_ia
            campo = "tipo_ia" if "tipo_ia" in err["msg"] else "cuestionario"
            mensaje = _TIPO_IA_OBLIGATORIO if campo == "tipo_ia" else err["msg"]
        else:
            mensaje = err["msg"]
        campos.add(campo.split(".")[0])
        lineas.append(f"- {campo}: {mensaje}")
    if (
        argumentos is not None
        and argumentos.get("usa_ia") is True
        and argumentos.get("tipo_ia") is None
        and "tipo_ia" not in campos
    ):
        lineas.append(f"- tipo_ia: {_TIPO_IA_OBLIGATORIO}")
    return lineas


def _raw_arguments(ctx: Context) -> dict[str, Any]:
    """Los argumentos tal como llegaron en ``tools/call``.

    No se usan los que el SDK pasa a la función: su ``pre_parse_json`` convierte en lista,
    objeto o nulo cualquier cadena que sea JSON válido (``'["email"]'``, ``"null"``) cuando
    el parámetro no está anotado como ``str``, y eso cambiaría el veredicto de la validación
    estricta y alteraría texto libre que casualmente parece JSON.
    """
    params = ctx.request_context.params or {}
    argumentos = params.get("arguments")
    return dict(argumentos) if isinstance(argumentos, Mapping) else {}


def _strict_validate(model: type[BaseModel], argumentos: dict[str, Any]) -> Any:
    # Modo estricto sobre JSON, como el esquema publicado: «true» no es un booleano y 1 no es
    # una cadena. Las entradas que llegan por MCP ya son JSON, así que no se pierde nada.
    return model.model_validate_json(json.dumps(argumentos), strict=True)


async def _with_progress(ctx: Context, coro) -> Any:
    """Espera ``coro`` emitiendo progreso cada ``PROGRESS_INTERVAL_S`` (RNF-19).

    ``report_progress`` no hace nada si la petición no trae progressToken. Si el cliente
    cancela (cierra el flujo), se cancela también la tarea; el hilo de recuperación, que no se
    puede interrumpir, termina en segundo plano (CU-07, flujo 5e).
    """
    task = asyncio.ensure_future(coro)
    pasos = 0
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=PROGRESS_INTERVAL_S)
            if done:
                return task.result()
            pasos += 1
            await ctx.report_progress(pasos, None, "Generando el informe")
    finally:
        if not task.done():
            task.cancel()


# --------------------------------------------------------------------------------------
# Servidor
# --------------------------------------------------------------------------------------


async def reject_unknown_tools(ctx, call_next):
    """Middleware del SDK: ``tools/call`` de una herramienta inexistente es un error del
    protocolo (-32602), no un resultado con ``isError`` (PP-04; tab:ana-errores-mcp)."""
    if ctx.method == "tools/call":
        params = ctx.params if isinstance(ctx.params, dict) else {}
        name = params.get("name")
        if name not in TOOL_NAMES:
            raise MCPError(
                ERROR_INVALID_PARAMS,
                "Herramienta desconocida",
                data={"disponibles": list(TOOL_NAMES)},
            )
    return await call_next(ctx)


def build_mcp_server(state, *, version: str = "0.0.0") -> MCPServer:
    """Servidor MCP con las tres herramientas sobre ``state`` (el ``app.state`` de FastAPI).

    Se construye en cada arranque, dentro del ``lifespan``, con el índice ya cargado: la
    enumeración de ``normativa`` sale de ``state.indexed_normativas``.
    """
    server = MCPServer(
        name=SERVER_NAME,
        title="LegalDev",
        version=version,
        instructions=SERVER_INSTRUCTIONS,
        cache_hints={
            "tools/list": CacheHint(
                ttl_ms=TOOLS_LIST_TTL_MS, scope=TOOLS_LIST_CACHE_SCOPE
            ),
        },
        middleware=[reject_unknown_tools],
    )

    # ---------------------------------------------------------------- analizar_proyecto

    async def analizar_proyecto(ctx: Context, **_campos: Any) -> Any:
        argumentos = _raw_arguments(ctx)
        try:
            cuestionario = _strict_validate(QuestionnaireInput, argumentos)
        except ValidationError as exc:
            return tool_error_result(
                CODIGO_CUESTIONARIO_INVALIDO,
                "El cuestionario no es válido. Corrige estos campos y vuelve a llamar a la "
                "herramienta:\n" + "\n".join(_campos_invalidos(exc, argumentos)),
            )
        await ctx.report_progress(0, None, "Recuperando la normativa aplicable")
        eco = cuestionario.model_dump(mode="json", exclude={"descripcion_breve"})
        try:
            analysis = await _with_progress(
                ctx, service.analyze(cuestionario, state, via=Via.MCP)
            )
        except service.NoCoverageError:
            indexadas = ", ".join(sorted(state.indexed_normativas))
            texto = (
                "Ninguna normativa del índice supera el umbral de relevancia para este "
                f"proyecto. Normativas indexadas: {indexadas}. {AVISO}"
            )
            resultado = AnalisisProyecto(
                informe=texto,
                cuestionario=eco,
                normativas_detectadas=[],
                fragmentos=[],
                corpus_version=state.corpus_version,
                sin_cobertura=True,
            )
            return _structured_result(texto, resultado)
        except service.RetrievalTimeoutError:
            return tool_error_result(
                CODIGO_TIEMPO_AGOTADO,
                "La búsqueda en el índice ha tardado demasiado. Vuelve a intentarlo.",
            )
        except service.LLMUnavailableError:
            return tool_error_result(
                CODIGO_MODELO_NO_DISPONIBLE,
                "El modelo de lenguaje no está disponible. Vuelve a intentarlo más tarde.",
            )
        response = analysis.result.response
        resultado = AnalisisProyecto(
            informe=response.respuesta_completa,
            cuestionario=eco,
            normativas_detectadas=response.normativas_detectadas,
            normativas_sin_desarrollar=analysis.result.normativas_sin_desarrollar,
            fragmentos=analysis.result.fragmentos,
            llm_model=response.llm_model,
            corpus_version=response.corpus_version,
            citas=response.citas,
        )
        return _structured_result(response.respuesta_completa, resultado)

    _set_signature(
        analizar_proyecto,
        list(QuestionnaireInput.model_fields),
        Annotated[CallToolResult, AnalisisProyecto],
    )
    _register(server, "analizar_proyecto", analizar_proyecto, published_input_schema())

    # ---------------------------------------------------------------- listar_normativas

    async def listar_normativas() -> ListadoNormativas:
        return await asyncio.to_thread(service.list_normativas, state)

    _register(server, "listar_normativas", listar_normativas, LISTAR_INPUT_SCHEMA)

    # ----------------------------------------------------------- consultar_obligaciones

    async def consultar_obligaciones(ctx: Context, **_campos: Any) -> Any:
        argumentos = _raw_arguments(ctx)
        try:
            args = _strict_validate(_ConsultaArgs, argumentos)
        except ValidationError as exc:
            return tool_error_result(
                CODIGO_ARGUMENTOS_INVALIDOS,
                "Argumentos no válidos:\n" + "\n".join(_campos_invalidos(exc)),
            )
        try:
            consulta = await service.consultar_obligaciones(
                args.normativa, args.contexto, state, via=Via.MCP
            )
        except service.UnknownNormativaError as exc:
            return tool_error_result(
                CODIGO_NORMATIVA_DESCONOCIDA,
                "Esa normativa no está en el índice. Usa uno de estos identificadores: "
                + ", ".join(exc.disponibles),
            )
        except service.RetrievalTimeoutError:
            return tool_error_result(
                CODIGO_TIEMPO_AGOTADO,
                "La búsqueda en el índice ha tardado demasiado. Vuelve a intentarlo.",
            )
        lineas = [
            f"Fragmentos de {consulta.normativa} (orden de pertinencia). {AVISO}",
        ]
        for f in consulta.fragmentos:
            donde = f"p. {f.pagina}" + (f", art. {f.articulo}" if f.articulo else "")
            lineas.append(f"\n[{f.identificador}] {f.normativa}, {donde}\n{f.texto}")
        return _structured_result(
            "\n".join(lineas), ConsultaObligaciones(**consulta.model_dump())
        )

    _set_signature(
        consultar_obligaciones,
        ["normativa", "contexto"],
        Annotated[CallToolResult, ConsultaObligaciones],
    )
    _register(
        server,
        "consultar_obligaciones",
        consultar_obligaciones,
        consultar_input_schema(list(state.indexed_normativas)),
    )
    return server


def _set_signature(fn, campos: list[str], retorno: Any) -> None:
    """Firma explícita para una herramienta que recibe ``**campos``.

    El SDK deriva de la firma el modelo de argumentos. Todos los campos son ``Any`` con
    valor ``None``, de modo que el SDK no rechaza nada; la herramienta ignora los valores que
    recibe y valida los argumentos en crudo (``_raw_arguments``) con el modelo Pydantic, en
    un único sitio y con mensajes que no repiten la entrada. El ``inputSchema`` publicado se
    sustituye después por el posprocesado (``_register``).
    """
    params = []
    if "ctx" in inspect.signature(fn).parameters:
        params.append(
            inspect.Parameter("ctx", inspect.Parameter.KEYWORD_ONLY, annotation=Context)
        )
    params += [
        inspect.Parameter(
            n, inspect.Parameter.KEYWORD_ONLY, annotation=Any, default=None
        )
        for n in campos
    ]
    fn.__signature__ = inspect.Signature(params, return_annotation=retorno)
    fn.__annotations__ = {p.name: p.annotation for p in params} | {"return": retorno}


def _register(server: MCPServer, name: str, fn, input_schema: dict[str, Any]) -> None:
    server.add_tool(
        fn,
        name=name,
        title=TOOL_TITLES[name],
        description=TOOL_DESCRIPTIONS[name],
        annotations=ToolAnnotations.model_validate(TOOL_ANNOTATIONS[name]),
    )
    # El SDK no ofrece otra forma de publicar un esquema distinto del derivado de la firma.
    server._tool_manager.get_tool(name).parameters = input_schema


# --------------------------------------------------------------------------------------
# Transporte HTTP
# --------------------------------------------------------------------------------------


def mount(app) -> None:
    """Añade ``POST /mcp`` a la aplicación FastAPI (ruta exacta: sin redirección 307).

    Solo ``POST``: GET (el flujo SSE de la era antigua, que quedaría abierto) y DELETE (fin de
    sesión, que no existe sin estado) responden 405 (PP-16). La guarda va delante del SDK.
    """
    from app.mcp_guard import McpGuard

    if is_mounted(app):
        return
    app.router.routes.append(
        Route(MCP_PATH, endpoint=McpGuard(_dispatch), methods=["POST"], name="mcp")
    )


def mount_if_enabled(app) -> bool:
    """Monta ``/mcp`` si ``MCP_ENABLED`` y hay claves (``MCP_API_KEYS`` o ``API_KEYS``); sin
    claves, avisa y no lo monta.

    RNF-15: ``/mcp`` exige siempre clave de API, así que nunca queda abierto.
    """
    if not config.settings.mcp_enabled:
        return False
    if not config.settings.mcp_key_set:
        logger.warning(
            "MCP_ENABLED=true sin MCP_API_KEYS ni API_KEYS: /mcp no se monta (RNF-15)"
        )
        return False
    mount(app)
    return True


def unmount(app) -> None:
    app.router.routes[:] = [
        r for r in app.router.routes if getattr(r, "path", None) != MCP_PATH
    ]


def is_mounted(app) -> bool:
    return any(getattr(r, "path", None) == MCP_PATH for r in app.router.routes)


async def _dispatch(scope, receive, send) -> None:
    manager = getattr(scope["app"].state, "mcp_session_manager", None)
    if manager is None:  # montado pero el lifespan no lo ha arrancado
        raise RuntimeError("Servidor MCP no iniciado")
    await manager.handle_request(scope, receive, send)


@contextlib.asynccontextmanager
async def serve(app, *, version: str) -> AsyncIterator[None]:
    """Arranca el servidor MCP en el ``lifespan`` si ``/mcp`` está montado.

    El gestor de sesiones del SDK solo puede ejecutarse una vez por instancia, así que se
    crea uno nuevo en cada arranque. Sin estado (cada POST es independiente) y con la
    comprobación de ``Host``/``Origin`` del SDK desactivada: la de ``Origin`` la hace
    ``McpGuard`` con su propia lista, y la de ``Host`` exigiría enumerar los dominios del
    despliegue (``docs/mcp/README.md``).
    """
    if not is_mounted(app):
        yield
        return
    server = build_mcp_server(app.state, version=version)
    server.streamable_http_app(
        streamable_http_path=MCP_PATH,
        stateless_http=True,
        json_response=False,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        ),
    )
    app.state.mcp_server = server
    async with server.session_manager.run():
        app.state.mcp_session_manager = server.session_manager
        logger.info("MCP server ready at %s (protocol %s)", MCP_PATH, PROTOCOL_VERSION)
        try:
            yield
        finally:
            app.state.mcp_session_manager = None
            app.state.mcp_server = None


def run_stdio() -> None:
    """Transporte stdio para uso local (RF-22: «y por stdio en local»).

    En stdio no hay capa HTTP: no se aplican ``Origin``, cabeceras ni clave, y solo quedan los
    errores de protocolo y de herramienta (21-analisis, «Errores de la interfaz MCP»).
    """
    # TODO(PT2/RF-22): aplazado en la prueba de concepto. La memoria no fija qué se ejecuta en
    # local: 22-arquitectura («Despliegue») y 30-manual-instalacion describen un puente que
    # reenvía al servidor remoto sin ejecutar el motor, mientras RF-22, la precondición de
    # CU-07 y el riesgo de latencia de 05-metodologia («ejecución local por stdio») suponen el
    # servidor en local. Con build_mcp_server bastaría server.run("stdio") tras cargar el
    # índice como el lifespan; decidir y alinear la memoria.
    raise NotImplementedError
