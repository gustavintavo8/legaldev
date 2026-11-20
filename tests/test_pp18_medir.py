"""Nombre del resultado de PP-18 con el modelo real (docs/mcp/pp18/medir.py).

El 13/11/2026 se midió dos veces en el mismo día, con ``ab3e3a3`` y con ``bd228c6``, y el
script escribía siempre ``resultado-AAAA-MM-DD.json``: la segunda medición habría pisado la
primera, que es la que documenta el README. Cada medición cuesta 12 llamadas a Groq, así
que el destino se elige antes de arrancar el servidor y nunca se sobrescribe.

Desde la 0.5.2 se prueban también ``--informes-completos`` (la fila de cada llamada) y la
selección de ``--solo``. El script no se ejecuta: arranca la API y lee el ``.env``.
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


# ------------------------------------------------- --informes-completos (P05 y P12, 0.5.2)
#
# Para revisar a mano si P05 y P12 obedecen, sin copiarlas, las órdenes en lenguaje natural
# hace falta el informe entero; el resultado solo guardaba extractos. Con
# --informes-completos guarda el informe saneado y el structuredContent de cada carga.


def _mensaje_ok(informe: str = "## RGPD\nTexto del informe saneado.") -> dict:
    datos = {
        "informe": informe,
        "normativas_detectadas": ["RGPD"],
        "llm_model": "openai/gpt-oss-120b",
        "citas": {"total": 1, "verificadas": 1},
        "saneado": {},
    }
    return {
        "result": {
            "content": [{"type": "text", "text": informe}],
            "structuredContent": datos,
            "isError": False,
        }
    }


def _carga(ident: str = "P05") -> dict:
    return {"id": ident, "tipo": "comentario_html", "texto": "x", "medir": True}


def test_by_default_only_extracts_are_kept():
    fila = _medir().evaluar(_carga(), _mensaje_ok())
    assert "informe_completo" not in fila
    assert "structured_content" not in fila


def test_informes_completos_keeps_the_whole_sanitized_report_and_structured_content():
    mensaje = _mensaje_ok("## RGPD\n" + "línea del informe\n" * 200)
    fila = _medir().evaluar(_carga(), mensaje, completos=True)
    datos = mensaje["result"]["structuredContent"]
    assert fila["informe_completo"] == datos["informe"]
    assert fila["structured_content"] == datos
    assert fila["reproducida"] is False  # la puntuación no cambia


def test_errors_carry_no_report_even_with_informes_completos():
    medir = _medir()
    error = {
        "result": {
            "content": [{"type": "text", "text": "[MODELO_NO_DISPONIBLE] x"}],
            "isError": True,
        }
    }
    assert "informe_completo" not in medir.evaluar(_carga(), error, completos=True)
    jsonrpc = {"error": {"code": -32603, "message": "x"}}
    assert "informe_completo" not in medir.evaluar(_carga(), jsonrpc, completos=True)


def test_parser_accepts_solo_and_informes_completos():
    args = _medir()._parser().parse_args(["--solo", "P05,P12", "--informes-completos"])
    assert args.solo == "P05,P12"
    assert args.informes_completos is True
    assert _medir()._parser().parse_args([]).informes_completos is False


def test_solo_p05_p12_selects_those_two_loads():
    medir = _medir()
    seleccion = medir.seleccionar(medir.cargas(), "P05,P12")
    assert [c["id"] for c in seleccion] == ["P05", "P12"]
    assert len(medir.seleccionar(medir.cargas(), "")) == 12


def test_solo_with_an_unknown_or_unmeasured_id_fails_before_any_call():
    """P13 está en cargas.json pero no se mide con el modelo real: antes se descartaba sin
    decir nada y la ejecución no medía lo que se le pedía."""
    medir = _medir()
    with pytest.raises(ValueError, match="P13"):
        medir.seleccionar(medir.cargas(), "P05,P13")
    with pytest.raises(ValueError, match="P99"):
        medir.seleccionar(medir.cargas(), "P99")
