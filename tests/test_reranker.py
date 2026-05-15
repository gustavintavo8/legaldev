from unittest.mock import MagicMock, patch

import pytest


def _make_doc(content: str):
    doc = MagicMock()
    doc.page_content = content
    doc.metadata = {"source": "RGPD.pdf"}
    return doc


def test_rerank_returns_top_k_docs():
    from app.reranker import rerank

    docs = [_make_doc(f"content {i}") for i in range(5)]
    scores = [0.9, 0.3, 0.8, 0.6, 0.1]

    with patch("app.reranker.get_encoder") as mock_get:
        encoder = MagicMock()
        encoder.predict.return_value = scores
        mock_get.return_value = encoder

        result = rerank("query text", docs, top_k=3)

    assert len(result) == 3
    assert result[0].page_content == "content 0"  # score 0.9 — highest
    assert result[1].page_content == "content 2"  # score 0.8
    assert result[2].page_content == "content 3"  # score 0.6


def test_rerank_empty_docs_returns_empty():
    from app.reranker import rerank

    assert rerank("query", [], top_k=5) == []


def test_rerank_fewer_docs_than_top_k():
    from app.reranker import rerank

    docs = [_make_doc("only one")]
    with patch("app.reranker.get_encoder") as mock_get:
        encoder = MagicMock()
        encoder.predict.return_value = [0.7]
        mock_get.return_value = encoder
        result = rerank("query", docs, top_k=10)
    assert len(result) == 1
