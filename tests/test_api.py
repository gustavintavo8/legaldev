def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "LegalDev"
    assert data["version"] == "0.1.0"
    assert "description" in data


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["docs_indexed"] == 1234


def test_analyze_returns_rag_response(client, sample_input_dict):
    response = client.post("/analyze", json=sample_input_dict)
    assert response.status_code == 200
    data = response.json()
    assert data["respuesta_completa"] == "Respuesta de prueba sobre RGPD"
    assert "normativas_detectadas" in data
    assert data["chunks_utilizados"] == 1
    assert "disclaimer" in data


def test_analyze_invalid_input_missing_fields(client):
    response = client.post("/analyze", json={"tipo_proyecto": "app_web"})
    assert response.status_code == 422


def test_analyze_descripcion_too_long(client, sample_input_dict):
    sample_input_dict["descripcion_breve"] = "x" * 501
    response = client.post("/analyze", json=sample_input_dict)
    assert response.status_code == 422


def test_analyze_groq_error_returns_503(client, sample_input_dict):
    client.app.state.groq_client.invoke.side_effect = Exception("LLM down")
    response = client.post("/analyze", json=sample_input_dict)
    assert response.status_code == 503


def test_analyze_no_relevant_docs_returns_404(client, sample_input_dict):
    client.app.state.vectorstore.similarity_search_with_relevance_scores.return_value = []
    response = client.post("/analyze", json=sample_input_dict)
    assert response.status_code == 404
