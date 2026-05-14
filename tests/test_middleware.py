import logging


def test_response_has_x_request_id_header(client, sample_input_dict):
    response = client.post("/v1/analyze", json=sample_input_dict)
    assert response.status_code == 200
    assert "x-request-id" in response.headers


def test_x_request_id_is_nonempty(client, sample_input_dict):
    response = client.post("/v1/analyze", json=sample_input_dict)
    assert len(response.headers["x-request-id"]) > 0


def test_get_endpoint_also_has_request_id(client):
    response = client.get("/health")
    assert "x-request-id" in response.headers


def test_request_id_in_rag_logs(client, sample_input_dict, caplog):
    with caplog.at_level(logging.INFO, logger="app.rag"):
        response = client.post("/v1/analyze", json=sample_input_dict)
    request_id = response.headers.get("x-request-id", "")
    assert request_id
    assert any(request_id in record.message for record in caplog.records)
