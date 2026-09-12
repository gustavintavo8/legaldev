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
# Fracción de un segmento que puede sobrar o faltar en CADA extremo sin dejar de
# considerarlo literal. Medido en producción (2026-09-12): 4 de 12 citas reales
# fallaban por un punto final que añade el LLM ("…utilizarlos." frente a
# "…utilizarlos los espacios") o por una palabra cortada en el borde del chunk
# ("los organismos…" frente a un chunk que empieza en "organismos…"). El núcleo
# del segmento sigue teniendo que coincidir exactamente: una paráfrasis en medio
# o una cita ajena al contexto siguen sin verificarse.
BOUNDARY_TOLERANCE = 0.10

# Línea de blockquote individual — se recorre línea a línea (no re.MULTILINE
# sobre todo el texto) para poder agrupar líneas consecutivas en un párrafo.
_BLOCKQUOTE_LINE_RE = re.compile(r"^\s*>\s?(.*)$")
# Primera comilla de apertura … última comilla de cierre seguida de guion (— – -).
# (.+) exige contenido no vacío: una cita vacía > "" — X no debe contar como cita.
_QUOTED_BEFORE_DASH_RE = re.compile(r"[\"“«](.+)[\"”»]\s*[—–-]")
_QUOTED_RE = re.compile(r"[\"“«](.+)[\"”»]")
_OPENING_QUOTE_RE = re.compile(r"[\"“«]")
# Un "marcador de atribución": comilla de cierre + guion, con espacio opcional
# entre medias. Precalculado una sola vez por párrafo en _split_paragraph para
# no re-escanear un prefijo cada vez más grande por cada comilla suelta.
_ATTRIBUTION_RE = re.compile(r"[\"”»]\s*[—–-]")
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
    … comilla + guion) — si no, sigue acumulando, para no partir una cita que
    el ajuste de línea del LLM dejó a medias.

    Los marcadores de atribución (comilla de cierre + guion) se precalculan
    UNA VEZ para todo el párrafo y se recorren con un puntero que solo avanza
    (`mi`), en vez de repetir _QUOTED_BEFORE_DASH_RE.search sobre un prefijo
    `paragraph[start:pos]` cada vez más largo por cada comilla suelta que no
    llega a completar una cita — eso último es O(n²) o peor (una respuesta con
    miles de comillas sueltas sin guion podía tardar minutos). Con el puntero,
    el trabajo total es O(len(paragraph) + nº de comillas).
    """
    positions = [m.start() for m in _OPENING_QUOTE_RE.finditer(paragraph)]
    if not positions:
        return [paragraph]
    # (marker_start, marker_end) de cada "comilla de cierre + guion" del párrafo.
    markers = [(m.start(), m.end()) for m in _ATTRIBUTION_RE.finditer(paragraph)]
    spans: list[str] = []
    start = positions[0]
    mi = 0
    for pos in positions[1:]:
        # Un marcador solo completa una cita que ABRE en `start` si su propia
        # comilla de cierre (marker_start) deja hueco para el contenido no
        # vacío que exige _QUOTED_BEFORE_DASH_RE — es decir, marker_start >=
        # start + 2 (comilla de apertura + ≥1 carácter de contenido). Sin este
        # +2, una comilla recta que ABRE una cita nueva y que además viene
        # seguida de un guion (su propio contenido empieza por "—") se contaría
        # a la vez como apertura Y como el cierre de sí misma, cosa que
        # _QUOTED_BEFORE_DASH_RE nunca podría hacer en un único match.
        while mi < len(markers) and markers[mi][0] < start + 2:
            mi += 1
        if mi < len(markers) and markers[mi][1] <= pos:
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
            # _QUOTED_BEFORE_DASH_RE can only ever match a span that contains an
            # attribution marker (_ATTRIBUTION_RE) — checking that cheaply first
            # avoids the regex's own catastrophic backtracking on a large span
            # with many quote characters but no dash at all (the same adversarial
            # shape _split_paragraph's marker precomputation exists to handle):
            # without this guard, extract_quotes stayed well over 1s even after
            # _split_paragraph itself became linear, because a never-completing
            # paragraph is returned as ONE big unsplit span.
            q = None
            if _ATTRIBUTION_RE.search(span):
                q = _QUOTED_BEFORE_DASH_RE.search(span)
            q = q or _QUOTED_RE.search(span)
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


def _segment_found(segment: str, corpus: str) -> bool:
    """¿Aparece el segmento (normalizado) en el corpus, exacto o recortando los extremos?

    Primero containment exacto. Si falla, se prueba a recortar hasta
    BOUNDARY_TOLERANCE del segmento por cada extremo (a chars al inicio, b al
    final), sin que el núcleo baje de MIN_SEGMENT_CHARS. Coste: como mucho
    (tol+1)² búsquedas de subcadena en C sobre el corpus — milisegundos.
    """
    if segment in corpus:
        return True
    tol = int(len(segment) * BOUNDARY_TOLERANCE)
    for a in range(tol + 1):
        for b in range(tol + 1):
            if a == 0 and b == 0:
                continue
            core = segment[a : len(segment) - b]
            if len(core) < MIN_SEGMENT_CHARS:
                break
            if core in corpus:
                return True
    return False


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
        if not segments or not all(_segment_found(s, corpus) for s in segments):
            unverified.append(quote[:MAX_REPORTED_CHARS])
    return CitationStats(
        total=len(quotes),
        verificadas=len(quotes) - len(unverified),
        no_verificadas=unverified,
    )
