"""Script de tokens por análisis (tools/medir_tokens.py, 0.5.2).

Lo ejecuta el autor, con Groq. Aquí se prueba con dobles y sin red: la llamada mínima contra
un transporte HTTP simulado, el motor con el índice y el modelo simulados (el modelo
devuelve la respuesta con los metadatos que da ``ChatGroq``) y las esperas sin dormir.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from langchain_core.messages import AIMessage

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import medir_tokens  # noqa: E402

CLAVE = "gsk_prueba_SECRETA_no_debe_salir"
MODELO = "openai/gpt-oss-120b"
CABECERAS = {
    "x-ratelimit-limit-requests": "1000",
    "x-ratelimit-limit-tokens": "8000",
    "x-ratelimit-remaining-requests": "998",
    "x-ratelimit-remaining-tokens": "7900",
    "x-ratelimit-reset-requests": "2m52.8s",
    "x-ratelimit-reset-tokens": "750ms",
    "x-request-id": "req_no_interesa",
    "set-cookie": "__cf_bm=no-interesa",
}


def _transporte(peticiones: list[httpx.Request], *, status: int = 200):
    def responder(peticion: httpx.Request) -> httpx.Response:
        peticiones.append(peticion)
        return httpx.Response(
            status,
            headers=CABECERAS,
            json={
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "length",
                    }
                ],
                "usage": {
                    "prompt_tokens": 80,
                    "completion_tokens": 16,
                    "total_tokens": 96,
                },
            },
        )

    return httpx.Client(transport=httpx.MockTransport(responder))


def _respuesta(i: int, *, finish_reason: str = "stop") -> AIMessage:
    entrada, salida, razonamiento = 6000 + 100 * i, 1500 + 10 * i, 300
    return AIMessage(
        content="## RGPD\nTexto.\n\n## LOPDGDD\nTexto.",
        response_metadata={
            "finish_reason": finish_reason,
            "token_usage": {
                "prompt_tokens": entrada,
                "completion_tokens": salida,
                "total_tokens": entrada + salida,
                "completion_time": 1.25,
                "completion_tokens_details": {"reasoning_tokens": razonamiento},
                "texto": "no se guarda",
            },
        },
        usage_metadata={
            "input_tokens": entrada,
            "output_tokens": salida,
            "total_tokens": entrada + salida,
            "output_token_details": {"reasoning": razonamiento},
        },
    )


def _doc(source: str):
    d = MagicMock()
    d.page_content = f"Contenido de {source}"
    d.metadata = {"source": source, "doc_type": "normativa_europea"}
    return d


def _estado(respuestas: list | None = None, *, error: Exception | None = None):
    docs = [
        _doc("RGPD.pdf"),
        _doc("RGPD.pdf"),
        _doc("LOPDGDD.pdf"),
        _doc("LOPDGDD.pdf"),
    ]
    state = MagicMock()
    state.vectorstore.similarity_search_with_relevance_scores.return_value = [
        (d, 0.85) for d in docs
    ]
    llm = MagicMock()
    if error is not None:
        llm.invoke.side_effect = error
    else:
        llm.invoke.side_effect = respuestas or [_respuesta(i) for i in range(1, 21)]
    state.groq_client = llm
    state.groq_fallback_client = None
    state.indexed_normativas = frozenset({"RGPD", "LOPDGDD"})
    state.corpus_version = "corpus-prueba"
    return state, llm


# ------------------------------------------------------------------- límites


def test_limits_are_read_from_the_ratelimit_headers():
    lim = medir_tokens.limites_de_cabeceras(CABECERAS)
    assert lim == {
        "rpd": 1000,
        "tpm": 8000,
        "restantes_rpd": 998,
        "restantes_tpm": 7900,
        "reposicion_rpd": "2m52.8s",
        "reposicion_tpm": "750ms",
    }
    assert medir_tokens.limites_de_cabeceras({}) == dict.fromkeys(lim)
    assert (
        medir_tokens.limites_de_cabeceras({"x-ratelimit-limit-tokens": "x"})["tpm"]
        is None
    )


def test_minimal_call_uses_the_model_and_keeps_only_ratelimit_headers():
    peticiones: list[httpx.Request] = []
    lim = medir_tokens.leer_limites(
        _transporte(peticiones), CLAVE, MODELO, reasoning_effort="low"
    )
    assert len(peticiones) == 1
    peticion = peticiones[0]
    assert str(peticion.url) == medir_tokens.URL_GROQ
    assert peticion.headers["authorization"] == f"Bearer {CLAVE}"  # se envía...
    cuerpo = json.loads(peticion.content)
    assert cuerpo["model"] == MODELO
    assert cuerpo["max_tokens"] <= 16
    assert cuerpo["reasoning_effort"] == "low"
    assert lim["http"] == 200
    assert lim["tpm"] == 8000 and lim["rpd"] == 1000
    assert set(lim["cabeceras"]) == {
        k for k in CABECERAS if k.startswith("x-ratelimit-")
    }
    assert lim["usage_llamada_minima"] == {
        "prompt_tokens": 80,
        "completion_tokens": 16,
        "total_tokens": 96,
    }
    assert CLAVE not in json.dumps(lim)  # ...pero no se guarda


def test_reasoning_effort_only_goes_to_gpt_oss():
    peticiones: list[httpx.Request] = []
    medir_tokens.leer_limites(
        _transporte(peticiones), CLAVE, "qwen/qwen3-32b", reasoning_effort="low"
    )
    assert "reasoning_effort" not in json.loads(peticiones[0].content)


# ------------------------------------------------------------------- cálculo


def _informe(total: int, *, entrada: int | None = None, finish: str = "stop"):
    entrada = entrada if entrada is not None else total - 1000
    return {
        "resultado": "ok",
        "finish_reason": finish,
        "tokens": {
            "entrada": entrada,
            "salida": 1000,
            "razonamiento": None,
            "total": total,
        },
    }


def test_summary_has_mean_and_max_and_counts_cuts():
    informes = [
        _informe(7000),
        _informe(7600, finish="length"),
        {"resultado": "error:LLMUnavailableError", "causa": "RateLimitError"},
    ]
    res = medir_tokens.resumen(informes)
    assert res["n"] == 3 and res["con_informe"] == 2
    assert res["truncados"] == 1
    assert res["finish_reason"] == {"stop": 1, "length": 1}
    assert res["excluidos"] == {"error:LLMUnavailableError": 1}
    assert res["total"] == {"n": 2, "media": 7300.0, "max": 7600}
    assert res["razonamiento"] == {"n": 0, "media": None, "max": None}


def test_capacity_per_minute_and_per_day():
    res = medir_tokens.resumen(
        [_informe(3000, entrada=2000), _informe(3900, entrada=2800)]
    )
    lim = {"tpm": 8000, "rpd": 1000}

    cap = medir_tokens.capacidad(res, lim, rpm=30, tpd=200_000, max_tokens=8000)

    assert cap["por_minuto"]["por_tokens_con_maximo"] == 2  # 8000 // 3900
    assert cap["por_minuto"]["por_tokens_con_media"] == 2  # 8000 // 3450
    assert cap["por_minuto"]["reservando_max_tokens"] == 0  # 8000 // (2800 + 8000)
    assert cap["por_minuto"]["cifra"] == 2  # min(2, 30)
    assert cap["por_dia"]["por_tokens_con_maximo"] == 51  # 200000 // 3900
    assert cap["por_dia"]["por_tokens_con_media"] == 57  # 200000 // 3450
    assert cap["por_dia"]["cifra"] == 51  # min(1000, 51)


def test_unknown_limits_stay_null_and_do_not_enter_the_figure():
    res = medir_tokens.resumen([_informe(4000)])
    cap = medir_tokens.capacidad(res, {"tpm": 8000, "rpd": 1000})
    assert cap["por_minuto"]["por_peticiones"] is None
    assert cap["por_minuto"]["cifra"] == 2
    assert cap["por_dia"]["por_tokens_con_maximo"] is None
    assert cap["por_dia"]["cifra"] == 1000
    sin_informes = medir_tokens.capacidad(medir_tokens.resumen([]), {"tpm": 8000})
    assert sin_informes["por_minuto"]["cifra"] is None


# ------------------------------------------------------------------- medición


def test_measures_n_distinct_analyses_spaced_without_retries(mock_reranker):
    state, llm = _estado()
    esperas: list[float] = []

    informes, llamadas = medir_tokens.medir(
        state, 3, marca="m1", espera=90, dormir=esperas.append
    )

    assert llamadas == 3 and llm.invoke.call_count == 3  # una por análisis
    assert [f["resultado"] for f in informes] == ["ok", "ok", "ok"]
    assert len(esperas) == 2 and all(89 < e <= 90 for e in esperas)
    assert informes[0]["tokens"] == {
        "entrada": 6100,
        "salida": 1510,
        "razonamiento": 300,
        "total": 7610,
    }
    assert informes[0]["usage_groq"]["completion_tokens_details"] == {
        "reasoning_tokens": 300
    }
    assert "texto" not in informes[0]["usage_groq"]  # solo números
    # Cuestionarios distintos, con la marca: ninguno sale de la caché.
    mensajes = [str(c.args[0][1].content) for c in llm.invoke.call_args_list]
    assert all(f"m1-{i}" in m for i, m in zip((1, 2, 3), mensajes, strict=True))


def test_a_failed_analysis_is_recorded_without_its_message(mock_reranker):
    state, llm = _estado(error=Exception("detalle de la organización org_123"))
    informes, llamadas = medir_tokens.medir(state, 2, marca="m2", espera=0)
    assert llamadas == 2  # sin respaldo ni reintentos
    assert informes[0]["resultado"] == "error:LLMUnavailableError"
    assert informes[0]["causa"] == "Exception"
    assert "org_123" not in json.dumps(informes)


def test_ejecutar_end_to_end_with_doubles(mock_reranker, capsys):
    state, _ = _estado([_respuesta(1), _respuesta(2, finish_reason="length")])
    peticiones: list[httpx.Request] = []
    avisos: list[str] = []

    resultado = medir_tokens.ejecutar(
        2,
        clave=CLAVE,
        modelo=MODELO,
        max_tokens=8000,
        reasoning_effort="low",
        cliente_http=_transporte(peticiones),
        cargar_motor=lambda: state,
        espera=0,
        marca="m3",
        rpm=30,
        commit="abc1234",
        avisar=avisos.append,
    )

    assert resultado["llamadas_groq"] == 3  # la mínima y una por análisis
    assert resultado["resumen"]["truncados"] == 1
    assert resultado["limites"]["tpm"] == 8000
    assert resultado["capacidad"]["por_minuto"]["cifra"] == 1  # 8000 // 7720
    assert resultado["corpus_version"] == "corpus-prueba"
    texto = json.dumps(resultado, ensure_ascii=False)
    assert CLAVE not in texto
    assert CLAVE not in "".join(avisos) + capsys.readouterr().out
    assert "Texto." not in texto  # ni el informe


def test_a_bad_key_stops_before_loading_the_engine():
    cargar = MagicMock()
    with pytest.raises(RuntimeError, match="401"):
        medir_tokens.ejecutar(
            2,
            clave=CLAVE,
            modelo=MODELO,
            max_tokens=8000,
            reasoning_effort=None,
            cliente_http=_transporte([], status=401),
            cargar_motor=cargar,
        )
    cargar.assert_not_called()


@pytest.mark.parametrize("n", [0, 21])
def test_n_has_a_cap(n):
    with pytest.raises(ValueError):
        medir_tokens.ejecutar(
            n,
            clave=CLAVE,
            modelo=MODELO,
            max_tokens=8000,
            reasoning_effort=None,
            cliente_http=MagicMock(),
            cargar_motor=MagicMock(),
        )


# ------------------------------------------------------------------- programa


def test_existing_output_stops_before_any_call(tmp_path):
    existente = tmp_path / "resultado.json"
    existente.write_text("{}", encoding="utf-8")
    with patch.object(medir_tokens, "ejecutar") as ejecutar:
        assert medir_tokens.main(["--salida", str(existente)]) == 2
    ejecutar.assert_not_called()


def test_n_out_of_range_stops_before_any_call():
    with patch.object(medir_tokens, "ejecutar") as ejecutar:
        assert medir_tokens.main(["--n", "0"]) == 2
    ejecutar.assert_not_called()


def test_default_destination_has_date_and_commit(tmp_path):
    ruta = medir_tokens.destino(
        None, dt.date(2026, 11, 20), "abc1234", carpeta=tmp_path
    )
    assert ruta == tmp_path / "resultado-2026-11-20-abc1234.json"
    assert medir_tokens.destino(None, dt.date(2026, 11, 20), "x").parent == (
        medir_tokens.RAIZ / "docs" / "mcp" / "tokens"
    )


def test_the_engine_gets_a_groq_client_without_retries_or_fallback():
    def cargar(state):
        state.groq_client = "cliente con los reintentos por defecto"
        state.groq_fallback_client = "respaldo"
        state.corpus_version = "corpus-prueba"

    with (
        patch("app.main.load_engine", side_effect=cargar),
        patch("app.main._make_groq_client", return_value="sin reintentos") as fabrica,
    ):
        state = medir_tokens._cargar_motor()

    assert fabrica.call_args.kwargs == {"max_retries": 0}
    assert state.groq_client == "sin reintentos"
    assert state.groq_fallback_client is None


# ------------------------------------------------------------------- la clave no se muestra
#
# main() pone GROQ_FALLBACK_MODEL, GROQ_VERIFY_MODEL_ON_STARTUP y LOG_LEVEL en el entorno:
# patch.dict lo deja como estaba, para no cambiar la configuración de otras pruebas.


def _main_con_clave(clave, tmp_path, monkeypatch, **ejecutar_kwargs):
    from app.config import settings

    monkeypatch.setattr(settings, "groq_api_key", clave)
    with (
        patch.dict(os.environ),
        patch.object(medir_tokens, "ejecutar", **ejecutar_kwargs) as ejecutar,
    ):
        rc = medir_tokens.main(["--salida", str(tmp_path / "resultado.json")])
    return rc, ejecutar


@pytest.mark.parametrize(
    "clave",
    [
        CLAVE + " ",
        CLAVE + "\n",
        CLAVE + "\r",
        CLAVE + "\t",
        " " + CLAVE,
        CLAVE + "ñ",
        CLAVE + "\x01",
    ],
    ids=[
        "espacio",
        "salto",
        "retorno",
        "tabulador",
        "espacio-delante",
        "no-ascii",
        "control",
    ],
)
def test_a_malformed_key_stops_before_any_call_without_showing_it(
    clave, tmp_path, monkeypatch, capsys
):
    # httpx (h11) rechaza una cabecera así con un error cuyo mensaje lleva la cabecera entera,
    # «Bearer <clave>». Se para antes de la llamada mínima, sin repetir la clave.
    rc, ejecutar = _main_con_clave(clave, tmp_path, monkeypatch)
    assert rc == 2
    ejecutar.assert_not_called()
    salida = capsys.readouterr()
    assert "SECRETA" not in salida.out + salida.err
    assert "GROQ_API_KEY" in salida.err
    assert not (tmp_path / "resultado.json").exists()


@pytest.mark.parametrize(
    "error",
    [
        # El mensaje real de h11 lleva el repr de los bytes: «\n» como dos caracteres.
        httpx.LocalProtocolError(f"Illegal header value b'Bearer {CLAVE}\\n'"),
        httpx.ConnectError(f"conexión rechazada (Bearer {CLAVE})"),
        UnicodeEncodeError("ascii", CLAVE, 0, 1, f"Bearer {CLAVE}"),
    ],
    ids=["cabecera", "conexion", "codificacion"],
)
def test_an_http_error_is_shown_without_its_message(
    error, tmp_path, monkeypatch, capsys
):
    rc, _ = _main_con_clave(CLAVE, tmp_path, monkeypatch, side_effect=error)
    assert rc == 1
    err = capsys.readouterr().err
    assert "SECRETA" not in err
    assert type(error).__name__ in err


def test_own_errors_keep_their_message(tmp_path, monkeypatch, capsys):
    error = RuntimeError("La llamada mínima a Groq respondió 401: no se mide nada")
    rc, _ = _main_con_clave(CLAVE, tmp_path, monkeypatch, side_effect=error)
    assert rc == 1
    assert "respondió 401" in capsys.readouterr().err
