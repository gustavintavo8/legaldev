import pytest
from app.ingest import get_doc_type


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("RGPD.pdf", "normativa_europea"),
        ("EU AI Act.pdf", "normativa_europea"),
        ("Directiva NIS2.pdf", "normativa_europea"),
        ("Directiva de Responsabilidad por Productos con IA.pdf", "normativa_europea"),
        ("Digital Services Act (Reglamento UE 2022-2065).pdf", "normativa_europea"),
        ("Cyber Resilience Act (Reglamento UE 2024-2847).pdf", "normativa_europea"),
        ("Directiva ePrivacy (2002-58-CE consolidada).pdf", "normativa_europea"),
        ("Data Act (Reglamento UE 2023-2854).pdf", "normativa_europea"),
        ("Data Governance Act (Reglamento UE 2022-868).pdf", "normativa_europea"),
        ("DORA (Reglamento UE 2022-2554).pdf", "normativa_europea"),
        ("LOPDGDD.pdf", "normativa_española"),
        ("Real Decreto 311-2022 ENS.pdf", "normativa_española"),
        ("LSSI.pdf", "normativa_española"),
        ("Ley de Propiedad Intelectual.pdf", "normativa_española"),
        ("Código Ético y Deontológico CCII.pdf", "deontologia"),
        ("Guía sobre uso de cookies - AEPD.pdf", "guia_aepd"),
        ("Guía de Anonimización - AEPD.pdf", "guia_aepd"),
        (
            "Adecuación al RGPD de tratamientos que incorporan IA - AEPD.pdf",
            "guia_aepd",
        ),
        ("Documento desconocido.pdf", "otro"),
    ],
)
def test_get_doc_type(filename, expected):
    assert get_doc_type(filename) == expected
