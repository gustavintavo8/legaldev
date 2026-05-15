from prometheus_client import Counter, Histogram

chunks_retrieved = Histogram(
    "legaldev_chunks_retrieved",
    "Number of chunks passed to LLM after filtering and reranking",
    buckets=[1, 2, 4, 8, 12, 16, 20, 30],
)

top_score = Histogram(
    "legaldev_top_score",
    "Top relevance score from ChromaDB retrieval",
    buckets=[0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

retrieval_duration = Histogram(
    "legaldev_retrieval_duration_seconds",
    "Time spent in ChromaDB retrieval (all searches combined)",
)

llm_duration = Histogram(
    "legaldev_llm_duration_seconds",
    "Time spent waiting for LLM response from Groq",
)

no_coverage_total = Counter(
    "legaldev_404_no_coverage_total",
    "Requests returning 404 due to no relevant chunks above threshold",
)

aux_search_triggered = Counter(
    "legaldev_aux_search_triggered_total",
    "Number of times each auxiliary search type was triggered",
    ["type"],
)
