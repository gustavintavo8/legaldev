"""Evidencias exportables (PP-10; RF-27; RNF-17; CU-08).

Las guardas que corren hoy comprueban que el modelo de la evidencia no admite la descripción
libre y que el esquema JSON del andamiaje es un JSON Schema 2020-12 válido.
"""

import json
from typing import get_args

import pytest

from app import evidence
from app.models import QuestionnaireInput
from app.obligations import MotivoSinTipificar


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


def test_rf27_schema_and_models_declare_the_same_closed_objects():
    # Guarda de sincronía mientras el esquema se mantenga a mano (ver su $comment): cada
    # objeto del esquema es cerrado y tiene los mismos campos que su modelo Pydantic.
    schema = json.loads(evidence.SCHEMA_PATH.read_text(encoding="utf-8"))
    props = schema["properties"]
    pairs = {
        "evidencia": (schema, evidence.EvidenceDocument),
        "generador": (props["generador"], evidence.Generador),
        "proyecto": (props["proyecto"], evidence.ProyectoEvidencia),
        "obligacion": (schema["$defs"]["obligacion"], evidence.ObligacionEvidencia),
        "sin_tipificar": (
            props["sin_tipificar"]["items"],
            evidence.SinTipificarEvidencia,
        ),
        "sin_mapeo": (props["sin_mapeo"]["items"], evidence.SinMapeoEvidencia),
    }
    for name, (node, model) in pairs.items():
        assert set(node["properties"]) == set(model.model_fields), name
        assert node["additionalProperties"] is False, name


def test_rf27_example_of_the_memoria_validates_against_the_schema(sample_input):
    # Los valores de lst:det-evidencia, construidos con los modelos: el esquema a mano y los
    # modelos Pydantic aceptan el mismo documento (tipos, no solo nombres de campo).
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(evidence.SCHEMA_PATH.read_text(encoding="utf-8"))
    doc = evidence.EvidenceDocument(
        generador=evidence.Generador(
            version="0.4.0",
            corpus_version="7a2029a4dfd8",
            mapeo_version="0.1.0",
            llm_model="openai/gpt-oss-120b",
        ),
        generado="2026-09-25T12:00:00Z",
        request_id="req-1",
        proyecto=evidence.ProyectoEvidencia.model_validate(
            sample_input.model_dump(exclude={"descripcion_breve"})
        ),
        obligaciones=[
            evidence.ObligacionEvidencia(
                id_tipo="lssi.art22.cookies",
                normativa="LSSI",
                articulo="22",
                pagina=17,
                fragmento="0123456789ab",
                cita="cita literal",
                cita_verificada=True,
                controles=evidence.ControlesAsociados(iso27001=["A.5.34"]),
                acciones=["acción del informe"],
            )
        ],
        sin_tipificar=[
            evidence.SinTipificarEvidencia(cita="...", motivo="fragmento sin artículo")
        ],
        sin_mapeo=[],
    )
    jsonschema.Draft202012Validator(schema).validate(doc.model_dump(mode="json"))


def test_cu08_untyped_reasons_are_those_of_the_typing_algorithm():
    # lst:det-alg-tipificacion (23-detalle): mismos motivos en el esquema y en el modelo.
    schema = json.loads(evidence.SCHEMA_PATH.read_text(encoding="utf-8"))
    motivo = schema["properties"]["sin_tipificar"]["items"]["properties"]["motivo"]
    expected = (
        "cita no verificada",
        "cita repartida en varios fragmentos",
        "fragmento sin artículo",
    )
    assert tuple(motivo["enum"]) == get_args(MotivoSinTipificar) == expected


@pytest.mark.skip(
    reason="TODO(PT3/PP-10): cada evidencia generada valida contra data/evidence.schema.json"
)
def test_pp10_generated_evidence_validates_against_schema():
    """build_evidence(...) con un informe simulado -> validate_against_schema no lanza."""


@pytest.mark.skip(
    reason="TODO(PT3/PP-10): la evidencia incluye corpus_version, mapeo_version y llm_model"
)
def test_pp10_evidence_includes_corpus_mapping_and_model_versions():
    """generador lleva las tres versiones con las que se generó (RNF-17); la página es base 1
    y el fragmento es service.fragment_id del fragmento de respaldo."""


@pytest.mark.skip(
    reason="TODO(PT3/RF-27): el Markdown contiene la misma información que el JSON"
)
def test_rf27_markdown_render_matches_json_content():
    """Mismas obligaciones, controles, estados, versiones y aviso."""


@pytest.mark.skip(reason="TODO(PT3/RF-27): POST /v1/evidence devuelve JSON y Markdown")
def test_rf27_post_v1_evidence_returns_json_and_markdown():
    """Mismo limitador, claves de API y caché que /v1/analyze; responde EvidenceResponse."""


@pytest.mark.skip(
    reason="TODO(PT3/PP-10): la evidencia se reproduce idéntica a partir del mismo informe"
)
def test_pp10_build_evidence_is_deterministic():
    """Mismas entradas (reloj y request_id como parámetros) -> mismo documento, byte a byte."""
