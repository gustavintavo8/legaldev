from unittest.mock import MagicMock, patch

import pytest


def _lifespan_patches(index_meta):
    mock_vs = MagicMock()
    mock_vs._collection.count.return_value = 10
    mock_vs._collection.get.return_value = {"metadatas": [{"source": "RGPD.pdf"}]}
    return (
        patch("app.main.HuggingFaceEmbeddings"),
        patch("app.main.Chroma", return_value=mock_vs),
        patch("app.main.ChatGroq"),
        patch("app.main._check_groq_model", return_value=True),
        patch("app.reranker.warmup"),
        patch("app.store.read_corpus_version", return_value="v"),
        patch("app.store.read_index_meta", return_value=index_meta),
    )


def test_startup_aborts_when_index_model_differs():
    from fastapi.testclient import TestClient

    from app.main import app

    p = _lifespan_patches({"embedding_model": "all-MiniLM-L6-v2"})
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6]:
        with pytest.raises(RuntimeError, match="built with 'all-MiniLM-L6-v2'"):
            with TestClient(app):
                pass


def test_startup_warns_when_index_has_no_meta(caplog):
    from fastapi.testclient import TestClient

    from app.main import app

    p = _lifespan_patches({})
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6]:
        with TestClient(app) as c:
            assert c.get("/health").status_code == 200
    assert "no .index_meta.json" in caplog.text


def test_startup_ok_when_index_model_matches():
    from fastapi.testclient import TestClient

    from app.corpus import EMBEDDING_MODEL
    from app.main import app

    p = _lifespan_patches({"embedding_model": EMBEDDING_MODEL})
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6]:
        with TestClient(app) as c:
            assert c.get("/health").status_code == 200
