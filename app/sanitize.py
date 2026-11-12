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

1. **Caracteres.** Quita las secuencias de escape ANSI y los caracteres de control (salvo el
   tabulador y los saltos de línea), los de formato invisibles (ancho cero, dirección bidi,
   etiquetas Unicode; se respeta el guion blando, que está en los textos oficiales) y los
   selectores de variación, salvo uno suelto detrás de un carácter visible (el de los emojis).
2. **Bloques que imitan llamadas a herramientas**: etiquetas de llamada al estilo XML, los
   tokens especiales ``<|…|>``, el formato de gpt-oss (``to=functions.…``), las marcas
   ``[TOOL_CALLS]`` y los objetos JSON con forma de llamada (nombre y argumentos, o
   ``tools/call``), estén o no en un bloque de código; y los bloques de código que se anuncian
   como llamada a herramienta.
3. **HTML en bruto**: comentarios, declaraciones, bloques ``script``/``style``/``iframe``/
   ``svg``… con su contenido y las etiquetas de elementos HTML o con atributos ``=``. Una
   etiqueta sin atributos que ocupa sola un código en línea (`` `<script>` ``) se queda en su
   nombre. Las etiquetas desconocidas sin atributos (``<nombre de la empresa>``) son inertes y
   se dejan.
4. **Markdown**: todas las imágenes; los enlaces y definiciones de referencia cuyo destino
   no sea ``http(s)`` a un dominio oficial del corpus (``DOMINIOS_OFICIALES``), de los que
   queda el texto, y los autoenlaces no oficiales, que pasan a código. ``[4](en adelante,
   RGPD)``, que está en el corpus, no es un enlace (el destino tiene espacios) y no se toca.
5. **URL sueltas** (las que un visor convierte en enlace): se quedan las de un dominio oficial
   y las que aparecen en los fragmentos que recibió el modelo, que se escribieron antes de la
   petición y no pueden llevar datos del usuario; las demás se muestran como código, sin
   enlace. El corpus tiene URL de más de 50 dominios no oficiales, así que quitarlas todas
   rompería citas literales.
6. **Bloques de código sin cerrar**: se cierran, para que no se traguen las secciones que
   añade el código ni, por MCP, el JSON del resultado.

Los pasos 2 a 4 se repiten hasta que el texto no cambia, porque quitar algo puede formar otra
construcción (``<scr<b>ipt>``).

Citas: ``sanear`` deja igual (comparando con ``citations.normalize``) los 13.756 fragmentos
del índice real, medido el 12/11/2026, así que una cita literal de un fragmento real no deja
de verificarse. Una cita de un fragmento envenenado que traiga marcado neutralizado sí deja
de verificarse, y es lo correcto.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
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
) - {"\t", "\n", "\r"}
_GUION_BLANDO: Final = "\u00ad"
_SELECTORES_EMOJI: Final = frozenset("\ufe0e\ufe0f")


def _es_selector(ch: str) -> bool:
    o = ord(ch)
    return 0xFE00 <= o <= 0xFE0F or 0xE0100 <= o <= 0xE01EF or 0x180B <= o <= 0x180F


def _es_invisible(ch: str) -> bool:
    return unicodedata.category(ch) == "Cf" and ch != _GUION_BLANDO


def _caracteres(texto: str, c: Counter) -> str:
    def _ansi(_m: re.Match) -> str:
        c["caracteres_control"] += 1
        return ""

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
_BLOQUE_HERRAMIENTA_RE = re.compile(
    r"<\s*(?P<n>" + _NOMBRE_HERRAMIENTA + r")\b[^>]*>.*?<\s*/\s*(?P=n)\s*>",
    re.I | re.S,
)
# Apertura sin cierre: hasta el final del párrafo.
_APERTURA_HERRAMIENTA_RE = re.compile(
    r"<\s*" + _NOMBRE_HERRAMIENTA + r"\b[^>]*>.*?(?=\n[ \t]*\n|\Z)", re.I | re.S
)
_CIERRE_HERRAMIENTA_RE = re.compile(r"<\s*/\s*" + _NOMBRE_HERRAMIENTA + r"\s*>", re.I)
# Tokens especiales de las plantillas de chat (<|im_start|>, <|call|>, <\uff5ctool▁calls▁begin\uff5c>).
_TOKEN_ESPECIAL_RE = re.compile(r"<[|\uff5c][^<>\n]{0,60}?[|\uff5c]>")
# Formato harmony de gpt-oss: «to=functions.bash … {…}» hasta el final de la línea.
_HARMONY_RE = re.compile(
    r"\bto=(?:functions|browser|python|container|repo_browser)\b[^\n]*", re.I
)
# Marcas de llamada de Mistral y similares; se quita también el JSON que las sigue.
_MARCA_HERRAMIENTA_RE = re.compile(
    r"\[/?(?:TOOL_CALLS?|TOOL_REQUEST|TOOL_RESULTS?|AVAILABLE_TOOLS)\]", re.I
)
# Un objeto JSON que empieza por una clave.
_INICIO_OBJETO_RE = re.compile(r'\{\s*"')
# Forma de llamada a herramienta dentro de un objeto JSON.
_LLAMADA_JSON_RES: Final = (
    re.compile(
        r'"(?:name|tool|tool_name|function|recipient_name)"\s*:\s*"[^"]*"'
        r'(?=.*"(?:arguments|parameters|input|args|params)"\s*:)',
        re.S,
    ),
    re.compile(
        r'"(?:arguments|parameters|input|args|params)"\s*:'
        r'(?=.*"(?:name|tool|tool_name|function|recipient_name)"\s*:\s*")',
        re.S,
    ),
    re.compile(r'"method"\s*:\s*"tools/call"'),
    re.compile(r'"(?:tool_calls|function_call|tool_use)"\s*:'),
    re.compile(r'"type"\s*:\s*"(?:tool_use|function|function_call|tool_call)"'),
)
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


def _fin_json(texto: str, i: int) -> int:
    """Índice siguiente al objeto o lista JSON que empieza en ``texto[i]``, o -1 si no se
    cierra. Tiene en cuenta las cadenas y sus escapes."""
    pila = 0
    en_cadena = escape = False
    for j in range(i, len(texto)):
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


def _fin_parrafo(texto: str, i: int) -> int:
    m = _FIN_PARRAFO_RE.search(texto, i)
    return m.start() if m else len(texto)


def _es_llamada(fragmento: str) -> bool:
    return any(r.search(fragmento) for r in _LLAMADA_JSON_RES)


def _objetos_llamada(texto: str, c: Counter) -> str:
    """Quita los objetos JSON de primer nivel con forma de llamada a herramienta.

    Solo mira los de primer nivel (el objeto exterior entero, con los anidados dentro), así
    que el coste es lineal; un objeto sin cerrar llega hasta el final del párrafo.
    """
    salida: list[str] = []
    pos = 0
    while True:
        m = _INICIO_OBJETO_RE.search(texto, pos)
        if not m:
            break
        inicio = m.start()
        fin = _fin_json(texto, inicio)
        if fin == -1:
            fin = _fin_parrafo(texto, inicio)
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
    salida: list[str] = []
    pos = 0
    for m in _MARCA_HERRAMIENTA_RE.finditer(texto):
        if m.start() < pos:
            continue
        salida.append(texto[pos : m.start()])
        fin = m.end()
        resto = len(texto[fin:]) - len(texto[fin:].lstrip())
        if fin + resto < len(texto) and texto[fin + resto] in "[{":
            cierre = _fin_json(texto, fin + resto)
            fin = cierre if cierre != -1 else _fin_parrafo(texto, fin)
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

    texto = _BLOQUE_HERRAMIENTA_RE.sub(_retirar, texto)
    texto = _APERTURA_HERRAMIENTA_RE.sub(_retirar, texto)
    texto = _CIERRE_HERRAMIENTA_RE.sub(_quitar, texto)
    texto = _HARMONY_RE.sub(_retirar, texto)
    texto = _TOKEN_ESPECIAL_RE.sub(_quitar, texto)
    texto = _marcas(texto, c)
    return _objetos_llamada(texto, c)


# ------------------------------------------------------------------- bloques de código

_VALLA_RE = re.compile(r"^( {0,3})(`{3,}|~{3,})(.*)$")
_CIERRE_VALLA_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*$")


def _vallas(texto: str, c: Counter, *, cerrar: bool) -> str:
    """Bloques de código delimitados por vallas (``` o ~~~).

    Quita los que se anuncian como llamada a herramienta y los que han quedado vacíos (por
    ejemplo, después de quitar el JSON de una llamada). Con ``cerrar``, cierra el último si
    quedó abierto: un bloque sin cerrar llega hasta el final del documento.
    """
    lineas = texto.split("\n")
    salida: list[str] = []
    i = 0
    while i < len(lineas):
        m = _VALLA_RE.match(lineas[i])
        if not m or (m.group(2)[0] == "`" and "`" in m.group(3)):
            salida.append(lineas[i])
            i += 1
            continue
        valla = m.group(2)
        j = i + 1
        while j < len(lineas):
            mc = _CIERRE_VALLA_RE.match(lineas[j])
            if mc and mc.group(1)[0] == valla[0] and len(mc.group(1)) >= len(valla):
                break
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
            salida.extend(contenido)
            if cerrada:
                salida.append(lineas[j])
            elif cerrar:
                salida.append(m.group(1) + valla)
                c["bloques_codigo_sin_cerrar"] += 1
        i = j + 1
    return "\n".join(salida)


# ---------------------------------------------------------------------------- 3. HTML

_ELEMENTOS_HTML: Final = frozenset(
    """a abbr acronym address applet area article aside audio b base basefont bdi bdo
    bgsound big blink blockquote body br button canvas caption center cite code col colgroup
    data datalist dd del details dfn dialog dir div dl dt em embed fieldset figcaption figure
    font footer form frame frameset h1 h2 h3 h4 h5 h6 head header hgroup hr html i iframe
    image img input ins isindex kbd keygen label legend li link listing main map mark marquee
    math menu menuitem meta meter nav nobr noembed noframes noscript object ol optgroup option
    output p param picture plaintext portal pre progress q rb rp rt rtc ruby s samp script
    search section select slot small source span strike strong style sub summary sup svg
    table tbody td template textarea tfoot th thead time title tr track tt u ul var video wbr
    xmp""".split()
)
_NOMBRES_HTML = "|".join(sorted(_ELEMENTOS_HTML, key=len, reverse=True))
# Elementos cuyo contenido no es texto para el lector: se quitan enteros.
_BLOQUE_HTML_RE = re.compile(
    r"<\s*(?P<n>script|style|iframe|noscript|template|svg|math|object|xmp|noembed|"
    r"noframes|textarea|title)\b[^>]*>.*?<\s*/\s*(?P=n)\s*>",
    re.I | re.S,
)
_COMENTARIO_RE = re.compile(r"<!--.*?-->", re.S)
_CDATA_RE = re.compile(r"<!\[CDATA\[.*?\]\]>", re.S)
_DECLARACION_RE = re.compile(r"<![A-Za-z][^>]*>")
_INSTRUCCION_RE = re.compile(r"<\?.*?\?>", re.S)
# Etiqueta sin atributos sola en un código en línea: se queda su nombre (`<script>` -> `script`).
_ETIQUETA_EN_CODIGO_RE = re.compile(
    r"`[ ]?<(/?)(" + _NOMBRES_HTML + r")[ ]*/?>[ ]?`", re.I
)
_ETIQUETA_RE = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9-]*)((?:\s[^<>]*)?)/?>")
# «<» que abre algo que un visor de Markdown leería como HTML aunque no se cierre
# («<script» al final de una línea abre un bloque HTML que llega hasta «</script>»).
_APERTURA_HTML_RE = re.compile(r"<(?=/?(?:" + _NOMBRES_HTML + r")(?![\w-])|[!?])", re.I)


def _html(texto: str, c: Counter) -> str:
    def _quitar(_m: re.Match) -> str:
        c["html"] += 1
        return ""

    def _etiqueta(m: re.Match) -> str:
        nombre, atributos = m.group(2), m.group(3)
        if nombre.lower() in _ELEMENTOS_HTML or "=" in atributos:
            c["html"] += 1
            return ""
        return m.group(0)  # elemento desconocido sin atributos: inerte

    def _en_codigo(m: re.Match) -> str:
        c["html"] += 1
        return f"`{m.group(1)}{m.group(2)}`"

    # Primero las etiquetas solas en código: si no, «`<script>` … `</script>`» se tomaría
    # por un bloque script y se iría el texto de en medio.
    texto = _ETIQUETA_EN_CODIGO_RE.sub(_en_codigo, texto)
    for patron in (_COMENTARIO_RE, _CDATA_RE, _INSTRUCCION_RE, _BLOQUE_HTML_RE):
        texto = patron.sub(_quitar, texto)
    texto = _DECLARACION_RE.sub(_quitar, texto)
    texto = _ETIQUETA_RE.sub(_etiqueta, texto)
    return _APERTURA_HTML_RE.sub(_quitar, texto)


# ------------------------------------------------------------------------- 4. Markdown

# Texto de un enlace: corchetes anidados un nivel y escapes.
_TEXTO_MD = r"\[((?:[^\[\]\\]|\\.|\[(?:[^\[\]\\]|\\.)*\])*)\]"
# Destino: entre <…> (admite espacios) o sin espacios, con paréntesis equilibrados un nivel.
_DESTINO_MD = r"(<[^<>\n]*>|(?:[^\s()<>\\]|\\.|\((?:[^\s()\\]|\\.)*\))*)"
_TITULO_MD = r"""(?:\s+(?:"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|\((?:[^()\\]|\\.)*\)))?"""
_IMAGEN_RE = re.compile(
    r"!" + _TEXTO_MD + r"\(\s*" + _DESTINO_MD + _TITULO_MD + r"\s*\)"
)
_IMAGEN_REF_RE = re.compile(r"!" + _TEXTO_MD + r"(?:\[[^\[\]\n]*\])?")
_ENLACE_RE = re.compile(_TEXTO_MD + r"\(\s*" + _DESTINO_MD + _TITULO_MD + r"\s*\)")
_AUTOENLACE_RE = re.compile(r"<([A-Za-z][A-Za-z0-9+.-]{1,31}:[^<>\s]*)>")
_DEFINICION_RE = re.compile(
    r"^(?:[ ]{0,3}>[ ]?)*[ ]{0,3}\[[^\]\n]+\]:[ \t]*(?:\n[ \t]*)?(<[^<>\n]*>|\S+)"
    r"[^\n]*(?:\n|$)",
    re.M,
)
_PARECE_URL_RE = re.compile(r"^(?:[A-Za-z][A-Za-z0-9+.-]*:|//|www\.)", re.I)
_HOST_VALIDO_RE = re.compile(r"[a-z0-9.-]+")


def destino_oficial(destino: str) -> bool:
    """¿Es ``destino`` una URL ``http(s)`` a un dominio oficial del corpus (o subdominio)?

    Se analiza la URL en lugar de buscar el dominio en el texto, así que no pasan
    ``javascript:``, ``data:``, ``//otro``, los esquemas con entidades
    (``https&#58;//…``), las credenciales (``https://boe.es@otro``) ni ``boe.es.otro.com``.
    """
    d = destino.strip()
    if d.startswith("<") and d.endswith(">"):
        d = d[1:-1].strip()
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


def _markdown(texto: str, c: Counter) -> str:
    def _imagen(_m: re.Match) -> str:
        c["imagenes"] += 1
        return IMAGEN_RETIRADA

    def _enlace(m: re.Match) -> str:
        if destino_oficial(m.group(2)):
            return m.group(0)
        c["enlaces"] += 1
        return m.group(1)

    def _autoenlace(m: re.Match) -> str:
        # El corpus sale de PDF y no tiene autoenlaces: si hay uno, lo ha escrito el modelo,
        # así que no se le aplica la excepción de las URL de los fragmentos (paso 5).
        if destino_oficial(m.group(1)):
            return m.group(0)
        c["enlaces"] += 1
        return "`" + m.group(1).replace("`", "") + "`"

    def _definicion(m: re.Match) -> str:
        destino = m.group(1).strip("<>")
        if not _PARECE_URL_RE.match(destino) or destino_oficial(destino):
            return m.group(0)
        c["enlaces"] += 1
        return ""

    texto = _IMAGEN_RE.sub(_imagen, texto)
    texto = _IMAGEN_REF_RE.sub(_imagen, texto)
    texto = _DEFINICION_RE.sub(_definicion, texto)
    texto = _ENLACE_RE.sub(_enlace, texto)
    return _AUTOENLACE_RE.sub(_autoenlace, texto)


# ---------------------------------------------------------------------- 5. URL sueltas

# Las que un visor GFM convierte en enlace: http(s):// o www.
_URL_SUELTA_RE = re.compile(r"(?<![\w@`/])(?:https?://|www\.)[^\s<>`\"']+", re.I)
_PUNTUACION_FINAL = "?!.,:;*_~'\""
_CODIGO_EN_LINEA_RE = re.compile(r"(?<![\\`])(`+)(?!`)(.+?)(?<!`)\1(?!`)")


def _recortar_url(url: str) -> str:
    """Quita la puntuación final que GFM no considera parte del enlace."""
    while url:
        if url[-1] in _PUNTUACION_FINAL:
            url = url[:-1]
        elif url[-1] == ")" and url.count(")") > url.count("("):
            url = url[:-1]
        else:
            break
    return url


def _tramos_de_codigo(texto: str) -> list[tuple[int, int]]:
    """Intervalos que un visor muestra como código: bloques con valla y código en línea."""
    tramos: list[tuple[int, int]] = []
    pos = 0
    abierta: str | None = None
    inicio = 0
    for linea in texto.split("\n"):
        fin = pos + len(linea)
        m = _VALLA_RE.match(linea)
        if abierta is None and m:
            abierta, inicio = m.group(2), pos
        elif abierta is not None:
            mc = _CIERRE_VALLA_RE.match(linea)
            if mc and mc.group(1)[0] == abierta[0] and len(mc.group(1)) >= len(abierta):
                tramos.append((inicio, fin))
                abierta = None
        pos = fin + 1
    if abierta is not None:
        tramos.append((inicio, len(texto)))
    for m in _CODIGO_EN_LINEA_RE.finditer(texto):
        if "\n\n" not in m.group(0):
            tramos.append((m.start(), m.end()))
    return tramos


def _urls_sueltas(texto: str, fuentes_norm: str, c: Counter) -> str:
    tramos = _tramos_de_codigo(texto)
    salida: list[str] = []
    pos = 0
    for m in _URL_SUELTA_RE.finditer(texto):
        url = _recortar_url(m.group(0))
        if not url or any(a <= m.start() < b for a, b in tramos):
            continue
        clave = normalize(url)
        if destino_oficial(url) or (clave and clave in fuentes_norm):
            continue
        salida.append(texto[pos : m.start()])
        salida.append(f"`{url}`")
        c["urls"] += 1
        pos = m.start() + len(url)
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
    for _ in range(MAX_PASADAS):
        antes = t
        t = _herramientas(t, c)
        t = _vallas(t, c, cerrar=False)
        t = _html(t, c)
        t = _markdown(t, c)
        if t == antes:
            break
    else:
        t = _neutralizar_resto(t, c)
    fuentes_norm = "|".join(normalize(f) for f in fuentes)
    t = _urls_sueltas(t, fuentes_norm, c)
    t = _vallas(t, c, cerrar=True)
    return t, SaneadoStats(**c)
