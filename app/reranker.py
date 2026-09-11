from sentence_transformers import CrossEncoder

_MODEL_NAME = "BAAI/bge-reranker-base"
_encoder: CrossEncoder | None = None


def get_encoder() -> CrossEncoder:
    global _encoder
    if _encoder is None:
        _encoder = CrossEncoder(_MODEL_NAME)
    return _encoder


def warmup() -> None:
    """Carga el modelo y ejecuta una predicción mínima para que la primera petición no lo pague.

    La carga desde disco cuesta ~2 s y la primera predicción compila kernels; en producción
    (CPU compartida) ese coste se sumaba al primer análisis. Idempotente: get_encoder es singleton.
    """
    get_encoder().predict([("warmup", "warmup")])


def rerank(query: str, docs: list, top_k: int) -> list:
    if not docs:
        return docs
    encoder = get_encoder()
    pairs = [(query, doc.page_content) for doc in docs]
    scores = encoder.predict(pairs)
    ranked = sorted(zip(scores, docs), key=lambda x: x[0], reverse=True)
    return [doc for _, doc in ranked[:top_k]]
