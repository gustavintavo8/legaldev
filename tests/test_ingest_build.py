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


def test_is_meaningful_keeps_short_chunk_with_article_heading():
    """A short but complete article (e.g. a repealed one) is meaningful legal content
    regardless of length — the length rule exists only to drop headerless page noise."""
    chunk = Document(
        page_content="Artículo 7. Derogado.", metadata={"article": "Artículo 7"}
    )
    assert ingest._is_meaningful(chunk) is True


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

    with pytest.raises(SystemExit, match="previous index was restored"):
        ingest._swap_dirs(build, final, attempts=2)

    assert (final / "old.txt").exists()
    assert (build / "new.txt").exists()


def test_swap_dirs_no_previous_index_message_when_move_fails_and_nothing_to_restore(
    tmp_path, monkeypatch
):
    final = tmp_path / "chroma_db"  # never created — no previous index to restore
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

    with pytest.raises(SystemExit, match="no previous index"):
        ingest._swap_dirs(build, final, attempts=2)

    assert build.exists()
    assert (build / "new.txt").exists()
    assert not final.exists()


def test_swap_dirs_aborts_immediately_when_moving_current_index_aside_fails(
    tmp_path, monkeypatch
):
    """The first rename (final_dir -> .old) is not retried: a locked live index (e.g. a
    running uvicorn still holding it open) must abort immediately with a curated
    message instead of silently retrying and risking a half-swapped state."""
    final = tmp_path / "chroma_db"
    final.mkdir()
    (final / "old.txt").write_text("old")
    build = tmp_path / "chroma_db.building"
    build.mkdir()
    (build / "new.txt").write_text("new")

    original_rename = Path.rename

    def _failing_rename(self, target):
        if self == final:
            raise PermissionError("file in use")
        return original_rename(self, target)

    monkeypatch.setattr(Path, "rename", _failing_rename)

    with pytest.raises(SystemExit, match="current index aside"):
        ingest._swap_dirs(build, final)

    assert (final / "old.txt").exists()
    assert (build / "new.txt").exists()
    assert not (tmp_path / "chroma_db.old").exists()


def test_swap_dirs_warns_but_succeeds_when_final_cleanup_of_old_dir_fails(
    tmp_path, monkeypatch, caplog
):
    """A leftover .old dir that can't be removed after a successful swap must not fail
    the ingest — it's cleanup of a backup that's no longer needed, not the swap itself."""
    final = tmp_path / "chroma_db"
    final.mkdir()
    (final / "old.txt").write_text("old")
    build = tmp_path / "chroma_db.building"
    build.mkdir()
    (build / "new.txt").write_text("new")

    old_dir = tmp_path / "chroma_db.old"
    original_rmtree = ingest.shutil.rmtree

    def _failing_rmtree(path, *args, **kwargs):
        if Path(path) == old_dir:
            raise OSError("locked")
        return original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(ingest.shutil, "rmtree", _failing_rmtree)

    ingest._swap_dirs(build, final)  # must not raise — cleanup failure is non-fatal

    assert (final / "new.txt").exists()
    assert "Could not remove" in caplog.text


def test_swap_dirs_aborts_when_stale_old_dir_cannot_be_removed(tmp_path, monkeypatch):
    final = tmp_path / "chroma_db"
    final.mkdir()
    build = tmp_path / "chroma_db.building"
    build.mkdir()
    (build / "new.txt").write_text("new")
    old_dir = tmp_path / "chroma_db.old"
    old_dir.mkdir()
    (old_dir / "stale.txt").write_text("stale")

    def _failing_rmtree(path, *args, **kwargs):
        raise OSError("locked")

    monkeypatch.setattr(ingest.shutil, "rmtree", _failing_rmtree)

    with pytest.raises(SystemExit, match="stale"):
        ingest._swap_dirs(build, final)

    assert old_dir.exists()
    assert (build / "new.txt").exists()


def test_swap_dirs_when_no_previous_index(tmp_path):
    final = tmp_path / "chroma_db"
    build = tmp_path / "chroma_db.building"
    build.mkdir()
    (build / "new.txt").write_text("new")
    ingest._swap_dirs(build, final)
    assert (final / "new.txt").exists()


def test_swap_dirs_succeeds_with_real_chroma_store_after_releasing_handles(tmp_path):
    """Regression for the Windows swap bug (fix round 1, CRITICAL finding): ChromaDB's
    SharedSystemClient caches the System (and its open SQLite connection) in a
    process-global registry, not per Chroma instance. `del vectorstore; gc.collect()`
    alone does NOT release it, so build_dir.rename(final_dir) raised WinError 5 on every
    attempt on Windows (reproduced manually before this fix — see task-10-report.md,
    Fix round 1). _release_chroma_handles (SharedSystemClient.clear_system_cache) plus
    the caller dropping its own reference is what actually frees the handle so the
    rename can succeed. Uses DeterministicFakeEmbedding — no model download, ~1s.
    """
    from langchain_chroma import Chroma
    from langchain_core.embeddings import DeterministicFakeEmbedding

    final_dir = tmp_path / "chroma_db"
    build_dir = tmp_path / "chroma_db.building"
    final_dir.mkdir()
    (final_dir / "old.txt").write_text("old")

    vectorstore = Chroma.from_documents(
        documents=[
            Document(page_content="texto de prueba uno", metadata={"source": "a.pdf"}),
            Document(page_content="texto de prueba dos", metadata={"source": "a.pdf"}),
        ],
        embedding=DeterministicFakeEmbedding(size=8),
        persist_directory=str(build_dir),
        collection_name="test",
    )

    ingest._release_chroma_handles(vectorstore)
    vectorstore = None

    ingest._swap_dirs(build_dir, final_dir)

    assert (final_dir / "chroma.sqlite3").exists()
    assert not (final_dir / "old.txt").exists()
    assert not build_dir.exists()
