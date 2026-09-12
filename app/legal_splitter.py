import re

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

_ARTICLE_PATTERN = re.compile(
    r"(?=(?:Artículo|Art\.|Considerando|ARTÍCULO)\s+\d+)",
    re.MULTILINE,
)
_ARTICLE_HEADING = re.compile(r"^(?:Artículo|Art\.|Considerando|ARTÍCULO)\s+\d+")
_MAX_ARTICLE_CHARS = 1500
_FALLBACK_SPLITTER = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)


def split_document(doc: Document) -> list[Document]:
    """Divide una página en chunks por límites de artículo, con fallback por tamaño.

    Cada parte que empieza por "Artículo N" / "Art. N" / "Considerando N" lleva
    metadata["article"] con ese encabezado. Si la parte supera _MAX_ARTICLE_CHARS se
    subdivide, y los sub-chunks a partir del segundo se prefijan con "<encabezado> (cont.): ".
    Ese prefijo es sintético (no existe en el PDF): se añade para que cada sub-chunk sea
    autodescriptivo para el embedding, el reranker y la cita del LLM; por eso la
    verificación de citas compara contra el texto del chunk, no contra el PDF.
    """
    text = doc.page_content.strip()
    if not text:
        return []

    parts = _ARTICLE_PATTERN.split(text)
    chunks: list[Document] = []

    for part in parts:
        part = part.strip()
        if not part:
            continue
        metadata = dict(doc.metadata)
        heading_match = _ARTICLE_HEADING.match(part)
        heading = heading_match.group(0) if heading_match else None
        if heading:
            metadata["article"] = heading
        if len(part) <= _MAX_ARTICLE_CHARS:
            chunks.append(Document(page_content=part, metadata=metadata))
            continue
        # Artículo largo: cada sub-chunk conserva el encabezado para que sea autodescriptivo
        # (embedding, reranker y cita del LLM saben de qué artículo es).
        sub = _FALLBACK_SPLITTER.create_documents([part], metadatas=[metadata])
        for i, sub_doc in enumerate(sub):
            if heading and i > 0:
                sub_doc.page_content = f"{heading} (cont.): {sub_doc.page_content}"
        chunks.extend(sub)

    if not chunks:
        return _FALLBACK_SPLITTER.split_documents([doc])
    return chunks
