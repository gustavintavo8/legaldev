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

_BLOCKQUOTE_RE = re.compile(r"^\s*>\s*(.+)$", re.MULTILINE)
# Primera comilla de apertura … última comilla de cierre seguida de guion (— – -).
_QUOTED_BEFORE_DASH_RE = re.compile(r"[\"“«](.*)[\"”»]\s*[—–-]")
_QUOTED_RE = re.compile(r"[\"“«](.+)[\"”»]")
_ELLIPSIS_RE = re.compile(r"\[\s*(?:\.\.\.|…)\s*\]|\.\.\.|…")
_STRIP_RE = re.compile(r"[\s\"“”«»'‘’\-–—­]+")


def extract_quotes(answer: str) -> list[str]:
    quotes: list[str] = []
    for m in _BLOCKQUOTE_RE.finditer(answer):
        line = m.group(1)
        q = _QUOTED_BEFORE_DASH_RE.search(line) or _QUOTED_RE.search(line)
        if q:
            quotes.append(q.group(1).strip())
    return quotes


def normalize(text: str) -> str:
    return _STRIP_RE.sub("", unicodedata.normalize("NFKC", text)).casefold()


def verify_citations(answer: str, docs: list) -> CitationStats:
    # "|" no sobrevive a la normalización de ningún texto, así que separa chunks sin falsos positivos.
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
