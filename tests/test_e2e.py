"""
E2E test: real ChromaDB ingest + run_pipeline with mocked LLM.
Marked @pytest.mark.slow — not run in standard CI, only in the test-slow job.

Run locally: pytest tests/test_e2e.py -v -m slow
"""

import asyncio
import tempfile
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(scope="module")
def tiny_pdf_dir(tmp_path_factory):
    from fpdf import FPDF

    pdf_dir = tmp_path_factory.mktemp("pdfs")
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    for i in range(1, 8):
        pdf.multi_cell(
            0,
            8,
            f"Article {i}. The data controller must inform the data subject in a concise, "
            "transparent and intelligible manner about personal data processing.",
        )
        pdf.ln(2)
    pdf.output(str(pdf_dir / "TestNorm.pdf"))
    return pdf_dir


@pytest.mark.slow
def test_e2e_pipeline_retrieves_from_real_chroma(tiny_pdf_dir):
    from langchain_chroma import Chroma
    from langchain_community.document_loaders import PyPDFLoader
    from langchain_huggingface import HuggingFaceEmbeddings
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    from app.models import QuestionnaireInput
    from app.rag import run_pipeline

    pdf_path = next(tiny_pdf_dir.glob("*.pdf"))
    loader = PyPDFLoader(str(pdf_path))
    pages = loader.load()
    for page in pages:
        page.metadata["source"] = pdf_path.name

    splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=50)
    chunks = splitter.split_documents(pages)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as chroma_dir:
        embeddings = HuggingFaceEmbeddings(
            model_name="paraphrase-multilingual-MiniLM-L12-v2",
            encode_kwargs={"normalize_embeddings": True},
        )
        vs = Chroma.from_documents(
            documents=chunks,
            embedding=embeddings,
            persist_directory=chroma_dir,
            collection_name="legaldev_e2e",
        )

        state = MagicMock()
        state.vectorstore = vs
        state.indexed_normativas = frozenset({"TestNorm"})
        state.corpus_version = "e2e-test"
        state.groq_client.invoke.return_value = MagicMock(content="Respuesta E2E")

        inp = QuestionnaireInput(
            tipo_proyecto="app_web",
            descripcion_breve="App with personal data processing, data controller, data subject",
            tiene_usuarios_registrados=True,
            acceso_publico=False,
            tipos_datos_personales=["email"],
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

        with (
            patch(
                "app.reranker.rerank", side_effect=lambda q, docs, top_k: docs[:top_k]
            ),
            patch("app.rag.settings") as mock_settings,
        ):
            mock_settings.min_relevance_score = 0.0
            mock_settings.overfetch_k = 20
            mock_settings.top_k_chunks = 5
            mock_settings.rgpd_k = 3
            mock_settings.cookies_k = 3
            mock_settings.colegiado_k = 3
            mock_settings.chroma_timeout = 30.0
            result = asyncio.run(run_pipeline(inp, state))

        assert result.chunks_utilizados >= 1
        assert "TestNorm" in result.normativas_detectadas
        assert result.respuesta_completa.startswith("Respuesta E2E")
