"""Extracción y tipificación de obligaciones (RF-26; CU-08).

La tipificación depende de que el segmentador reconozca «Ar tículo» (PT10; prueba xfail en
tests/test_legal_splitter.py): con el índice actual ninguna obligación del RGPD tendría
artículo. La localización de cada cita en su fragmento (locate_citations) también es PT10.
"""

import pytest


@pytest.mark.skip(
    reason="TODO(PT3/RF-26): extract_obligations sigue el formato fijado por SYSTEM_PROMPT"
)
def test_rf26_extract_obligations_from_report_format():
    """Un bloque cita + atribución + Interpretación + Implementación -> una Obligacion con sus
    acciones; el sumario y las secciones que añade el código se ignoran."""


@pytest.mark.skip(
    reason="TODO(PT10/RF-18): locate_citations indica el fragmento de cada cita"
)
def test_rf18_locate_citations_returns_chunk_metadata():
    """source, article, page y chunk_index del primer fragmento, en el orden del contexto, que
    contiene todos los segmentos de la cita; chunk_index None si se reparten entre varios."""


@pytest.mark.skip(
    reason="TODO(PT10/RF-18): locate_citations y verify_citations coinciden en verificada"
)
def test_rf18_locate_citations_agrees_with_verify_citations():
    """Mismo recuento de verificadas que CitationStats para los casos de test_citations.py."""


@pytest.mark.parametrize(
    "encabezado,numero",
    [
        ("Artículo 13", "13"),
        ("Artículo 35 (cont.)", "35"),
        ("ARTÍCULO 5", "5"),
        ("Considerando 4", None),  # un considerando no es un artículo
        ("Artículo 2918", None),  # número pegado a una llamada de nota
        (None, None),
    ],
)
def test_rf26_parse_article_number(encabezado, numero):
    """'Artículo 13' -> '13'; 'Artículo 35 (cont.)' -> '35'; 'Considerando 4' -> None.

    Es el mismo analizador que da ``FragmentoRef.articulo`` (``app.fragments.localizador``):
    la clave de la tipificación y el campo de las herramientas no pueden divergir."""
    from app.obligations import parse_article_number

    assert parse_article_number(encabezado) == numero


@pytest.mark.skip(
    reason="TODO(PT3/CU-08): cita no verificada -> sin tipificar (flujo 3a)"
)
def test_cu08_unverified_citation_is_not_typed():
    """motivo == 'cita no verificada'."""


@pytest.mark.skip(
    reason="TODO(PT3/CU-08): cita repartida en varios fragmentos -> sin tipificar (flujo 3a)"
)
def test_cu08_citation_spread_over_chunks_is_not_typed():
    """motivo == 'cita repartida en varios fragmentos'."""


@pytest.mark.skip(
    reason="TODO(PT3/CU-08): fragmento sin artículo -> sin tipificar (flujo 3a)"
)
def test_cu08_chunk_without_article_is_not_typed():
    """motivo == 'fragmento sin artículo' (considerandos, exposiciones de motivos y, mientras
    no se decida su clave, las guías de la AEPD)."""
