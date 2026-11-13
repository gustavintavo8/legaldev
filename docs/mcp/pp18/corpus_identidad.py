"""¿Se siguen verificando las citas literales del índice real después del saneado?

Comprobación de RNF-20: si el texto saneado de cada fragmento (app/sanitize.py) es igual al
original comparando con ``citations.normalize``, como la verificación de citas, una cita
literal de un fragmento real no puede dejar de verificarse por culpa del saneado. Desde la
codificación de la salida (12/11/2026) el saneado cambia muchos fragmentos (pone una barra
invertida delante de «<», «[», «@», el «&» de una referencia, «://», «//» y «www.»), y
``normalize`` quita esas barras. Desde el 13/11/2026 también resuelve las referencias de
carácter y pasa a ASCII las formas de ancho completo; el índice no tiene ninguna de las dos. Cuenta los cambiados por el saneado, cuántos lo hacen solo por la codificación y los
que quedan distintos tras ``normalize``, que tienen que ser 0.

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
from app.sanitize import codificar, sanear  # noqa: E402


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
    cambiados = solo_codificacion = distintos_normalizados = 0
    por_tipo: Counter = Counter()
    fuentes: Counter = Counter()
    for _id, texto, fuente in filas:
        saneado, stats = sanear(texto)
        if saneado != texto:
            cambiados += 1
            fuentes[fuente] += 1
            por_tipo.update({k: v for k, v in stats.model_dump().items() if v})
            if saneado == codificar(texto):
                solo_codificacion += 1
        if normalize(saneado) != normalize(texto):
            distintos_normalizados += 1
    print(f"Índice: {ruta} (corpus {version})")
    print(f"Fragmentos: {len(filas)}")
    print(f"Cambiados por el saneado: {cambiados}")
    print(f"  de ellos, solo por la codificación: {solo_codificacion}")
    print(f"Distintos tras normalize: {distintos_normalizados}")
    if por_tipo:
        print(f"Recuentos del saneado: {dict(por_tipo)}")
    print(f"Fuentes con fragmentos cambiados: {len(fuentes)}")
    print(f"Tiempo: {time.perf_counter() - t0:.1f} s")


if __name__ == "__main__":
    main()
