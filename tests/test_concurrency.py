"""H2 regression: reranker/Groq calls must not block the event loop.

Criterio de done (legaldev-plan-auditoria.md, 1.3): /health responde en
<500ms mientras un análisis está en curso. These tests assert a stricter
<300ms bound for a clearer red/green signal — if someone reverts the
asyncio.to_thread wrapping, /health will take ~450ms here, well past the
bound.
"""

import asyncio
import time
from unittest.mock import MagicMock, patch

from httpx import ASGITransport, AsyncClient

from app.main import app

_HEALTH_THRESHOLD = 0.3
_SLOW_CALL_SECONDS = 0.6


async def _probe_health_during_analyze(payload, *, slow_reranker, slow_groq, mock_doc):
    with (
        patch("app.main.HuggingFaceEmbeddings"),
        patch("app.main.Chroma") as mock_chroma_cls,
        patch("app.main.ChatGroq") as mock_groq_cls,
        patch("app.store.read_corpus_version", return_value="abc123"),
        patch("app.reranker.rerank") as mock_rerank,
    ):

        def _rerank(query, docs, top_k):
            if slow_reranker:
                time.sleep(_SLOW_CALL_SECONDS)
            return docs[:top_k]

        mock_rerank.side_effect = _rerank

        mock_vectorstore = MagicMock()
        mock_vectorstore.similarity_search_with_relevance_scores.return_value = [
            (mock_doc, 0.85)
        ]
        mock_vectorstore._collection.count.return_value = 1
        mock_vectorstore._collection.get.return_value = {
            "metadatas": [{"source": "RGPD.pdf"}]
        }
        mock_chroma_cls.return_value = mock_vectorstore

        def _invoke(messages):
            if slow_groq:
                time.sleep(_SLOW_CALL_SECONDS)
            return MagicMock(content="ok")

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = _invoke
        mock_groq_cls.return_value = mock_llm

        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                # t0 MUST be captured before the head-start sleep below. If the
                # event loop is blocked, that sleep itself overruns — timing
                # only the /health call after it would silently absorb the
                # blocked time instead of exposing it.
                t0 = time.perf_counter()
                analyze_task = asyncio.create_task(
                    client.post("/v1/analyze", json=payload)
                )
                await asyncio.sleep(0.05)  # let analyze reach the slow mocked call

                health_resp = await client.get("/health")
                health_elapsed = time.perf_counter() - t0

                analyze_resp = await analyze_task

    assert analyze_resp.status_code == 200, analyze_resp.text
    return health_resp, health_elapsed


def test_health_responds_fast_during_reranker(sample_input_dict, mock_doc):
    """H2: _reranker.rerank ran synchronously in the event loop, freezing /health."""

    async def _run():
        return await _probe_health_during_analyze(
            sample_input_dict, slow_reranker=True, slow_groq=False, mock_doc=mock_doc
        )

    health_resp, health_elapsed = asyncio.run(_run())
    assert health_resp.status_code == 200
    assert health_elapsed < _HEALTH_THRESHOLD, (
        f"/health took {health_elapsed:.2f}s while reranker ran — event loop blocked"
    )


def test_health_responds_fast_during_groq_invoke(sample_input_dict, mock_doc):
    """H2: state.groq_client.invoke ran synchronously in the event loop, freezing /health."""

    async def _run():
        return await _probe_health_during_analyze(
            sample_input_dict, slow_reranker=False, slow_groq=True, mock_doc=mock_doc
        )

    health_resp, health_elapsed = asyncio.run(_run())
    assert health_resp.status_code == 200
    assert health_elapsed < _HEALTH_THRESHOLD, (
        f"/health took {health_elapsed:.2f}s while groq.invoke ran — event loop blocked"
    )
