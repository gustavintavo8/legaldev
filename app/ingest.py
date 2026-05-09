import logging
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DOCS_PATH = os.getenv("DOCS_PATH", "./docs")
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_db")
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
COLLECTION_NAME = "legaldev"

DOC_TYPE_MAP = {
    "RGPD.pdf": "normativa_europea",
    "EU AI Act.pdf": "normativa_europea",
    "Directiva NIS2.pdf": "normativa_europea",
    "Directiva de Responsabilidad por Productos con IA.pdf": "normativa_europea",
    "LOPDGDD.pdf": "normativa_española",
    "ENS.pdf": "normativa_española",
    "LSSI.pdf": "normativa_española",
    "Ley de Propiedad Intelectual.pdf": "normativa_española",
    "Código Ético y Deontológico CCII.pdf": "deontologia",
}


def get_doc_type(filename: str) -> str:
    if "AEPD" in filename:
        return "guia_aepd"
    return DOC_TYPE_MAP.get(filename, "otro")


def main() -> None:
    docs_dir = Path(DOCS_PATH)
    pdf_files = sorted(docs_dir.glob("*.pdf"))

    if not pdf_files:
        logger.warning("No PDF files found in %s", DOCS_PATH)
        return

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    all_chunks = []

    for pdf_path in pdf_files:
        filename = pdf_path.name
        doc_type = get_doc_type(filename)
        loader = PyPDFLoader(str(pdf_path))
        pages = loader.load()
        chunks = splitter.split_documents(pages)

        for chunk in chunks:
            chunk.metadata["source"] = filename
            chunk.metadata["doc_type"] = doc_type

        logger.info("Indexing %s → %d chunks (doc_type=%s)", filename, len(chunks), doc_type)
        all_chunks.extend(chunks)

    if Path(CHROMA_DB_PATH).exists():
        shutil.rmtree(CHROMA_DB_PATH)
        logger.info("Wiped existing ChromaDB at %s", CHROMA_DB_PATH)

    logger.info("Generating embeddings and persisting %d chunks...", len(all_chunks))
    Chroma.from_documents(
        documents=all_chunks,
        embedding=embeddings,
        persist_directory=CHROMA_DB_PATH,
        collection_name=COLLECTION_NAME,
    )

    logger.info(
        "Indexing complete — %d total chunks across %d documents",
        len(all_chunks),
        len(pdf_files),
    )


if __name__ == "__main__":
    main()
