from langchain_core.documents import Document

from app.legal_splitter import split_document


def test_splits_on_articulo_boundary():
    text = (
        "Artículo 1. El responsable del tratamiento debe informar al interesado.\n\n"
        "Artículo 2. El interesado tiene derecho de acceso a sus datos personales."
    )
    doc = Document(page_content=text, metadata={"source": "test.pdf", "page": 0})
    chunks = split_document(doc)
    assert len(chunks) == 2
    assert chunks[0].page_content.startswith("Artículo 1")
    assert chunks[1].page_content.startswith("Artículo 2")


def test_splits_on_considerando_boundary():
    text = (
        "Considerando 1. La protección de datos es un derecho fundamental.\n\n"
        "Considerando 2. El tratamiento de datos debe ser lícito."
    )
    doc = Document(page_content=text, metadata={"source": "test.pdf"})
    chunks = split_document(doc)
    assert len(chunks) == 2
    assert chunks[0].page_content.startswith("Considerando 1")
    assert chunks[1].page_content.startswith("Considerando 2")


def test_fallback_on_no_legal_structure():
    long_text = "Este es un texto sin estructura de artículos. " * 50
    doc = Document(page_content=long_text, metadata={"source": "test.pdf"})
    chunks = split_document(doc)
    assert len(chunks) >= 1
    for chunk in chunks:
        assert len(chunk.page_content) <= 600


def test_preserves_metadata_in_all_chunks():
    text = "Artículo 1. Texto. Artículo 2. Más texto."
    doc = Document(
        page_content=text,
        metadata={"source": "norm.pdf", "page": 3, "doc_type": "normativa_europea"},
    )
    chunks = split_document(doc)
    for chunk in chunks:
        assert chunk.metadata["source"] == "norm.pdf"
        assert chunk.metadata["page"] == 3
        assert chunk.metadata["doc_type"] == "normativa_europea"


def test_empty_doc_returns_no_chunks():
    doc = Document(page_content="   ", metadata={"source": "test.pdf"})
    chunks = split_document(doc)
    assert len(chunks) == 0


def test_very_long_article_is_split_by_fallback():
    long_article = "Artículo 1. " + ("Texto muy largo. " * 200)
    doc = Document(page_content=long_article, metadata={"source": "test.pdf"})
    chunks = split_document(doc)
    assert len(chunks) >= 2
