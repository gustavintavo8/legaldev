from unittest.mock import patch


def test_analyze_open_when_no_api_keys_configured(client, sample_input_dict):
    resp = client.post("/v1/analyze", json=sample_input_dict)
    assert resp.status_code == 200


def test_analyze_requires_key_when_api_keys_set(client, sample_input_dict):
    with patch("app.main.settings") as mock_settings:
        mock_settings.api_key_set = frozenset({"secret-key-abc"})
        mock_settings.rate_limit = "10/minute"
        resp = client.post("/v1/analyze", json=sample_input_dict)
    assert resp.status_code == 401


def test_analyze_rejects_wrong_key(client, sample_input_dict):
    with patch("app.main.settings") as mock_settings:
        mock_settings.api_key_set = frozenset({"correct-key"})
        mock_settings.rate_limit = "10/minute"
        resp = client.post(
            "/v1/analyze",
            json=sample_input_dict,
            headers={"X-API-Key": "wrong-key"},
        )
    assert resp.status_code == 403


def test_analyze_accepts_valid_key(client, sample_input_dict):
    with patch("app.main.settings") as mock_settings:
        mock_settings.api_key_set = frozenset({"valid-key-xyz"})
        mock_settings.rate_limit = "10/minute"
        resp = client.post(
            "/v1/analyze",
            json=sample_input_dict,
            headers={"X-API-Key": "valid-key-xyz"},
        )
    assert resp.status_code == 200


def test_health_open_without_key(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_normativas_open_without_key(client):
    resp = client.get("/normativas")
    assert resp.status_code == 200
