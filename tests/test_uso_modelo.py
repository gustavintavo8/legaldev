"""Tokens y corte del informe (idea de prioridad 9 de la revisión «fable:código», 13/11/2026).

El motor lee de la respuesta del modelo por qué terminó (``finish_reason``) y cuántos tokens
gastó. Si se cortó por longitud (``length``), el informe lo dice en «Cobertura del análisis»
con un texto del código, y se cuenta en una métrica. Los tokens van al registro (sin texto
del usuario, PP-08), a ``PipelineResult`` y a una métrica por informe. El contrato público
no cambia: ni la respuesta REST ni el contenido estructurado de ``analizar_proyecto`` llevan
campos nuevos.

La lectura se prueba con el cliente real (``ChatGroq`` y el SDK de Groq) sobre un transporte
HTTP simulado, para no depender de cómo se supone que langchain-groq rellena los metadatos.
"""

from __future__ import annotations

import asyncio
import json
import logging
from unittest.mock import MagicMock

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_groq import ChatGroq
from prometheus_client import REGISTRY

from app import rag, service
from app.config import settings
from app.mcp_server import AnalisisProyecto
from app.models import PipelineResult, QuestionnaireInput, RAGResponse, UsoModelo
from app.rag import DISCLAIMER, _render_coverage_section, run_pipeline_detailed

AVISO_CORTE = "se cortó al llegar al límite de tokens de salida"


def _metric(name: str, **labels) -> float:
    for metric in REGISTRY.collect():
        for sample in metric.samples:
            if sample.name == name and all(
                sample.labels.get(k) == v for k, v in labels.items()
            ):
                return sample.value
    return 0.0


def _respuesta_groq(
    contenido: str,
    *,
    finish_reason: str = "stop",
    entrada: int = 6200,
    salida: int = 1900,
    razonamiento: int | None = 350,
) -> dict:
    """Cuerpo de una respuesta de chat completions de Groq (formato de OpenAI)."""
    uso: dict = {
        "prompt_tokens": entrada,
        "completion_tokens": salida,
        "total_tokens": entrada + salida,
        "prompt_time": 0.02,
        "completion_time": 1.5,
        "total_time": 1.52,
    }
    if razonamiento is not None:
        uso["completion_tokens_details"] = {"reasoning_tokens": razonamiento}
    return {
        "id": "chatcmpl-prueba",
        "object": "chat.completion",
        "created": 1_790_000_000,
        "model": "openai/gpt-oss-120b",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": contenido},
                "finish_reason": finish_reason,
                "logprobs": None,
            }
        ],
        "usage": uso,
        "system_fingerprint": "fp_prueba",
    }


def _chatgroq(cuerpo: dict) -> tuple[ChatGroq, list[httpx.Request]]:
    """``ChatGroq`` real, sin reintentos, con un transporte que devuelve ``cuerpo``."""
    peticiones: list[httpx.Request] = []

    def responder(peticion: httpx.Request) -> httpx.Response:
        peticiones.append(peticion)
        return httpx.Response(200, json=cuerpo)

    cliente = ChatGroq(
        api_key="clave-de-prueba",
        model_name="openai/gpt-oss-120b",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(responder)),
    )
    return cliente, peticiones


def _input(**overrides) -> QuestionnaireInput:
    base = dict(
        tipo_proyecto="app_web",
        descripcion_breve="Agenda de citas para una peluquería",
        tiene_usuarios_registrados=True,
        acceso_publico=True,
        tipos_datos_personales=["nombre", "email"],
        usuarios_menores=False,
        usuarios_ue=True,
        transferencia_datos_terceros=False,
        usa_ia=False,
        tipo_ia=None,
        usa_cookies=False,
        monetizacion=None,
        contenido_digital=False,
        ccaa="Asturias",
        es_empresa=False,
        colegiado=None,
    )
    base.update(overrides)
    return QuestionnaireInput(**base)


def _doc(source: str):
    d = MagicMock()
    d.page_content = f"Contenido de prueba de {source}"
    d.metadata = {"source": source, "doc_type": "normativa_europea"}
    return d


def _state(llm_response) -> MagicMock:
    """Dos fragmentos del RGPD y dos de la LOPDGDD: las dos se detectan."""
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
    state.groq_client.invoke.return_value = llm_response
    state.groq_fallback_client = None
    state.indexed_normativas = frozenset({"RGPD", "LOPDGDD"})
    state.corpus_version = "corpus-prueba"
    return state


def _mensaje(contenido: str, *, finish_reason: str = "stop", **uso) -> AIMessage:
    """La respuesta tal como la devuelve ChatGroq (sin pasar por HTTP)."""
    entrada = uso.get("entrada", 6200)
    salida = uso.get("salida", 1900)
    usage = {
        "input_tokens": entrada,
        "output_tokens": salida,
        "total_tokens": entrada + salida,
    }
    if uso.get("razonamiento") is not None:
        usage["output_token_details"] = {"reasoning": uso["razonamiento"]}
    return AIMessage(
        content=contenido,
        response_metadata={"finish_reason": finish_reason, "model_name": "x"},
        usage_metadata=usage,
    )


# ------------------------------------------------------------------- lectura del uso


def test_uso_is_read_from_a_real_chatgroq_response():
    cliente, peticiones = _chatgroq(
        _respuesta_groq("Informe", finish_reason="length", razonamiento=350)
    )
    respuesta = cliente.invoke([HumanMessage(content="hola")])
    assert len(peticiones) == 1

    uso = rag._uso_modelo(respuesta)

    assert uso == UsoModelo(
        finish_reason="length",
        tokens_entrada=6200,
        tokens_salida=1900,
        tokens_razonamiento=350,
        tokens_total=8100,
    )
    assert uso.truncado is True


def test_reasoning_is_none_when_groq_does_not_report_it():
    cliente, _ = _chatgroq(_respuesta_groq("Informe", razonamiento=None))
    uso = rag._uso_modelo(cliente.invoke([HumanMessage(content="hola")]))
    assert uso.finish_reason == "stop"
    assert uso.tokens_entrada == 6200
    assert uso.tokens_razonamiento is None
    assert uso.truncado is False


def test_a_response_without_metadata_gives_an_empty_uso():
    """Los dobles de las demás pruebas son MagicMock(content=...): sus atributos son más
    MagicMock. El uso queda vacío, en lugar de romper el registro o la validación."""
    uso = rag._uso_modelo(MagicMock(content="Informe"))
    assert uso == UsoModelo()
    assert uso.truncado is False
    json.dumps(uso.model_dump())  # serializable para el registro


def test_only_ints_and_strings_are_accepted():
    respuesta = AIMessage(
        content="x",
        response_metadata={"finish_reason": 7},
        usage_metadata={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
    )
    respuesta.usage_metadata["input_tokens"] = True  # un booleano no es un recuento
    uso = rag._uso_modelo(respuesta)
    assert uso.finish_reason is None
    assert uso.tokens_entrada is None
    assert uso.tokens_salida == 2


# ---------------------------------------------------------- sección de cobertura


def test_truncation_notice_alone_renders_the_coverage_section():
    seccion = _render_coverage_section([], truncado=True)
    assert seccion.startswith("\n\n## Cobertura del análisis\n")
    assert AVISO_CORTE in seccion
    assert "incompleto" in seccion


def test_truncation_notice_goes_first():
    seccion = _render_coverage_section(
        ["DORA"], ["Data Act"], ["LOPDGDD"], truncado=True
    )
    assert seccion.index(AVISO_CORTE) < seccion.index("no desarrolla")
    assert seccion.index("no desarrolla") < seccion.index("DORA")


def test_no_truncation_keeps_the_section_as_it_was():
    assert _render_coverage_section([]) == ""
    assert AVISO_CORTE not in _render_coverage_section(["DORA"])


# ---------------------------------------------------------------- pipeline


def test_truncated_report_says_so_and_is_counted(mock_reranker):
    """El modelo se corta a mitad de la segunda normativa: el informe lo dice (texto del
    código, antes del aviso final), la LOPDGDD sale como no desarrollada y la métrica cuenta
    el corte con el modelo que lo produjo."""
    state = _state(
        _mensaje("## RGPD\nObligación del RGPD.\n\nLa LOPDG", finish_reason="length")
    )
    antes = _metric("legaldev_llm_truncated_total", model=settings.groq_model)

    result = asyncio.run(run_pipeline_detailed(_input(), state))

    informe = result.response.respuesta_completa
    assert "## Cobertura del análisis" in informe
    assert AVISO_CORTE in informe
    assert informe.index(AVISO_CORTE) < informe.rindex(DISCLAIMER)
    assert result.normativas_sin_desarrollar == ["LOPDGDD"]
    assert result.uso_modelo.truncado is True
    assert result.uso_modelo.tokens_total == 8100
    assert (
        _metric("legaldev_llm_truncated_total", model=settings.groq_model) == antes + 1
    )


def test_complete_report_has_no_notice_and_is_not_counted(mock_reranker):
    state = _state(
        _mensaje("## RGPD\nTexto.\n\n## LOPDGDD\nTexto.", finish_reason="stop")
    )
    antes = _metric("legaldev_llm_truncated_total", model=settings.groq_model)

    result = asyncio.run(run_pipeline_detailed(_input(), state))

    assert AVISO_CORTE not in result.response.respuesta_completa
    assert "## Cobertura del análisis" not in result.response.respuesta_completa
    assert result.uso_modelo.finish_reason == "stop"
    assert _metric("legaldev_llm_truncated_total", model=settings.groq_model) == antes


def test_tokens_are_observed_once_per_report(mock_reranker):
    state = _state(_mensaje("## RGPD\nT.\n\n## LOPDGDD\nT.", razonamiento=350))
    antes = {
        k: (
            _metric("legaldev_llm_tokens_sum", kind=k),
            _metric("legaldev_llm_tokens_count", kind=k),
        )
        for k in ("input", "output", "reasoning", "total")
    }

    asyncio.run(run_pipeline_detailed(_input(), state))

    esperado = {"input": 6200, "output": 1900, "reasoning": 350, "total": 8100}
    for kind, valor in esperado.items():
        suma, cuenta = antes[kind]
        assert _metric("legaldev_llm_tokens_sum", kind=kind) == suma + valor
        assert _metric("legaldev_llm_tokens_count", kind=kind) == cuenta + 1


def test_missing_tokens_are_not_observed(mock_reranker):
    state = _state(MagicMock(content="## RGPD\nT.\n\n## LOPDGDD\nT."))
    antes = _metric("legaldev_llm_tokens_count", kind="input")
    result = asyncio.run(run_pipeline_detailed(_input(), state))
    assert result.uso_modelo == UsoModelo()
    assert _metric("legaldev_llm_tokens_count", kind="input") == antes


def test_a_cache_hit_does_not_count_tokens_again(mock_reranker):
    state = _state(_mensaje("## RGPD\nT.\n\n## LOPDGDD\nT."))
    antes = _metric("legaldev_llm_tokens_count", kind="total")
    primera = asyncio.run(service.analyze(_input(), state, via=service.Via.MCP))
    segunda = asyncio.run(service.analyze(_input(), state, via=service.Via.MCP))
    assert not primera.cache_hit and segunda.cache_hit
    assert segunda.result.uso_modelo.tokens_total == 8100  # el de la primera, guardado
    assert _metric("legaldev_llm_tokens_count", kind="total") == antes + 1


def test_fallback_reports_its_own_tokens_and_cut(mock_reranker):
    state = _state(None)
    state.groq_client.invoke.side_effect = Exception("model_decommissioned")
    state.groq_fallback_client = MagicMock()
    state.groq_fallback_client.invoke.return_value = _mensaje(
        "## RGPD\nT.", finish_reason="length", entrada=6000, salida=8000
    )
    antes = _metric("legaldev_llm_truncated_total", model=settings.groq_fallback_model)

    result = asyncio.run(run_pipeline_detailed(_input(), state))

    assert result.response.llm_model == settings.groq_fallback_model
    assert result.uso_modelo.tokens_salida == 8000
    assert (
        _metric("legaldev_llm_truncated_total", model=settings.groq_fallback_model)
        == antes + 1
    )


def test_tokens_and_finish_reason_are_logged_without_user_text(mock_reranker, caplog):
    """PP-08: el evento rag_pipeline lleva los recuentos y el motivo de fin, nunca la
    descripción."""
    centinela = "CENTINELA-TOKENS-5d1e"
    state = _state(_mensaje("## RGPD\nT.", finish_reason="length", razonamiento=350))

    with caplog.at_level(logging.DEBUG):
        asyncio.run(
            run_pipeline_detailed(
                _input(descripcion_breve=f"Peluquería {centinela}"), state
            )
        )

    eventos = [
        json.loads(r.getMessage())
        for r in caplog.records
        if r.getMessage().startswith('{"event": "rag_pipeline"')
    ]
    assert len(eventos) == 1
    assert eventos[0]["llm_finish_reason"] == "length"
    assert eventos[0]["llm_tokens"] == {
        "input": 6200,
        "output": 1900,
        "reasoning": 350,
        "total": 8100,
    }
    assert centinela not in caplog.text


def test_log_has_null_tokens_when_the_provider_gives_none(mock_reranker, caplog):
    state = _state(MagicMock(content="## RGPD\nT."))
    with caplog.at_level(logging.INFO, logger="app.rag"):
        asyncio.run(run_pipeline_detailed(_input(), state))
    evento = next(
        json.loads(r.getMessage())
        for r in caplog.records
        if r.getMessage().startswith('{"event": "rag_pipeline"')
    )
    assert evento["llm_finish_reason"] is None
    assert evento["llm_tokens"] == {
        "input": None,
        "output": None,
        "reasoning": None,
        "total": None,
    }


# ------------------------------------------------------- el contrato público no cambia


@pytest.mark.parametrize("modelo", [RAGResponse, AnalisisProyecto])
def test_public_models_do_not_carry_usage(modelo):
    campos = set(modelo.model_fields)
    assert "uso_modelo" not in campos
    assert not any("token" in c or "finish" in c for c in campos)


def test_rest_response_has_no_usage_fields(client, sample_input_dict):
    client.app.state.groq_client.invoke.return_value = _mensaje(
        "## RGPD\nT.", finish_reason="length"
    )
    r = client.post("/v1/analyze", json=sample_input_dict)
    assert r.status_code == 200
    assert set(r.json()) == set(RAGResponse.model_fields)
    assert AVISO_CORTE in r.json()["respuesta_completa"]


def test_pipeline_result_carries_usage_with_a_default():
    assert PipelineResult.model_fields["uso_modelo"].default_factory is UsoModelo
