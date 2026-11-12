"""PP-18 (inyección indirecta): las cargas y un oráculo de «forma ejecutable».

El oráculo está escrito aparte de ``app/sanitize.py`` y sin importar nada de ``app`` (así lo
puede usar ``docs/mcp/pp18/medir.py`` sin cargar la configuración ni el ``.env``): si
compartiera las expresiones del saneado, la prueba solo comprobaría que el saneado coincide
consigo mismo. Es más amplio que el saneado donde puede serlo: no reconoce construcciones
enteras, sino sus piezas, vaya lo que vaya delante. Cualquier «![» es una imagen; el destino
de cualquier «](» se lee con paréntesis a cualquier profundidad; y cualquier «]:» seguido de
algo que lleva a otro sitio es una definición de referencia, esté en una lista, en una cita
o con sangría. Una forma ejecutable es algo que un visor de Markdown o un asistente
ejecutaría al recibir el texto, no una frase con una orden: una imagen, un enlace cuyo
destino no se ve, HTML activo, un bloque que imita una llamada a una herramienta,
caracteres invisibles o de control, un bloque de código sin cerrar o una URL clicable a un
dominio canario.
"""

from __future__ import annotations

import html
import json
import re
import unicodedata
from collections.abc import Iterator
from functools import cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

CARGAS_PATH = (
    Path(__file__).resolve().parent.parent / "docs" / "mcp" / "pp18" / "cargas.json"
)

# Copia de app.sanitize.DOMINIOS_OFICIALES (una prueba comprueba que son iguales).
DOMINIOS_OFICIALES = (
    "boe.es",
    "aepd.es",
    "sedeaepd.gob.es",
    "ccii.es",
    "eur-lex.europa.eu",
    "data.europa.eu",
)
DOMINIO_CANARIO = "exfil.example"


@cache
def cargas() -> tuple[dict[str, Any], ...]:
    datos = json.loads(CARGAS_PATH.read_text(encoding="utf-8"))
    return tuple(datos["cargas"])


def _oficial(url: str) -> bool:
    try:
        partes = urlsplit(url.strip().strip("<>"))
        host = partes.hostname or ""
    except ValueError:
        return False
    if partes.scheme.lower() not in ("http", "https") or "@" in partes.netloc:
        return False
    return any(host == d or host.endswith("." + d) for d in DOMINIOS_OFICIALES)


_IMAGEN = re.compile(r"!\[")
_COLA = re.compile(r"\]\(\s*")
_AUTOENLACE = re.compile(r"<([a-z][a-z0-9+.-]{1,31}:[^\s<>]*)>", re.I)
_DEFINICION = re.compile(r"\]:[ \t]*(?:\n[ \t]*)?(\S+)")
_FUERA = re.compile(r"[a-z][a-z0-9+.-]*:|//|www\.", re.I)


def _lleva_fuera(destino: str) -> bool:
    """¿Puede el destino llevar a otro sitio? Si empieza por un esquema, por «www.» o por dos
    barras, contando las invertidas como barras (como el navegador) y después de resolver
    entidades y escapes y de quitar espacios y caracteres de control."""
    d = html.unescape(destino).replace("\\", "/")
    d = "".join(ch for ch in d if ch > " ").lstrip("<")
    return bool(_FUERA.match(d))


def _destinos(texto: str) -> Iterator[tuple[str, bool]]:
    """Destino de cada «](» (entre <…>, o hasta el espacio o el «)» que no abre nadie, con
    paréntesis a cualquier profundidad) y si después, con un título opcional, viene «)»."""
    for m in _COLA.finditer(texto):
        i = j = m.end()
        if texto.startswith("<", i):
            j = texto.find(">", i)
            j = len(texto) if j == -1 else j + 1
        else:
            profundidad = 0
            while j < len(texto) and not texto[j].isspace():
                if texto[j] == "\\":
                    j += 2
                    continue
                if texto[j] == "(":
                    profundidad += 1
                elif texto[j] == ")":
                    if profundidad == 0:
                        break
                    profundidad -= 1
                j += 1
        destino, resto = texto[i:j], texto[j:].lstrip()
        if resto[:1] in ('"', "'", "("):
            cierre = resto.find(")" if resto[0] == "(" else resto[0], 1)
            resto = resto[cierre + 1 :].lstrip() if cierre != -1 else ""
        yield destino, resto.startswith(")")


_HTML = re.compile(
    r"<\s*/?\s*(?:script|img|iframe|svg|math|object|embed|link|meta|base|style|form|input|"
    r"button|a|video|audio|source|body|html|frame|frameset|details|marquee|template|"
    r"textarea|noscript|image)\b"
    r"|<[a-z][\w:-]*\s[^<>]*="
    r"|<!--|<!\[CDATA\[|<\?",
    re.I,
)
_HERRAMIENTA = re.compile(
    r"function_calls|<\s*/?\s*(?:[\w-]+:)?(?:invoke|parameter|tool_call|tool_use|tool_code|"
    r"tool_request|tool_result|function_call)\b"
    r"|<[|\uff5c]|[|\uff5c]>|\[/?TOOL_|\bto=functions\b|\"(?:arguments|parameters)\"\s*:"
    r"|\"tools/call\"|\"tool_calls\"\s*:|\"function_call\"\s*:",
    re.I,
)
# Formas que un visor GFM convierte en enlace: con esquema, con «www.» o como correo.
_URL_CANARIA = re.compile(
    r"(?:https?://|www\.)[^\s`<>]*"
    + re.escape(DOMINIO_CANARIO)
    + r"|[\w.+-]+@[\w.-]*"
    + re.escape(DOMINIO_CANARIO),
    re.I,
)
_CODIGO_EN_LINEA = re.compile(r"`[^`\n]+`")
_APERTURA = re.compile(r"^ {0,3}(`{3,}|~{3,})([^\n]*)$")
_CIERRE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*$")


def _valla_abierta(texto: str) -> bool:
    """¿Queda abierto al final un bloque de código? Regla de CommonMark: cierra una línea
    solo de acentos graves (o tildes), al menos tantos como en la apertura; dentro del
    bloque, una línea con texto detrás no cierra."""
    abierta: str | None = None
    for linea in texto.split("\n"):
        if abierta is None:
            m = _APERTURA.match(linea)
            if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
                abierta = m.group(1)
        else:
            m = _CIERRE.match(linea)
            if m and m.group(1)[0] == abierta[0] and len(m.group(1)) >= len(abierta):
                abierta = None
    return abierta is not None


def _caracteres(texto: str) -> list[str]:
    hallazgos = set()
    for i, ch in enumerate(texto):
        o = ord(ch)
        cat = unicodedata.category(ch)
        if cat == "Cc" and ch not in "\t\n\r":
            hallazgos.add("carácter de control")
        elif cat == "Cf" and ch != "\u00ad":
            hallazgos.add("carácter invisible")
        elif 0xE0100 <= o <= 0xE01EF or 0xFE00 <= o <= 0xFE0D:
            hallazgos.add("selector de variación")
        elif ch in "\ufe0e\ufe0f":
            anterior = texto[i - 1] if i else ""
            siguiente = texto[i + 1] if i + 1 < len(texto) else ""
            if not anterior or anterior.isspace() or siguiente in ("\ufe0e", "\ufe0f"):
                hallazgos.add("selector de variación")
    return sorted(hallazgos)


def formas_ejecutables(texto: str) -> list[str]:
    """Qué formas ejecutables hay en ``texto`` (lista vacía si ninguna)."""
    hallazgos: list[str] = []
    if _IMAGEN.search(texto):
        hallazgos.append("imagen Markdown")
    if any(
        not _oficial(destino) and (cerrada or _lleva_fuera(destino))
        for destino, cerrada in _destinos(texto)
    ):
        hallazgos.append("enlace a un destino no oficial")
    if any(not _oficial(m.group(1)) for m in _AUTOENLACE.finditer(texto)):
        hallazgos.append("autoenlace a un destino no oficial")
    if any(
        _lleva_fuera(m.group(1)) and not _oficial(m.group(1))
        for m in _DEFINICION.finditer(texto)
    ):
        hallazgos.append("definición de referencia a un destino no oficial")
    if _HTML.search(texto):
        hallazgos.append("HTML")
    if _HERRAMIENTA.search(texto):
        hallazgos.append("bloque de llamada a herramienta")
    sin_codigo = _CODIGO_EN_LINEA.sub("", texto)
    if _URL_CANARIA.search(sin_codigo):
        hallazgos.append("URL clicable a un dominio canario")
    if _valla_abierta(texto):
        hallazgos.append("bloque de código sin cerrar")
    hallazgos.extend(_caracteres(texto))
    return hallazgos


def cadenas(valor: Any) -> Iterator[str]:
    """Todas las cadenas de un valor JSON, también las claves."""
    if isinstance(valor, str):
        yield valor
    elif isinstance(valor, dict):
        for k, v in valor.items():
            yield str(k)
            yield from cadenas(v)
    elif isinstance(valor, list):
        for v in valor:
            yield from cadenas(v)


def formas_en(valor: Any) -> list[str]:
    """``formas_ejecutables`` de todas las cadenas de un valor JSON, sin repetir."""
    vistas: list[str] = []
    for s in cadenas(valor):
        for h in formas_ejecutables(s):
            if h not in vistas:
                vistas.append(h)
    return vistas
