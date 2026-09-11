import importlib.util
from pathlib import Path

import pytest


def _load_eval_retrieval():
    spec = importlib.util.spec_from_file_location(
        "eval_retrieval",
        Path(__file__).parent.parent / "tools" / "eval_retrieval.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_model_flag_accepted():
    er = _load_eval_retrieval()
    parser = er._build_parser()
    args = parser.parse_args(["--model", "paraphrase-multilingual-MiniLM-L12-v2"])
    assert args.model == "paraphrase-multilingual-MiniLM-L12-v2"


def test_default_model_is_multilingual():
    er = _load_eval_retrieval()
    parser = er._build_parser()
    args = parser.parse_args([])
    assert args.model == "paraphrase-multilingual-MiniLM-L12-v2"


def test_invalid_model_rejected():
    er = _load_eval_retrieval()
    parser = er._build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--model", "not-a-real-model"])


def test_chroma_path_flag_defaults_to_settings():
    er = _load_eval_retrieval()
    args = er._build_parser().parse_args([])
    assert args.chroma_path == er.settings.chroma_db_path
    assert args.force is False


def test_check_index_model_aborts_on_mismatch():
    er = _load_eval_retrieval()
    with pytest.raises(SystemExit):
        er._check_index_model({"embedding_model": "a"}, "b", force=False)


def test_check_index_model_force_skips_abort():
    er = _load_eval_retrieval()
    er._check_index_model({"embedding_model": "a"}, "b", force=True)


def test_check_index_model_passes_when_match_or_missing():
    er = _load_eval_retrieval()
    er._check_index_model({"embedding_model": "a"}, "a", force=False)
    er._check_index_model({}, "a", force=False)
