"""Fuzzer de coste del saneado (RNF-20): ¿hay alguna entrada que lo haga lento?

``rag.run_pipeline_detailed`` sanea en un hilo, pero una llamada a una expresión regular no
suelta el GIL: si una tarda, el bucle de eventos (la API, ``/mcp``, la salud) espera. Mide
``sanear`` con textos de ``--n`` caracteres (32.000 por defecto, más de lo que cabe en
``GROQ_MAX_TOKENS``): repeticiones de unidades cortas de los caracteres que importan,
repeticiones de las unidades de las revisiones del 12/11/2026 (con las de los hallazgos 5 y
7 de la comprobación: miles de nombres distintos de etiqueta de llamada y «[a]: //x» en una
línea), mezclas aleatorias de esas unidades y texto aleatorio. Imprime los 15 peores
tiempos. Solo importa ``app.sanitize``. Uso, desde la raíz del repositorio:

    uv run python docs/mcp/pp18/fuzz_tiempo.py [--n 32000] [--limite 0.5]

Sale con 1 si alguno pasa de ``--limite`` segundos.
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.sanitize import sanear  # noqa: E402

ALFABETO = list("<a \"'>=/\n`[]():!\\{}|~hw.*_-@")
UNIDADES = [
    '<a "', "<a '", '<a "<a \'', '<a \'"', '<x title="', "<x/", '<x/y="', "](", "]: ", "[a](",
    "![a](", "`", "``", "` `", "https://", "www.", "https://a`", "https://a|", "[TOOL_CALLS]",
    '{"name": "x", "', "<function=x>", "<function=", "<!--", "<?", "<![CDATA[", "<script ",
    "~~~\n", "```\n", "```~\n", "- [r]: ", "[r]:\n", "a]: //x\n", "\\`", "`https://a` ",
    "<https://a`>", "[a](https://a`) ", "https://a/(", "https://a.)", "&a;", "<https://a>",
    "[a](https://a)https://b", "\\``", "\\", "\\\\x", "//", "/", "://", "wwww.", "@",
    "\\@", "<|", "<|x", "|>", "<invoke>", "</invoke>", "<invoke ", "to=functions.x ",
    "[a]: //x ", '{"', '{"\n\n', "- ```\n  ", "\r\n", "­", "​",
]  # fmt: skip


def _repetida(unidad: str, n: int) -> str:
    return (unidad * (n // len(unidad) + 1))[:n]


def casos(n: int) -> list[tuple[str, str]]:
    salida = []
    for k in (2, 3, 4):
        rng = random.Random(k)
        for _ in range(300):
            u = "".join(rng.choice(ALFABETO) for _ in range(k))
            salida.append((f"rep {u!r}", _repetida(u, n)))
    for u in UNIDADES:
        salida.append((f"rep {u!r}", _repetida(u, n)))
    # Hallazgo 5 de la comprobación: un nombre de cierre distinto por etiqueta.
    nombres = "".join(f"<n{k}:invoke>\n\n" for k in range(n // 10))
    salida.append(("nombres distintos", nombres[:n]))
    salida.append(("nombres distintos sin párrafos", nombres.replace("\n\n", " ")[:n]))
    rng = random.Random(7)
    for _ in range(300):
        u = "".join(rng.choices(UNIDADES, k=6))
        salida.append((f"mezcla {u!r}", _repetida(u, n)))
    for s in range(100):
        rng = random.Random(1000 + s)
        salida.append(
            (f"aleatorio {s}", "".join(rng.choice(ALFABETO) for _ in range(n)))
        )
    return salida


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--n", type=int, default=32000)
    p.add_argument("--limite", type=float, default=0.5)
    args = p.parse_args()
    tiempos = []
    for nombre, texto in casos(args.n):
        t0 = time.perf_counter()
        sanear(texto)
        tiempos.append((time.perf_counter() - t0, nombre))
    tiempos.sort(reverse=True)
    print(f"{len(tiempos)} textos de {args.n} caracteres")
    for dt, nombre in tiempos[:15]:
        print(f"{dt:.3f} s  {nombre[:90]}")
    sys.exit(1 if tiempos[0][0] > args.limite else 0)


if __name__ == "__main__":
    main()
