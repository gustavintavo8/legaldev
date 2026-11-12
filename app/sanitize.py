"""Saneado de la salida del modelo (RNF-20; PP-18; ``docs/mcp/README.md``, «Salida segura»).

El informe que redacta el modelo llega a un navegador (la web lo pinta como Markdown), a
integradores de la API y a asistentes con herramientas (por MCP). Quien controla parte del
texto que lee el modelo (la descripción libre del cuestionario o, si alguien lo envenenara, un
fragmento del índice) puede pedirle que escriba algo que no es un informe, sino algo que se
ejecuta al mostrarlo o al leerlo: una imagen que se descarga sola con datos en la URL, un
enlace cuyo destino no se ve, HTML, caracteres invisibles con órdenes escondidas o un bloque
que imita una llamada a una herramienta. ``sanear`` los retira del texto del modelo antes de
verificar las citas y de guardar el resultado en la caché común, así que REST y MCP reciben lo
mismo. El prompt no cambia (decisión D-1).

Qué hace, en este orden:

1. **Caracteres.** Normaliza los saltos de línea (CRLF y CR sueltos pasan a LF, como hace
   marked al pintar) y quita el guion blando, que es invisible y partía las palabras clave
   de los pasos 2 y 3 (``citations.normalize`` también lo quita, así que las citas no
   cambian). Ninguna de las dos cosas cuenta como saneado. Quita las secuencias de escape
   ANSI y los caracteres de control (salvo el tabulador y el salto de línea), los de formato
   invisibles (ancho cero, dirección bidi, etiquetas Unicode) y los selectores de variación,
   salvo uno suelto detrás de un carácter visible (el de los emojis).
2. **Bloques que imitan llamadas a herramientas**: etiquetas de llamada al estilo XML, el
   formato ``<function=…>`` de Llama, los tokens especiales ``<|…|>``, el formato de gpt-oss
   (``to=functions.…``), las marcas ``[TOOL_CALLS]``, ``[ARGS]`` y similares y los objetos JSON
   con forma de llamada (nombre y argumentos, o ``tools/call``, también con las claves
   escritas con escapes ``\\u…``), estén o no en un bloque de código; y los bloques de código
   que se anuncian como llamada a herramienta. El cierre de un objeto JSON se busca dentro de
   su párrafo.
3. **HTML en bruto**: comentarios, declaraciones, bloques ``script``/``style``/``iframe``/
   ``svg``… con su contenido y las etiquetas de elementos HTML (todas las que deja DOMPurify)
   o con atributos ``=``. Una etiqueta sin atributos que ocupa sola un código en línea
   (`` `<script>` ``) se queda en su nombre. Las etiquetas desconocidas sin atributos
   (``<nombre de la empresa>``) son inertes y se dejan.
4. **Markdown**: todas las imágenes; los enlaces y definiciones de referencia cuyo destino
   no sea ``http(s)`` a un dominio oficial del corpus (``DOMINIOS_OFICIALES``), de los que
   queda el texto, y los autoenlaces no oficiales, que pasan a código. Las expresiones siguen
   la gramática de marked (el visor de la web): el destino y el título se separan con
   espacios, tabuladores o saltos de línea, no con otros espacios Unicode. ``[4](en
   adelante, RGPD)``, que está en el corpus, no es un enlace (el destino tiene espacios) y no
   se toca. Las expresiones reconocen un nivel de corchetes y de paréntesis anidados. Detrás
   van tres reglas que no dependen de reconocer la construcción entera: todo «![» que quede
   pierde el «!»; de toda «](» se lee el destino, con paréntesis a cualquier profundidad, y
   se quita si no es oficial; y de todo «]:» cuya etiqueta empiece una línea (detrás de
   marcas de lista o de cita) y vaya seguido de algo que puede llevar a otro sitio
   (``_parece_url``) se quita ese destino si no es oficial. Así caen también los corchetes
   anidados a más niveles y las definiciones dentro de listas, con sangría o con la etiqueta
   escapada o partida en dos líneas.
5. **URL sueltas** (las que un visor convierte en enlace: ``http(s)://``, ``ftp://`` y
   ``www.``, vaya detrás de lo que vaya): se quedan las de un dominio oficial y las que
   aparecen en los fragmentos que recibió el modelo con el mismo host, que se escribieron
   antes de la petición y no pueden llevar datos del usuario; las demás se muestran como
   código, sin enlace. Se juzga la URL entera como la lee marked, también lo que va detrás de
   un «|» o de un acento grave, y se corta donde marked la daría por terminada (al cerrar un
   autoenlace, un enlace, un énfasis o una referencia, o en un «(» sin cerrar), porque detrás
   puede empezar otra. El corpus tiene URL de más de 50 dominios no oficiales, así
   que quitarlas todas rompería citas literales. No se tocan las URL que están en código para
   cualquier lectura: los bloques con valla que cierran igual para marked y para CommonMark y
   el código en línea cuyos acentos solo se pueden emparejar de una manera (``_codigo_en_linea``).
6. **Bloques de código sin cerrar**: se cierran, para que no se traguen las secciones que
   añade el código ni, por MCP, el JSON del resultado. Un bloque acaba donde lo cierra marked
   o CommonMark, y esa línea se reescribe para que cierre en los dos (``_vallas``, que corre
   también en las pasadas).

Los pasos 2 a 4 se repiten hasta que el texto no cambia, porque quitar algo puede formar otra
construcción (``<scr<b>ipt>``). Las tres reglas de piezas sueltas del paso 4 se aplican en la
primera pasada y cuando lo demás ya no cambia nada, no en cada pasada.

Coste: ninguna búsqueda vuelve a recorrer el texto por cada construcción. Los cierres (de un
comentario, de un bloque ``script``, de una etiqueta de llamada) se buscan una vez y, si no
hay, no se vuelven a buscar; las expresiones de los enlaces usan cuantificadores posesivos.
``rag.run_pipeline_detailed`` lo llama en un hilo, pero el hilo no basta: una llamada a una
expresión regular no suelta el intérprete (GIL) y el bucle de eventos espera lo que dure. Por
eso importa que cada una sea lineal. Tiempos medidos en ``tests/test_sanitize.py`` y en
``docs/mcp/README.md``.

Citas: ``sanear`` deja igual (comparando con ``citations.normalize``) los 13.756 fragmentos
del índice real, así que una cita literal de un fragmento real no deja de verificarse. Una
cita de un fragmento envenenado que traiga marcado neutralizado sí deja de verificarse, y es
lo correcto.
"""

from __future__ import annotations

import html
import re
import unicodedata
from bisect import bisect_left, bisect_right
from collections import Counter
from collections.abc import Callable, Iterable
from functools import cache
from typing import Final
from urllib.parse import urlsplit

from app.citations import normalize
from app.models import SaneadoStats

# Dominios de las fuentes oficiales del corpus (docs/CORPUS_SOURCES.md), con sus subdominios.
# data.europa.eu es el de los identificadores ELI de la Oficina de Publicaciones, que citan
# los propios textos de EUR-Lex; sedeaepd.gob.es, la sede electrónica de la AEPD.
DOMINIOS_OFICIALES: Final[tuple[str, ...]] = (
    "boe.es",
    "aepd.es",
    "sedeaepd.gob.es",
    "ccii.es",
    "eur-lex.europa.eu",
    "data.europa.eu",
)

IMAGEN_RETIRADA: Final = "(imagen retirada)"
BLOQUE_RETIRADO: Final = "(bloque retirado)"

# Límite de pasadas de los pasos 2 a 4; si el texto sigue cambiando (anidamiento
# adversario), se neutralizan a lo bruto los «<» y las «](» que queden.
MAX_PASADAS: Final = 20

# ------------------------------------------------------------------------- 1. caracteres

_ANSI_RE = re.compile(
    r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)?|[@-Z\\-_])"
)
_CONTROL: Final = frozenset(
    chr(c) for c in (*range(0x00, 0x20), *range(0x7F, 0xA0))
) - {"\t", "\n"}
# El guion blando está en 243 fragmentos de la Directiva ePrivacy, pero es invisible y con él
# «function_calls» o «TOOL_CALLS» con uno dentro no casaban con ninguna regla. Se quita sin
# contarlo.
_GUION_BLANDO: Final = "\u00ad"
_SELECTORES_EMOJI: Final = frozenset("\ufe0e\ufe0f")


def _es_selector(ch: str) -> bool:
    o = ord(ch)
    return 0xFE00 <= o <= 0xFE0F or 0xE0100 <= o <= 0xE01EF or 0x180B <= o <= 0x180F


def _es_invisible(ch: str) -> bool:
    return unicodedata.category(ch) == "Cf"


def _caracteres(texto: str, c: Counter) -> str:
    def _ansi(_m: re.Match) -> str:
        c["caracteres_control"] += 1
        return ""

    # marked normaliza igual antes de pintar. Sin esto, «```\r» no cerraba un bloque para el
    # saneado y sí para el visor: la URL de detrás quedaba como enlace y la valla que se
    # añadía al final metía en un bloque de código las secciones del informe.
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    texto = texto.replace(_GUION_BLANDO, "")
    texto = _ANSI_RE.sub(_ansi, texto)
    salida: list[str] = []
    n = len(texto)
    for i, ch in enumerate(texto):
        if ch in _CONTROL:
            c["caracteres_control"] += 1
            continue
        if _es_selector(ch):
            anterior = texto[i - 1] if i else ""
            siguiente = texto[i + 1] if i + 1 < n else ""
            if (
                ch in _SELECTORES_EMOJI
                and anterior
                and not anterior.isspace()
                and not _es_selector(anterior)
                and not _es_invisible(anterior)
                and not (siguiente and _es_selector(siguiente))
            ):
                salida.append(ch)
            else:
                c["caracteres_invisibles"] += 1
            continue
        if _es_invisible(ch):
            c["caracteres_invisibles"] += 1
            continue
        salida.append(ch)
    return "".join(salida)


# ------------------------------------------------- búsquedas de cierre en tiempo lineal


def _buscador(texto: str, aguja: str | re.Pattern) -> Callable[[int], int]:
    """Posición de la siguiente ``aguja`` (un texto o una expresión de un carácter) desde
    ``i``, o -1, sin volver a recorrer lo ya recorrido: si la última búsqueda empezó en
    ``desde`` y encontró ``pos``, para todo ``i`` entre los dos la respuesta es la misma. Sin
    esto, mil aperturas seguidas sin «>» recorrían mil veces el resto."""
    ultima = [-1, -1]

    def buscar(i: int) -> int:
        desde, pos = ultima
        if desde != -1 and desde <= i and (pos == -1 or i <= pos):
            return pos
        if isinstance(aguja, str):
            pos = texto.find(aguja, i)
        else:
            m = aguja.search(texto, i)
            pos = m.start() if m else -1
        ultima[0], ultima[1] = i, pos
        return pos

    return buscar


def _quitar_entre(
    texto: str, apertura: re.Pattern, cierre: str, c: Counter, clave: str
) -> str:
    """Quita cada «apertura … cierre» (el primer cierre detrás), como ``apertura.*?cierre``
    con ``re.S`` pero en tiempo lineal: si una apertura no tiene cierre detrás, tampoco lo
    tienen las siguientes y se para. La expresión, con 32.000 caracteres de «<?», tardaba
    2,2 s (con 200.000, más de un minuto), medido el 12/11/2026."""
    salida: list[str] = []
    pos = 0
    while m := apertura.search(texto, pos):
        j = texto.find(cierre, m.end())
        if j == -1:
            break
        salida.append(texto[pos : m.start()])
        c[clave] += 1
        pos = j + len(cierre)
    salida.append(texto[pos:])
    return "".join(salida)


@cache
def _cierre_de(nombre: str) -> re.Pattern:
    return re.compile(r"<\s*/\s*" + re.escape(nombre) + r"\s*>", re.I)


def _quitar_bloques(
    texto: str,
    apertura: re.Pattern,
    cierre: Callable[[re.Match], re.Pattern],
    c: Counter,
    clave: str,
    sustituto: str,
    *,
    hasta_mayor: bool,
    sin_cierre_hasta_parrafo: bool,
) -> str:
    """Quita cada bloque «apertura … cierre» (el primer cierre detrás), en tiempo lineal.

    Con ``hasta_mayor``, la etiqueta de apertura acaba en el siguiente «>» (``[^>]*>``). El
    cierre de cada nombre se busca una vez por bloque y, si no hay, no se vuelve a buscar.
    Una apertura sin cierre se queda (la recogen otras reglas) o, con
    ``sin_cierre_hasta_parrafo``, se quita hasta el final de su párrafo.
    """
    mayor = _buscador(texto, ">")
    sin_cierre: set[re.Pattern] = set()
    salida: list[str] = []
    pos = i = 0
    while m := apertura.search(texto, i):
        fin_etiqueta = m.end()
        if hasta_mayor:
            gt = mayor(m.end())
            if gt == -1:
                break  # ninguna apertura de aquí en adelante se cierra con «>»
            fin_etiqueta = gt + 1
        patron = cierre(m)
        fin = -1
        if patron not in sin_cierre:
            mc = patron.search(texto, fin_etiqueta)
            if mc:
                fin = mc.end()
            else:
                sin_cierre.add(patron)
        if fin == -1:
            if not sin_cierre_hasta_parrafo:
                i = m.end()
                continue
            fin = _fin_parrafo(texto, fin_etiqueta)
        salida.append(texto[pos : m.start()])
        salida.append(sustituto)
        c[clave] += 1
        pos = i = fin
    salida.append(texto[pos:])
    return "".join(salida)


# --------------------------------------------------------- 2. llamadas a herramientas

# Etiquetas de llamada al estilo XML (Anthropic, Hermes/Qwen, Cline…), con prefijo de
# espacio de nombres opcional («ns:invoke»).
_ETIQUETAS_HERRAMIENTA: Final[tuple[str, ...]] = (
    "function_calls",
    "function_call",
    "function_results",
    "invoke",
    "parameter",
    "tool_calls",
    "tool_call",
    "tool_use",
    "tool_code",
    "tool_request",
    "tool_response",
    "tool_result",
    "use_mcp_tool",
    "use_tool",
    "execute_command",
)
_NOMBRE_HERRAMIENTA = (
    r"(?:[\w-]+:)?(?:" + "|".join(map(re.escape, _ETIQUETAS_HERRAMIENTA)) + r")"
)
# Apertura «<nombre …>»: sin cierre, se quita hasta el final del párrafo.
_APERTURA_HERRAMIENTA_RE = re.compile(r"<\s*(" + _NOMBRE_HERRAMIENTA + r")\b", re.I)
_CIERRE_HERRAMIENTA_RE = re.compile(r"<\s*/\s*" + _NOMBRE_HERRAMIENTA + r"\s*>", re.I)
# Formato de Llama 3.1/3.2 para herramientas propias: <function=nombre>{…}</function>.
_APERTURA_FUNCION_RE = re.compile(r"<\s*function\s*=\s*[\w.-]+\s*>", re.I)
_CIERRE_FUNCION_RE = re.compile(r"<\s*/\s*function\s*>", re.I)
# Tokens especiales de las plantillas de chat (<|im_start|>, <|call|>, <\uff5ctool▁calls▁begin\uff5c>).
_TOKEN_ESPECIAL_RE = re.compile(r"<[|\uff5c][^<>\n]{0,60}?[|\uff5c]>")
# Formato harmony de gpt-oss: «to=functions.bash … {…}» hasta el final de la línea.
_HARMONY_RE = re.compile(
    r"\bto=(?:functions|browser|python|container|repo_browser)\b[^\n]*", re.I
)
# Marcas de llamada de Mistral y similares; se quita también lo que las sigue: el JSON, otra
# marca y, delante de [ARGS] o [CALL_ID], el nombre («[TOOL_CALLS]borrar[ARGS]{…}», v11).
_MARCA_HERRAMIENTA_RE = re.compile(
    r"\[/?(?:TOOL_CALLS?|TOOL_REQUEST|TOOL_RESULTS?|AVAILABLE_TOOLS|ARGS|CALL_ID)\]",
    re.I,
)
_NOMBRE_TRAS_MARCA_RE = re.compile(r"[\w.-]{1,64}[ \t]*(?=\[(?:ARGS|CALL_ID)\])", re.I)
# Un objeto JSON que empieza por una clave.
_INICIO_OBJETO_RE = re.compile(r'\{\s*"')
# Forma de llamada a herramienta dentro de un objeto JSON: un nombre y unos argumentos, en
# cualquier orden (dos búsquedas independientes, lineales; una con «(?=.*…)» recorría el
# resto del texto por cada clave), o una de las claves o tipos propios de una llamada.
_CLAVE_NOMBRE_RE = re.compile(
    r'"(?:name|tool|tool_name|function|recipient_name)"\s*:\s*"[^"]*"'
)
_CLAVE_ARGUMENTOS_RE = re.compile(r'"(?:arguments|parameters|input|args|params)"\s*:')
_LLAMADA_JSON_RES: Final = (
    re.compile(r'"method"\s*:\s*"tools/call"'),
    re.compile(r'"(?:tool_calls|function_call|tool_use)"\s*:'),
    re.compile(r'"type"\s*:\s*"(?:tool_use|function|function_call|tool_call)"'),
)
# Escapes de las cadenas JSON que pueden escribir una letra o la barra de «tools/call».
_ESCAPE_UNICODE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")
# Palabras de la línea de apertura de un bloque de código que lo anuncian como llamada.
_INFO_HERRAMIENTA: Final = frozenset(
    {
        "tool_call",
        "tool_calls",
        "tool_code",
        "tool_use",
        "function_call",
        "function_calls",
        "tool",
        "tools",
    }
)


def _fin_json(texto: str, i: int, tope: int) -> int:
    """Índice siguiente al objeto o lista JSON que empieza en ``texto[i]``, o -1 si no se
    cierra antes de ``tope``. Tiene en cuenta las cadenas y sus escapes."""
    pila = 0
    en_cadena = escape = False
    for j in range(i, tope):
        ch = texto[j]
        if en_cadena:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                en_cadena = False
        elif ch == '"':
            en_cadena = True
        elif ch in "{[":
            pila += 1
        elif ch in "}]":
            pila -= 1
            if pila == 0:
                return j + 1
    return -1


_FIN_PARRAFO_RE = re.compile(r"\n[ \t]*\n")
_ESPACIOS_RE = re.compile(r"\s*")


def _fin_parrafo(texto: str, i: int) -> int:
    m = _FIN_PARRAFO_RE.search(texto, i)
    return m.start() if m else len(texto)


def _decodificar_escapes(fragmento: str) -> str:
    """El fragmento con los escapes ``\\uXXXX`` y ``\\/`` de JSON resueltos. Con ellos,
    ``"na\\u006de"`` es la clave ``name`` para cualquier analizador de JSON, y las reglas, que
    buscan el texto literal, no la veían."""
    if "\\" not in fragmento:
        return fragmento
    fragmento = _ESCAPE_UNICODE_RE.sub(lambda m: chr(int(m.group(1), 16)), fragmento)
    return fragmento.replace("\\/", "/")


def _es_llamada(fragmento: str) -> bool:
    fragmento = _decodificar_escapes(fragmento)
    if _CLAVE_NOMBRE_RE.search(fragmento) and _CLAVE_ARGUMENTOS_RE.search(fragmento):
        return True
    return any(r.search(fragmento) for r in _LLAMADA_JSON_RES)


def _objetos_llamada(texto: str, c: Counter) -> str:
    """Quita los objetos JSON de primer nivel con forma de llamada a herramienta.

    Solo mira los de primer nivel (el objeto exterior entero, con los anidados dentro). El
    cierre se busca dentro del párrafo en que empieza el objeto: si no se cierra ahí (sin
    cerrar, o con una línea en blanco dentro), el objeto llega hasta el final del párrafo.
    Así cada carácter se recorre una vez. Buscando el cierre en todo el texto, cada «{"» sin
    cerrar recorría el resto: 16.000 caracteres de «{"» y líneas en blanco tardaban 2,58 s
    (0,02 s ahora), medido el 12/11/2026 en el portátil de desarrollo.
    """
    salida: list[str] = []
    pos = 0
    tope = -1
    while True:
        m = _INICIO_OBJETO_RE.search(texto, pos)
        if not m:
            break
        inicio = m.start()
        if inicio >= tope:  # el final del párrafo se calcula una vez por párrafo
            tope = _fin_parrafo(texto, inicio)
        fin = _fin_json(texto, inicio, tope)
        if fin == -1:
            fin = tope
        if _es_llamada(texto[inicio:fin]):
            salida.append(texto[pos:inicio])
            salida.append(BLOQUE_RETIRADO)
            c["bloques_herramienta"] += 1
        else:
            salida.append(texto[pos:fin])
        pos = fin
    salida.append(texto[pos:])
    return "".join(salida)


def _marcas(texto: str, c: Counter) -> str:
    """Quita las marcas de llamada y lo que las sigue (ver _MARCA_HERRAMIENTA_RE). El final
    del párrafo se calcula una vez por párrafo, como en _objetos_llamada: calcularlo por
    marca hacía cuadrático el coste con miles de «[TOOL_CALLS]{}» en un párrafo."""
    salida: list[str] = []
    pos = 0
    tope = -1
    for m in _MARCA_HERRAMIENTA_RE.finditer(texto):
        if m.start() < pos:
            continue
        fin = m.end()
        while True:
            k = _ESPACIOS_RE.match(texto, fin).end()
            if k >= len(texto):
                break
            if k >= tope:
                tope = _fin_parrafo(texto, k)
            if otra := _MARCA_HERRAMIENTA_RE.match(texto, k):
                fin = otra.end()
                continue
            if nombre := _NOMBRE_TRAS_MARCA_RE.match(texto, k):
                fin = nombre.end()
                continue
            if texto[k] in "[{":
                cierre = _fin_json(texto, k, tope)
                fin = cierre if cierre != -1 else tope
            break
        salida.append(texto[pos : m.start()])
        salida.append(BLOQUE_RETIRADO)
        c["bloques_herramienta"] += 1
        pos = fin
    salida.append(texto[pos:])
    return "".join(salida)


def _herramientas(texto: str, c: Counter) -> str:
    def _retirar(_m: re.Match) -> str:
        c["bloques_herramienta"] += 1
        return BLOQUE_RETIRADO

    def _quitar(_m: re.Match) -> str:
        c["bloques_herramienta"] += 1
        return ""

    texto = _quitar_bloques(
        texto,
        _APERTURA_HERRAMIENTA_RE,
        lambda m: _cierre_de(m.group(1).lower()),
        c,
        "bloques_herramienta",
        BLOQUE_RETIRADO,
        hasta_mayor=True,
        sin_cierre_hasta_parrafo=True,
    )
    texto = _quitar_bloques(
        texto,
        _APERTURA_FUNCION_RE,
        lambda _m: _CIERRE_FUNCION_RE,
        c,
        "bloques_herramienta",
        BLOQUE_RETIRADO,
        hasta_mayor=False,
        sin_cierre_hasta_parrafo=True,
    )
    texto = _CIERRE_HERRAMIENTA_RE.sub(_quitar, texto)
    texto = _HARMONY_RE.sub(_retirar, texto)
    texto = _TOKEN_ESPECIAL_RE.sub(_quitar, texto)
    texto = _marcas(texto, c)
    return _objetos_llamada(texto, c)


# ------------------------------------------------------------------- bloques de código

_VALLA_RE = re.compile(r"^( {0,3})(`{3,}|~{3,})(.*)$")
_CIERRE_VALLA_COMMONMARK_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*$")


def _apertura_valla(linea: str) -> re.Match | None:
    """Línea que abre un bloque de código con valla, con la regla de CommonMark (y de
    marked): una valla de acentos graves no puede llevar un acento grave en la información
    (```` ```x` ```` es texto). La usan ``_vallas`` y ``_tramos_de_valla``, para que el
    saneado no tome por código lo que el visor pinta como texto."""
    m = _VALLA_RE.match(linea)
    if m and m.group(2)[0] == "`" and "`" in m.group(3):
        return None
    return m


def _cierra_valla(linea: str, valla: str) -> bool:
    """¿Cierra ``linea`` el bloque abierto con ``valla``, para marked? Su regla es
    ``' {0,3}' + valla + '[~`]* *$'``: la valla de apertura exacta y detrás cualquier mezcla
    de «~» y «`» y espacios (no tabuladores). Así «```~» cierra un bloque abierto con «```»."""
    sin_sangria = linea.lstrip(" ")
    if len(linea) - len(sin_sangria) > 3 or not sin_sangria.startswith(valla):
        return False
    return all(ch in "~`" for ch in sin_sangria[len(valla) :].rstrip(" "))


def _cierra_valla_commonmark(linea: str, valla: str) -> bool:
    """¿Cierra ``linea`` el bloque, para CommonMark? Mismo carácter, al menos tantos, y
    detrás solo espacios o tabuladores."""
    mc = _CIERRE_VALLA_COMMONMARK_RE.match(linea)
    return bool(mc and mc.group(1)[0] == valla[0] and len(mc.group(1)) >= len(valla))


def _cierra_alguna(linea: str, valla: str) -> bool:
    return _cierra_valla(linea, valla) or _cierra_valla_commonmark(linea, valla)


def _sangrar(contenido: list[str], sangria: int) -> list[str]:
    """Las líneas de un bloque con la apertura sangrada, sangradas al menos como ella. Dentro
    de una lista, CommonMark acaba el elemento (y el bloque) en una línea con menos sangría,
    y la valla de cierre abre otro bloque que se traga el resto; marked sigue en el bloque.
    Los dos quitan esa sangría al pintar, así que el código se ve igual."""
    if not sangria:
        return contenido
    salida = []
    for linea in contenido:
        falta = sangria - (len(linea) - len(linea.lstrip(" ")))
        salida.append(" " * falta + linea if falta > 0 and linea.strip() else linea)
    return salida


def _vallas(texto: str, c: Counter, *, cerrar: bool) -> str:
    """Bloques de código delimitados por vallas (``` o ~~~).

    Quita los que se anuncian como llamada a herramienta y los que han quedado vacíos (por
    ejemplo, después de quitar el JSON de una llamada). Con ``cerrar``, cierra el último si
    quedó abierto: un bloque sin cerrar llega hasta el final del documento.

    Un bloque acaba en la primera línea que lo cierra para marked o para CommonMark, y si
    solo lo cierra para una de las dos («```~», o «```» con un tabulador detrás), esa línea
    se reescribe como la valla de apertura, para que cierre en las dos. Si no, en una de las
    dos lecturas el bloque seguía abierto y se tragaba las secciones que añade el código.
    """
    lineas = texto.split("\n")
    salida: list[str] = []
    i = 0
    while i < len(lineas):
        m = _apertura_valla(lineas[i])
        if not m:
            salida.append(lineas[i])
            i += 1
            continue
        valla = m.group(2)
        j = i + 1
        while j < len(lineas) and not _cierra_alguna(lineas[j], valla):
            j += 1
        cerrada = j < len(lineas)
        contenido = lineas[i + 1 : j]
        info = m.group(3).strip().split()
        restante = "".join(contenido).strip()
        if info and info[0].lower() in _INFO_HERRAMIENTA:
            c["bloques_herramienta"] += 1
            salida.append(BLOQUE_RETIRADO)
        elif restante == BLOQUE_RETIRADO:
            salida.append(BLOQUE_RETIRADO)  # solo tenía la llamada, ya retirada
        elif not restante:
            pass  # vacío: no aporta nada y una valla suelta podría quedar abierta
        else:
            salida.append(lineas[i])
            salida.extend(_sangrar(contenido, len(m.group(1))))
            if cerrada:
                cierre = lineas[j]
                if not (
                    _cierra_valla(cierre, valla)
                    and _cierra_valla_commonmark(cierre, valla)
                ):
                    cierre = cierre[: len(cierre) - len(cierre.lstrip(" "))] + valla
                salida.append(cierre)
            elif cerrar:
                salida.append(m.group(1) + valla)
                c["bloques_codigo_sin_cerrar"] += 1
        i = j + 1
    return "\n".join(salida)


# ---------------------------------------------------------------------------- 3. HTML

# Las etiquetas HTML que deja pasar DOMPurify 3.4.17 (su lista html, con content, decorator,
# element, shadow y spacer, que faltaban: con un atributo style que cargaba una imagen de
# otro dominio llegaban a la web), más las que son peligrosas aunque DOMPurify las quite. Las
# de SVG y MathML no hacen falta: fuera de <svg> o <math>, DOMPurify las quita, y esos dos
# están aquí. Si se actualiza DOMPurify, hay que repasar la lista (lo comprueba una prueba).
_ELEMENTOS_HTML: Final = frozenset(
    """a abbr acronym address applet area article aside audio b base basefont bdi bdo
    bgsound big blink blockquote body br button canvas caption center cite code col colgroup
    content data datalist dd decorator del details dfn dialog dir div dl dt element em embed
    fieldset figcaption figure font footer form frame frameset h1 h2 h3 h4 h5 h6 head header
    hgroup hr html i iframe image img input ins isindex kbd keygen label legend li link
    listing main map mark marquee math menu menuitem meta meter nav nobr noembed noframes
    noscript object ol optgroup option output p param picture plaintext portal pre progress q
    rb rp rt rtc ruby s samp script search section select shadow slot small source spacer
    span strike strong style sub summary sup svg table tbody td template textarea tfoot th
    thead time title tr track tt u ul var video wbr xmp""".split()
)
_NOMBRES_HTML = "|".join(sorted(_ELEMENTOS_HTML, key=len, reverse=True))
# Elementos cuyo contenido no es texto para el lector: se quitan enteros.
_APERTURA_BLOQUE_HTML_RE = re.compile(
    r"<\s*(script|style|iframe|noscript|template|svg|math|object|xmp|noembed|"
    r"noframes|textarea|title)\b",
    re.I,
)
_COMENTARIO_RE = re.compile(r"<!--")
_CDATA_RE = re.compile(r"<!\[CDATA\[")
_DECLARACION_RE = re.compile(r"<![A-Za-z]")
_INSTRUCCION_RE = re.compile(r"<\?")
# Etiqueta sin atributos sola en un código en línea: se queda su nombre (`<script>` -> `script`).
_ETIQUETA_EN_CODIGO_RE = re.compile(
    r"`[ ]?<(/?)(" + _NOMBRES_HTML + r")[ ]*/?>[ ]?`", re.I
)
# Etiqueta con sus atributos como los lee un navegador: los valores entre comillas pueden
# llevar «<» y «>», y los atributos pueden ir detrás de «/» («<x/style=…>»). Con [^<>]*,
# «<spacer title="<" style=…>» no casaba y el «=» no se veía.
_ETIQUETA_RE = re.compile(
    r"""<(/?)([A-Za-z][A-Za-z0-9-]*)((?:[\s/](?:[^<>"']|"[^"]*+"|'[^']*+')*+)?+)/?>"""
)
# «<» que abre algo que un visor de Markdown leería como HTML aunque no se cierre
# («<script» al final de una línea abre un bloque HTML que llega hasta «</script>»).
_APERTURA_HTML_RE = re.compile(r"<(?=/?(?:" + _NOMBRES_HTML + r")(?![\w-])|[!?])", re.I)


def _html(texto: str, c: Counter) -> str:
    def _etiqueta(m: re.Match) -> str:
        nombre, atributos = m.group(2), m.group(3)
        if nombre.lower() in _ELEMENTOS_HTML or "=" in atributos:
            c["html"] += 1
            return ""
        return m.group(0)  # elemento desconocido sin atributos: inerte

    def _en_codigo(m: re.Match) -> str:
        c["html"] += 1
        return f"`{m.group(1)}{m.group(2)}`"

    def _quitar(_m: re.Match) -> str:
        c["html"] += 1
        return ""

    # Primero las etiquetas solas en código: si no, «`<script>` … `</script>`» se tomaría
    # por un bloque script y se iría el texto de en medio.
    texto = _ETIQUETA_EN_CODIGO_RE.sub(_en_codigo, texto)
    texto = _quitar_entre(texto, _COMENTARIO_RE, "-->", c, "html")
    texto = _quitar_entre(texto, _CDATA_RE, "]]>", c, "html")
    texto = _quitar_entre(texto, _INSTRUCCION_RE, "?>", c, "html")
    texto = _quitar_bloques(
        texto,
        _APERTURA_BLOQUE_HTML_RE,
        lambda m: _cierre_de(m.group(1).lower()),
        c,
        "html",
        "",
        hasta_mayor=True,
        sin_cierre_hasta_parrafo=False,
    )
    texto = _quitar_entre(texto, _DECLARACION_RE, ">", c, "html")
    texto = _ETIQUETA_RE.sub(_etiqueta, texto)
    return _APERTURA_HTML_RE.sub(_quitar, texto)


# ------------------------------------------------------------------------- 4. Markdown

# Un carácter del texto de un enlace o de una etiqueta: cualquiera menos corchetes y barra
# invertida, y saltos de línea solo si no empiezan una línea en blanco. En CommonMark ni el
# texto de un enlace ni una etiqueta cruzan un párrafo; sin esa condición, un «[» o un «![»
# sin cerrar se llevaba por delante los párrafos que hubiera hasta el siguiente «]».
_CARACTER_MD = r"(?:[^\[\]\\\n]|\n(?![ \t]*\n))"
# Texto de un enlace: corchetes anidados un nivel y escapes. No empieza en un «[» detrás de
# una barra invertida: con «\[» repetido, cada uno recorría el resto del párrafo (2 s con
# 16.000 caracteres, medido el 12/11/2026). Si la barra estaba a su vez escapada, el enlace
# no se reconoce entero, pero _colas quita igualmente su destino.
_TEXTO_MD = (
    r"(?<!\\)\[((?:" + _CARACTER_MD + r"|\\.|\[(?:" + _CARACTER_MD + r"|\\.)*\])*)\]"
)
# La gramática de marked 18 (inline.link): entre «(», el destino, el título y «)» solo
# separan el espacio, el tabulador y el salto de línea, y el destino sin <…> admite cualquier
# otro carácter que no sea de control. Con \s, que en Python casa también los espacios
# Unicode, «[BOE](https://www.boe.es<NBSP>"@otro/…")» se leía como destino oficial más un
# título, y marked lo pinta como un enlace a otro (el NBSP queda dentro del usuario de la URL).
_DESTINO_CARACTER = r"[^ \t\n\x00-\x1f()\\]"
# Destino: entre <…> (admite espacios) o sin espacios, con paréntesis equilibrados un nivel.
# Los cuantificadores posesivos evitan la vuelta atrás: con «[a](» y 16.000 espacios, el
# reparto de los espacios entre los «\s*» tardaba 2,6 s (cuadrático), medido el 12/11/2026.
_DESTINO_MD = (
    r"(<[^<>\n]*>|(?:[^ \t\n\x00-\x1f()<>\\]|\\.|\((?:"
    + _DESTINO_CARACTER
    + r"|\\.)*+\))*+)"
)
_SEPARADOR_TITULO = r"(?:[ \t]++(?:\n[ \t]*+)?+|\n[ \t]*+)"
_TITULO = r"""(?:"(?:[^"\\]|\\[\s\S])*+"|'(?:[^'\\]|\\[\s\S])*+'|\((?:[^()\\]|\\[\s\S])*+\))"""
_TITULO_MD = r"(?:" + _SEPARADOR_TITULO + _TITULO + r")?+"
_COLA_MD = r"\([ \t\n]*+" + _DESTINO_MD + _TITULO_MD + r"[ \t\n]*+\)"
_IMAGEN_RE = re.compile(r"!" + _TEXTO_MD + _COLA_MD)
_IMAGEN_REF_RE = re.compile(r"!" + _TEXTO_MD + r"(?:\[[^\[\]\n]*\])?")
_ENLACE_RE = re.compile(_TEXTO_MD + _COLA_MD)
_AUTOENLACE_RE = re.compile(r"<([A-Za-z][A-Za-z0-9+.-]{1,31}:[^<>\s]*)>")
# Lo que puede seguir al destino de una definición de referencia: nada, o el principio de
# un título. Con otra cosa detrás no es una definición (ni para CommonMark ni para marked) y
# el destino es texto, del que se encargan los pasos siguientes.
_FORMA_DEFINICION = r"""(?=[ \t]*(?:$|["'(]))"""
# Definición de referencia al principio de una línea, detrás de cualquier combinación de
# sangría, marcas de cita («>») y marcas de lista («-», «*», «+», «1.», «1)»), con escapes y
# saltos de línea en la etiqueta. Se quita la línea entera; lo que no reconozca lo recoge
# _resto_definicion.
_PREFIJO_CONTENEDOR = r"(?:[ \t]*(?:>|(?:[-+*]|\d{1,9}[.)])(?=[ \t])))*[ \t]*"
_PREFIJO_CONTENEDOR_RE = re.compile(_PREFIJO_CONTENEDOR)
_DEFINICION_RE = re.compile(
    r"^"
    + _PREFIJO_CONTENEDOR
    + r"\[(?:"
    + _CARACTER_MD
    + r"|\\.)+\]:[ \t]*(?:\n[ \t]*)?(<[^<>\n]*>|\S++)"
    + _FORMA_DEFINICION
    + r"[^\n]*(?:\n|$)",
    re.M,
)
_HOST_VALIDO_RE = re.compile(r"[a-z0-9.-]+")

# Últimos recursos (ver el paso 4 de la cabecera).
# Los «!» delante de un «[»: sin ellos, ninguna construcción es una imagen. Se mira cada
# tira de «!» una vez, desde su principio: si no, una tira sin «[» detrás se recorría desde
# cada uno de sus «!».
_RESTO_IMAGEN_RE = re.compile(r"(?<!!)!++(?=\[)")
# Cola de un enlace en línea a partir de su «(»: destino entre <…> o sin espacios, con
# paréntesis equilibrados hasta 32 niveles (CommonMark no pone límite; commonmark.js admite
# 32), título opcional y «)». Los cuantificadores posesivos evitan la vuelta atrás: cada
# intento cuesta lo que recorre.
_PROFUNDIDAD_PARENTESIS: Final = 32


def _destino_anidado(niveles: int) -> str:
    patron = r"(?:" + _DESTINO_CARACTER + r"|\\.)"
    for _ in range(niveles):
        patron = r"(?:" + _DESTINO_CARACTER + r"|\\.|\(" + patron + r"*+\))"
    return patron + "*+"


_COLA_RE = re.compile(
    r"\([ \t\n]*+(<(?:[^<>\n\\]|\\.)*+>|"
    + _destino_anidado(_PROFUNDIDAD_PARENTESIS)
    + r")"
    + _TITULO_MD
    + r"[ \t\n]*+\)"
)
# Si la cola no se reconoce (más de 32 niveles, un paréntesis sin cerrar, un título roto),
# se quita igualmente lo que va hasta el primer espacio cuando parece una URL no oficial.
# Para decidir si lo parece basta el principio; el resto solo se lee si hay que quitarlo.
_PRINCIPIO_COLA_RE = re.compile(r"\([ \t\n]*+([^ \t\n]{1,64})")
_TOKEN_COLA_RE = re.compile(r"\([ \t\n]*+([^ \t\n]{1,2048})")
# «]:» seguido de un destino; solo cuenta si la etiqueta empieza una línea
# (_etiqueta_empieza_linea). No se exige la forma de una definición: aunque marked no la
# lea como tal, el destino que queda es una URL suelta, y una de un fragmento envenenado se
# quedaría como enlace por la excepción del paso 5.
_RESTO_DEFINICION_RE = re.compile(r"\]:[ \t]*(?:\n[ \t]*)?(<[^<>\n]*>|\S+)")
# Para _parece_url: escapes de Markdown, lo que el navegador ignora y el principio de una URL.
_ESCAPE_MD_RE = re.compile(r"\\([!-/:-@\[-`{-~])")
_IGNORADOS_RE = re.compile(r"[\x00-\x20\x7f]+")
_PRINCIPIO_URL_RE = re.compile(r"(?:[A-Za-z][A-Za-z0-9+.-]*:|[/\\]{2}|www\.)", re.I)
_SOLO_ESQUEMA_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")


def destino_oficial(destino: str) -> bool:
    """¿Es ``destino`` una URL ``http(s)`` a un dominio oficial del corpus (o subdominio)?

    Se analiza la URL en lugar de buscar el dominio en el texto, así que no pasan
    ``javascript:``, ``data:``, ``//otro``, los esquemas con entidades
    (``https&#58;//…``), las credenciales (``https://boe.es@otro``) ni ``boe.es.otro.com``.
    Tampoco una URL con espacios (de cualquier tipo), caracteres no imprimibles o acentos
    graves dentro: ninguna URL oficial los lleva, y marked y el navegador no los leen como
    Python (el NBSP queda dentro del usuario de la URL; el acento grave, en el código en
    línea).
    """
    d = destino.strip()
    if d.startswith("<") and d.endswith(">"):
        d = d[1:-1].strip()
    if not d.isprintable() or any(ch.isspace() for ch in d) or "`" in d:
        return False
    if d.lower().startswith("www."):
        d = "https://" + d
    if "\\" in d:
        return False
    try:
        partes = urlsplit(d)
        host = partes.hostname
        con_credenciales = partes.username is not None or partes.password is not None
    except ValueError:
        return False
    if partes.scheme.lower() not in ("http", "https") or con_credenciales:
        return False
    if not host or not _HOST_VALIDO_RE.fullmatch(host):
        return False
    return any(host == dom or host.endswith("." + dom) for dom in DOMINIOS_OFICIALES)


def _parece_url(destino: str) -> bool:
    """¿Puede ``destino`` llevar a otro sitio? Sí si empieza por un esquema (``https:``,
    ``javascript:``), por «www.» o por dos barras (relativa al protocolo), también escritas
    con escapes de Markdown (``\\/\\/``), con entidades HTML (``&#47;&#47;``) o con barras
    invertidas (``/\\``, que el navegador lee como ``//``). Antes se quitan los espacios y
    caracteres de control, que el navegador ignora. Un destino relativo (``#rgpd``,
    ``x.png``) se queda en el sitio que pinta el informe, y un esquema sin nada detrás
    («Plazo:», «try:») no lleva a ningún sitio."""
    d = html.unescape(_ESCAPE_MD_RE.sub(r"\1", destino))
    d = _IGNORADOS_RE.sub("", d).removeprefix("<").removesuffix(">")
    if _SOLO_ESQUEMA_RE.fullmatch(d):
        return False
    return bool(_PRINCIPIO_URL_RE.match(d))


def _escapado(texto: str, i: int) -> bool:
    """¿Va ``texto[i]`` escapado (detrás de un número impar de barras invertidas)?"""
    j = i
    while j > 0 and texto[j - 1] == "\\":
        j -= 1
    return (i - j) % 2 == 1


_MAX_ETIQUETA: Final = (
    1000  # CommonMark y marked: como mucho 999 caracteres en la etiqueta
)


def _etiqueta_empieza_linea(texto: str, cierre: int) -> bool:
    """¿Abre la etiqueta que acaba en ``texto[cierre]`` («]») una definición de referencia?

    Para CommonMark y para marked, solo si su «[» empieza una línea, detrás de marcas de
    lista o de cita, sin corchetes sin escapar dentro y sin cruzar una línea en blanco. En
    «list[dict]:», «button[aria-pressed]:» o «brechas [art. 33]: Plazo:» no lo es, y quitar
    lo que seguía estropeaba código y texto legítimos. Lo que se deja lo decide el paso 5."""
    i = cierre - 1
    limite = max(0, cierre - _MAX_ETIQUETA)
    while i >= limite:
        ch = texto[i]
        if ch in "[]" and not _escapado(texto, i):
            if ch == "]":
                return False
            inicio_linea = texto.rfind("\n", 0, i) + 1
            return bool(_PREFIJO_CONTENEDOR_RE.fullmatch(texto, inicio_linea, i))
        if ch == "\n" and texto[texto.rfind("\n", 0, i) + 1 : i].strip(" \t") == "":
            return False  # línea en blanco
        i -= 1
    return False


def _colas(texto: str, c: Counter) -> str:
    """Quita el destino no oficial de cada «](», sin buscar el «[» que le corresponde.

    Así no importa cuántos corchetes anidados lleve el texto del enlace o de la imagen
    («[a [b [c]]](//otro)»), que _ENLACE_RE solo reconoce con un nivel. Queda el texto con
    sus corchetes. Si después del destino quitado viene otra cola («](x)(y)»), se quita
    también, porque se uniría al mismo «]». Cada «](» se mira una vez, y la expresión de la
    cola no vuelve atrás.
    """
    if "](" not in texto:
        return texto
    salida: list[str] = []
    pos = 0
    i = texto.find("](")
    while i != -1:
        p = siguiente = i + 1
        if not _escapado(texto, i):
            while True:
                m = _COLA_RE.match(texto, p)
                if m:
                    if destino_oficial(m.group(1)):
                        siguiente = m.end()  # enlace oficial: se deja entero
                        break
                else:
                    principio = _PRINCIPIO_COLA_RE.match(texto, p)
                    if not principio or not _parece_url(principio.group(1)):
                        break
                    m = _TOKEN_COLA_RE.match(texto, p)
                    if destino_oficial(m.group(1)):
                        break
                c["enlaces"] += 1
                p = m.end()
        if p > i + 1:
            salida.append(texto[pos : i + 1])
            pos = p
        i = texto.find("](", max(siguiente, p))
    salida.append(texto[pos:])
    return "".join(salida)


_ACENTOS_RE = re.compile(r"`+")


def _longitudes(texto: str, tira: re.Match) -> tuple[int, ...]:
    """Las longitudes que puede tener ``tira`` para marked: detrás de una barra invertida, el
    primer acento puede ser un escape y la tira cuenta como una más corta («\\``» deja «`»)."""
    n = len(tira.group())
    if texto[tira.start() - 1 : tira.start()] == "\\":
        return (n, n - 1)
    return (n,)


def _delimitador(texto: str) -> str:
    """Acentos graves para encerrar algo en código: tantos como el primer número que no
    tiene ninguna tira de acentos del texto. Con uno solo, un acento suelto de antes («Ver
    `x https://…») se emparejaría con el de apertura y la URL quedaría fuera del código. Las
    tiras escapadas cuentan también con un acento menos."""
    usadas = {n for t in _ACENTOS_RE.finditer(texto) for n in _longitudes(texto, t)}
    n = 1
    while n in usadas:
        n += 1
    return "`" * n


def _en_codigo(
    texto: str, inicio: int, fin: int, contenido: str, delimitador: str
) -> str:
    """``contenido`` encerrado en código para ponerlo en lugar de ``texto[inicio:fin]``, con
    un espacio de separación si al lado hay un acento grave (si no, se sumaría a la tira) o
    delante una barra invertida (escaparía el primer acento)."""
    antes = " " if texto[inicio - 1 : inicio] in ("`", "\\") else ""
    despues = " " if texto[fin : fin + 1] == "`" else ""
    return f"{antes}{delimitador}{contenido}{delimitador}{despues}"


def _markdown(texto: str, c: Counter) -> str:
    def _imagen(_m: re.Match) -> str:
        c["imagenes"] += 1
        return IMAGEN_RETIRADA

    def _enlace(m: re.Match) -> str:
        if destino_oficial(m.group(2)):
            return m.group(0)
        c["enlaces"] += 1
        return m.group(1)

    delimitador = ""

    def _autoenlace(m: re.Match) -> str:
        # El corpus sale de PDF y no tiene autoenlaces: si hay uno, lo ha escrito el modelo,
        # así que no se le aplica la excepción de las URL de los fragmentos (paso 5).
        if destino_oficial(m.group(1)):
            return m.group(0)
        c["enlaces"] += 1
        url = m.group(1).replace("`", "")
        return _en_codigo(m.string, m.start(), m.end(), url, delimitador)

    def _definicion(m: re.Match) -> str:
        if not _parece_url(m.group(1)) or destino_oficial(m.group(1).strip("<>")):
            return m.group(0)
        c["enlaces"] += 1
        return ""

    texto = _IMAGEN_RE.sub(_imagen, texto)
    texto = _IMAGEN_REF_RE.sub(_imagen, texto)
    texto = _DEFINICION_RE.sub(_definicion, texto)
    texto = _ENLACE_RE.sub(_enlace, texto)
    if "<" in texto:
        delimitador = _delimitador(texto)
        texto = _AUTOENLACE_RE.sub(_autoenlace, texto)
    return texto


def _ultimos_recursos(texto: str, c: Counter) -> str:
    """Las tres reglas de piezas sueltas del paso 4. Se aplican en la primera pasada y
    cuando las demás ya no cambian nada, no en cada pasada: en cada pasada, con un prefijo
    que forzara las 20, multiplicaban por 20 su coste (2,3 s con 32.000 caracteres, medido
    el 12/11/2026)."""

    def _resto_imagen(_m: re.Match) -> str:
        c["imagenes"] += 1
        return ""

    def _resto_definicion(m: re.Match) -> str:
        if (
            _escapado(m.string, m.start())
            or not _parece_url(m.group(1))
            or destino_oficial(m.group(1).strip("<>"))
            or not _etiqueta_empieza_linea(m.string, m.start())
        ):
            return m.group(0)
        c["enlaces"] += 1
        return "]:"

    texto = _RESTO_IMAGEN_RE.sub(_resto_imagen, texto)
    texto = _colas(texto, c)
    return _RESTO_DEFINICION_RE.sub(_resto_definicion, texto)


# ---------------------------------------------------------------------- 5. URL sueltas

# Las que un visor convierte en enlace: http(s)://, ftp:// o www. Sin mirar lo que va
# delante: marked (el visor de la web) enlaza también detrás de una letra, un dígito, «_»,
# «/» o «@», aunque la especificación de GFM solo lo haga tras un espacio o «*_~(». La
# expresión para en «|» y en el acento grave, que en una tabla y en el código en línea
# pueden cortar la URL; lo que marked leería detrás (su clase es [^\s<], así que llega hasta
# _FIN_CONTINUACION_RE) cuenta para decidir si la URL es oficial.
_URL_SUELTA_RE = re.compile(r"(?:https?://|ftp://|www\.)[^\s<|`]+", re.I)
# _urls busca por separado el principio y el final de cada URL: con la expresión entera,
# cada búsqueda recorría el resto del trozo sin espacios, y se repite tras cada corte.
_INICIO_URL_RE = re.compile(r"(?:https?://|ftp://|www\.)(?=[^\s<|`])", re.I)
_FIN_URL_RE = re.compile(r"[\s<|`]")
_FIN_CONTINUACION_RE = re.compile(r"[\s<]")
_CIERRE_EN_URL_RE = re.compile(r"[*_~\]]")
_CORTE_CODIGO_RE = re.compile(r"[>)]")
# Detrás del esquema (o de «www.»), lo que cierra el host.
_FIN_AUTORIDAD_RE = re.compile(r"[/?#\\]")
_PUNTUACION_FINAL = "?!.,:;*_~'\""
# Corte de línea de la extracción de los PDF («https://prism-\nbreak.org»).
_SALTO_RE = re.compile(r"[ \t]*\n[ \t]*")


def _recortar_url(url: str) -> str:
    """Quita la puntuación final que GFM no considera parte del enlace. marked quita además
    una entidad final («&amp;»): la URL que queda aquí es igual o más larga que su enlace."""
    abiertos, cerrados = url.count("("), url.count(")")
    fin = len(url)
    while fin:
        ch = url[fin - 1]
        if ch in _PUNTUACION_FINAL:
            fin -= 1
        elif ch == ")" and cerrados > abiertos:
            fin -= 1
            cerrados -= 1
        else:
            break
    return url[:fin]


def _lineas_en_valla(
    lineas: list[str], cierra: Callable[[str, str], bool]
) -> list[bool]:
    """Qué líneas son de un bloque con valla (las vallas incluidas) con la regla de cierre
    ``cierra``. Un bloque con la apertura sangrada puede estar dentro de una lista y acabar
    con ella antes de su valla de cierre; solo cuenta si todo su contenido va sangrado al
    menos como la apertura."""
    dentro = [False] * len(lineas)
    i = 0
    while i < len(lineas):
        m = _apertura_valla(lineas[i])
        if not m:
            i += 1
            continue
        valla, sangria = m.group(2), len(m.group(1))
        j = i + 1
        while j < len(lineas) and not cierra(lineas[j], valla):
            j += 1
        if sangria == 0 or all(
            not linea.strip() or len(linea) - len(linea.lstrip(" ")) >= sangria
            for linea in lineas[i + 1 : j]
        ):
            for k in range(i, min(j, len(lineas) - 1) + 1):
                dentro[k] = True
        i = j + 1
    return dentro


def _tramos_de_valla(texto: str) -> list[tuple[int, int]]:
    """Intervalos que son código con valla para marked y para CommonMark a la vez. Las dos
    reglas de cierre no coinciden («```~» cierra para marked y no para CommonMark; «```» con
    un tabulador detrás, al revés), y lo que solo es código en una lectura es texto en la
    otra, donde una URL se pinta como enlace."""
    lineas = texto.split("\n")
    marked = _lineas_en_valla(lineas, _cierra_valla)
    commonmark = _lineas_en_valla(lineas, _cierra_valla_commonmark)
    tramos: list[tuple[int, int]] = []
    pos = 0
    inicio = fin_tramo = -1
    for k, linea in enumerate(lineas):
        fin = pos + len(linea)
        if marked[k] and commonmark[k]:
            if inicio == -1:
                inicio = pos
            fin_tramo = fin
        elif inicio != -1:
            tramos.append((inicio, fin_tramo))
            inicio = -1
        pos = fin + 1
    if inicio != -1:
        tramos.append((inicio, fin_tramo))
    return tramos


def _dentro(pos: int, tramos: list[tuple[int, int]], inicios: list[int]) -> bool:
    k = bisect_right(inicios, pos) - 1
    return k >= 0 and pos < tramos[k][1]


def _codigo_en_linea(
    texto: str,
    vallas: list[tuple[int, int]],
    urls: list[tuple[int, int, int, int]],
) -> list[tuple[int, int]]:
    """Código en línea que marked pinta como código lo lea como lo lea.

    marked empareja los acentos de izquierda a derecha, pero antes pueden consumirlos un
    escape, una URL, un autoenlace, el destino, el título o la etiqueta de un enlace o una
    celda de tabla, y el código en línea puede cruzar líneas. Una expresión que solo buscaba
    parejas de acentos tomaba por código, por ejemplo, «<https://www.boe.es/`> URL
    <https://www.boe.es/`>», y la URL de en medio se quedaba como enlace. Aquí, una longitud
    de tira de acentos solo es de fiar si todas las tiras de esa longitud (fuera de los
    bloques con valla) forman parejas seguidas en la misma línea, sin acentos dentro, sin una
    barra invertida delante de la apertura, sin una URL anterior que llegue hasta ella, y con
    un contenido que es una URL sola o que no lleva «]», «)», «>» ni «|» (los cierres de lo
    que podría haber consumido la apertura); y si ninguna tira escapada puede contar con esa
    longitud. Lo que no es de fiar se trata como texto: la URL pasa a código con un
    delimitador nuevo, que en el peor caso se ve con acentos de más.
    """
    inicios_valla = [a for a, _b in vallas]
    por_longitud: dict[int, list[re.Match]] = {}
    dudosas: set[int] = set()  # longitudes de una tira escapada: no se sabe cuál cuenta
    for m in _ACENTOS_RE.finditer(texto):
        if not _dentro(m.start(), vallas, inicios_valla):
            por_longitud.setdefault(len(m.group()), []).append(m)
            if len(longitudes := _longitudes(texto, m)) > 1:
                dudosas.update(longitudes)
    inicios_url = [u[0] for u in urls]
    url_en = {u[0]: u[3] for u in urls}  # fin de la expresión, sin los cortes

    def _pareja_fiable(a: re.Match, b: re.Match) -> bool:
        contenido = texto[a.end() : b.start()]
        if (
            "\n" in contenido
            or "`" in contenido
            or texto[a.start() - 1 : a.start()] == "\\"
        ):
            return False
        k = bisect_right(inicios_url, a.start()) - 1
        if k >= 0 and urls[k][2] > a.start():
            return False  # la apertura está dentro de lo que marked leería como URL
        izquierda = a.end() + (1 if contenido.startswith(" ") else 0)
        derecha = b.start() - (
            1 if contenido.endswith(" ") and len(contenido) > 1 else 0
        )
        if url_en.get(izquierda) == derecha:
            return True  # una URL sola
        return not any(ch in contenido for ch in "])>|")

    tramos: list[tuple[int, int]] = []
    for longitud, tiras in por_longitud.items():
        if len(tiras) % 2 or longitud in dudosas:
            continue
        parejas = list(zip(tiras[0::2], tiras[1::2], strict=True))
        if all(_pareja_fiable(a, b) for a, b in parejas):
            tramos.extend((a.start(), b.end()) for a, b in parejas)
    return tramos


def _host(url: str) -> str:
    try:
        return urlsplit(url if "://" in url else "https://" + url).hostname or ""
    except ValueError:
        return ""


def _host_cerrado(url: str) -> bool:
    """¿Termina el host dentro de ``url`` (hay una «/», «?», «#» o «\\» detrás)?"""
    resto = url[4:] if url[:4].lower() == "www." else url.partition("://")[2]
    return bool(_FIN_AUTORIDAD_RE.search(resto))


def _cierres(texto: str) -> list[int]:
    """Dónde cierra marked un autoenlace («>») o la cola de un enlace en línea («)»): lo que
    va detrás es texto nuevo, aunque no haya un espacio. «<https://www.boe.es/>https://otro»
    se leía como una sola URL, oficial, y marked enlaza la segunda."""
    cierres = [m.end() - 1 for m in _AUTOENLACE_RE.finditer(texto)]
    i = texto.find("](")
    while i != -1:
        if m := _COLA_RE.match(texto, i + 1):
            cierres.append(m.end() - 1)
        i = texto.find("](", i + 2)
    return sorted(cierres)


def _urls(texto: str) -> list[tuple[int, int, int, int]]:
    """Cada URL suelta: inicio, fin de lo que reconoce _URL_SUELTA_RE (cortado donde marked
    cierra un autoenlace o un enlace o donde para su retroceso, que enlaza solo hasta el
    primer «(» sin cerrar; desde ahí se vuelve a buscar, porque lo de detrás es texto y en él
    puede empezar otra URL, como en «https://www.boe.es/(ftp://otro») y fin de lo que leería
    marked si no hubiera enlace (hasta un espacio o un «<»): la URL se juzga con lo segundo y
    se encierra en código hasta lo primero. El cuarto valor es el fin de la expresión sin
    cortes. Los finales se buscan una vez por trozo sin espacios, no una por URL."""
    if not _URL_SUELTA_RE.search(texto):
        return []
    parada = _buscador(texto, _FIN_URL_RE)
    separador = _buscador(texto, _FIN_CONTINUACION_RE)
    cierres = _cierres(texto)
    abre = [i for i, ch in enumerate(texto) if ch == "("]
    cierra = [i for i, ch in enumerate(texto) if ch == ")"]
    urls = []
    pos = 0
    while m := _INICIO_URL_RE.search(texto, pos):
        s = m.start()
        e = e_expresion = parada(m.end())
        e = e_expresion = len(texto) if e == -1 else e
        k = bisect_right(cierres, s)
        if k < len(cierres) and cierres[k] < e:
            e = cierres[k]
        # Retroceso de marked: para en el primer «(» que no tiene un «)» detrás, es decir,
        # en el primer «(» posterior al último «)» de la URL.
        j = bisect_left(cierra, e) - 1
        ultimo = cierra[j] if j >= 0 and cierra[j] > s else s
        a = bisect_right(abre, ultimo)
        if a < len(abre) and abre[a] < e:
            e = abre[a]
        # Un énfasis, un tachado o una referencia abiertos antes de la URL pueden cerrarse
        # dentro de ella, en un «*», «_», «~» o «]»: lo de detrás es texto nuevo, y una URL
        # que empiece ahí es otra («~~a https://www.boe.es/~~https://otro»).
        if disparador := _CIERRE_EN_URL_RE.search(texto, s, e):
            inicio = max(m.end(), disparador.start() + 1)
            if interior := _INICIO_URL_RE.search(texto, inicio, e):
                e = interior.start()
        # El código que pone el saneado no lleva «>» ni «)»: para el énfasis, marked aparta
        # «<…>» y «[…](…)» con una búsqueda propia que podía acabar dentro del código, y
        # entonces un «~» de dentro cerraba un tachado y la URL quedaba como enlace.
        if corte := _CORTE_CODIGO_RE.search(texto, s, e):
            e = corte.start()
        fin = separador(m.end())
        urls.append((s, e, len(texto) if fin == -1 else fin, e_expresion))
        pos = e
    return urls


def _fuentes(fuentes: Iterable[str]) -> tuple[str, frozenset[str]]:
    """Texto normalizado de los fragmentos y hosts exactos de sus URL.

    Una URL suelta se respeta si está en los fragmentos (comparando con
    ``citations.normalize``, que tolera los cortes y espacios de la extracción de los PDF) y
    además su host es el de una URL de los fragmentos. Sin lo segundo pasaba una URL de otro
    dominio que solo se diferenciara en guiones (``ar-xiv.org`` por ``arxiv.org``), porque
    ``normalize`` los quita. Los hosts se sacan también del fragmento con los cortes de línea
    unidos: 14 de las 674 URL del índice tienen el host partido en dos líneas. Del fragmento
    se quita antes el guion blando, como del texto del modelo (paso 1).
    """
    lista = [f.replace(_GUION_BLANDO, "") for f in fuentes]
    hosts: set[str] = set()
    for f in lista:
        for variante in (f, _SALTO_RE.sub("", f)):
            for m in _URL_SUELTA_RE.finditer(variante):
                host = _host(_recortar_url(m.group(0)))
                if host:
                    hosts.add(host)
    return "|".join(normalize(f) for f in lista), frozenset(hosts)


def _urls_sueltas(texto: str, fuentes: tuple[str, frozenset[str]], c: Counter) -> str:
    fuentes_norm, hosts = fuentes
    vallas = _tramos_de_valla(texto)
    inicios_valla = [a for a, _b in vallas]
    urls = [u for u in _urls(texto) if not _dentro(u[0], vallas, inicios_valla)]
    if not urls:
        return texto
    codigo = sorted(vallas + _codigo_en_linea(texto, vallas, urls))
    inicios_codigo = [a for a, _b in codigo]
    delimitador = ""
    salida: list[str] = []
    pos = 0
    for k, (s, e, fin_marked, _e) in enumerate(urls):
        if _dentro(s, codigo, inicios_codigo):
            continue
        # Se juzga lo que enlazaría marked, también lo que va detrás de un «|» o de un acento
        # grave («https://www.boe.es`@otro/…» lleva a otro), hasta donde empieza la URL
        # siguiente: juzgar cada una con todo el trozo costaba el cuadrado del número de URL.
        # Si la siguiente empieza antes de que se cierre el host, no se respeta: sin el corte,
        # lo de detrás podría hacer de usuario de la URL y cambiar el host. Se encierra en
        # código lo que reconoce la expresión (con sus cortes), y lo de detrás queda como texto.
        siguiente = urls[k + 1][0] if k + 1 < len(urls) else len(texto)
        completa = _recortar_url(texto[s : min(fin_marked, siguiente)])
        clave = normalize(completa)
        if (siguiente >= fin_marked or _host_cerrado(completa)) and (
            destino_oficial(completa)
            or (clave and clave in fuentes_norm and _host(completa) in hosts)
        ):
            continue
        url = _recortar_url(texto[s:e])
        if not delimitador:
            delimitador = _delimitador(texto)
        fin = s + len(url)
        salida.append(texto[pos:s])
        if s == pos and salida[-2:-1] and salida[-2].endswith(delimitador):
            salida.append(" ")  # pegada a la anterior: los acentos se sumarían
        salida.append(_en_codigo(texto, s, fin, url, delimitador))
        c["urls"] += 1
        pos = fin
    salida.append(texto[pos:])
    return "".join(salida)


# --------------------------------------------------------------------------- conjunto


def _neutralizar_resto(texto: str, c: Counter) -> str:
    """Último recurso si las pasadas no convergen: ningún «<» ni «](» con significado."""
    n = texto.count("<") + texto.count("](")
    if n:
        c["html"] += n
    return texto.replace("<", "‹").replace("](", "] (")


def sanear(texto: str, fuentes: Iterable[str] = ()) -> tuple[str, SaneadoStats]:
    """Texto del modelo saneado y lo que se ha retirado, por tipo (RNF-20).

    ``fuentes`` son los textos de los fragmentos que recibió el modelo: sus URL se respetan
    (paso 5). La descripción del usuario no es una fuente.
    """
    c: Counter = Counter()
    t = _caracteres(texto, c)
    for pasada in range(MAX_PASADAS):
        antes = t
        t = _herramientas(t, c)
        t = _vallas(t, c, cerrar=False)
        t = _html(t, c)
        t = _markdown(t, c)
        # Los últimos recursos, en la primera pasada (quitan de golpe las colas de los enlaces
        # anidados, que _ENLACE_RE pelaría de nivel en nivel, una pasada por nivel) y cuando
        # lo demás ya no cambia nada.
        if pasada == 0 or t == antes:
            t = _ultimos_recursos(t, c)
            if t == antes:
                break
    else:
        t = _neutralizar_resto(_ultimos_recursos(t, c), c)
    t = _urls_sueltas(t, _fuentes(fuentes), c)
    t = _vallas(t, c, cerrar=True)
    return t, SaneadoStats(**c)
