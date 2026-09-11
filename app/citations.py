"""Verificación determinista de citas: ¿cada cita textual del informe existe en los fragmentos?

El SYSTEM_PROMPT exige citas literales; este módulo comprueba que lo sean. La comparación
ignora mayúsculas, comillas, guiones y TODO el espacio en blanco, porque el texto extraído
de los PDFs contiene artefactos ("tratamient o", "prot ecci ón") y saltos de línea con guion
que el LLM corrige al citar.
"""

import re
import unicodedata

from app.models import CitationStats

MIN_SEGMENT_CHARS = 12
MAX_REPORTED_CHARS = 120

# Línea de blockquote individual — se recorre línea a línea (no re.MULTILINE
# sobre todo el texto) para poder agrupar líneas consecutivas en un párrafo.
_BLOCKQUOTE_LINE_RE = re.compile(r"^\s*>\s?(.*)$")
# Primera comilla de apertura … última comilla de cierre seguida de guion (— – -).
# (.+) exige contenido no vacío: una cita vacía > "" — X no debe contar como cita.
_QUOTED_BEFORE_DASH_RE = re.compile(r"[\"“«](.+)[\"”»]\s*[—–-]")
_QUOTED_RE = re.compile(r"[\"“«](.+)[\"”»]")
_OPENING_QUOTE_RE = re.compile(r"[\"“«]")
_ELLIPSIS_RE = re.compile(r"\[\s*(?:\.\.\.|…)\s*\]|\.\.\.|…")
# Espacio en blanco, comillas, guiones, "|" (separador de chunks — ver
# verify_citations) y caracteres invisibles (ZWSP/ZWNJ/ZWJ/word joiner/BOM) que
# el texto extraído de PDFs a veces intercala dentro de una misma palabra.
_STRIP_RE = re.compile(r"[\s\"“”«»'‘’\-–—­|​‌‍⁠﻿]+")


def _split_paragraph(paragraph: str) -> list[str]:
    """Divide un párrafo que junta varias líneas de blockquote en un tramo por cita.

    Solo se invoca desde extract_quotes cuando el párrafo se formó uniendo 2+
    líneas físicas (ver más abajo) — es decir, solo para deshacer la unión
    cuando esas líneas contenían en realidad citas independientes, no para
    citas que ya vivían en una única línea (ese caso conserva el comportamiento
    histórico, ver el comentario en extract_quotes).

    Recorre las posiciones de comilla de apertura; corta justo antes de una
    comilla si el tramo acumulado hasta ahí YA es una cita completa (comilla
    … comilla + guion) — si no, seguye acumulando, para no partir una cita que
    el ajuste de línea del LLM dejó a medias.
    """
    positions = [m.start() for m in _OPENING_QUOTE_RE.finditer(paragraph)]
    if not positions:
        return [paragraph]
    spans: list[str] = []
    start = positions[0]
    for pos in positions[1:]:
        if _QUOTED_BEFORE_DASH_RE.search(paragraph[start:pos]):
            spans.append(paragraph[start:pos])
            start = pos
    spans.append(paragraph[start:])
    return spans


def extract_quotes(answer: str) -> list[str]:
    quotes: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        if not buffer:
            return
        paragraph = " ".join(buffer)
        # _split_paragraph solo entra en juego cuando el párrafo junta 2+ líneas
        # físicas de blockquote — el caso que existe para arreglar: una cita
        # partida en dos líneas por el ajuste de línea del LLM, o dos citas
        # autocontenidas que caen en líneas consecutivas. Un párrafo que
        # siempre fue una única línea física conserva el comportamiento
        # histórico (una sola aplicación de las dos regexes a toda la línea):
        # ver test_verify_same_line_nested_quote_greedy_overcapture_is_pinned
        # para el trade-off documentado de comillas anidadas en una sola línea.
        spans = _split_paragraph(paragraph) if len(buffer) > 1 else [paragraph]
        buffer.clear()
        for span in spans:
            q = _QUOTED_BEFORE_DASH_RE.search(span) or _QUOTED_RE.search(span)
            if q:
                quotes.append(q.group(1).strip())

    for line in answer.splitlines():
        m = _BLOCKQUOTE_LINE_RE.match(line)
        content = m.group(1).strip() if m else ""
        if content:
            buffer.append(content)
        else:
            flush()
    flush()
    return quotes


def normalize(text: str) -> str:
    return _STRIP_RE.sub("", unicodedata.normalize("NFKC", text)).casefold()


def verify_citations(answer: str, docs: list) -> CitationStats:
    # La normalización elimina "|", por lo que el separador no puede aparecer
    # dentro de un chunk normalizado: une chunks sin riesgo de falsos positivos
    # en una cita que en realidad abarque dos fragmentos distintos.
    corpus = "|".join(normalize(d.page_content) for d in docs)
    quotes = extract_quotes(answer)
    unverified: list[str] = []
    for quote in quotes:
        segments = [normalize(s) for s in _ELLIPSIS_RE.split(quote)]
        segments = [s for s in segments if len(s) >= MIN_SEGMENT_CHARS]
        if not segments or not all(s in corpus for s in segments):
            unverified.append(quote[:MAX_REPORTED_CHARS])
    return CitationStats(
        total=len(quotes),
        verificadas=len(quotes) - len(unverified),
        no_verificadas=unverified,
    )
