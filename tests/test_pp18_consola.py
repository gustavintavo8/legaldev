"""Salida de los scripts de PP-18 en una consola que no es UTF-8.

En Windows, con la salida redirigida a un fichero o a una tubería, Python escribe con la
codificación local (cp1252), que no tiene «❮», «ᐸ» ni «〈». ``fuzz_tiempo.py`` imprime los
nombres de los 15 casos más lentos, y desde la 0.5.1 algunos llevan esos signos: según el
orden, que depende del ruido de las medidas, el script acababa con ``UnicodeEncodeError`` y
código 1, que una comprobación automática tomaría por una regresión de coste (revisión
independiente de la 0.5.1). ``fuzz.py`` y ``oraculo.py`` imprimen los casos que fallan con
``repr()``, que no escapa esos signos, así que se caían justo cuando tenían algo que
enseñar. Los tres pasan ahora su salida a UTF-8. Los scripts no se ejecutan de verdad:
se cargan y se sustituye lo que pinta con Node o mide tiempos.
"""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path

import pytest

PP18 = Path(__file__).resolve().parent.parent / "docs" / "mcp" / "pp18"
SIGNOS = "❮|x ᐸinvoke 〈/invoke〉"


def _cargar(nombre: str, monkeypatch):
    # fuzz.py añade su carpeta a sys.path para importar oraculo: se deja como estaba.
    monkeypatch.setattr(sys, "path", list(sys.path))
    spec = importlib.util.spec_from_file_location(
        f"pp18_{nombre}", PP18 / f"{nombre}.py"
    )
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _consola_cp1252(monkeypatch, *argv: str) -> io.TextIOWrapper:
    salida = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", salida)
    monkeypatch.setattr(sys, "argv", list(argv))
    return salida


def _texto(salida: io.TextIOWrapper) -> str:
    salida.flush()
    return salida.buffer.getvalue().decode(salida.encoding)


def test_fuzz_tiempo_prints_angle_signs_to_a_cp1252_console(monkeypatch):
    fuzz_tiempo = _cargar("fuzz_tiempo", monkeypatch)
    monkeypatch.setattr(fuzz_tiempo, "casos", lambda n: [(f"mezcla {SIGNOS!r}", "x")])
    salida = _consola_cp1252(monkeypatch, "fuzz_tiempo.py", "--n", "10")
    with pytest.raises(SystemExit) as fin:
        fuzz_tiempo.main()
    assert fin.value.code == 0
    assert SIGNOS in _texto(salida)


def test_fuzz_prints_a_failing_case_with_angle_signs_to_a_cp1252_console(monkeypatch):
    fuzz = _cargar("fuzz", monkeypatch)
    monkeypatch.setattr(fuzz, "fallos", lambda textos, web: [(SIGNOS, SIGNOS, ["x"])])
    monkeypatch.setattr(fuzz, "pintar_web", lambda textos, web: [{}] * len(textos))
    monkeypatch.setattr(fuzz, "fallos_web", lambda pintado: [])
    monkeypatch.setattr(fuzz, "fallos_mdit", lambda texto: [])
    salida = _consola_cp1252(monkeypatch, "fuzz.py", "codigo", "--casos", "3")
    with pytest.raises(SystemExit) as fin:
        fuzz.main()
    assert fin.value.code == 1
    assert SIGNOS in _texto(salida)


def test_oracle_prints_a_failing_case_with_angle_signs_to_a_cp1252_console(monkeypatch):
    oraculo = _cargar("oraculo", monkeypatch)
    resultado = {
        "casos": 1,
        "peligrosos_antes": {"marked": 1, "markdown-it": 1},
        "fallos": {"marked": [("g", SIGNOS, SIGNOS, ["x"])], "markdown-it": []},
        "difusos": [],
        "centinela": {"marked": [], "markdown-it": []},
    }
    monkeypatch.setattr(oraculo, "comprobar", lambda casos, web: resultado)
    monkeypatch.setattr(oraculo, "comprobar_legitimos", lambda textos, web: [])
    monkeypatch.setattr(oraculo, "informe_de_ejemplo", lambda web: None)
    salida = _consola_cp1252(monkeypatch, "oraculo.py", ".")
    with pytest.raises(SystemExit) as fin:
        oraculo.main()
    assert fin.value.code == 1
    assert SIGNOS in _texto(salida)
