from prometheus_client import REGISTRY


def _sample_value(sample_name: str, labels: dict | None = None) -> float:
    for metric in REGISTRY.collect():
        for sample in metric.samples:
            if sample.name == sample_name:
                if labels is None or all(
                    sample.labels.get(k) == v for k, v in labels.items()
                ):
                    return sample.value
    return 0.0


def test_chunks_retrieved_recorded_after_analyze(client, sample_input_dict):
    before = _sample_value("legaldev_chunks_retrieved_sum")
    client.post("/v1/analyze", json=sample_input_dict)
    after = _sample_value("legaldev_chunks_retrieved_sum")
    assert after > before


def test_retrieval_duration_recorded(client, sample_input_dict):
    before = _sample_value("legaldev_retrieval_duration_seconds_count")
    client.post("/v1/analyze", json=sample_input_dict)
    after = _sample_value("legaldev_retrieval_duration_seconds_count")
    assert after == before + 1


def test_no_coverage_counter_increments_on_404(client, sample_input_dict):
    from unittest.mock import MagicMock

    client.app.state.vectorstore.similarity_search_with_relevance_scores.return_value = []
    before = _sample_value("legaldev_404_no_coverage_total")
    client.post("/v1/analyze", json=sample_input_dict)
    after = _sample_value("legaldev_404_no_coverage_total")
    assert after == before + 1
    # restore
    mock_doc = MagicMock()
    mock_doc.page_content = (
        "El RGPD establece que los datos personales deben tratarse de forma lícita."
    )
    mock_doc.metadata = {"source": "RGPD.pdf", "doc_type": "normativa_europea"}
    client.app.state.vectorstore.similarity_search_with_relevance_scores.return_value = [
        (mock_doc, 0.85)
    ]
