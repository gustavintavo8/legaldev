"""Lista el trabajo pendiente del TFG agrupado por paquete de trabajo.

Recorre app/, tests/, eval/, data/ y docs/mcp/ (además de Makefile y pyproject.toml) y
recoge los marcadores formados por la palabra TODO seguida, sin espacio, de «(PTn)» o
«(PTn/ID)»: PTn es el paquete de trabajo de la planificación de la memoria (PT1 a PT10) e
ID el identificador del requisito, caso de uso, prueba, pregunta de investigación o criterio
de aceptación que motiva el hueco (RF-22, RNF-18, CU-07, PP-01, PI7, CA-09...). Sirve para
sincronizar el código con el anexo de pendientes de la memoria.

Uso:
    python tools/list_todos.py                 # texto agrupado por paquete
    python tools/list_todos.py --format markdown
    python tools/list_todos.py --format json
    python tools/list_todos.py --strict        # sale con 1 si hay marcadores mal formados
                                               # o identificadores que la memoria no define

Solo usa la biblioteca estándar.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = ("app", "tests", "eval", "data", "docs/mcp")
SCAN_FILES = ("Makefile", "pyproject.toml")
SUFFIXES = {".py", ".md", ".yaml", ".yml", ".json", ".toml", ".txt", ""}
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".ruff_cache", "runs"}

# Paquetes de trabajo (05-metodologia.tex, tab:met-plan). PT10 se numera al final pero se
# ejecuta antes de PT3 y PT4, que dependen de él.
PACKAGES = {
    "PT1": "Arranque y línea base",
    "PT2": "Servidor MCP",
    "PT3": "Mapeo a controles y evidencias",
    "PT4": "Conjunto de prueba",
    "PT5": "Líneas base y experimentos",
    "PT6": "Comprobación en CI (opcional)",
    "PT7": "Validación externa",
    "PT8": "Redacción y cierre técnico",
    "PT9": "Defensa",
    "PT10": "Segmentador v3",
}

# Identificadores definidos en la memoria que pueden motivar un hueco (copia de trabajo del
# 25/09/2026, comprobada con grep sobre capitulos/*.tex): RF-22..RF-28 y RNF-15..RNF-21
# (20-requisitos), más RF-18, el reindexado que está «implementado en parte» y completa
# PT10; CU-07..CU-09 (21-analisis); PP-01..PP-18 (24-pruebas, tab:pru-propuestas); PI1..PI8
# (24-pruebas; PI7 y PI8 son de PT5); CA-01..CA-11 (20-requisitos, tab:req-aceptacion: los
# del punto de partida pueden motivar un hueco, como CA-07 con el reindexado de PT10).
KNOWN_IDS = (
    {f"RF-{n}" for n in range(22, 29)}
    | {"RF-18"}
    | {f"RNF-{n}" for n in range(15, 22)}
    | {f"CU-{n:02d}" for n in range(7, 10)}
    | {f"PP-{n:02d}" for n in range(1, 19)}
    | {f"PI{n}" for n in range(1, 9)}
    | {f"CA-{n:02d}" for n in range(1, 12)}
)

_OPEN = "TODO" + "("  # partido para que este fichero no aparezca en su propio listado
MARKER_RE = re.compile(re.escape(_OPEN) + r"(PT\d+)(?:/([A-Z]+-?\d+))?\)[:\s]*")
LOOSE_RE = re.compile(re.escape(_OPEN) + r"PT")
# Lo que suele cerrar la línea tras el texto: comillas de cierre de una cadena, «),»,
# o la redirección de los echo del Makefile.
_TRAILER_RE = re.compile(r"""\s*["']\s*(?:\)\s*,?|,|>&2.*)?\s*$""")
_MAX_CONTINUATION = 6


@dataclass(frozen=True)
class Todo:
    package: str
    ident: str | None
    path: str
    line: int
    text: str


def _iter_files(root: Path):
    for name in SCAN_FILES:
        path = root / name
        if path.is_file():
            yield path
    for d in SCAN_DIRS:
        base = root / d
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if (
                path.is_file()
                and path.suffix in SUFFIXES
                and not SKIP_PARTS.intersection(path.relative_to(root).parts)
            ):
                yield path


def _clean(text: str) -> str:
    return _TRAILER_RE.sub("", text).strip()


def _continuation(lines: list[str], start: int, is_markdown: bool) -> list[str]:
    """Líneas siguientes que continúan el texto del marcador de la línea ``start``.

    Continúan: comentarios ``#`` y citas ``>`` con el mismo prefijo, trozos de cadena que
    empiezan por comillas y, en Markdown, el resto del párrafo. Se corta en la primera línea
    en blanco, de otro tipo o con otro marcador.
    """
    first = lines[start].strip()
    prefix = next((p for p in ("#", ">", '"') if first.startswith(p)), None)
    if prefix is None and not is_markdown:
        return []
    # Un trozo de cadena solo continúa si la línea acaba en comillas (concatenación implícita
    # de Python); una línea JSON acaba en «",» y no continúa.
    if prefix == '"' and not first.endswith('"'):
        return []
    out: list[str] = []
    for line in lines[start + 1 : start + 1 + _MAX_CONTINUATION]:
        s = line.strip()
        if not s or LOOSE_RE.search(s):
            break
        if prefix is None:
            if s.startswith(("#", "- ", "* ", "|", "```", ">")):
                break
            out.append(s)
            continue
        if not s.startswith(prefix):
            break
        body = s[len(prefix) :].strip()
        if not body:
            break
        if prefix != '"':
            out.append(body)
            continue
        out.append(_clean(body))
        if not s.endswith('"'):
            break
    return out


def scan(root: Path = ROOT) -> tuple[list[Todo], list[tuple[str, int, str]]]:
    """Devuelve (marcadores válidos, líneas con un marcador mal formado)."""
    todos: list[Todo] = []
    malformed: list[tuple[str, int, str]] = []
    for path in _iter_files(root):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        rel = path.relative_to(root).as_posix()
        is_markdown = path.suffix == ".md"
        for idx, line in enumerate(lines):
            if not LOOSE_RE.search(line):
                continue
            matches = list(MARKER_RE.finditer(line))
            if not matches:
                malformed.append((rel, idx + 1, line.strip()))
                continue
            # El texto de cada marcador llega hasta el siguiente marcador de la línea.
            ends = [n.start() for n in matches[1:]] + [len(line)]
            for m, end in zip(matches, ends):
                parts = [_clean(line[m.end() : end])]
                if end == len(line):
                    parts += _continuation(lines, idx, is_markdown)
                text = " ".join(p for p in parts if p)
                todos.append(Todo(m.group(1), m.group(2), rel, idx + 1, text))
    return todos, malformed


def _group(todos: list[Todo]) -> dict[str, list[Todo]]:
    groups: dict[str, list[Todo]] = defaultdict(list)
    for t in todos:
        groups[t.package].append(t)
    return dict(sorted(groups.items(), key=lambda kv: int(kv[0][2:])))


def _label(t: Todo) -> str:
    return f"{t.package}/{t.ident}" if t.ident else t.package


def render_text(todos: list[Todo]) -> str:
    out: list[str] = []
    for pkg, items in _group(todos).items():
        out.append(f"{pkg} {PACKAGES.get(pkg, '(paquete desconocido)')} [{len(items)}]")
        for t in items:
            out.append(f"  {_label(t):<12} {t.path}:{t.line}  {t.text}")
        out.append("")
    out.append(f"Total: {len(todos)} marcadores")
    return "\n".join(out)


def render_markdown(todos: list[Todo]) -> str:
    out: list[str] = []
    for pkg, items in _group(todos).items():
        out.append(
            f"## {pkg} {PACKAGES.get(pkg, '(paquete desconocido)')} ({len(items)})"
        )
        out.append("")
        for t in items:
            ident = f"**{t.ident}** " if t.ident else ""
            out.append(f"- {ident}{t.text} (`{t.path}:{t.line}`)")
        out.append("")
    out.append(f"Total: {len(todos)} marcadores")
    return "\n".join(out)


def problems(todos: list[Todo], malformed: list[tuple[str, int, str]]) -> list[str]:
    msgs = [f"{p}:{n}: marcador mal formado: {line}" for p, n, line in malformed]
    for t in todos:
        if t.package not in PACKAGES:
            msgs.append(f"{t.path}:{t.line}: paquete desconocido {t.package}")
        if t.ident and t.ident not in KNOWN_IDS:
            msgs.append(
                f"{t.path}:{t.line}: identificador no definido en la memoria {t.ident}"
            )
    return msgs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--format", choices=["text", "markdown", "json"], default="text"
    )
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    # En Windows, con la salida redirigida, stdout usa la página de códigos local.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    todos, malformed = scan(args.root)
    if args.format == "json":
        print(json.dumps([asdict(t) for t in todos], ensure_ascii=False, indent=2))
    elif args.format == "markdown":
        print(render_markdown(todos))
    else:
        print(render_text(todos))

    issues = problems(todos, malformed)
    for msg in issues:
        print(msg, file=sys.stderr)
    return 1 if args.strict and issues else 0


if __name__ == "__main__":
    sys.exit(main())
