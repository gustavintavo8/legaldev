import asyncio
import time
import unicodedata
from unittest.mock import MagicMock

from prometheus_client import REGISTRY

from app.citations import extract_quotes, normalize, verify_citations
from app.models import CitationStats, QuestionnaireInput
from app.rag import _render_citation_section, run_pipeline


def _doc(text, source="RGPD.pdf"):
    d = MagicMock()
    d.page_content = text
    d.metadata = {"source": source}
    return d


def _metric_value(name: str) -> float:
    """Mirrors the `_metric`/`_sample_value` helper used in test_llm_fallback.py /
    test_metrics.py: metrics live in the shared global REGISTRY across the whole
    test run, so tests compare before/after rather than asserting absolute values.
    """
    for metric in REGISTRY.collect():
        for sample in metric.samples:
            if sample.name == name:
                return sample.value
    return 0.0


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


# ── Fix round 1 — review findings ────────────────────────────────────────────


def test_extract_quotes_wrapped_two_line_quote_joins_and_verifies():
    """[Important] A quote wrapped by the LLM across two blockquote lines must be
    joined into ONE quote, not silently dropped from `total`."""
    answer = (
        '> "Los datos personales seran tratados de manera licita, leal y\n'
        '> transparente en relacion con el interesado" — RGPD, p. 36\n'
    )
    assert extract_quotes(answer) == [
        "Los datos personales seran tratados de manera licita, leal y "
        "transparente en relacion con el interesado"
    ]
    chunk = (
        "Articulo 5. Los datos personales seran tratados de manera licita, "
        "leal y transparente en relacion con el interesado, segun el RGPD."
    )
    stats = verify_citations(answer, [_doc(chunk)])
    assert stats.total == 1
    assert stats.verificadas == 1


def test_extract_quotes_two_self_contained_citations_on_consecutive_lines():
    """Two already-complete citations on consecutive `>` lines must NOT fuse into
    one when their paragraph gets joined for the wrapped-quote fix above."""
    answer = '> "cita" — RGPD, p. 36\n> "otra" — LSSI, p. 2\n'
    assert extract_quotes(answer) == ["cita", "otra"]


def test_extract_quotes_blank_line_separates_paragraphs():
    answer = (
        '> "primera cita completa aqui" — RGPD, p. 1\n'
        "\n"
        '> "segunda cita completa aqui" — RGPD, p. 2\n'
    )
    assert extract_quotes(answer) == [
        "primera cita completa aqui",
        "segunda cita completa aqui",
    ]


def test_verify_crlf_line_endings_behave_like_lf():
    answer = (
        '> "tratados de manera lícita" — RGPD, p. 36\r\n'
        '> "leal y transparente" — RGPD, p. 36\r\n'
    )
    stats = verify_citations(answer, [_doc(CHUNK)])
    assert stats.total == 2
    assert stats.verificadas == 2


def test_verify_same_line_nested_quote_greedy_overcapture_is_pinned():
    """[Minor] Documented trade-off of the "last closing quote before a dash" rule:
    when a SECOND quoted span follows the attribution on the SAME physical line
    (no line-wrap involved), the greedy match still fuses both into one blob
    instead of extracting two citations. Only paragraphs assembled by joining
    2+ raw blockquote lines go through `_split_paragraph`'s disambiguation
    (see extract_quotes) — a single physical line keeps the historical,
    deliberately naive behaviour pinned here."""
    answer = '> "cita real" — RGPD, p. 36 (vease tambien "art. 6" — LOPDGDD)'
    stats = verify_citations(answer, [_doc(CHUNK)])
    assert stats.total == 1
    assert stats.verificadas == 0


def test_normalize_strips_pipe_character():
    assert normalize("a | b") == "ab"


def test_verify_quote_with_pipe_does_not_bridge_chunks():
    """[Minor] "|" must be stripped by normalize() so a quote that happens to
    contain a literal "|" cannot align with the "|" verify_citations inserts
    between chunks and falsely verify a citation spanning two fragments."""
    stats = verify_citations(
        '> "fin del primero|inicio del segundo texto aqui" — RGPD',
        [_doc("texto fin del primero"), _doc("inicio del segundo texto aqui")],
    )
    assert stats.verificadas == 0


def test_verify_tolerates_zero_width_characters():
    chunk = "tratados de ma​nera licita y transparente en el texto"
    stats = verify_citations(
        '> "de manera licita y transparente" — RGPD', [_doc(chunk)]
    )
    assert stats.verificadas == 1


def test_extract_quotes_empty_quote_is_ignored():
    assert extract_quotes('> "" — RGPD') == []


def test_extract_quotes_multiline_paragraph_without_quotes_yields_nothing():
    """Covers _split_paragraph's degenerate case: a paragraph joined from 2+
    physical lines that contains no quote characters at all."""
    answer = "> Esto es una nota de dos líneas\n> sin ninguna cita literal.\n"
    assert extract_quotes(answer) == []


# ── Fix round 2 — linear _split_paragraph ────────────────────────────────────


def test_split_paragraph_is_linear_on_many_stray_quotes():
    """[Important] Regression for the non-linear slowdown: a paragraph joined
    from 2+ lines with many stray, never-completing quote characters must not
    make _split_paragraph re-scan an ever-larger prefix per quote."""
    fragment_count = 4000
    answer = "> " + ('"a" ' * fragment_count) + "\n> mas texto sin cierre\n"

    start = time.perf_counter()
    result1 = extract_quotes(answer)
    elapsed = time.perf_counter() - start

    assert elapsed < 1.0, f"extract_quotes took {elapsed:.3f}s, expected < 1.0s"
    result2 = extract_quotes(answer)
    assert result1 == result2


def test_split_paragraph_many_self_contained_quotes_stays_fast():
    quote_count = 2000
    answer = "".join(f'> "cita {i}" — RGPD\n' for i in range(quote_count))

    start = time.perf_counter()
    quotes = extract_quotes(answer)
    elapsed = time.perf_counter() - start

    assert elapsed < 1.0, f"extract_quotes took {elapsed:.3f}s, expected < 1.0s"
    assert len(quotes) == quote_count


def test_run_pipeline_records_citation_metrics(mock_reranker):
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

    before_ratio_count = _metric_value("legaldev_citations_verified_ratio_count")
    before_unverified = _metric_value("legaldev_citations_unverified_total")

    asyncio.run(run_pipeline(inp, state))

    assert (
        _metric_value("legaldev_citations_verified_ratio_count")
        == before_ratio_count + 1
    )
    assert _metric_value("legaldev_citations_unverified_total") == before_unverified + 1


def test_run_pipeline_without_quotes_does_not_touch_citation_metrics(mock_reranker):
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
        content="## RGPD\n\nEste informe no incluye citas textuales en este ejemplo.\n"
    )
    state.groq_fallback_client = None
    state.indexed_normativas = frozenset({"RGPD"})
    state.corpus_version = "v1"

    before_ratio_count = _metric_value("legaldev_citations_verified_ratio_count")
    before_unverified = _metric_value("legaldev_citations_unverified_total")

    result = asyncio.run(run_pipeline(inp, state))

    assert result.citas.total == 0
    assert (
        _metric_value("legaldev_citations_verified_ratio_count") == before_ratio_count
    )
    assert _metric_value("legaldev_citations_unverified_total") == before_unverified


def test_verify_segment_exactly_min_chars_verifies():
    chunk = "abcdefghijkl texto adicional de relleno"
    stats = verify_citations('> "abcdefghijkl" — RGPD', [_doc(chunk)])
    assert stats.verificadas == 1


def test_verify_segment_below_min_chars_does_not_verify():
    chunk = "abcdefghijk texto adicional de relleno"
    stats = verify_citations('> "abcdefghijk" — RGPD', [_doc(chunk)])
    assert stats.verificadas == 0


def test_verify_empty_docs_list_all_unverified_without_exception():
    stats = verify_citations(
        '> "cualquier cita de al menos doce caracteres" — RGPD', []
    )
    assert stats.total == 1
    assert stats.verificadas == 0
    assert stats.no_verificadas == ["cualquier cita de al menos doce caracteres"]


def test_verify_nfd_decomposed_chunk_matches_nfc_quote():
    composed_quote = "protección de datos personales completa"
    decomposed_chunk = unicodedata.normalize("NFD", composed_quote)
    stats = verify_citations(f'> "{composed_quote}" — RGPD', [_doc(decomposed_chunk)])
    assert stats.verificadas == 1


def test_verify_all_caps_accented_chunk_verifies():
    chunk = "TRATAMIENTO LÍCITO Y TRANSPARENTE DE DATOS PERSONALES"
    stats = verify_citations(
        '> "tratamiento lícito y transparente" — RGPD', [_doc(chunk)]
    )
    assert stats.verificadas == 1


# --- Tolerancia en los extremos (casos reales del despliegue del sprint 3, 2026-09-12) ---

_AI_ACT_CHUNK = (
    "organismos notificados y otras entidades pertinentes, como centros europeos de "
    "innovación digital, instalaciones de ensayo y experimentación e investigadores, "
    "deben tener acceso a conjuntos de datos de alta calidad en sus campos de actividad "
    "relacionados con el presente Reglamento y deben poder utilizarlos. Los espacios "
    "comunes europeos de datos establecidos"
)


def test_verify_tolerates_trailing_period_added_by_llm():
    chunk = (
        "un consentimiento informado con el fin de asegurar que los usuarios de esos"
    )
    stats = verify_citations(
        '> "un consentimiento informado con el fin de asegurar que los usuarios." — Cookies',
        [_doc(chunk)],
    )
    assert stats.verificadas == 1


def test_verify_tolerates_leading_word_cut_by_chunk_boundary():
    # El chunk empieza a mitad de frase ("organismos…"); el LLM cita la frase
    # completa con su artículo ("los organismos…"). Diferencia: 3 chars de 269.
    stats = verify_citations(
        '> "los organismos notificados y otras entidades pertinentes, como centros '
        "europeos de innovación digital, instalaciones de ensayo y experimentación e "
        "investigadores, deben tener acceso a conjuntos de datos de alta calidad en sus "
        'campos de actividad relacionados con el presente Reglamento y deben poder utilizarlos." — EU AI Act, p. 5',
        [_doc(_AI_ACT_CHUNK)],
    )
    assert stats.verificadas == 1


def test_verify_tolerates_page_footer_glued_to_chunk_end():
    chunk = "la modificación de las opciones de privacidad37Agencia Española de Protección de Datos"
    stats = verify_citations(
        '> "la modificación de las opciones de privacidad." — Guía AEPD, p. 37',
        [_doc(chunk)],
    )
    assert stats.verificadas == 1


def test_verify_rejects_more_than_ten_percent_missing_at_the_start():
    # 40 chars de prefijo inventado sobre una cita de ~100 chars → no verificada.
    stats = verify_citations(
        '> "según establece el artículo cuarenta y dos, organismos notificados y otras '
        'entidades pertinentes, como centros europeos de innovación digital" — EU AI Act',
        [_doc(_AI_ACT_CHUNK)],
    )
    assert stats.verificadas == 0


def test_verify_rejects_difference_in_the_middle_of_the_quote():
    stats = verify_citations(
        '> "organismos notificados y otras entidades IRRELEVANTES, como centros europeos '
        'de innovación digital, instalaciones de ensayo" — EU AI Act',
        [_doc(_AI_ACT_CHUNK)],
    )
    assert stats.verificadas == 0


def test_verify_still_rejects_quote_absent_from_context():
    # Caso real: cita del considerando 12 del AI Act que NO estaba en los chunks.
    stats = verify_citations(
        '> "Debe definirse con claridad el concepto de «sistema de IA» en el presente '
        'reglamento y armonizarlo estrictamente." — EU AI Act',
        [_doc(_AI_ACT_CHUNK)],
    )
    assert stats.verificadas == 0
    assert stats.no_verificadas[0].startswith("Debe definirse con claridad")


def test_verify_tolerance_does_not_shorten_below_min_segment():
    # Segmento de 13 chars normalizados con 1 char sobrante: el núcleo tendría 12,
    # justo el mínimo → se acepta; con 2 chars sobrantes el núcleo bajaría de 12 → no.
    assert (
        verify_citations(
            '> "abcdefghijklm" — X', [_doc("abcdefghijkl zzz")]
        ).verificadas
        == 1
    )
    assert (
        verify_citations(
            '> "abcdefghijklmn" — X', [_doc("abcdefghijkl zzz")]
        ).verificadas
        == 0
    )
