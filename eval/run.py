"""Ejecución de la evaluación extendida sobre el conjunto acotado (esqueleto).

Uso previsto, desde la raíz del repositorio::

    python -m eval.run --config S --via rest --cases eval/cases/acotado --out eval/runs/<id>
    python -m eval.run --config S --via rest --out eval/runs/<id> --resume

Cada par (caso, configuración, vía) produce una línea en ``<out>/results.jsonl`` con:
id del caso, configuración, vía, ``corpus_version``, ``llm_model``, hash del conjunto de
casos, normativas y fragmentos recuperados, estadísticas de citas, informe, tokens de entrada
y salida, latencia y marca de tiempo. Las líneas nunca se reescriben.

``--resume`` reanuda una ejecución interrumpida (cuota de Groq agotada, 429, caída de red):
lee ``results.jsonl`` y omite los pares ya presentes, siempre que el hash del conjunto de
casos, el modelo y la versión del corpus coincidan con los de la ejecución original; si no
coinciden, aborta en lugar de mezclar resultados.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from eval.baselines import Configuracion

DEFAULT_CASES = Path("eval/cases/acotado")
RESULTS_FILE = "results.jsonl"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m eval.run",
        description="Evaluación extendida de LegalDev (B1, B2, B3 y S) sobre el conjunto acotado.",
    )
    parser.add_argument(
        "--config",
        choices=[c.value for c in Configuracion],
        action="append",
        help="Configuración a ejecutar; repetible. Por defecto, las cuatro.",
    )
    parser.add_argument(
        "--via",
        choices=["rest", "mcp"],
        default="rest",
        help="Vía de acceso para S (PI6); las líneas base solo admiten rest.",
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument(
        "--out", type=Path, help="Directorio de la ejecución en eval/runs/."
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reanuda la ejecución de --out omitiendo los pares ya registrados.",
    )
    return parser.parse_args(argv)


def verify_frozen(cases_dir: Path) -> str:
    """Devuelve el hash del conjunto de casos y aborta si no coincide con el congelado.

    Ver ``eval/cases/acotado/README.md``: el conjunto se congela con su hash antes de la
    primera ejecución y cualquier cambio posterior crea una versión nueva del conjunto.
    """
    # TODO(PT4): implementar (SHA-256 del contenido canónico de los casos, en orden de nombre).
    raise NotImplementedError


def main(argv: list[str] | None = None) -> int:
    parse_args(argv)
    # TODO(PT5/PI1): implementar el bucle casos x configuraciones sobre eval.baselines,
    # registrando tokens y latencia, y la vía MCP de S cuando exista el servidor.
    # TODO(PT5/PI6): ejecutar S por --via rest y --via mcp y comparar (equivalencia con LLM real).
    print(
        "Pendiente (PT5): eval/run.py no está implementado (ver eval/cases/acotado/README.md)",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
