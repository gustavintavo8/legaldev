"""Wrapper for ChromaDB's internal _collection API.

Uses _collection directly because langchain-chroma 1.1 has no public equivalents
for count() or bulk metadata retrieval. If Chroma adds public methods, update here.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


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


def read_index_meta(chroma_db_path: str) -> dict:
    meta_file = Path(chroma_db_path) / ".index_meta.json"
    if not meta_file.exists():
        return {}
    try:
        data = json.loads(meta_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not read %s: %s", meta_file, e)
        return {}
    if not isinstance(data, dict):
        return {}
    return data
