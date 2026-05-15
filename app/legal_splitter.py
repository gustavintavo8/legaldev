import re

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

_ARTICLE_PATTERN = re.compile(
    r"(?=(?:Artículo|Art\.|Considerando|ARTÍCULO)\s+\d+)",
    re.MULTILINE,
)
_MAX_ARTICLE_CHARS = 1500
_FALLBACK_SPLITTER = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)


def split_document(doc: Document) -> list[Document]:
    text = doc.page_content.strip()
    if not text:
        return []

    parts = _ARTICLE_PATTERN.split(text)
    chunks: list[Document] = []

    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(part) <= _MAX_ARTICLE_CHARS:
            chunks.append(Document(page_content=part, metadata=dict(doc.metadata)))
        else:
            sub = _FALLBACK_SPLITTER.create_documents(
                [part], metadatas=[dict(doc.metadata)]
            )
            chunks.extend(sub)

    if not chunks:
        return _FALLBACK_SPLITTER.split_documents([doc])
    return chunks
