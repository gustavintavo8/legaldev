"""Nombre del resultado de PP-18 con el modelo real (docs/mcp/pp18/medir.py).

El 13/11/2026 se midió dos veces en el mismo día, con ``ab3e3a3`` y con ``bd228c6``, y el
script escribía siempre ``resultado-AAAA-MM-DD.json``: la segunda medición habría pisado la
primera, que es la que documenta el README. Cada medición cuesta 12 llamadas a Groq, así
que el destino se elige antes de arrancar el servidor y nunca se sobrescribe. Solo se
prueba esa parte: el script no se ejecuta (arranca la API y lee el ``.env``).
"""

from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
FECHA = dt.date(2026, 11, 13)


def _medir():
    spec = importlib.util.spec_from_file_location(
        "pp18_medir", RAIZ / "docs" / "mcp" / "pp18" / "medir.py"
    )
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_default_name_carries_the_date_and_the_short_commit(tmp_path):
    medir = _medir()
    destino = medir.destino(None, FECHA, "bd228c6", carpeta=tmp_path)
    assert destino == tmp_path / "resultado-2026-11-13-bd228c6.json"


def test_default_folder_is_the_script_folder():
    medir = _medir()
    destino = medir.destino(None, FECHA, "abc1234")
    assert destino.parent == RAIZ / "docs" / "mcp" / "pp18"


def test_existing_results_are_never_overwritten(tmp_path):
    medir = _medir()
    (tmp_path / "resultado-2026-11-13-bd228c6.json").write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError, match="--salida"):
        medir.destino(None, FECHA, "bd228c6", carpeta=tmp_path)
    otra = tmp_path / "otra.json"
    otra.write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError):
        medir.destino(otra, FECHA, "bd228c6", carpeta=tmp_path)


def test_salida_chooses_another_file(tmp_path):
    medir = _medir()
    (tmp_path / "resultado-2026-11-13-bd228c6.json").write_text("{}", encoding="utf-8")
    salida = tmp_path / "resultado-2026-11-13-bd228c6-segunda.json"
    assert medir.destino(salida, FECHA, "bd228c6", carpeta=tmp_path) == salida


def test_the_results_already_in_the_repository_keep_their_names():
    """Los de antes de este cambio no se renombran: el README los cita así."""
    carpeta = RAIZ / "docs" / "mcp" / "pp18"
    assert (carpeta / "resultado-2026-11-12.json").is_file()
    assert (carpeta / "resultado-2026-11-13.json").is_file()
