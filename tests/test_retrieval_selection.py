import asyncio
from unittest.mock import MagicMock, patch

from app.config import settings
from app.models import QuestionnaireInput
from app.rag import _select_diverse, run_pipeline


def _doc(source, text=None):
    d = MagicMock()
    d.page_content = text or f"{source}-{id(d)}"
    d.metadata = {"source": source}
    return d


def _input(**overrides):
    base = dict(
        tipo_proyecto="app_web",
        descripcion_breve="App de gestión",
        tiene_usuarios_registrados=True,
        acceso_publico=False,
        tipos_datos_personales=["ninguno"],
        usuarios_menores=False,
        usuarios_ue=True,
        transferencia_datos_terceros=False,
        usa_ia=False,
        tipo_ia=None,
        usa_cookies=False,
        monetizacion=None,
        contenido_digital=False,
        ccaa="Madrid",
        es_empresa=False,
        colegiado=None,
    )
    base.update(overrides)
    return QuestionnaireInput(**base)


def test_select_diverse_caps_chunks_per_source_and_keeps_order():
    ranked = [_doc("A.pdf") for _ in range(6)] + [_doc("B.pdf"), _doc("B.pdf")]
    chosen = _select_diverse(ranked, top_k=5, max_per_source=4)
    assert [d.metadata["source"] for d in chosen] == ["A.pdf"] * 4 + ["B.pdf"]


def test_select_diverse_backfills_with_skipped_when_short():
    ranked = [_doc("A.pdf") for _ in range(6)]
    chosen = _select_diverse(ranked, top_k=5, max_per_source=4)
    assert len(chosen) == 5
    assert chosen == ranked[:5]


def test_select_diverse_disabled_with_zero():
    ranked = [_doc("A.pdf") for _ in range(6)]
    assert _select_diverse(ranked, top_k=3, max_per_source=0) == ranked[:3]


def test_select_diverse_returns_all_when_fewer_than_top_k():
    ranked = [_doc("A.pdf"), _doc("B.pdf")]
    assert _select_diverse(ranked, top_k=12, max_per_source=4) == ranked


def test_select_diverse_backfill_keeps_chosen_first_then_skipped_in_rank_order():
    a = [_doc("A.pdf") for _ in range(4)]
    b = _doc("B.pdf")
    ranked = [a[0], a[1], a[2], b, a[3]]
    chosen = _select_diverse(ranked, top_k=5, max_per_source=2)
    assert chosen == [a[0], a[1], b, a[2], a[3]]


def test_excluded_docs_never_reach_the_reranker():
    ens = _doc("Real Decreto 311-2022 ENS.pdf")
    rgpd = [_doc("RGPD.pdf"), _doc("RGPD.pdf")]
    state = MagicMock()
    state.vectorstore.similarity_search_with_relevance_scores.return_value = [
        (ens, 0.9),
        (rgpd[0], 0.8),
        (rgpd[1], 0.7),
    ]
    state.groq_client.invoke.return_value = MagicMock(content="ok")
    state.groq_fallback_client = None
    state.indexed_normativas = frozenset({"RGPD", "Real Decreto 311-2022 ENS"})
    state.corpus_version = "v1"

    with patch("app.reranker.rerank", side_effect=lambda q, docs, top_k: docs) as rr:
        asyncio.run(run_pipeline(_input(), state))

    docs_sent = rr.call_args.args[1]
    assert ens not in docs_sent
    assert rr.call_args.kwargs["top_k"] == len(docs_sent)


def test_excluded_docs_do_not_consume_reranker_slots(monkeypatch):
    """Con reranker_top_k=2, ENS (excluida) no debe ocupar una de las dos plazas."""
    monkeypatch.setattr(settings, "reranker_top_k", 2)
    ens = _doc("Real Decreto 311-2022 ENS.pdf")
    rgpd = [_doc("RGPD.pdf"), _doc("RGPD.pdf")]
    state = MagicMock()
    state.vectorstore.similarity_search_with_relevance_scores.return_value = [
        (ens, 0.9),
        (rgpd[0], 0.8),
        (rgpd[1], 0.7),
    ]
    state.groq_client.invoke.return_value = MagicMock(content="ok")
    state.groq_fallback_client = None
    state.indexed_normativas = frozenset({"RGPD"})
    state.corpus_version = "v1"

    with patch("app.reranker.rerank", side_effect=lambda q, docs, top_k: docs) as rr:
        result = asyncio.run(run_pipeline(_input(), state))

    assert rr.call_args.args[1] == rgpd
    assert result.chunks_utilizados == 2


def test_run_pipeline_applies_per_source_cap(monkeypatch):
    monkeypatch.setattr(settings, "top_k_chunks", 3)
    monkeypatch.setattr(settings, "max_chunks_per_source", 2)
    guia = [_doc("Guía de Privacidad desde el Diseño - AEPD.pdf") for _ in range(3)]
    lopd = _doc("LOPDGDD.pdf")
    state = MagicMock()
    state.vectorstore.similarity_search_with_relevance_scores.return_value = [
        (d, 0.9) for d in guia
    ] + [(lopd, 0.8)]
    state.groq_client.invoke.return_value = MagicMock(content="ok")
    state.groq_fallback_client = None
    state.indexed_normativas = frozenset()
    state.corpus_version = "v1"

    with patch("app.reranker.rerank", side_effect=lambda q, docs, top_k: docs):
        result = asyncio.run(run_pipeline(_input(), state))

    assert result.chunks_utilizados == 3
    sent = state.groq_client.invoke.call_args.args[0][1].content
    assert "LOPDGDD.pdf" in sent
