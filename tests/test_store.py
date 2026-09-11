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


def test_read_index_meta_returns_dict(tmp_path):
    (tmp_path / ".index_meta.json").write_text('{"embedding_model": "m", "chunks": 3}')
    assert store.read_index_meta(str(tmp_path)) == {"embedding_model": "m", "chunks": 3}


def test_read_index_meta_missing_file_returns_empty(tmp_path):
    assert store.read_index_meta(str(tmp_path)) == {}


def test_read_index_meta_corrupt_json_returns_empty(tmp_path):
    (tmp_path / ".index_meta.json").write_text("{not valid json")
    assert store.read_index_meta(str(tmp_path)) == {}


def test_read_index_meta_non_dict_payload_returns_empty(tmp_path):
    (tmp_path / ".index_meta.json").write_text("[1, 2, 3]")
    assert store.read_index_meta(str(tmp_path)) == {}
