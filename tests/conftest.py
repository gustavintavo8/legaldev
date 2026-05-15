import os

os.environ.setdefault("GROQ_API_KEY", "test-key-not-real")

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_doc():
    doc = MagicMock()
    doc.page_content = (
        "El RGPD establece que los datos personales deben tratarse de forma lícita."
    )
    doc.metadata = {"source": "RGPD.pdf", "doc_type": "normativa_europea"}
    return doc


@pytest.fixture
def sample_input():
    from app.models import QuestionnaireInput

    return QuestionnaireInput(
        tipo_proyecto="app_web",
        descripcion_breve="Plataforma SaaS para gestión de facturas",
        tiene_usuarios_registrados=True,
        acceso_publico=False,
        tipos_datos_personales=["nombre", "email"],
        usuarios_menores=False,
        usuarios_ue=True,
        transferencia_datos_terceros=False,
        usa_ia=True,
        tipo_ia="generativa",
        usa_cookies=True,
        monetizacion="suscripcion",
        contenido_digital=False,
        ccaa="Asturias",
        es_empresa=False,
        colegiado=None,
    )


@pytest.fixture
def sample_input_dict():
    return {
        "tipo_proyecto": "app_web",
        "descripcion_breve": "Plataforma SaaS para gestión de facturas",
        "tiene_usuarios_registrados": True,
        "acceso_publico": False,
        "tipos_datos_personales": ["nombre", "email"],
        "usuarios_menores": False,
        "usuarios_ue": True,
        "transferencia_datos_terceros": False,
        "usa_ia": True,
        "tipo_ia": "generativa",
        "usa_cookies": True,
        "monetizacion": "suscripcion",
        "contenido_digital": False,
        "ccaa": "Asturias",
        "es_empresa": False,
        "colegiado": None,
    }


@pytest.fixture
def client(mock_doc):
    from unittest.mock import patch

    with (
        patch("app.main.HuggingFaceEmbeddings"),
        patch("app.main.Chroma") as mock_chroma_cls,
        patch("app.main.ChatGroq") as mock_groq_cls,
        patch("app.store.read_corpus_version", return_value="abc123def456"),
    ):
        mock_vectorstore = MagicMock()
        mock_vectorstore.similarity_search_with_relevance_scores.return_value = [
            (mock_doc, 0.85)
        ]
        mock_vectorstore._collection.count.return_value = 1234
        mock_vectorstore._collection.get.return_value = {
            "metadatas": [
                {"source": "RGPD.pdf"},
                {"source": "LOPDGDD.pdf"},
                {"source": "RGPD.pdf"},
            ]
        }
        mock_chroma_cls.return_value = mock_vectorstore

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content="Respuesta de prueba sobre RGPD"
        )
        mock_groq_cls.return_value = mock_llm

        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app) as c:
            yield c


@pytest.fixture(autouse=True)
def clear_response_cache():
    from app import cache as _cache

    _cache.clear()
    yield
    _cache.clear()


@pytest.fixture(autouse=True)
def mock_reranker():
    from unittest.mock import patch

    with patch(
        "app.reranker.rerank",
        side_effect=lambda query, docs, top_k: docs[:top_k],
    ):
        yield


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    yield
    try:
        import app.main as main_module

        main_module.limiter._storage.reset()
    except Exception:
        pass
