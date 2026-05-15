import hashlib
import json
import logging
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader
from langchain_huggingface import HuggingFaceEmbeddings

from app.corpus import REQUIRED_DOCS
from app.legal_splitter import split_document

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DOCS_PATH = os.getenv("DOCS_PATH", "./docs")
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_db")
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
COLLECTION_NAME = "legaldev"

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


def main() -> None:
    docs_dir = Path(DOCS_PATH)

    _check_required_docs(docs_dir)

    pdf_files = sorted(docs_dir.glob("*.pdf"))
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    all_chunks = []

    for pdf_path in pdf_files:
        filename = pdf_path.name
        doc_type = get_doc_type(filename)
        loader = PyPDFLoader(str(pdf_path))
        pages = loader.load()
        page_chunks = []
        for page in pages:
            page.metadata["source"] = filename
            page.metadata["doc_type"] = doc_type
            page_chunks.extend(split_document(page))
        chunks = page_chunks

        logger.info(
            "Indexing %s → %d chunks (doc_type=%s)", filename, len(chunks), doc_type
        )
        all_chunks.extend(chunks)

    corpus_version = _compute_corpus_version(docs_dir)
    version_file = Path(CHROMA_DB_PATH) / ".corpus_version"

    if Path(CHROMA_DB_PATH).exists():
        logger.warning(
            "Wiping existing ChromaDB at %s — this is irreversible", CHROMA_DB_PATH
        )
        shutil.rmtree(CHROMA_DB_PATH)
        logger.info("Wiped existing ChromaDB at %s", CHROMA_DB_PATH)

    logger.info("Generating embeddings and persisting %d chunks...", len(all_chunks))
    Chroma.from_documents(
        documents=all_chunks,
        embedding=embeddings,
        persist_directory=CHROMA_DB_PATH,
        collection_name=COLLECTION_NAME,
    )

    version_file.write_text(corpus_version)
    logger.info("Corpus version: %s", corpus_version)

    logger.info(
        "Indexing complete — %d total chunks across %d documents",
        len(all_chunks),
        len(pdf_files),
    )


if __name__ == "__main__":
    main()
