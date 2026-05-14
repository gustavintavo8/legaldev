from unittest.mock import MagicMock

from app import store


def test_count_returns_chunk_total():
    vs = MagicMock()
    vs._collection.count.return_value = 42
    assert store.count(vs) == 42


def test_list_sources_deduplicates_and_sorts():
    vs = MagicMock()
    vs._collection.get.return_value = {
        "metadatas": [
            {"source": "RGPD.pdf"},
            {"source": "LOPDGDD.pdf"},
            {"source": "RGPD.pdf"},
        ]
    }
    assert store.list_sources(vs) == ["LOPDGDD.pdf", "RGPD.pdf"]


def test_list_sources_skips_entries_without_source():
    vs = MagicMock()
    vs._collection.get.return_value = {
        "metadatas": [{"source": "RGPD.pdf"}, {}, {"other": "x"}]
    }
    assert store.list_sources(vs) == ["RGPD.pdf"]


def test_list_sources_calls_collection_with_metadatas():
    vs = MagicMock()
    vs._collection.get.return_value = {"metadatas": []}
    store.list_sources(vs)
    vs._collection.get.assert_called_once_with(include=["metadatas"])
