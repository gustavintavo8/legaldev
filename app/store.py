"""Wrapper for ChromaDB's internal _collection API.

Uses _collection directly because langchain-chroma 1.1 has no public equivalents
for count() or bulk metadata retrieval. If Chroma adds public methods, update here.
"""

from pathlib import Path


def count(vectorstore) -> int:
    return vectorstore._collection.count()


def list_sources(vectorstore) -> list[str]:
    result = vectorstore._collection.get(include=["metadatas"])
    return sorted({m["source"] for m in result["metadatas"] if m.get("source")})


def read_corpus_version(chroma_db_path: str) -> str:
    version_file = Path(chroma_db_path) / ".corpus_version"
    if version_file.exists():
        return version_file.read_text().strip()
    return "unknown"
