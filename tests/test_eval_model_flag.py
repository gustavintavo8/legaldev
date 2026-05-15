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


def test_default_model_is_minilm():
    er = _load_eval_retrieval()
    parser = er._build_parser()
    args = parser.parse_args([])
    assert args.model == "all-MiniLM-L6-v2"


def test_invalid_model_rejected():
    er = _load_eval_retrieval()
    parser = er._build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--model", "not-a-real-model"])
