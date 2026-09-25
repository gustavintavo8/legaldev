"""Extracción y tipificación de obligaciones (RF-26; CU-08).

La tipificación depende de que el segmentador reconozca «Ar tículo» (prueba xfail en
tests/test_legal_splitter.py): con el índice actual ninguna obligación del RGPD tendría
artículo.
"""

import pytest


@pytest.mark.skip(
    reason="TODO(PT3/RF-26): extract_obligations sigue el formato fijado por SYSTEM_PROMPT"
)
def test_rf26_extract_obligations_from_report_format():
    """Un bloque cita + Interpretación + Implementación -> una Obligacion con sus bullets."""


@pytest.mark.skip(
    reason="TODO(PT3/RF-26): locate_citations indica el fragmento de cada cita"
)
def test_rf26_locate_citations_returns_chunk_metadata():
    """source, article, page y chunk_index del fragmento que contiene la cita."""


@pytest.mark.skip(
    reason="TODO(PT3/RF-26): locate_citations y verify_citations coinciden en verificada"
)
def test_rf26_locate_citations_agrees_with_verify_citations():
    """Mismo recuento de verificadas que CitationStats para los casos de test_citations.py."""


@pytest.mark.skip(
    reason="TODO(PT3/RF-26): parse_article_number admite '(cont.)' y rechaza considerandos"
)
def test_rf26_parse_article_number():
    """'Artículo 13' -> 13; 'Artículo 35 (cont.)' -> 35; 'Considerando 4' -> None."""


@pytest.mark.skip(
    reason="TODO(PT3/CU-08): cita no verificada -> sin tipificar (flujo 3a)"
)
def test_cu08_unverified_citation_is_not_typed():
    """motivo == 'cita no verificada'."""


@pytest.mark.skip(
    reason="TODO(PT3/CU-08): fragmento sin artículo ni página mapeable -> sin tipificar"
)
def test_cu08_chunk_without_article_is_not_typed():
    """motivo == 'artículo desconocido' (considerandos, exposiciones de motivos)."""


@pytest.mark.skip(reason="TODO(PT3/RF-26): guía sin articulado se tipifica por página")
def test_rf26_guide_without_articles_is_typed_by_page():
    """Guía de cookies de la AEPD: pagina en base 1 y articulo None."""
