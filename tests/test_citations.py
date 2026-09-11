import asyncio
from unittest.mock import MagicMock

from app.citations import extract_quotes, normalize, verify_citations
from app.models import CitationStats, QuestionnaireInput
from app.rag import _render_citation_section, run_pipeline


def _doc(text, source="RGPD.pdf"):
    d = MagicMock()
    d.page_content = text
    d.metadata = {"source": source}
    return d


CHUNK = (
    "Artículo 5. Principios relativos al tratamiento. Los datos personales serán "
    "tratados de manera lícita, leal y transparente en relación con el interesado."
)


def test_extract_quotes_standard_format():
    answer = '> "tratados de manera lícita, leal y transparente" — RGPD, p. 36'
    assert extract_quotes(answer) == ["tratados de manera lícita, leal y transparente"]


def test_extract_quotes_typographic_and_guillemets():
    answer = (
        "> “tratados de manera lícita” — RGPD, p. 36\n"
        "> «leal y transparente» – LOPDGDD, p. 2\n"
    )
    assert extract_quotes(answer) == [
        "tratados de manera lícita",
        "leal y transparente",
    ]


def test_extract_quotes_without_dash_still_captures():
    assert extract_quotes('> "leal y transparente"') == ["leal y transparente"]


def test_extract_quotes_ignores_non_blockquote_lines():
    answer = 'El RGPD dice "algo" en el artículo 5.\n**Interpretación:** "nada"'
    assert extract_quotes(answer) == []


def test_normalize_removes_whitespace_quotes_hyphens_and_case():
    assert normalize('Trata-\nmient o "lícito"') == "tratamientolícito"


def test_verify_exact_quote_is_verified():
    stats = verify_citations(
        '> "tratados de manera lícita, leal y transparente" — RGPD, p. 36',
        [_doc(CHUNK)],
    )
    assert stats == CitationStats(total=1, verificadas=1, no_verificadas=[])


def test_verify_tolerates_pdf_extraction_spacing():
    chunk = "Los dat os personales ser án trat ados de manera líc ita, leal y transparen te."
    stats = verify_citations(
        '> "Los datos personales serán tratados de manera lícita" — RGPD',
        [_doc(chunk)],
    )
    assert stats.verificadas == 1


def test_verify_tolerates_line_break_hyphenation():
    chunk = "serán tratados de manera lícita, leal y trans-\nparente en relación"
    stats = verify_citations(
        '> "leal y transparente en relación" — RGPD', [_doc(chunk)]
    )
    assert stats.verificadas == 1


def test_verify_ellipsis_splits_into_segments():
    stats = verify_citations(
        '> "Los datos personales serán […] leal y transparente" — RGPD',
        [_doc(CHUNK)],
    )
    assert stats.verificadas == 1


def test_verify_paraphrase_is_not_verified():
    stats = verify_citations(
        '> "los datos deben tratarse siempre con lealtad absoluta" — RGPD, p. 36',
        [_doc(CHUNK)],
    )
    assert stats.total == 1
    assert stats.verificadas == 0
    assert stats.no_verificadas == [
        "los datos deben tratarse siempre con lealtad absoluta"
    ]


def test_verify_too_short_quote_is_not_verified():
    stats = verify_citations('> "lícita" — RGPD', [_doc(CHUNK)])
    assert stats.verificadas == 0


def test_verify_quote_spanning_two_chunks_is_not_verified():
    stats = verify_citations(
        '> "fin del primero inicio del segundo" — RGPD',
        [_doc("texto fin del primero"), _doc("inicio del segundo texto")],
    )
    assert stats.verificadas == 0


def test_verify_no_quotes_gives_zero_total():
    assert verify_citations("Sin citas.", [_doc(CHUNK)]) == CitationStats(
        total=0, verificadas=0, no_verificadas=[]
    )


def test_verify_truncates_unverified_to_120_chars():
    long_quote = "x" * 200
    stats = verify_citations(f'> "{long_quote}" — RGPD', [_doc(CHUNK)])
    assert len(stats.no_verificadas[0]) == 120


def test_render_citation_section_empty_when_no_quotes():
    assert (
        _render_citation_section(
            CitationStats(total=0, verificadas=0, no_verificadas=[])
        )
        == ""
    )


def test_render_citation_section_lists_unverified():
    text = _render_citation_section(
        CitationStats(total=3, verificadas=2, no_verificadas=["cita inventada"])
    )
    assert "## Verificación de citas" in text
    assert "2 de 3" in text
    assert '- "cita inventada"' in text


def test_run_pipeline_reports_citation_stats(mock_reranker):
    inp = QuestionnaireInput(
        tipo_proyecto="app_web",
        descripcion_breve="App de gestión",
        tiene_usuarios_registrados=True,
        acceso_publico=False,
        tipos_datos_personales=["ninguno"],
        usuarios_menores=False,
        usuarios_ue=True,
        transferencia_datos_terceros=False,
        usa_ia=False,
        tipo_ia=None,
        usa_cookies=False,
        monetizacion=None,
        contenido_digital=False,
        ccaa="Madrid",
        es_empresa=False,
        colegiado=None,
    )
    state = MagicMock()
    state.vectorstore.similarity_search_with_relevance_scores.return_value = [
        (_doc(CHUNK), 0.9),
        (_doc(CHUNK + " Segundo fragmento."), 0.8),
    ]
    state.groq_client.invoke.return_value = MagicMock(
        content=(
            "## RGPD\n\n"
            '> "tratados de manera lícita, leal y transparente" — RGPD, p. 36\n\n'
            '> "esta cita no existe en ningún fragmento recuperado" — RGPD, p. 1\n'
        )
    )
    state.groq_fallback_client = None
    state.indexed_normativas = frozenset({"RGPD"})
    state.corpus_version = "v1"

    result = asyncio.run(run_pipeline(inp, state))

    assert result.citas.total == 2
    assert result.citas.verificadas == 1
    assert result.citas.no_verificadas == [
        "esta cita no existe en ningún fragmento recuperado"
    ]
    assert "## Verificación de citas" in result.respuesta_completa
    assert "1 de 2" in result.respuesta_completa
