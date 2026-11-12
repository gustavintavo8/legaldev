"""Script de latencia por MCP (tools/medir_latencia_mcp.py; RNF-19, PT2-latencia).

El cálculo se prueba aparte, y la medición entera contra ``/mcp`` en proceso
(``mcp_http``: motor y modelo simulados), sin esperas, sin red y sin Groq. La medición real
se hace contra el Space después de desplegar (``docs/mcp/README.md``, «Latencia»).
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import sys
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import medir_latencia_mcp as medir  # noqa: E402

CLAVE = "test-key-1"


@pytest.fixture(autouse=True)
def _fechas_distintas(monkeypatch):
    """Una fecha de generación distinta por informe.

    El script distingue un acierto de caché por ``generado_por_ia.fecha``. Con el modelo real
    dos informes están separados por segundos, pero el simulado tarda milisegundos y el reloj
    de Python 3.12 en Windows avanza a saltos de 15,6 ms: dos informes podrían tener la misma
    fecha y la prueba fallaría sin que el script lo hiciera.
    """
    from app import rag

    base = dt.datetime(2026, 11, 12, tzinfo=dt.UTC)
    contador = itertools.count()

    class _Reloj(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return base + dt.timedelta(milliseconds=next(contador))

    monkeypatch.setattr(rag, "datetime", _Reloj)


def _sin_espera(_segundos: float) -> None:
    pass


def _medir(mcp_http, **kwargs):
    opciones = {
        "n_frio": 2,
        "n_caliente": 2,
        "n_consultas": 2,
        "dormir": _sin_espera,
        "marca": "prueba",
    }
    opciones.update(kwargs)
    return medir.medir(mcp_http, "", CLAVE, **opciones)


# --------------------------------------------------------------------------- cálculo


def test_the_script_asks_for_the_revision_the_server_targets():
    from app.mcp_server import PROTOCOL_VERSION, TOOL_NAMES

    assert medir.PROTOCOLO == PROTOCOL_VERSION
    assert set(medir.HERRAMIENTAS) == set(TOOL_NAMES)


@pytest.mark.parametrize(
    ("valores", "p", "esperado"),
    [
        ([1.0], 50, 1.0),
        ([1.0], 95, 1.0),
        ([3.0, 1.0, 2.0], 50, 2.0),
        ([1.0, 2.0, 3.0, 4.0], 50, 2.0),  # ceil(0,5·4) = 2
        ([float(v) for v in range(1, 11)], 50, 5.0),
        ([float(v) for v in range(1, 11)], 95, 10.0),  # n < 20: el máximo
        ([float(v) for v in range(1, 21)], 95, 19.0),  # ceil(0,95·20) = 19
        ([float(v) for v in range(1, 101)], 95, 95.0),
        ([float(v) for v in range(1, 101)], 100, 100.0),
    ],
)
def test_nearest_rank_percentile(valores, p, esperado):
    assert medir.percentil(valores, p) == esperado


def test_percentile_of_an_empty_sample_is_none_and_p_is_bounded():
    assert medir.percentil([], 95) is None
    for p in (0, -1, 101):
        with pytest.raises(ValueError):
            medir.percentil([1.0], p)


def test_summary_rounds_and_handles_empty_series():
    assert medir.resumen([0.12345, 2.0, 1.0]) == {
        "n": 3,
        "p50": 1.0,
        "p95": 2.0,
        "min": 0.123,
        "max": 2.0,
    }
    assert medir.resumen([]) == {
        "n": 0,
        "p50": None,
        "p95": None,
        "min": None,
        "max": None,
    }


@pytest.mark.parametrize(
    "base",
    [
        "https://legaldev.example",
        "https://legaldev.example/",
        "https://legaldev.example/mcp",
        " https://legaldev.example/mcp/ ",
    ],
)
def test_mcp_url_from_base_with_or_without_path(base):
    assert medir.url_mcp(base) == "https://legaldev.example/mcp"


def test_cold_questionnaires_are_distinct_valid_and_tagged_with_the_run():
    from app.models import QuestionnaireInput

    lote = medir.cuestionarios(12, "abc123")
    assert len({json.dumps(c, sort_keys=True) for c in lote}) == 12
    assert all("abc123" in c["descripcion_breve"] for c in lote)
    otra = medir.cuestionarios(12, "def456")
    assert not {json.dumps(c, sort_keys=True) for c in lote} & {
        json.dumps(c, sort_keys=True) for c in otra
    }
    for c in lote:
        QuestionnaireInput.model_validate(c, strict=False)


def test_consultas_only_use_indexed_normativas():
    assert {n for n, _ in medir.consultas(10, {"RGPD", "LSSI"})} == {"RGPD", "LSSI"}
    assert medir.consultas(3, {"Otra"}) == [("Otra", "obligaciones principales")] * 3
    assert medir.consultas(3, set()) == []


@pytest.mark.parametrize(
    ("llamada", "motivo"),
    [
        (medir.Llamada(None, None, 1.0, "ConnectTimeout"), "fallo_red:ConnectTimeout"),
        (medir.Llamada(429, {"error": {"code": -32000}}, 1.0), "http_429"),
        (medir.Llamada(200, {"error": {"code": -32602}}, 1.0), "jsonrpc_-32602"),
        (
            medir.Llamada(
                200,
                {
                    "result": {
                        "isError": True,
                        "content": [
                            {"type": "text", "text": "[MODELO_NO_DISPONIBLE] x"}
                        ],
                    }
                },
                1.0,
            ),
            "is_error:MODELO_NO_DISPONIBLE",
        ),
        (medir.Llamada(200, {"result": {"content": []}}, 1.0), "ok"),
    ],
)
def test_classification_of_each_outcome(llamada, motivo):
    assert medir.clasificar(llamada)[0] == motivo


def test_limits_protect_the_quota():
    with pytest.raises(ValueError, match="--frio"):
        medir.medir(None, "", CLAVE, n_frio=medir.MAX_FRIO + 1)
    with pytest.raises(ValueError, match="--caliente"):
        medir.medir(None, "", CLAVE, n_frio=0, n_caliente=1)


def test_main_requires_url_and_key_and_never_prints_the_key(monkeypatch, capsys):
    monkeypatch.delenv("LEGALDEV_URL", raising=False)
    monkeypatch.setenv("LEGALDEV_API_KEY", "clave-secreta-de-prueba")
    assert medir.main(["--frio", "0", "--caliente", "0", "--consultas", "0"]) == 2
    salida = capsys.readouterr()
    assert "clave-secreta-de-prueba" not in salida.out + salida.err


def test_main_writes_the_report_without_the_key(
    mcp_http, monkeypatch, tmp_path, capsys
):
    from contextlib import nullcontext

    monkeypatch.setenv("LEGALDEV_URL", "http://testserver/mcp")
    monkeypatch.setenv("LEGALDEV_API_KEY", CLAVE)
    monkeypatch.setattr(medir.httpx, "Client", lambda **_: nullcontext(mcp_http))
    destino = tmp_path / "latencia" / "resultado.json"
    argv = [
        "--frio",
        "1",
        "--caliente",
        "1",
        "--consultas",
        "1",
        "--salida",
        str(destino),
    ]
    argv += ["--espera-frio", "0", "--espera-caliente", "0", "--espera-consulta", "0"]
    assert medir.main(argv) == 0
    salida = capsys.readouterr()
    informe = json.loads(destino.read_text(encoding="utf-8"))
    assert json.loads(salida.out) == informe
    assert informe["servidor"] == "http://testserver"
    assert [s["n"] for s in informe["series"].values()] == [1, 1, 1]
    assert CLAVE not in salida.out + salida.err + destino.read_text(encoding="utf-8")


# ------------------------------------------------------------- medición en proceso


def test_full_run_against_the_in_process_server(mcp_http):
    informe = _medir(mcp_http)
    series = informe["series"]
    assert series["analizar_frio"]["n"] == 2
    assert series["analizar_caliente"]["n"] == 2
    assert series["consultar_obligaciones"]["n"] == 2
    assert all(not s["excluidas"] for s in series.values())
    for s in series.values():
        assert s["min"] <= s["p50"] <= s["p95"] <= s["max"]

    calientes = [f for f in informe["llamadas"] if f["serie"] == "analizar_caliente"]
    frias = [f for f in informe["llamadas"] if f["serie"] == "analizar_frio"]
    assert all(f["desde_cache"] for f in calientes)
    assert [f["fecha_generacion"] for f in calientes] == [
        f["fecha_generacion"] for f in frias
    ]
    assert len({f["fecha_generacion"] for f in frias}) == 2
    assert informe["protocolo"] == "2026-07-28"
    assert informe["corpus_version"] == "abc123def456"
    assert informe["version_servidor"]
    assert set(informe["despertar"]) == {"health_s", "discover_s", "tools_list_s"}

    serializado = json.dumps(informe, ensure_ascii=False)
    assert CLAVE not in serializado
    assert "Medición de latencia" not in serializado  # no repite los cuestionarios


def test_a_rerun_with_a_new_mark_is_cold_again(mcp_http):
    primera = _medir(mcp_http, n_caliente=0, n_consultas=0, marca="uno")
    segunda = _medir(mcp_http, n_caliente=0, n_consultas=0, marca="dos")
    fechas = {f["fecha_generacion"] for f in primera["llamadas"] + segunda["llamadas"]}
    assert len(fechas) == 4
    assert segunda["series"]["analizar_frio"]["n"] == 2


def test_more_cold_calls_than_projects_are_still_cache_misses(mcp_http):
    # 6 cuestionarios con 5 proyectos: el sexto repite proyecto, pero lleva su número.
    informe = _medir(mcp_http, n_frio=6, n_caliente=0, n_consultas=0)
    frias = [f for f in informe["llamadas"] if f["serie"] == "analizar_frio"]
    assert informe["series"]["analizar_frio"]["n"] == 6
    assert len({f["fecha_generacion"] for f in frias}) == 6


def test_a_server_without_ai_marking_cannot_verify_warm_calls(mcp_http):
    # Un servidor anterior al marcado de C-05 (el Space antes de desplegar) no devuelve
    # generado_por_ia: las llamadas en frío cuentan, las de caliente no se pueden verificar.
    original = medir._resultado_tools

    def _sin_marca(estructurado):
        return {**original(estructurado), "fecha_generacion": None}

    with patch.object(medir, "_resultado_tools", side_effect=_sin_marca):
        informe = _medir(mcp_http, n_consultas=0)
    assert informe["series"]["analizar_frio"]["n"] == 2
    assert informe["series"]["analizar_caliente"]["excluidas"] == {
        "cache_no_verificable": 2
    }


def test_rate_limited_calls_are_excluded_and_counted(mcp_http):
    from app import config

    with patch.object(config.settings, "rate_limit", "3/minute"):
        informe = _medir(mcp_http, n_frio=2, n_caliente=3, n_consultas=1)
    caliente = informe["series"]["analizar_caliente"]
    assert caliente["n"] == 1
    assert caliente["excluidas"] == {"http_429": 2}
    # consultar_obligaciones no tiene cupo.
    assert informe["series"]["consultar_obligaciones"]["n"] == 1


def test_a_warm_call_that_is_not_a_cache_hit_is_excluded(mcp_http):
    from app import cache

    original = cache.get
    llamadas = {"n": 0}

    def _sin_cache_en_caliente(key):
        llamadas["n"] += 1
        # Las dos primeras búsquedas son las de frío; después, la caché «se ha vaciado».
        return original(key) if llamadas["n"] <= 2 else None

    with patch("app.cache.get", side_effect=_sin_cache_en_caliente):
        informe = _medir(mcp_http, n_consultas=0)
    assert informe["series"]["analizar_caliente"]["n"] == 0
    assert informe["series"]["analizar_caliente"]["excluidas"] == {"fuera_de_cache": 2}


def test_model_errors_in_cold_calls_leave_nothing_to_repeat(mcp_http):
    from app.errors import LLMUnavailableError

    with patch(
        "app.service._rag.run_pipeline_detailed",
        side_effect=LLMUnavailableError("caído"),
    ):
        informe = _medir(mcp_http, n_consultas=0)
    assert informe["series"]["analizar_frio"]["excluidas"] == {
        "is_error:MODELO_NO_DISPONIBLE": 2
    }
    assert informe["series"]["analizar_caliente"]["excluidas"] == {
        "sin_informe_en_frio": 2
    }


def test_a_wrong_key_stops_before_measuring(mcp_http):
    with pytest.raises(RuntimeError, match="server/discover"):
        medir.medir(mcp_http, "", "clave-falsa", n_frio=1, dormir=_sin_espera)


def test_spacing_is_measured_from_the_start_of_the_previous_call(mcp_http):
    esperas: list[float] = []
    _medir(
        mcp_http,
        n_frio=2,
        n_caliente=1,
        n_consultas=1,
        espera_frio=90,
        espera_caliente=8,
        espera_consulta=2,
        dormir=esperas.append,
    )
    # La primera llamada no espera; las siguientes, lo que falte hasta su espera.
    assert len(esperas) == 3
    assert 85 < esperas[0] <= 90
    assert 0 < esperas[1] <= 8
    assert 0 < esperas[2] <= 2


def test_health_wait_retries_until_the_server_answers():
    respuestas = iter([httpx.ConnectError("dormido"), 503, 200])

    def _manejador(request):
        r = next(respuestas)
        if isinstance(r, Exception):
            raise r
        return httpx.Response(r)

    cliente = httpx.Client(transport=httpx.MockTransport(_manejador))
    esperas: list[float] = []
    medir._esperar_salud(cliente, "http://x/health", esperas.append, 60)
    assert esperas == [5, 5]
