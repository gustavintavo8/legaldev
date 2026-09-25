"""Evidencias exportables (PP-10; RF-27; RNF-17; CU-08).

Las guardas que corren hoy comprueban que el modelo de la evidencia no admite la descripción
libre y que el esquema JSON del andamiaje es un JSON Schema 2020-12 válido.
"""

import json

import pytest

from app import evidence
from app.models import QuestionnaireInput


def test_rf27_project_fields_are_questionnaire_fields_without_free_text():
    expected = set(QuestionnaireInput.model_fields) - {"descripcion_breve"}
    assert set(evidence.ProyectoEvidencia.model_fields) == expected


def test_rf27_status_values_are_the_four_of_the_requirement():
    assert [e.value for e in evidence.EstadoObligacion] == [
        "no_iniciado",
        "en_curso",
        "implementado",
        "no_aplica",
    ]


def test_evidence_schema_is_valid_json_schema_2020_12():
    # jsonschema llega hoy transitivamente (chromadb); aún no es dependencia explícita.
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(evidence.SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    jsonschema.Draft202012Validator.check_schema(schema)
    assert "descripcion_breve" not in schema["properties"]["proyecto"]["properties"]
    assert schema["properties"]["proyecto"]["additionalProperties"] is False


@pytest.mark.skip(
    reason="TODO(PT3/PP-10): cada evidencia generada valida contra data/evidence.schema.json"
)
def test_pp10_generated_evidence_validates_against_schema():
    """build_evidence(...) con un informe simulado -> validate_against_schema no lanza."""


@pytest.mark.skip(
    reason="TODO(PT3/PP-10): la evidencia incluye corpus_version, mapeo_version y llm_model"
)
def test_pp10_evidence_includes_corpus_mapping_and_model_versions():
    """generador lleva las tres versiones con las que se generó (RNF-17)."""


@pytest.mark.skip(
    reason="TODO(PT3/RF-27): el Markdown contiene la misma información que el JSON"
)
def test_rf27_markdown_render_matches_json_content():
    """Mismas obligaciones, controles, estados, versiones y aviso."""


@pytest.mark.skip(reason="TODO(PT3/RF-27): POST /v1/evidence devuelve JSON y Markdown")
def test_rf27_post_v1_evidence_returns_json_and_markdown():
    """Mismo limitador, claves de API y caché que /v1/analyze; responde EvidenceResponse."""


@pytest.mark.skip(
    reason="TODO(PT3/RF-27): build_evidence es pura (reloj y request_id como parámetros)"
)
def test_rf27_build_evidence_is_deterministic():
    """Mismas entradas -> mismo documento, byte a byte."""
