"""Tope diario por clave en /mcp (MCP_DAILY_LIMIT; RNF-21 y modelo de amenazas).

Se suma al cupo por minuto (PP-17, tests/test_mcp_security.py): cuenta por clave las
llamadas a analizar_proyecto, en el mismo almacén del limitador, y al agotarse responde 429
con Retry-After, como el resto de rechazos de la guarda.
"""

import logging
from unittest.mock import patch

import pytest

from app import config, mcp_guard
from app.config import Settings
from tests._mcp import message, rpc
from tests.conftest import MCP_TEST_KEYS

LISTAR = {"name": "listar_normativas", "arguments": {}}
CONSULTAR = {
    "name": "consultar_obligaciones",
    "arguments": {"normativa": "RGPD", "contexto": "cookies"},
}
DIA_S = 86_400


def _analizar(cuestionario):
    return {"name": "analizar_proyecto", "arguments": cuestionario}


def _limites(daily: str, rate: str = "100/minute"):
    """Cupo por minuto holgado salvo que la prueba diga otra cosa: así el 429 es del tope."""
    return patch.multiple(config.settings, rate_limit=rate, mcp_daily_limit=daily)


def _restantes(http, api_key: str) -> int:
    """Llamadas que le quedan hoy a ``api_key``, leídas del almacén del limitador."""
    clave = mcp_guard.rate_limit_key(api_key, "testclient")
    estrategia = http.app.state.limiter._limiter
    item = config.settings.mcp_daily_limit_item
    return estrategia.get_window_stats(item, clave, mcp_guard.DAILY_LIMIT_SCOPE)[1]


# ------------------------------------------------------------------------------ el tope


def test_daily_limit_rejects_with_429_and_retry_after(mcp_http, sample_input_dict):
    """Con «2/day», la tercera llamada de la clave recibe 429, con Retry-After de horas (no
    del cupo por minuto), código -32000 y un mensaje que dice qué se ha agotado."""
    with _limites("2/day"):
        for _ in range(2):
            ok = rpc(mcp_http, "tools/call", _analizar(sample_input_dict))
            assert ok.status_code == 200
            assert message(ok)["result"]["isError"] is False
        rechazo = rpc(mcp_http, "tools/call", _analizar(sample_input_dict))

    assert rechazo.status_code == 429
    assert 3600 < int(rechazo.headers["retry-after"]) <= DIA_S
    error = message(rechazo)["error"]
    assert error["code"] == -32000
    assert "Tope diario" in error["message"]
    assert "(2 al día)" in error["message"]
    assert message(rechazo)["id"] == 1


def test_cache_hits_count_towards_the_daily_limit(mcp_http, sample_input_dict):
    """Decisión documentada: la guarda cuenta antes de mirar la caché, así que la segunda
    llamada con el mismo cuestionario cuenta aunque no llame al modelo."""
    with _limites("2/day"):
        for _ in range(2):
            assert (
                rpc(mcp_http, "tools/call", _analizar(sample_input_dict)).status_code
                == 200
            )
        assert mcp_http.app.state.groq_client.invoke.call_count == 1  # 2.ª, de la caché
        assert (
            rpc(mcp_http, "tools/call", _analizar(sample_input_dict)).status_code == 429
        )


def test_invalid_questionnaires_count_too(mcp_http, sample_input_dict):
    """También cuenta un cuestionario inválido (resultado con isError): la guarda no valida."""
    invalido = {**sample_input_dict, "tipo_proyecto": "no-existe"}
    with _limites("1/day"):
        primera = rpc(mcp_http, "tools/call", _analizar(invalido))
        assert primera.status_code == 200
        assert message(primera)["result"]["isError"] is True
        assert (
            rpc(mcp_http, "tools/call", _analizar(sample_input_dict)).status_code == 429
        )


def test_daily_limit_only_counts_analizar_proyecto(mcp_http, sample_input_dict):
    """Las herramientas que solo leen el índice, tools/list y server/discover no gastan el
    tope y siguen respondiendo cuando se agota."""
    with _limites("1/day"):
        for _ in range(3):
            assert rpc(mcp_http, "tools/call", LISTAR).status_code == 200
            assert rpc(mcp_http, "tools/call", CONSULTAR).status_code == 200
        assert (
            rpc(mcp_http, "tools/call", _analizar(sample_input_dict)).status_code == 200
        )
        assert (
            rpc(mcp_http, "tools/call", _analizar(sample_input_dict)).status_code == 429
        )
        assert rpc(mcp_http, "server/discover").status_code == 200
        assert rpc(mcp_http, "tools/list").status_code == 200
        assert rpc(mcp_http, "tools/call", LISTAR).status_code == 200
        assert rpc(mcp_http, "tools/call", CONSULTAR).status_code == 200


def test_legacy_clients_are_counted_too(mcp_http, sample_input_dict):
    """Un cliente de la era del initialize, sin Mcp-Method ni Mcp-Name, tampoco se libra."""
    with _limites("1/day"):
        primera = rpc(
            mcp_http, "tools/call", _analizar(sample_input_dict), modern=False
        )
        assert primera.status_code == 200
        segunda = rpc(
            mcp_http, "tools/call", _analizar(sample_input_dict), modern=False
        )
        assert segunda.status_code == 429


# ----------------------------------------------------------------- aislamiento entre claves


def test_daily_limit_is_counted_per_key(mcp_http, sample_input_dict):
    """Agotar el tope de una clave no afecta a otra, aunque lleguen desde la misma IP."""
    primera, segunda = MCP_TEST_KEYS

    def llamar(key: str) -> int:
        return rpc(
            mcp_http, "tools/call", _analizar(sample_input_dict), key=key
        ).status_code

    with _limites("1/day"):
        assert llamar(primera) == 200
        assert llamar(primera) == 429
        assert _restantes(mcp_http, segunda) == 1
        assert llamar(segunda) == 200
        assert llamar(segunda) == 429
        assert llamar(primera) == 429


def test_daily_counter_stores_a_digest_not_the_key(mcp_http, sample_input_dict):
    with _limites("1/day"):
        rpc(mcp_http, "tools/call", _analizar(sample_input_dict))
    almacen = repr(vars(mcp_http.app.state.limiter._storage))
    assert mcp_guard.DAILY_LIMIT_SCOPE in almacen
    assert all(k not in almacen for k in MCP_TEST_KEYS)


# ---------------------------------------------------------------- relación con RATE_LIMIT


def test_daily_counter_is_not_shared_with_an_equal_rate_limit(
    mcp_http, sample_input_dict
):
    """RATE_LIMIT y MCP_DAILY_LIMIT con el mismo límite diario: si compartieran contador,
    cada llamada contaría dos veces y la segunda ya se rechazaría."""
    with _limites("3/day", rate="100/minute;3/day"):
        for _ in range(3):
            assert (
                rpc(mcp_http, "tools/call", _analizar(sample_input_dict)).status_code
                == 200
            )
        assert (
            rpc(mcp_http, "tools/call", _analizar(sample_input_dict)).status_code == 429
        )


def test_minute_limit_rejection_does_not_spend_the_daily_limit(
    mcp_http, sample_input_dict
):
    """El cupo por minuto se comprueba antes: una llamada frenada por él no gasta el tope."""
    with _limites("5/day", rate="1/minute"):
        assert (
            rpc(mcp_http, "tools/call", _analizar(sample_input_dict)).status_code == 200
        )
        frenada = rpc(mcp_http, "tools/call", _analizar(sample_input_dict))
        assert frenada.status_code == 429
        assert "Tope diario" not in message(frenada)["error"]["message"]
        assert _restantes(mcp_http, MCP_TEST_KEYS[0]) == 4


def test_daily_rejection_is_logged_with_its_own_reason(
    mcp_http, sample_input_dict, caplog
):
    caplog.set_level(logging.INFO, logger="app.mcp_guard")
    with _limites("1/day"):
        for _ in range(2):
            rpc(mcp_http, "tools/call", _analizar(sample_input_dict))
    assert '"reason": "DailyLimitExceeded"' in caplog.text
    assert '"status": 429' in caplog.text


# ------------------------------------------------------------------ ausencia y configuración


@pytest.mark.parametrize("valor", ["", "0", "0/day", "  "])
def test_no_daily_limit_when_empty_or_zero(valor):
    s = Settings(groq_api_key="x", mcp_daily_limit=valor)
    assert s.mcp_daily_limit == ""
    assert s.mcp_daily_limit_item is None


def test_without_daily_limit_only_the_rate_limit_applies(mcp_http, sample_input_dict):
    """Sin tope (el valor por defecto) no hay límite diario: solo cuenta RATE_LIMIT."""
    assert Settings(groq_api_key="x").mcp_daily_limit_item is None
    with _limites(""):
        for _ in range(6):
            assert (
                rpc(mcp_http, "tools/call", _analizar(sample_input_dict)).status_code
                == 200
            )
    almacen = repr(vars(mcp_http.app.state.limiter._storage))
    assert mcp_guard.DAILY_LIMIT_SCOPE not in almacen


@pytest.mark.parametrize(
    ("valor", "normal"),
    [("200", "200/day"), ("200/day", "200/day"), (" 200 per day ", "200/day")],
)
def test_daily_limit_accepts_a_number_per_day(valor, normal):
    s = Settings(groq_api_key="x", mcp_daily_limit=valor)
    assert s.mcp_daily_limit == normal
    assert s.mcp_daily_limit_item.amount == 200
    assert s.mcp_daily_limit_item.get_expiry() == DIA_S


@pytest.mark.parametrize(
    "valor", ["200/hour", "10/minute", "200/2 days", "1/day;2/day", "doscientos", "-1"]
)
def test_daily_limit_rejects_anything_but_one_limit_per_day(valor):
    """Falla al arrancar, como MCP_ALLOWED_ORIGINS con «*»: un valor que no es un tope diario
    no se interpreta a medias."""
    with pytest.raises(ValueError, match="MCP_DAILY_LIMIT"):
        Settings(groq_api_key="x", mcp_daily_limit=valor)
