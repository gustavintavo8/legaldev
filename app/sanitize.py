"""Saneado de la salida del modelo (RNF-20; PP-18; ``docs/mcp/README.md``, «Salida segura»).

El informe que redacta el modelo llega a un navegador (la web lo pinta como Markdown con
marked), a integradores de la API y a asistentes con herramientas (por MCP), que lo pintan
con otros intérpretes. Quien controla parte del texto que lee el modelo (la descripción
libre del cuestionario o, si alguien lo envenenara, un fragmento del índice) puede pedirle
que escriba algo que se ejecuta al mostrarlo o al leerlo: una imagen que se descarga sola
con datos en la URL, un enlace cuyo destino no se ve, HTML, caracteres invisibles con
órdenes escondidas o un bloque que imita una llamada a una herramienta. ``sanear`` lo
neutraliza en el texto del modelo antes de verificar las citas y de guardar el resultado en
la caché común, así que REST y MCP reciben lo mismo. Las secciones que el código añade
detrás (cobertura, saneado, verificación de citas y el aviso) no pasan por aquí. El prompt
no cambia (decisión D-1).

Principio: codificar la salida, no detectar lo peligroso (OWASP). Hasta el 12/11/2026 el
saneado buscaba con expresiones regulares las imágenes, los enlaces, el HTML y las URL,
imitando la gramática de marked y de CommonMark. Tres revisiones encontraron 10, 19 y 7
huecos: cada arreglo abría otros y, además, solo protegía frente a marked. Ahora no se busca
ninguna de esas construcciones: se escapan los caracteres que las abren, en todo el texto.

Qué hace, en este orden:

1. **Caracteres.** Primero se lleva el texto a una sola forma, la que leen el visor y el
   asistente: las formas de compatibilidad de ASCII (ancho completo «＜», formas pequeñas
   «﹤» y verticales) pasan al carácter ASCII que les da NFKC, y las referencias de carácter
   (``&lt;``, ``&#60;``, ``&#x202E;``, ``&ZeroWidthSpace;``…) se resuelven una vez, como
   hace el visor, salvo las que van escapadas. Sin esto, una llamada escrita con ``&lt;`` o
   con «＜» llegaba entera al asistente, y un carácter invisible escrito como referencia
   aparecía en la página (revisión de la codificación, 13/11/2026). Después normaliza los
   saltos de línea (CRLF y CR sueltos pasan a LF, como hace marked al pintar) y quita el
   guion blando, que es invisible y partía las palabras clave del paso 2
   (``citations.normalize`` también lo quita, así que las citas no cambian). Nada de esto
   cuenta como saneado. Quita las secuencias de escape ANSI y los caracteres de control
   (salvo el tabulador y el salto de línea), los de formato invisibles (ancho cero,
   dirección bidi, etiquetas Unicode) y los selectores de variación, salvo uno suelto detrás
   de un carácter visible (el de los emojis).
2. **Bloques que imitan llamadas a herramientas**, que pasan a «(bloque retirado)»:
   etiquetas de llamada al estilo XML (con espacio de nombres o sin él, y también sin el
   «>» que las cierra), el formato ``<function=…>`` de Llama (con cualquier nombre), los
   tokens especiales ``<|…|>``, el formato de gpt-oss (``to=functions.…``), las marcas
   ``[TOOL_CALLS]``, ``[ARGS]`` y similares, los objetos JSON con forma de llamada (nombre y
   argumentos, o ``tools/call``, en cualquier caja y también con las claves escritas con
   escapes ``\\u…``) y los bloques de código que se anuncian como llamada, también detrás de
   un marcador de lista o de cita. Esto no es para el visor sino para el asistente que lee
   el texto: escapar no le impide leer una llamada. Es una heurística para las formas
   conocidas, no una frontera (lo que no cubre, en el README). En estas reglas, y solo en
   ellas, cuentan como «<» y «>» los signos de un solo ángulo que se leen igual y que el
   paso 1 no lleva a ASCII (``_ANGULOS``: «‹›», «〈〉», «⟨⟩», «❮❯»…): la 0.5.0 entregaba
   la descripción al modelo con «‹» y «›», el modelo copió así una llamada y este paso no
   la reconocía (PP-18 repetida sobre la 0.5.0, 13/11/2026). Fuera de las llamadas esos
   signos no cambian ni se escapan. Se repite hasta que el texto no cambia, porque quitar
   algo puede formar otra (``<in<|x|>voke>``), como mucho ``MAX_PASADAS`` veces; si no
   converge, todos los signos de apertura que quedan pasan a ``RESPALDO``.
3. **Codificación.** Se pone una barra invertida delante de cada «<», «[» y «@», del «&»
   que va delante de «#» o de una letra o cifra (el de una referencia de carácter), del «:»
   de «://», de la segunda barra de «//» y del punto de «www.» (sin distinguir mayúsculas),
   salvo que ya vayan escapados (detrás de un número impar de barras invertidas). En
   cualquier intérprete que siga CommonMark, todo el HTML en bruto, los autoenlaces, los
   enlaces en línea y por referencia, las imágenes y las definiciones empiezan por «<» o por
   «[», así que ya no se forma ninguno, y ninguna referencia de carácter se resuelve. Los
   autoenlaces de GFM y de linkify (``https://``, ``ftp://``, ``www.``, ``//`` y los
   correos) tampoco: marked no los reconoce y markdown-it (desde la 13) parte el texto en
   cada escape y no enlaza lo que empieza justo detrás. El texto se ve igual fuera del
   código; dentro, los escapes se ven, y es solo cosmético. No hay excepción para el
   código: las diferencias entre lo que el saneado tomaba por código y lo que pintaba el
   visor son de donde salieron la mayoría de los huecos. Las barras invertidas del modelo
   no se duplican: «\\|» en una celda de tabla o «\\*» siguen siendo escapes (con «\\\\|»,
   marked parte la celda).
4. **Bloques de código sin cerrar**: se cierran, para que no se traguen las secciones que
   añade el código ni, por MCP, el JSON del resultado. Un bloque acaba en la primera línea
   que lo cierra para marked o para CommonMark, y si solo lo cierra para uno de los dos, esa
   línea se reescribe como la valla de apertura, para que cierre en los dos.

Lo que queda fuera (detalle en el README): un dominio sin esquema que escribe el modelo
(``evil.com/?d=…``) sigue siendo enlace en los visores con linkify en modo difuso. Hay que
pulsarlo y se ve a dónde lleva. Las casillas de las listas de tareas (``- [ ]``) se ven
como texto. Y el paso 2 no ve una llamada escrita de otra forma (en lenguaje natural, con
signos que se parecen a «<» y no están en ``_ANGULOS``, con dos niveles de referencias o
como un objeto JSON partido por una línea en blanco fuera de un bloque de código).

Coste: lineal. Los cierres de las etiquetas de llamada se buscan una vez para todo el texto
y se agrupan por nombre; el cierre de un objeto JSON se busca dentro de su párrafo; la
codificación es una sola expresión que solo empieza en el principio de cada tira de barras
invertidas. ``rag.run_pipeline_detailed`` lo llama en un hilo, pero una llamada a una
expresión regular no suelta el intérprete (GIL), así que importa que cada una sea lineal.
Lo que más cuesta son las 21 pasadas que fuerza un anidamiento adversario, porque en cada
una se recorren en Python las líneas y los objetos JSON: el peor caso conocido tarda unos
0,6 s con 32.000 caracteres (el doble con la máquina ocupada), sin parar el bucle de
eventos (``docs/mcp/pp18/fuzz_tiempo.py`` y ``tests/test_sanitize.py``, 13/11/2026).

Citas: ``citations.normalize`` quita las barras invertidas, así que una cita literal se
verifica igual sobre el texto saneado (``docs/mcp/pp18/corpus_identidad.py``).
"""

from __future__ import annotations

import re
import unicodedata
from bisect import bisect_left
from collections import Counter
from collections.abc import Callable
from html.entities import html5
from typing import Final

from app.models import SaneadoStats

BLOQUE_RETIRADO: Final = "(bloque retirado)"

# Límite de pasadas del paso 2; si el texto sigue cambiando (anidamiento adversario), los
# signos de apertura que quedan pasan a RESPALDO y ya no se puede formar ninguna etiqueta.
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
_GUION_BLANDO: Final = "­"
_SELECTORES_EMOJI: Final = frozenset("︎️")


def _ascii_de(punto: int) -> str | None:
    forma = unicodedata.normalize("NFKC", chr(punto))
    return forma if forma.isascii() else None


# Formas de compatibilidad de los caracteres ASCII (verticales, pequeñas y de ancho
# completo): NFKC las lleva al carácter ASCII («＜» a «<») y un asistente las lee igual. El
# índice no tiene ninguna y citations.normalize ya aplica NFKC, así que las citas no cambian.
_COMPATIBLES: Final = {
    punto: forma
    for punto in (*range(0xFE30, 0xFE70), *range(0xFF01, 0xFF5F))
    if (forma := _ascii_de(punto)) is not None
}
# Referencias de carácter: con nombre (de la tabla de HTML5, con «;»), decimales y
# hexadecimales, con cualquier número de cifras (CommonMark admite 7 y 6, pero marked deja
# pasar las demás y el navegador las resuelve). Solo las que no van escapadas, como en el
# visor: «\&lt;» se ve como «&lt;».
_REFERENCIA_RE = re.compile(
    r"(?<!\\)((?:\\\\)*+)&(#[xX][0-9a-fA-F]++|#[0-9]++|[A-Za-z][A-Za-z0-9]{1,31});"
)
_NOMBRES: Final = {k[:-1]: v for k, v in html5.items() if k.endswith(";")}


def _resolver(m: re.Match) -> str:
    cuerpo = m.group(2)
    if cuerpo[0] != "#":
        caracter = _NOMBRES.get(cuerpo)
        return m.group(0) if caracter is None else m.group(1) + caracter
    hexadecimal = cuerpo[1] in "xX"
    cifras = cuerpo[2 if hexadecimal else 1 :].lstrip("0") or "0"
    punto = int(cifras, 16 if hexadecimal else 10) if len(cifras) <= 8 else -1
    if not 0 < punto <= 0x10FFFF or 0xD800 <= punto <= 0xDFFF:
        punto = 0xFFFD  # como CommonMark y los navegadores
    return m.group(1) + chr(punto)


def _una_forma(texto: str) -> str:
    """El texto con las formas de compatibilidad pasadas a ASCII y las referencias de
    carácter resueltas una vez (paso 1 de la cabecera). Las formas se pasan antes y después:
    «＆lt;» forma una referencia y «&#xFF1C;» da una forma de compatibilidad."""
    texto = texto.translate(_COMPATIBLES)
    return _REFERENCIA_RE.sub(_resolver, texto).translate(_COMPATIBLES)


def _es_selector(ch: str) -> bool:
    o = ord(ch)
    return 0xFE00 <= o <= 0xFE0F or 0xE0100 <= o <= 0xE01EF or 0x180B <= o <= 0x180F


def _es_invisible(ch: str) -> bool:
    return unicodedata.category(ch) == "Cf"


def _caracteres(texto: str, c: Counter) -> str:
    def _ansi(_m: re.Match) -> str:
        c["caracteres_control"] += 1
        return ""

    # Primero, lo que resuelven los lectores: una referencia puede dar un carácter invisible,
    # de control o un «\r», que se tratan abajo como los demás.
    texto = _una_forma(texto)
    # marked normaliza igual antes de pintar. Sin esto, «```\r» no cerraba un bloque para el
    # saneado y sí para el visor, y la valla que se añadía al final metía en un bloque de
    # código las secciones del informe.
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


# --------------------------------------------------------- 2. llamadas a herramientas


def _buscador(texto: str, aguja: re.Pattern) -> Callable[[int], int]:
    """Posición de la siguiente coincidencia de ``aguja`` desde ``i``, o -1, sin volver a
    recorrer lo ya recorrido: si la última búsqueda empezó en ``desde`` y encontró ``pos``,
    para todo ``i`` entre los dos la respuesta es la misma. Sin esto, mil aperturas seguidas
    sin «>» recorrían mil veces el resto."""
    ultima = [-1, -1]

    def buscar(i: int) -> int:
        desde, pos = ultima
        if desde != -1 and desde <= i and (pos == -1 or i <= pos):
            return pos
        m = aguja.search(texto, i)
        pos = m.start() if m else -1
        ultima[0], ultima[1] = i, pos
        return pos

    return buscar


_FIN_PARRAFO_RE = re.compile(r"\n[ \t]*\n")
_ESPACIOS_RE = re.compile(r"\s*")


def _fin_parrafo(texto: str, i: int) -> int:
    m = _FIN_PARRAFO_RE.search(texto, i)
    return m.start() if m else len(texto)


def _quitar_bloques(
    texto: str,
    apertura: re.Pattern,
    cierre: re.Pattern,
    nombre: Callable[[re.Match], str],
    c: Counter,
) -> str:
    """Quita cada bloque «apertura … cierre del mismo nombre» (el primer cierre detrás), en
    tiempo lineal. La etiqueta de apertura acaba en el siguiente «>» o signo que se lee como
    él (``_ANGULOS``); sin cierre, el bloque llega hasta el final de su párrafo, y sin
    ningún «>» detrás, también. Antes, sin «>» detrás no se quitaba esa apertura ni ninguna
    de las siguientes: bastaba con poner la llamada al final del informe (revisión de la
    codificación, 13/11/2026).

    Los cierres se buscan una vez para todo el texto y se agrupan por nombre (en minúsculas,
    con su espacio de nombres); cada apertura busca el suyo con una bisección. Antes se
    compilaba y se buscaba una expresión por nombre, guardada en una caché sin límite: con
    miles de nombres distintos («<n1:invoke>», «<n2:invoke>»…) el coste era cuadrático y la
    memoria del proceso crecía con cada petición (comprobación del 12/11/2026).
    """
    inicios: dict[str, list[int]] = {}
    finales: dict[str, list[int]] = {}
    for m in cierre.finditer(texto):
        clave = m.group(1).lower()
        inicios.setdefault(clave, []).append(m.start())
        finales.setdefault(clave, []).append(m.end())
    mayor = _buscador(texto, _MAYOR_RE)
    salida: list[str] = []
    pos = 0
    while m := apertura.search(texto, pos):
        gt = mayor(m.end())
        if gt == -1:
            # Ni esta ni las siguientes tienen un «>» detrás, ni por tanto un cierre.
            fin = _fin_parrafo(texto, m.end())
        else:
            fin_etiqueta = gt + 1
            clave = nombre(m).lower()
            posiciones = inicios.get(clave, [])
            k = bisect_left(posiciones, fin_etiqueta)
            if k < len(posiciones):
                fin = finales[clave][k]
            else:
                fin = _fin_parrafo(texto, fin_etiqueta)
        salida.append(texto[pos : m.start()])
        salida.append(BLOQUE_RETIRADO)
        c["bloques_herramienta"] += 1
        pos = fin
    salida.append(texto[pos:])
    return "".join(salida)


# Signos de un solo ángulo que se leen como «<» y «>» y que el paso 1 no lleva a ASCII (las
# formas de ancho completo y pequeñas, «＜» y «﹤», ya son «<» ahí). Las reglas de este paso
# los toman por «<» y «>», solo para reconocer y retirar llamadas: fuera de ellas no cambian
# y la codificación no los toca. La 0.5.0 entregaba la descripción al modelo con «‹» y «›»,
# el modelo copió así la carga P06 y este paso no la reconocía (PP-18 repetida sobre la
# 0.5.0, 13/11/2026). Están los que se confunden con «<» y «>» y los corchetes angulares,
# con las formas que NFKC lleva a uno de ellos («〈» U+2329 y «︿» U+FE3F dan «〈» U+3008),
# porque el oráculo pasa el texto por NFKC; tests/test_sanitize.py comprueba que no falta
# ninguna. Quedan fuera los dobles: «» son las comillas del español (un informe puede decir
# «invoke» o «tool_use» entre comillas), y «《》» o «⟪⟫» no se leen como un «<». Tampoco
# están los signos de relación (≺ ≻) ni los triángulos. La lista no es exhaustiva: lo que se
# parezca a «<» y no esté aquí es el residual del README («Lo que no cubre»).
_ANGULOS: Final[tuple[tuple[str, str], ...]] = (
    ("\u2039", "\u203a"),  # ‹ › comillas angulares simples (las de la 0.5.0)
    ("\u3008", "\u3009"),  # 〈 〉 corchetes angulares
    ("\u2329", "\u232a"),  # U+2329 y U+232A: los mismos, técnicos (NFKC)
    ("\ufe3f", "\ufe40"),  # ︿ ﹀ los mismos, verticales (NFKC: U+3008 y U+3009)
    ("\u27e8", "\u27e9"),  # ⟨ ⟩ corchetes angulares matemáticos
    ("\u276c", "\u276d"),  # ❬ ❭ ornamentos
    ("\u276e", "\u276f"),  # ❮ ❯ ornamentos (comillas angulares gruesas)
    ("\u2770", "\u2771"),  # ❰ ❱ ornamentos
    ("\u02c2", "\u02c3"),  # ˂ ˃ puntas de flecha modificadoras
    ("\u1438", "\u1433"),  # ᐸ ᐳ sílabas PA y PO del silabario canadiense
    ("\u29fc", "\u29fd"),  # ⧼ ⧽ corchetes angulares curvos
)
_APERTURAS: Final = "<" + "".join(a for a, _ in _ANGULOS)
_CIERRES: Final = ">" + "".join(c for _, c in _ANGULOS)
_MENOR = f"[{_APERTURAS}]"
_MAYOR = f"[{_CIERRES}]"
_MAYOR_RE = re.compile(_MAYOR)
# Si el paso 2 no converge, todos los signos de apertura pasan a este. No puede ser ninguno
# de _ANGULOS: hasta la 0.5.0 era «‹», que ahora este paso lee como «<», y al sanear otra
# vez se habrían retirado más cosas (sanear dejaría de ser idempotente). Tampoco un carácter
# que el paso 1 lleve a «<», que se quite por invisible o que escape la codificación. Es el
# carácter de sustitución, el que da también una referencia de carácter inválida.
RESPALDO: Final = "\ufffd"
_SIN_APERTURAS: Final = str.maketrans(dict.fromkeys(_APERTURAS, RESPALDO))

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
# Detrás del nombre, ni una letra ni una cifra, tampoco detrás de «_»: con «\b»,
# «</invoke_» no era un cierre, pero si el «_» cierra un énfasis el visor lo quita y se ve
# «</invoke» (fuzzers, 13/11/2026). Un marcador como «<parameter_name>» o «<invoke_url>»
# sigue sin ser una etiqueta de llamada.
_FIN_NOMBRE = r"(?!_*[A-Za-z0-9])"
_APERTURA_HERRAMIENTA_RE = re.compile(
    _MENOR + r"\s*(" + _NOMBRE_HERRAMIENTA + r")" + _FIN_NOMBRE, re.I
)
_CIERRE_HERRAMIENTA_RE = re.compile(
    _MENOR + r"\s*/\s*(" + _NOMBRE_HERRAMIENTA + r")\s*" + _MAYOR, re.I
)
# Los cierres sueltos que quedan se quitan también sin su «>» («</invoke» al final) y con
# la «/» escapada («<\/invoke>», que el visor pinta «</invoke>»).
_CIERRE_SUELTO_RE = re.compile(
    _MENOR + r"\s*\\?/\s*" + _NOMBRE_HERRAMIENTA + _FIN_NOMBRE + r"\s*" + _MAYOR + "?",
    re.I,
)
# Formato de Llama 3.1/3.2 para herramientas propias: <function=nombre>{…}</function>. El
# nombre puede llevar espacio de nombres o comillas («github/create_issue», «fs:borrar»,
# «"borrar"»): la etiqueta llega hasta el «>».
_APERTURA_FUNCION_RE = re.compile(_MENOR + r"\s*function\s*=", re.I)
_CIERRE_FUNCION_RE = re.compile(_MENOR + r"\s*/\s*(function)\s*" + _MAYOR, re.I)
# Tokens especiales de las plantillas de chat (<|im_start|>, <|call|>, <｜tool▁calls▁begin｜>).
# El «|» puede ir escapado: el visor quita la barra de «<\|…|>» y se ve el token
# (fuzzers, 13/11/2026). Dentro no puede haber otro signo de apertura ni de cierre: así un
# anidamiento se quita de dentro afuera, un nivel por pasada, sin dejar medias marcas.
_TOKEN_ESPECIAL_RE = re.compile(
    _MENOR + r"\\?[|｜][^" + _APERTURAS + _CIERRES + r"\n]{0,60}?[|｜]" + _MAYOR
)
# Formato harmony de gpt-oss: «to=functions.bash … {…}» hasta el final de la línea.
_HARMONY_RE = re.compile(
    r"\bto=(?:functions|browser|python|container|repo_browser)\b[^\n]*", re.I
)
# Marcas de llamada de Mistral y similares; se quita también lo que las sigue: el JSON, otra
# marca y, delante de [ARGS] o [CALL_ID], el nombre («[TOOL_CALLS]borrar[ARGS]{…}», v11).
_MARCA_HERRAMIENTA_RE = re.compile(
    r"\[/?(?:TOOL_CALLS?|TOOL_REQUEST|TOOL_RESULTS?|TOOL_CONTENT|AVAILABLE_TOOLS|ARGS"
    r"|CALL_ID)\]",
    re.I,
)
_NOMBRE_TRAS_MARCA_RE = re.compile(r"[\w.-]{1,64}[ \t]*(?=\[(?:ARGS|CALL_ID)\])", re.I)
# Un objeto JSON que empieza por una clave.
_INICIO_OBJETO_RE = re.compile(r'\{\s*"')
# Forma de llamada a herramienta dentro de un objeto JSON: un nombre y unos argumentos, en
# cualquier orden (dos búsquedas independientes, lineales; una con «(?=.*…)» recorría el
# resto del texto por cada clave), o una de las claves o tipos propios de una llamada. Sin
# distinguir mayúsculas: con «"Name"» y «"Arguments"» el objeto llegaba entero (revisión de
# la codificación, 13/11/2026).
_CLAVE_NOMBRE_RE = re.compile(
    r'"(?:name|tool|tool_name|function|recipient_name)"\s*:\s*"[^"]*"', re.I
)
_CLAVE_ARGUMENTOS_RE = re.compile(
    r'"(?:arguments|parameters|input|args|params)"\s*:', re.I
)
_LLAMADA_JSON_RES: Final = (
    re.compile(r'"method"\s*:\s*"tools/call"', re.I),
    re.compile(r'"(?:tool_calls|function_call|tool_use)"\s*:', re.I),
    re.compile(r'"type"\s*:\s*"(?:tool_use|function|function_call|tool_call)"', re.I),
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


def _puede_haber_llamada(texto: str) -> bool:
    """¿Tiene el texto alguna de las claves sin las que ningún objeto es una llamada? Si no,
    no hace falta recorrer sus objetos uno a uno (en Python): es lo que más cuesta en cada
    pasada con miles de «{"»."""
    texto = _decodificar_escapes(texto)
    return bool(_CLAVE_ARGUMENTOS_RE.search(texto)) or any(
        r.search(texto) for r in _LLAMADA_JSON_RES
    )


def _objetos_llamada(texto: str, c: Counter, *, por_parrafos: bool = True) -> str:
    """Quita los objetos JSON de primer nivel con forma de llamada a herramienta.

    Solo mira los de primer nivel (el objeto exterior entero, con los anidados dentro). El
    cierre se busca dentro del párrafo en que empieza el objeto: si no se cierra ahí (sin
    cerrar, o con una línea en blanco dentro), el objeto llega hasta el final del párrafo.
    Así cada carácter se recorre una vez; buscando el cierre en todo el texto, cada «{"» sin
    cerrar recorría el resto (2,58 s con 16.000 caracteres, medido el 12/11/2026). Sin
    ``por_parrafos`` (el contenido de un bloque de código, que los visores pintan entero), el
    cierre se busca hasta el final del texto; sigue siendo lineal, porque un objeto sin
    cerrar llega hasta el final y la búsqueda sigue desde ahí.
    """
    if not _puede_haber_llamada(texto):
        return texto
    salida: list[str] = []
    pos = 0
    tope = -1
    while m := _INICIO_OBJETO_RE.search(texto, pos):
        inicio = m.start()
        if inicio >= tope:  # el final del párrafo se calcula una vez por párrafo
            tope = _fin_parrafo(texto, inicio) if por_parrafos else len(texto)
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
        _CIERRE_HERRAMIENTA_RE,
        lambda m: m.group(1),
        c,
    )
    texto = _quitar_bloques(
        texto, _APERTURA_FUNCION_RE, _CIERRE_FUNCION_RE, lambda _m: "function", c
    )
    texto = _CIERRE_SUELTO_RE.sub(_quitar, texto)
    texto = _HARMONY_RE.sub(_retirar, texto)
    texto = _TOKEN_ESPECIAL_RE.sub(_quitar, texto)
    texto = _marcas(texto, c)
    return _objetos_llamada(texto, c)


# ------------------------------------------------------------------- bloques de código

_VALLA_RE = re.compile(r"^( {0,3})(`{3,}|~{3,})(.*)$")
_CIERRE_VALLA_COMMONMARK_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*$")
# Una valla con cualquier sangría y detrás de cualquier marcador de lista o de cita
# («- ```tool_code», «> ```tool_call», «1. ```function_call», la continuación sangrada de
# una lista anidada). Solo se mira si se anuncia como llamada (_vallas_de_llamada).
_VALLA_EN_CONTENEDOR_RE = re.compile(
    r"^((?:[ \t]*+(?:>|[-+*]|\d{1,9}[.)]))*+[ \t]*+)(`{3,}|~{3,})(.*)$"
)
_CIERRE_EN_CONTENEDOR_RE = re.compile(r"^[ \t>*+\-\d.)]*+(`{3,}|~{3,})[ \t]*$")


def _anuncia_llamada(info: str) -> bool:
    palabras = info.strip().split()
    return bool(palabras) and palabras[0].lower() in _INFO_HERRAMIENTA


def _cierra_en_contenedor(linea: str, valla: str) -> bool:
    m = _CIERRE_EN_CONTENEDOR_RE.match(linea)
    return bool(m and m.group(1)[0] == valla[0] and len(m.group(1)) >= len(valla))


def _vallas_de_llamada(lineas: list[str], c: Counter) -> list[str]:
    """Las líneas sin los bloques que se anuncian como llamada (```` ```tool_code ````),
    estén donde estén: con cualquier sangría, detrás de marcadores de lista o de cita y
    también dentro de lo que el saneado toma por otro bloque. Cada uno se retira hasta la
    primera línea que tenga, detrás de esos marcadores, una valla de cierre, y sin ella hasta
    el final, como uno de nivel superior; se conservan los marcadores, para que la lista
    siga siendo una lista.

    No depende de qué bloques ve el saneado, que no es lo mismo que ven los visores: los
    fuzzers encontraron una valla de llamada en una cita que el saneado tomaba por contenido
    de un bloque abierto con «~~~`» en una lista (revisión de la codificación, 13/11/2026).
    Retira de más si el prefijo no es de verdad un marcador o la línea es contenido de otro
    bloque, que es el lado seguro. Coste lineal: cada línea se mira una vez."""
    salida: list[str] = []
    i = 0
    while i < len(lineas):
        linea = lineas[i]
        m = (
            _VALLA_EN_CONTENEDOR_RE.match(linea)
            if "```" in linea or "~~~" in linea
            else None
        )
        if not (
            m
            and _anuncia_llamada(m.group(3))
            and not (m.group(2)[0] == "`" and "`" in m.group(3))
        ):
            salida.append(linea)
            i += 1
            continue
        j = i + 1
        while j < len(lineas) and not _cierra_en_contenedor(lineas[j], m.group(2)):
            j += 1
        c["bloques_herramienta"] += 1
        salida.append(m.group(1) + BLOQUE_RETIRADO)
        i = j + 1
    return salida


def _apertura_valla(linea: str) -> re.Match | None:
    """Línea que abre un bloque de código con valla, con la regla de CommonMark (y de
    marked): una valla de acentos graves no puede llevar un acento grave en la información
    (```` ```x` ```` es texto)."""
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
    # Las dos reglas piden al menos tres acentos o tildes, y lo más frecuente es que no estén.
    if valla[:3] not in linea:
        return False
    return _cierra_valla(linea, valla) or _cierra_valla_commonmark(linea, valla)


def _vallas(texto: str, c: Counter, *, cerrar: bool) -> str:
    """Bloques de código delimitados por vallas (``` o ~~~).

    Quita los que se anuncian como llamada a herramienta y los que han quedado vacíos (por
    ejemplo, después de quitar el JSON de una llamada). Con ``cerrar``, cierra el último si
    quedó abierto: un bloque sin cerrar llega hasta el final del documento.

    Un bloque acaba en la primera línea que lo cierra para marked o para CommonMark, y si
    solo lo cierra para una de las dos («```~», o «```» con un tabulador detrás), esa línea
    se reescribe como la valla de apertura, para que cierre en las dos. Si no, en una de las
    dos lecturas el bloque seguía abierto y se tragaba las secciones que añade el código.
    Las líneas del bloque no se tocan: la versión anterior las sangraba como la apertura y,
    con vallas abiertas detrás de un guion de lista, estropeaba listas legítimas
    (comprobación del 12/11/2026).

    Los que se anuncian como llamada se retiran antes, estén donde estén
    (``_vallas_de_llamada``), y dentro de un bloque el cierre de un objeto JSON se busca
    hasta el final del bloque, no del párrafo: los visores lo pintan entero, y con una línea
    en blanco dentro del objeto la llamada llegaba al asistente (revisión de la
    codificación, 13/11/2026).
    """
    lineas = _vallas_de_llamada(texto.split("\n"), c)
    salida: list[str] = []
    i = 0
    while i < len(lineas):
        if "```" not in lineas[i] and "~~~" not in lineas[i]:
            # Sin tres acentos o tildes no hay valla: se ahorran dos expresiones por línea
            # en cada pasada (el peor caso conocido son 21 pasadas con miles de líneas).
            salida.append(lineas[i])
            i += 1
            continue
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
        if cerrar and not _anuncia_llamada(m.group(3)):
            # Solo en la última llamada, fuera de las pasadas: retirar aquí pone texto en
            # lugar del objeto y no junta nada, así que no puede formar otra llamada, y
            # hacerlo en cada pasada doblaba el coste del peor caso.
            bloque = "\n".join(contenido)
            revisado = _objetos_llamada(bloque, c, por_parrafos=False)
            if revisado != bloque:
                contenido = revisado.split("\n")
        restante = "".join(contenido).strip()
        if _anuncia_llamada(m.group(3)):
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


# ---------------------------------------------------------------------- 3. codificación

# Lo que hay que escapar. La primera alternativa solo empieza al principio de una tira de
# barras invertidas («(?<!\\)»), que se toma entera y sin vuelta atrás («*+»): si no, cada
# barra de una tira larga que no va delante de nada que escapar volvía a recorrer el resto
# de la tira. La segunda barra de «//» y el punto de «www.» van siempre detrás de «/» y de
# «w», así que nunca están escapados. El «&» solo delante de «#», una letra o una cifra:
# así ninguna referencia de carácter se resuelve en ningún visor (marked deja pasar al
# navegador cualquier «&…;» de letras y cifras), y «&&» o «a & b» no cambian.
_CODIFICAR_RE = re.compile(
    r"(?<!\\)(\\*+)([<\[@]|:(?=//)|&(?=[#A-Za-z0-9]))|(?<=/)/|(?<=www)\.",
    re.I,
)


def _escapar(m: re.Match) -> str:
    if m.group(2) is None:
        return "\\" + m.group(0)
    barras = m.group(1)
    if len(barras) % 2:
        return m.group(0)  # ya va escapado
    return barras + "\\" + m.group(2)


def codificar(texto: str) -> str:
    """El texto con los caracteres que abren HTML, enlaces, imágenes, autoenlaces y
    referencias de carácter escapados (paso 3 de la cabecera). Es idempotente: lo ya
    escapado no cambia."""
    return _CODIFICAR_RE.sub(_escapar, texto)


# --------------------------------------------------------------------------- conjunto


def sanear(texto: str) -> tuple[str, SaneadoStats]:
    """Texto del modelo saneado y lo que se ha retirado, por tipo (RNF-20)."""
    c: Counter = Counter()
    t = _caracteres(texto, c)
    for _ in range(MAX_PASADAS):
        antes = t
        t = _vallas(_herramientas(t, c), c, cerrar=False)
        if t == antes:
            break
    else:
        # Anidamiento adversario: sin signos de apertura no se forma ninguna etiqueta ni
        # ningún token especial, y las demás reglas no quitan nada que pueda unir lo que
        # queda. RESPALDO no es ninguno de ellos, así que sanear otra vez no cambia nada.
        t = _vallas(_herramientas(t.translate(_SIN_APERTURAS), c), c, cerrar=False)
    t = codificar(t)
    t = _vallas(t, c, cerrar=True)
    return t, SaneadoStats(**c)
