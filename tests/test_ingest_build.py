import json
from pathlib import Path

import pytest
from langchain_core.documents import Document

from app import ingest
from app.corpus import EMBEDDING_MODEL


def test_is_meaningful_drops_tiny_chunks():
    assert ingest._is_meaningful(Document(page_content="ES", metadata={})) is False
    assert ingest._is_meaningful(Document(page_content="  12  ", metadata={})) is False
    assert ingest._is_meaningful(Document(page_content="x" * 40, metadata={})) is True


def test_load_pages_with_pypdf(tmp_path):
    from fpdf import FPDF

    pdf = FPDF()
    for i in range(2):
        pdf.add_page()
        pdf.set_font("Helvetica", size=11)
        pdf.multi_cell(0, 8, f"Articulo {i + 1}. Texto de la pagina {i + 1}.")
    path = tmp_path / "Norma.pdf"
    pdf.output(str(path))

    pages = ingest._load_pages(path)

    assert len(pages) == 2
    assert pages[0].metadata == {"source": "Norma.pdf", "page": 0, "total_pages": 2}
    assert "Texto de la pagina 1" in pages[0].page_content
    assert pages[1].metadata["page"] == 1


def test_write_index_meta(tmp_path):
    ingest._write_index_meta(tmp_path, corpus_version="abc123", chunks=10, documents=2)
    meta = json.loads((tmp_path / ".index_meta.json").read_text(encoding="utf-8"))
    assert meta["embedding_model"] == EMBEDDING_MODEL
    assert meta["corpus_version"] == "abc123"
    assert meta["chunks"] == 10
    assert meta["documents"] == 2
    assert meta["splitter_version"] == ingest.SPLITTER_VERSION
    assert meta["min_chunk_chars"] == ingest.MIN_CHUNK_CHARS
    assert meta["created_at"].endswith("+00:00")


def test_swap_dirs_replaces_old_index(tmp_path):
    final = tmp_path / "chroma_db"
    final.mkdir()
    (final / "old.txt").write_text("old")
    build = tmp_path / "chroma_db.building"
    build.mkdir()
    (build / "new.txt").write_text("new")

    ingest._swap_dirs(build, final)

    assert (final / "new.txt").exists()
    assert not (final / "old.txt").exists()
    assert not build.exists()
    assert not (tmp_path / "chroma_db.old").exists()


def test_swap_dirs_restores_previous_index_when_move_fails(tmp_path, monkeypatch):
    final = tmp_path / "chroma_db"
    final.mkdir()
    (final / "old.txt").write_text("old")
    build = tmp_path / "chroma_db.building"
    build.mkdir()
    (build / "new.txt").write_text("new")

    original_rename = Path.rename

    def _failing_rename(self, target):
        if self == build:
            raise PermissionError("file in use")
        return original_rename(self, target)

    monkeypatch.setattr(Path, "rename", _failing_rename)
    monkeypatch.setattr(ingest.time, "sleep", lambda s: None)

    with pytest.raises(SystemExit):
        ingest._swap_dirs(build, final, attempts=2)

    assert (final / "old.txt").exists()
    assert (build / "new.txt").exists()


def test_swap_dirs_when_no_previous_index(tmp_path):
    final = tmp_path / "chroma_db"
    build = tmp_path / "chroma_db.building"
    build.mkdir()
    (build / "new.txt").write_text("new")
    ingest._swap_dirs(build, final)
    assert (final / "new.txt").exists()
