"""Guarda de los marcadores de trabajo pendiente (tools/list_todos.py).

Mantiene que un grep de los marcadores de paquete dé la lista completa y bien formada: todo
marcador cita un paquete PT1-PT10 y, si lleva identificador, uno que la memoria define.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import list_todos  # noqa: E402

_OPEN = "TODO" + "("  # partido para que este fichero no cuente como marcador


def test_repository_markers_are_well_formed_and_known():
    todos, malformed = list_todos.scan()
    assert todos, "no se encontró ningún marcador de trabajo pendiente"
    assert list_todos.problems(todos, malformed) == []


def test_scan_parses_package_identifier_and_continuation(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "m.py").write_text(
        f"# {_OPEN}PT3/RF-26): primera línea\n# y su continuación\nx = 1\n"
        f'reason="{_OPEN}PT2): sin identificador"\n'
        f"# {_OPEN}PT2/XX-99): identificador inventado\n"
        f"# {_OPEN}PTX): mal formado\n"
        f"x = 2  # {_OPEN}PT4): uno; {_OPEN}PT5/PI1): dos\n",
        encoding="utf-8",
    )
    todos, malformed = list_todos.scan(tmp_path)
    assert [(t.package, t.ident, t.text) for t in todos] == [
        ("PT3", "RF-26", "primera línea y su continuación"),
        ("PT2", None, "sin identificador"),
        ("PT2", "XX-99", "identificador inventado"),
        ("PT4", None, "uno;"),
        ("PT5", "PI1", "dos"),
    ]
    assert len(malformed) == 1
    assert len(list_todos.problems(todos, malformed)) == 2


def test_known_identifiers_include_those_added_by_the_memoria():
    # Paquetes e identificadores que la memoria recortada añadió (grep sobre capitulos/*.tex).
    assert list(list_todos.PACKAGES) == [f"PT{n}" for n in range(1, 11)]
    added = {"RF-18", "RNF-18", "RNF-21", "PI7", "PI8", "PP-13", "PP-18", "CA-11"}
    assert added <= list_todos.KNOWN_IDS
    assert not {"PP-19", "RNF-22", "PI9", "CA-12"} & list_todos.KNOWN_IDS
