"""Wrapper for ChromaDB's internal _collection API.

Uses _collection directly because langchain-chroma 1.1 has no public equivalents
for count() or bulk metadata retrieval. If Chroma adds public methods, update here.
"""


def count(vectorstore) -> int:
    return vectorstore._collection.count()


def list_sources(vectorstore) -> list[str]:
    result = vectorstore._collection.get(include=["metadatas"])
    return sorted({m["source"] for m in result["metadatas"] if m.get("source")})
