import gc
import hashlib
import json
import logging
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from pypdf import PdfReader

from app.corpus import EMBEDDING_MODEL, REQUIRED_DOCS
from app.legal_splitter import split_document

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DOCS_PATH = os.getenv("DOCS_PATH", "./docs")
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_db")
COLLECTION_NAME = "legaldev"

# Chunks más cortos son cabeceras/pies de página ("ES", números) cuyo embedding es ruido.
MIN_CHUNK_CHARS = 40
# Súbelo cuando cambie la estrategia de chunking; queda registrado en .index_meta.json.
SPLITTER_VERSION = 2

DOC_TYPE_MAP = {
    # Normativa europea
    "RGPD.pdf": "normativa_europea",
    "EU AI Act.pdf": "normativa_europea",
    "Directiva NIS2.pdf": "normativa_europea",
    "Directiva de Responsabilidad por Productos con IA.pdf": "normativa_europea",
    "Digital Services Act (Reglamento UE 2022-2065).pdf": "normativa_europea",
    "Cyber Resilience Act (Reglamento UE 2024-2847).pdf": "normativa_europea",
    "Directiva ePrivacy (2002-58-CE consolidada).pdf": "normativa_europea",
    "Data Act (Reglamento UE 2023-2854).pdf": "normativa_europea",
    "Data Governance Act (Reglamento UE 2022-868).pdf": "normativa_europea",
    "DORA (Reglamento UE 2022-2554).pdf": "normativa_europea",
    # Normativa española
    "LOPDGDD.pdf": "normativa_española",
    "Real Decreto 311-2022 ENS.pdf": "normativa_española",
    "LSSI.pdf": "normativa_española",
    "Ley de Propiedad Intelectual.pdf": "normativa_española",
    # Deontología
    "Código Ético y Deontológico CCII.pdf": "deontologia",
}


def get_doc_type(filename: str) -> str:
    if "AEPD" in filename:
        return "guia_aepd"
    return DOC_TYPE_MAP.get(filename, "otro")


def _compute_corpus_version(docs_dir: Path) -> str:
    pdf_files = sorted(docs_dir.glob("*.pdf"))
    fingerprint = json.dumps(
        [(f.name, f.stat().st_size) for f in pdf_files], sort_keys=True
    )
    return hashlib.sha256(fingerprint.encode()).hexdigest()[:12]


def _check_required_docs(docs_dir: Path) -> None:
    present = {f.name for f in docs_dir.glob("*.pdf")}
    missing = REQUIRED_DOCS - present
    if missing:
        for name in sorted(missing):
            logger.error("Missing required document: %s", name)
        raise SystemExit(
            f"Aborted: {len(missing)} required document(s) missing from {docs_dir}. "
            "Add the missing PDFs and re-run."
        )


def _load_pages(pdf_path: Path) -> list[Document]:
    """Una página por Document, con page 0-indexed (como PyPDFLoader; _build_user_message suma 1)."""
    reader = PdfReader(str(pdf_path))
    total = len(reader.pages)
    return [
        Document(
            page_content=page.extract_text() or "",
            metadata={"source": pdf_path.name, "page": i, "total_pages": total},
        )
        for i, page in enumerate(reader.pages)
    ]


def _is_meaningful(chunk: Document) -> bool:
    # Un artículo parseado (e.g. "Artículo 7. Derogado.") es contenido legal completo
    # aunque sea corto — la regla de longitud sólo existe para descartar ruido de
    # cabecera/pie de página sin estructura reconocida.
    if "article" in chunk.metadata:
        return True
    return len(chunk.page_content.strip()) >= MIN_CHUNK_CHARS


def _write_index_meta(
    target: Path, *, corpus_version: str, chunks: int, documents: int
) -> None:
    meta = {
        "embedding_model": EMBEDDING_MODEL,
        "corpus_version": corpus_version,
        "chunks": chunks,
        "documents": documents,
        "splitter_version": SPLITTER_VERSION,
        "min_chunk_chars": MIN_CHUNK_CHARS,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (target / ".index_meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )


def _release_chroma_handles(vectorstore) -> None:
    """Libera los descriptores de SQLite que ChromaDB mantiene abiertos tras from_documents.

    chromadb.api.client.SharedSystemClient cachea el System (y su conexión SQLite) en un
    registro GLOBAL DE PROCESO indexado por configuración, no por instancia de Chroma. Por
    eso `del vectorstore` + gc.collect() en el llamador NO basta para soltar el archivo:
    el proceso sigue reteniendo la conexión a través de ese caché compartido. Windows no
    permite renombrar (ni borrar) un directorio con archivos abiertos dentro — a diferencia
    de POSIX, donde un rename tiene éxito aunque el archivo siga abierto — así que sin este
    paso `_swap_dirs` fallaba con WinError 5 el 100% de las veces en Windows.

    El parámetro `vectorstore` no se usa dentro de esta función (el caché que hay que
    limpiar es global, no depende de la instancia); se mantiene en la firma para que el
    call site sea explícito sobre qué recurso se está liberando. Quien llama SIGUE
    reteniendo su propia referencia local hasta que la reasigna (`vectorstore = None`)
    inmediatamente después de esta llamada — sin eso, gc.collect() no puede recolectar
    un objeto todavía alcanzable desde una variable viva.
    """
    gc.collect()
    try:
        from chromadb.api.client import SharedSystemClient

        SharedSystemClient.clear_system_cache()
    except Exception as e:
        # API privada de chromadb: si cambia de forma incompatible, preferimos seguir
        # (el swap reintentará y puede que el SO libere el handle por otra vía) a tumbar
        # la ingesta entera por esto.
        logger.warning("Could not clear ChromaDB's shared system cache: %s", e)


def _swap_dirs(build_dir: Path, final_dir: Path, attempts: int = 5) -> None:
    """Sustituye final_dir por build_dir sin destruir nunca el índice viejo antes de tener el nuevo.

    ChromaDB puede mantener descriptores abiertos (sobre todo en Windows) incluso tras
    _release_chroma_handles, así que el rename del nuevo índice se reintenta; si no lo
    consigue, restaura el índice anterior (cuando había uno) y aborta con SystemExit en
    vez de dejar el sistema sin índice o con dos copias a medias.
    """
    old_dir = final_dir.with_name(final_dir.name + ".old")
    had_previous = final_dir.exists()

    if old_dir.exists():
        try:
            shutil.rmtree(old_dir)
        except OSError as e:
            raise SystemExit(
                f"Could not remove the stale {old_dir} left by a previous failed swap "
                f"({e}). The new index is already complete in {build_dir}; remove "
                f"{old_dir} manually and re-run make ingest."
            )

    if had_previous:
        try:
            final_dir.rename(old_dir)
        except OSError as e:
            raise SystemExit(
                f"Could not move the current index aside ({e}). Is the API still running "
                f"against it? The new index is complete in {build_dir}; stop the process "
                f"and re-run make ingest, or move it manually."
            )

    for attempt in range(1, attempts + 1):
        try:
            build_dir.rename(final_dir)
            break
        except OSError as e:
            logger.warning("Swap attempt %d/%d failed: %s", attempt, attempts, e)
            gc.collect()
            time.sleep(1.0)
    else:
        if had_previous:
            try:
                old_dir.rename(final_dir)
            except OSError as e:
                raise SystemExit(
                    f"Could not move {build_dir} into place after {attempts} attempts, "
                    f"and RESTORE FAILED: the previous index is at {old_dir} ({e}). Move "
                    f"it back to {final_dir} manually."
                )
            restored_clause = f"The previous index was restored to {final_dir}. "
        else:
            restored_clause = f"There is no previous index at {final_dir}. "
        raise SystemExit(
            f"Could not move {build_dir} into place after {attempts} attempts. "
            f"{restored_clause}"
            f"Close any process using it, then remove {final_dir} (if present) and "
            f"rename {build_dir} to {final_dir}."
        )

    if old_dir.exists():
        try:
            shutil.rmtree(old_dir)
        except OSError as e:
            logger.warning("Could not remove %s: %s", old_dir, e)


def main() -> None:
    docs_dir = Path(DOCS_PATH)
    _check_required_docs(docs_dir)

    pdf_files = sorted(docs_dir.glob("*.pdf"))
    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL, encode_kwargs={"normalize_embeddings": True}
    )
    all_chunks: list[Document] = []
    dropped = 0

    for pdf_path in pdf_files:
        doc_type = get_doc_type(pdf_path.name)
        chunks: list[Document] = []
        for page in _load_pages(pdf_path):
            page.metadata["doc_type"] = doc_type
            for chunk in split_document(page):
                if _is_meaningful(chunk):
                    chunks.append(chunk)
                else:
                    dropped += 1
        logger.info(
            "Indexing %s → %d chunks (doc_type=%s)",
            pdf_path.name,
            len(chunks),
            doc_type,
        )
        all_chunks.extend(chunks)

    logger.info("Dropped %d chunks shorter than %d chars", dropped, MIN_CHUNK_CHARS)
    corpus_version = _compute_corpus_version(docs_dir)

    final_dir = Path(CHROMA_DB_PATH)
    build_dir = final_dir.with_name(final_dir.name + ".building")
    if build_dir.exists():
        shutil.rmtree(build_dir)

    logger.info(
        "Generating embeddings and persisting %d chunks into %s...",
        len(all_chunks),
        build_dir,
    )
    vectorstore = Chroma.from_documents(
        documents=all_chunks,
        embedding=embeddings,
        persist_directory=str(build_dir),
        collection_name=COLLECTION_NAME,
    )
    (build_dir / ".corpus_version").write_text(corpus_version)
    _write_index_meta(
        build_dir,
        corpus_version=corpus_version,
        chunks=len(all_chunks),
        documents=len(pdf_files),
    )
    _release_chroma_handles(vectorstore)
    vectorstore = None

    _swap_dirs(build_dir, final_dir)
    logger.info(
        "Indexing complete — %d total chunks across %d documents (corpus %s)",
        len(all_chunks),
        len(pdf_files),
        corpus_version,
    )


if __name__ == "__main__":
    main()
