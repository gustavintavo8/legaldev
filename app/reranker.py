from sentence_transformers import CrossEncoder

_MODEL_NAME = "BAAI/bge-reranker-base"
_encoder: CrossEncoder | None = None


def get_encoder() -> CrossEncoder:
    global _encoder
    if _encoder is None:
        _encoder = CrossEncoder(_MODEL_NAME)
    return _encoder


def rerank(query: str, docs: list, top_k: int) -> list:
    if not docs:
        return docs
    encoder = get_encoder()
    pairs = [(query, doc.page_content) for doc in docs]
    scores = encoder.predict(pairs)
    ranked = sorted(zip(scores, docs), key=lambda x: x[0], reverse=True)
    return [doc for _, doc in ranked[:top_k]]
