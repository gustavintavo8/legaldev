"""¿Deja el saneado (app/sanitize.py) igual el texto de los fragmentos del índice real?

Comprobación de RNF-20: si ``sanear`` no cambia ningún fragmento (comparando con
``citations.normalize``, como la verificación de citas), una cita literal de un fragmento real
no puede dejar de verificarse por culpa del saneado. Cada fragmento se sanea con él mismo como
fuente, que es lo que pasa en el análisis: sus URL vienen de los fragmentos que recibe el
modelo.

Solo lee: abre ``chroma.sqlite3`` en modo de solo lectura y no carga la configuración (ni el
``.env``) ni los modelos. Uso, desde la raíz del repositorio:

    uv run python docs/mcp/pp18/corpus_identidad.py [chroma_db/chroma.sqlite3]
"""

from __future__ import annotations

import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.citations import normalize  # noqa: E402
from app.sanitize import sanear  # noqa: E402


def main() -> None:
    ruta = Path(sys.argv[1] if len(sys.argv) > 1 else "chroma_db/chroma.sqlite3")
    con = sqlite3.connect(ruta.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        filas = con.execute(
            "SELECT m.id, m.string_value, s.string_value FROM embedding_metadata m "
            "LEFT JOIN embedding_metadata s ON s.id = m.id AND s.key = 'source' "
            "WHERE m.key = 'chroma:document'"
        ).fetchall()
        version = (ruta.parent / ".corpus_version").read_text(encoding="utf-8").strip()
    finally:
        con.close()
    t0 = time.perf_counter()
    cambiados = distintos_normalizados = 0
    por_tipo: Counter = Counter()
    fuentes: Counter = Counter()
    for _id, texto, fuente in filas:
        saneado, stats = sanear(texto, [texto])
        if saneado != texto:
            cambiados += 1
            fuentes[fuente] += 1
            por_tipo.update({k: v for k, v in stats.model_dump().items() if v})
        if normalize(saneado) != normalize(texto):
            distintos_normalizados += 1
    print(f"Índice: {ruta} (corpus {version})")
    print(f"Fragmentos: {len(filas)}")
    print(f"Cambiados por el saneado: {cambiados}")
    print(f"Distintos tras normalize: {distintos_normalizados}")
    if por_tipo:
        print(f"Por tipo: {dict(por_tipo)}")
        print(f"Por fuente: {dict(fuentes)}")
    print(f"Tiempo: {time.perf_counter() - t0:.1f} s")


if __name__ == "__main__":
    main()
