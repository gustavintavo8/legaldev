"""Oráculo doble del saneado (RNF-20): ¿pinta algo peligroso el texto saneado?

Sanea cada caso y lo pinta, antes y después, con dos intérpretes:

1. el visor de la web: marked 18.1.2 + DOMPurify 3.4.17, el ``renderMarkdown`` de
   ``legaldev-web/src/lib/markdown.ts`` (``visor_web.mjs``, con Node);
2. markdown-it-py en modo CommonMark con tablas, tachado y linkify (``tests/_pp18.py``), como
   los visores que siguen CommonMark y enlazan URL sueltas.

Un caso falla si, después del saneado, alguno de los dos pinta una imagen, un elemento que
carga algo solo (con ``style``, ``src``, ``srcset``, ``poster`` o ``background``; en
markdown-it, cualquier HTML en bruto, porque no lleva DOMPurify detrás) o un enlace cuyo
destino, absoluto o relativo al protocolo («//»), lleva a un host que no es un dominio
oficial del corpus. Los destinos relativos no cuentan. Los enlaces que linkify forma en modo
difuso con un dominio sin esquema se cuentan aparte: son el residual documentado. Desde la
revisión de la codificación (13/11/2026) también falla si en lo que pinta (con las
referencias de carácter resueltas y pasado por NFKC) se ve una llamada a una herramienta, un
bloque de código se anuncia como llamada (```` ```tool_code ````, también en una lista o una
cita) o aparece un carácter invisible o de control.

Comprueba además, con los dos intérpretes:

- que una línea puesta detrás del texto saneado, como las secciones que añade el código, no
  queda dentro de un bloque de código (``centinela``; los casos conocidos están en
  ``COSMETICOS`` de ``tests/_casos_saneado.py``). Si queda, es cosmético (se ve como
  código y no se ejecuta nada) y no cuenta como fallo: es el residual documentado de las
  listas con un bloque de código y líneas sin sangrar (uno en CommonMark y, desde la
  revisión de la codificación, uno de los fuzzers en marked);
- que los informes legítimos (``LEGITIMOS`` y, si existe, el informe de ejemplo de la web)
  conservan su estructura: las mismas etiquetas HTML en el mismo orden, sin contar los
  enlaces, que ya no se pintan, ni las casillas de las listas de tareas, que se ven como
  «[ ]» (los dos son cambios aceptados).

Casos: las cargas de PP-18 (``cargas.json``) y las entradas de ``tests/_casos_saneado.py``
(las tres revisiones del 12/11/2026 y las entradas de ataque de las pruebas anteriores).
Los fuzzers están en ``fuzz.py``.

Solo lee: no carga la configuración, el ``.env`` ni el índice, y de ``legaldev-web`` solo
usa sus ``node_modules`` (hace falta haber ejecutado ``npm ci`` allí) y su informe de
ejemplo. Necesita Node. Uso, desde la raíz del repositorio:

    uv run python docs/mcp/pp18/oraculo.py [ruta de legaldev-web]

Sale con 1 si algún caso falla con alguno de los dos intérpretes o si un informe legítimo
cambia de estructura.
"""

from __future__ import annotations

import json
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))

from app.sanitize import sanear  # noqa: E402
from tests import _casos_saneado, _pp18  # noqa: E402

CENTINELA = "\n\n## Verificación de citas\nCENTINELA"


# ------------------------------------------------------------------- marked + DOMPurify


def pintar_web(textos: list[str], web: Path) -> list[dict]:
    """Pinta los textos con el visor de la web, en tandas para no pasar el límite de la
    entrada estándar."""
    salida: list[dict] = []
    for i in range(0, len(textos), 2000):
        r = subprocess.run(
            ["node", str(Path(__file__).with_name("visor_web.mjs")), str(web)],
            input=json.dumps(textos[i : i + 2000]),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        salida.extend(json.loads(r.stdout))
    return salida


def fallos_web(pintado: dict) -> list[str]:
    """Imágenes, elementos que cargan algo y enlaces no oficiales, juzgados por el host que
    resuelve el navegador (con «www.boe.es%C2%A0"@otro», el host es «otro»); y llamadas,
    bloques anunciados como llamada e invisibles en lo que se ve."""
    fallos = [f"img {s}" for s in pintado["imgs"]]
    fallos += [f"carga {c}" for c in pintado["cargas"]]
    fallos += _pp18.formas_pintadas(pintado["textos"], pintado["lenguajes"])
    for e in pintado["links"]:
        if not e["href"] or e["protocolo"] is None:
            continue  # sin href, o una URL que el navegador no puede abrir
        if e["host"] == "legaldev.invalid" and not e["usuario"]:
            continue  # relativa: se queda en el sitio
        oficial = (
            e["protocolo"] in ("http:", "https:")
            and not e["usuario"]
            and _pp18.host_oficial(f"https://{e['host']}/")
        )
        if not oficial:
            fallos.append(f"enlace {e['href']}")
    return fallos


# --------------------------------------------------------------------------- markdown-it


def fallos_mdit(texto: str) -> list[str]:
    pintado = _pp18.pintar(texto)
    fallos = [f"img {s}" for s in pintado["imgs"]]
    fallos += [f"html {h[:60]!r}" for h in pintado["html"]]
    fallos += [f"enlace {h}" for h in pintado["enlaces"] if _pp18.destino_no_oficial(h)]
    fallos += _pp18.formas_pintadas(pintado["visible"], pintado["vallas"])
    return fallos


# ------------------------------------------------------------------------- estructura

# Lo que el saneado deja de pintar a propósito: los enlaces del modelo y las casillas de
# las listas de tareas («- [ ]»), porque se escapa su «[» (docs/mcp/README.md).
_SIN_CONTAR = frozenset({"a", "input"})


class _Etiquetas(HTMLParser):
    """Las etiquetas de apertura de un HTML, sin los enlaces ni las casillas."""

    def __init__(self) -> None:
        super().__init__()
        self.etiquetas: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag not in _SIN_CONTAR:
            self.etiquetas.append(tag)


def estructura(html: str) -> list[str]:
    lector = _Etiquetas()
    lector.feed(html)
    return lector.etiquetas


def informe_de_ejemplo(web: Path) -> str | None:
    ruta = web / "src" / "data" / "informe-ejemplo.json"
    if not ruta.exists():
        return None
    return json.loads(ruta.read_text(encoding="utf-8"))["respuesta_completa"]


# ------------------------------------------------------------------------------ informe


def comprobar(casos: list[tuple[str, str]], web: Path) -> dict:
    """Sanea y pinta los casos con los dos intérpretes. Devuelve los recuentos y los fallos."""
    textos = [t for _g, t in casos]
    saneados = [sanear(t)[0] for t in textos]
    antes_web = pintar_web(textos, web)
    despues_web = pintar_web(saneados, web)
    centinelas_web = pintar_web([s + CENTINELA for s in saneados], web)
    r = {
        "casos": len(casos),
        "peligrosos_antes": {"marked": 0, "markdown-it": 0},
        "fallos": {"marked": [], "markdown-it": []},
        "difusos": [],
        "centinela": {"marked": [], "markdown-it": []},
    }
    for (grupo, t), s, a, d, cw in zip(
        casos, saneados, antes_web, despues_web, centinelas_web, strict=True
    ):
        r["peligrosos_antes"]["marked"] += bool(fallos_web(a))
        r["peligrosos_antes"]["markdown-it"] += bool(fallos_mdit(t))
        if f := fallos_web(d):
            r["fallos"]["marked"].append((grupo, t, s, f))
        if f := fallos_mdit(s):
            r["fallos"]["markdown-it"].append((grupo, t, s, f))
        if difusos := _pp18.enlaces_difusos(s):
            r["difusos"].append((grupo, t, difusos))
        if "CENTINELA" not in cw["fuera_de_codigo"]:
            r["centinela"]["marked"].append((grupo, t))
        if "CENTINELA" not in _pp18.fuera_de_codigo(s + CENTINELA):
            r["centinela"]["markdown-it"].append((grupo, t))
    return r


def comprobar_legitimos(textos: list[str], web: Path) -> list[tuple[str, str]]:
    """Informes legítimos cuya estructura cambia con el saneado, con cada intérprete."""
    saneados = [sanear(t)[0] for t in textos]
    antes, despues = pintar_web(textos, web), pintar_web(saneados, web)
    cambios = []
    for t, s, a, d in zip(textos, saneados, antes, despues, strict=True):
        if estructura(a["html"]) != estructura(d["html"]):
            cambios.append(("marked", t))
        if estructura(_pp18._md().render(t)) != estructura(_pp18._md().render(s)):
            cambios.append(("markdown-it", t))
    return cambios


def _mostrar(titulo: str, lista: list, n: int = 10) -> None:
    print(f"{titulo}: {len(lista)}")
    for item in lista[:n]:
        print("   ", repr(item)[:220])


def main() -> None:
    web = Path(sys.argv[1] if len(sys.argv) > 1 else "../legaldev-web").resolve()
    casos = [("carga", c["texto"]) for c in _pp18.cargas()] + _casos_saneado.todos()
    r = comprobar(casos, web)
    legitimos = list(_casos_saneado.LEGITIMOS)
    if ejemplo := informe_de_ejemplo(web):
        legitimos.append(ejemplo)
    cambios = comprobar_legitimos(legitimos, web)
    print(f"Visor 1: marked + DOMPurify de {web}")
    print("Visor 2: markdown-it-py (CommonMark, tablas, tachado y linkify)")
    print(
        f"Casos: {r['casos']} ({len(_pp18.cargas())} cargas de PP-18 y "
        f"{r['casos'] - len(_pp18.cargas())} de tests/_casos_saneado.py)"
    )
    for visor in ("marked", "markdown-it"):
        print(
            f"[{visor}] con algo peligroso sin sanear: {r['peligrosos_antes'][visor]}"
        )
        _mostrar(
            f"[{visor}] con algo peligroso después del saneado", r["fallos"][visor]
        )
        _mostrar(
            f"[{visor}] centinela dentro de un bloque de código (cosmético)",
            r["centinela"][visor],
        )
    _mostrar("[markdown-it] enlaces difusos (residual documentado)", r["difusos"])
    _mostrar(
        f"Informes legítimos ({len(legitimos)}) que cambian de estructura", cambios
    )
    fallos = r["fallos"]["marked"] or r["fallos"]["markdown-it"] or cambios
    sys.exit(1 if fallos else 0)


if __name__ == "__main__":
    main()
