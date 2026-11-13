"""Fuzzers del saneado (RNF-20) con el oráculo doble de ``oraculo.py``.

Genera textos aleatorios con piezas de Markdown, los sanea y los pinta con marked +
DOMPurify (el visor de la web) y con markdown-it-py (CommonMark, tablas, tachado y linkify).
Cuenta los que pintan una imagen, un elemento que carga algo o un enlace no oficial, o en
los que se ve una llamada, un bloque anunciado como llamada o un invisible
(``oraculo.fallos_web`` y ``oraculo.fallos_mdit``), y aparte los enlaces difusos de
linkify (el residual documentado). Con ``--reducir``, reduce cada fallo al texto más corto
que sigue fallando. Son los fuzzers con los que la segunda revisión y su comprobación
(12/11/2026) buscaron huecos en el saneado anterior, con piezas nuevas con dominios que
linkify enlaza en modo difuso (``.com``, ``.co.uk``) y, desde la revisión de la
codificación (13/11/2026), con referencias de carácter, ancho completo, etiquetas de
llamada y vallas que se anuncian como llamada, y desde la 0.5.1, con los signos de un ángulo
que el saneado lee como «<» y «>» en las llamadas («‹», «〈», «ᐸ»…).

Tres modos:

- ``piezas``: cualquier mezcla de piezas sueltas (corchetes, acentos, URL, HTML, escapes…);
- ``lineas``: líneas con prefijos de lista, cita y sangría, vallas, URL y referencias;
- ``codigo``: acentos graves, escapes y URL, para el código en línea.

Uso, desde la raíz del repositorio (necesita Node y ``npm ci`` en legaldev-web):

    uv run python docs/mcp/pp18/fuzz.py piezas --semilla 1 --casos 4000 [--web RUTA] [--reducir]

Sale con 1 si algún caso falla con alguno de los dos intérpretes.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from oraculo import fallos_mdit, fallos_web, pintar_web  # noqa: E402

from app.sanitize import sanear  # noqa: E402
from tests import _pp18  # noqa: E402

URLS = [
    "https://p.exfil.example/?d=DATOS",
    "www.p.exfil.example/x",
    "ftp://p.exfil.example/",
    "//p.exfil.example/x",
    "https://p.exfil.com/?d=DATOS",
    "www.p.exfil.com/x",
    "datos@p.exfil.com",
    "mailto:datos@p.exfil.co.uk",
    "HTTPS://P.EXFIL.COM/x",
    "https://www.boe.es/",
    "p.exfil.com/?d=DATOS",  # dominio sin esquema: el residual de linkify en modo difuso
]
PIEZAS = [
    "`", "``", "```", "~", "~~", "~~~", "*", "_", "[", "]", "(", ")", "![", "](", "]:",
    "<", ">", "|", "\\", "\n", "\n\n", " ", "  ", "a", "x y", "- ", "> ", "1. ", "# ",
    "   ", "<https://www.boe.es/>", "<https://p.exfil.example/>", "<https://p.exfil.com/>",
    "[r]: https://p.exfil.example/x", "[r]: //p.exfil.com/x", "[r]", '"', "'", "@", "\t",
    '<span style="background:url(//p.exfil.example/i)">', "<spacer/style=x>", "<foo>",
    "|---|---|", "\\`", "&#47;&#47;p.exfil.example", "&#47;&#47;p.exfil.com", "&amp;",
    "&x;", "(a)", "((", "))", "[a](https://www.boe.es/)", "[t](https://www.boe.es/ 'x')",
    "<x@p.exfil.example>", "<x@p.exfil.com>", "a@b.c", ",", ".", "!", "?", "[^1]", "{",
    "}", ":", "/", "//", "www", "www.", "https:", "http", "\\\\", "\\[", "\\<", "\\@",
    "<img src=//p.exfil.com/i>", "<!--", "-->", "<script>", *URLS,
    # Revisión de la codificación (13/11/2026): referencias de carácter, ancho completo,
    # etiquetas de llamada sin «>» y vallas que se anuncian como llamada.
    "&lt;", "&gt;", "&#60;", "&#x3C;", "&#91;", "&#64;", "&#58;", "&#x202E;",
    "&ZeroWidthSpace;", "&amp;lt;", "＜", "＞", "［", "＠", "invoke", "<invoke ",
    "</invoke", "tool_code", "```tool_code\n", "- ```tool_call\n", "    ```tools\n",
    # PP-18 repetida sobre la 0.5.0: signos de un ángulo que se leen como «<» y «>».
    "‹", "›", "〈", "〉", "ᐸ", "ᐳ", "❮", "‹invoke ", "‹/invoke", "⟨|", "|⟩", "&lsaquo;",
]  # fmt: skip
PREFIJOS = [
    "",
    "",
    "",
    "- ",
    "  ",
    "1. ",
    "   ",
    "> ",
    "    ",
    "* ",
    "> - ",
    "  - ",
    "\t",
    " ",
]
CUERPOS = [
    "```", "```", "~~~", "````", "```~", "```\t", "``` x", "~~~`", "```js", "",
    "x https://p.exfil.example/x y", "texto", "`a`", "``", "`", "[r]: //p.exfil.example/x",
    "[a][r]", "[r]", "<foo>", "| a | b |", "|---|---|", "===", "---",
    "[BOE](https://www.boe.es/)", "![i](//p.exfil.example/i.png)", "[t](//p.exfil.com/t)",
    "*", "<https://p.exfil.example/>", "datos@p.exfil.com", "www.p.exfil.com/x", *URLS,
    "```tool_code", "~~~tool_call", "```function_call x", "&lt;invoke&gt;", "&#x202E;x",
    "＜invoke＞", "<invoke name=x", "‹invoke name=x›", "〈|call|〉", "ᐸ/invoke",
]  # fmt: skip
CODIGO = [
    "`", "`", "`", "``", "```", "\\", "\\`", " ", " ", "|", "*", "_", "~", "~~", "[",
    "]", "(", ")", "<", ">", "<https://www.boe.es/`>", "[a](https://www.boe.es/)",
    "[a](https://www.boe.es/ '`')", "[x`]", "\n", "x", "'", '"', "!", "&", ";", ":", "@",
    "#", "&lt;", "&#96;", "&#x60;", "＜", "‹", "›", *URLS,
]  # fmt: skip


def _piezas(rng: random.Random) -> str:
    return "".join(rng.choice(PIEZAS) for _ in range(rng.randint(3, 40)))


def _lineas(rng: random.Random) -> str:
    return "\n".join(
        rng.choice(PREFIJOS) + rng.choice(CUERPOS) for _ in range(rng.randint(2, 9))
    )


def _codigo(rng: random.Random) -> str:
    return "".join(rng.choice(CODIGO) for _ in range(rng.randint(3, 14)))


MODOS = {"piezas": _piezas, "lineas": _lineas, "codigo": _codigo}


def fallos(textos: list[str], web: Path) -> list[tuple[str, str, list[str]]]:
    """(texto, saneado, fallos) de los textos que fallan con alguno de los dos visores."""
    saneados = [sanear(t)[0] for t in textos]
    malos = []
    for t, s, p in zip(textos, saneados, pintar_web(saneados, web), strict=True):
        if f := fallos_web(p) + fallos_mdit(s):
            malos.append((t, s, f))
    return malos


def reducir(texto: str, web: Path) -> str:
    """El texto más corto que sigue fallando, quitando trozos de 8, 4, 2 y 1 caracteres."""
    while True:
        candidatos = list(
            dict.fromkeys(
                texto[:i] + texto[i + n :]
                for n in (8, 4, 2, 1)
                for i in range(len(texto) - n + 1)
            )
        )
        siguen = [t for t, _s, _f in fallos(candidatos, web)]
        if not siguen:
            return texto
        texto = min(siguen, key=len)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("modo", choices=sorted(MODOS))
    p.add_argument("--semilla", type=int, default=1)
    p.add_argument("--casos", type=int, default=4000)
    p.add_argument("--web", type=Path, default=Path("../legaldev-web"))
    p.add_argument("--reducir", action="store_true")
    args = p.parse_args()
    rng = random.Random(args.semilla)
    textos = list(dict.fromkeys(MODOS[args.modo](rng) for _ in range(args.casos)))
    web = args.web.resolve()
    malos = fallos(textos, web)
    difusos = sum(1 for t in textos if _pp18.enlaces_difusos(sanear(t)[0]))
    antes = sum(
        1
        for t, p in zip(textos, pintar_web(textos, web), strict=True)
        if fallos_web(p) or fallos_mdit(t)
    )
    print(
        f"modo={args.modo} semilla={args.semilla} casos={len(textos)} "
        f"peligrosos_sin_sanear={antes} fallos={len(malos)} difusos={difusos}"
    )
    for t, s, f in sorted(malos, key=lambda m: len(m[0]))[:6]:
        if args.reducir:
            t = reducir(t, web)
            s = sanear(t)[0]
        print("-" * 60)
        print("ENTRADA:", repr(t))
        print("SANEADO:", repr(s))
        print("FALLOS :", f)
    sys.exit(1 if malos else 0)


if __name__ == "__main__":
    main()
