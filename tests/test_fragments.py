"""Localización de un fragmento: ``articulo`` y ``considerando`` de ``FragmentoRef``.

El índice guarda en ``metadata["article"]`` el encabezado con que empieza el fragmento
(``app/legal_splitter.py``), no el número. Los casos son las formas que tiene el índice real
(consulta de solo lectura a una copia de ``chroma_db``, 13/11/2026: 1.422 fragmentos con
``article``):

- «Artículo N»: 1.308; «ARTÍCULO N»: 23 (la guía de privacidad desde el diseño copia los
  artículos del RGPD en mayúsculas); «Artículo \\nN»: 1 (el salto de línea de pypdf entre la
  palabra y el número);
- «Considerando N»: 90, menciones a considerandos del RGPD en cuatro guías de la AEPD (45 en
  la de análisis de riesgos, 42 en la de adecuación de la IA, 2 en la de privacidad desde el
  diseño y 1 en la de IA agéntica);
- siete encabezados con el número pegado a una llamada de nota de la guía (44 fragmentos, 28
  de la guía de análisis de riesgos y 16 de la de adecuación de la IA; 7 «Artículo» y 37
  «Considerando»): «Artículo 2918» es el «Artículo 29» de la nota 18, «Considerando 49127» es
  el 49 de la nota 127. Ninguna norma del corpus pasa de 999 artículos ni considerandos (el
  máximo real del índice es 203 y 149), así que un número de cuatro o más cifras no localiza
  nada.

El metadato nunca lleva «(cont.)»: ese prefijo va en el texto de los sub-fragmentos. Se acepta
igualmente, por si un índice futuro lo guardara así.

La última prueba comprueba estas cifras contra ``chroma_db`` en solo lectura. Sin Git LFS
(como en la CI) el fichero es un puntero y la prueba se omite.
"""

import sqlite3
from collections import Counter
from pathlib import Path

import pytest
from langchain_core.documents import Document

from app.fragments import FragmentoRef, fragment_id, localizador

# Las siete colisiones con llamadas de nota del índice real.
ENCABEZADOS_CON_NOTA = (
    "Artículo 2918",
    "Considerando 3965",
    "Considerando 7160",
    "Considerando 7522",
    "Considerando 7551",
    "Considerando 7882",
    "Considerando 49127",
)


@pytest.mark.parametrize(
    "encabezado,esperado",
    [
        ("Artículo 22", ("22", None)),
        ("Artículo 5", ("5", None)),
        ("Artículo 203", ("203", None)),  # el mayor número real de artículo del índice
        ("ARTÍCULO 5", ("5", None)),
        ("ARTÍCULO 83", ("83", None)),
        ("Art. 5", ("5", None)),  # forma que reconoce el segmentador
        ("Artículo \n35", ("35", None)),  # salto de línea de pypdf
        ("Artículo 13 (cont.)", ("13", None)),
        ("Considerando 32", (None, "32")),
        ("Considerando 149", (None, "149")),  # el mayor considerando real del índice
        ("Considerando 4 (cont.)", (None, "4")),
    ],
)
def test_localizador_separa_articulo_y_considerando(encabezado, esperado):
    assert localizador(encabezado) == esperado


@pytest.mark.parametrize("encabezado", ENCABEZADOS_CON_NOTA)
def test_localizador_descarta_los_numeros_pegados_a_una_nota(encabezado):
    """Un localizador falso es peor que ninguno: nulos, nunca «considerando 49127»."""
    assert localizador(encabezado) == (None, None)


@pytest.mark.parametrize(
    "encabezado",
    [
        None,
        "",
        "22",  # número suelto: no se sabe si es artículo o considerando
        "Capítulo 3",
        "Anexo III",
        "Disposición adicional primera",
        "Artículo",
        "Artículo 22 bis",  # el segmentador no lo produce; mejor nulo que «22»
        "Artículo 22. Derechos",
    ],
)
def test_localizador_sin_encabezado_reconocible_es_nulo(encabezado):
    assert localizador(encabezado) == (None, None)


def _doc(article=None, *, page=16, source="LSSI.pdf", texto="Texto del fragmento."):
    meta = {"source": source, "page": page}
    if article is not None:
        meta["article"] = article
    return Document(page_content=texto, metadata=meta)


@pytest.mark.parametrize(
    "article,articulo,considerando",
    [
        ("Artículo 22", "22", None),
        ("ARTÍCULO 32", "32", None),
        ("Artículo \n35", "35", None),
        ("Considerando 32", None, "32"),
        ("Considerando 49127", None, None),
        (None, None, None),
    ],
)
def test_from_doc_normaliza_el_encabezado_del_indice(article, articulo, considerando):
    ref = FragmentoRef.from_doc(_doc(article), con_texto=False)
    assert (ref.articulo, ref.considerando) == (articulo, considerando)
    assert ref.normativa == "LSSI"
    assert ref.pagina == 17
    assert ref.identificador == fragment_id("Texto del fragmento.")


@pytest.mark.parametrize(
    "article",
    ["Artículo 22", "Considerando 32", *ENCABEZADOS_CON_NOTA, "Art. 5", None],
)
def test_from_doc_nunca_rellena_los_dos_campos(article):
    ref = FragmentoRef.from_doc(_doc(article), con_texto=True)
    assert ref.articulo is None or ref.considerando is None
    assert ref.articulo is None or ref.articulo.isdigit()
    assert ref.considerando is None or ref.considerando.isdigit()


INDICE = Path(__file__).resolve().parents[1] / "chroma_db" / "chroma.sqlite3"
RIESGOS = "Guía de Análisis de Riesgos para tratamientos de datos personales - AEPD.pdf"
ADECUACION_IA = "Adecuación al RGPD de tratamientos que incorporan IA - AEPD.pdf"
PRIVACIDAD_DISENO = "Guía de Privacidad desde el Diseño - AEPD.pdf"
IA_AGENTICA = "IA Agentica desde la perspectiva de proteccion de datos - AEPD.pdf"


def _encabezados_del_indice() -> list[tuple[str, str]]:
    """(fuente, encabezado) de cada fragmento del índice que lleva ``article``.

    Se abre en solo lectura y como inmutable (``mode=ro&immutable=1``): SQLite no escribe nada,
    ni bloqueos ni ficheros ``-wal``/``-shm``. No pasa por ``settings`` para no leer ``.env``.
    """
    try:
        with INDICE.open("rb") as f:
            cabecera = f.read(16)
    except FileNotFoundError:
        pytest.skip("no hay chroma_db/chroma.sqlite3")
    if cabecera != b"SQLite format 3\x00":
        pytest.skip("chroma_db/chroma.sqlite3 es un puntero de Git LFS (sin LFS)")
    con = sqlite3.connect(INDICE.as_uri() + "?mode=ro&immutable=1", uri=True)
    try:
        return con.execute(
            "SELECT s.string_value, m.string_value FROM embedding_metadata m"
            " JOIN embedding_metadata s ON s.id = m.id AND s.key = 'source'"
            " WHERE m.key = 'article'"
        ).fetchall()
    finally:
        con.close()


def _forma(encabezado: str) -> str:
    if "\n" in encabezado:
        return "Artículo \\nN"
    if encabezado.startswith("ARTÍCULO "):
        return "ARTÍCULO N"
    if encabezado.startswith("Artículo "):
        return "Artículo N"
    if encabezado.startswith("Considerando "):
        return "Considerando N"
    return encabezado


def test_el_indice_tiene_las_formas_y_el_reparto_que_cita_la_documentacion():
    """Las cifras del índice que citan este módulo, app/obligations.py y docs/mcp/README.md.

    Si se reindexa (PT10, segmentador v3), esta prueba falla y hay que actualizar las tres
    cosas a la vez: las cifras de aquí, el docstring de ``app/obligations.py`` y «Diseño
    resumido» de ``docs/mcp/README.md``.
    """
    filas = _encabezados_del_indice()
    actualizar = (
        "reindexado: actualizar obligations.py, docs/mcp/README.md y esta prueba"
    )

    assert len(filas) == 1422, actualizar
    assert Counter(_forma(art) for _, art in filas) == {
        "Artículo N": 1308,
        "ARTÍCULO N": 23,
        "Artículo \\nN": 1,
        "Considerando N": 90,
    }, actualizar
    # Los «Considerando N» son menciones al RGPD en cuatro guías, no considerandos propios.
    assert Counter(f for f, art in filas if _forma(art) == "Considerando N") == {
        RIESGOS: 45,
        ADECUACION_IA: 42,
        PRIVACIDAD_DISENO: 2,
        IA_AGENTICA: 1,
    }, actualizar

    localizados = [(f, art, localizador(art)) for f, art in filas]
    assert all(a is None or c is None for _, _, (a, c) in localizados)
    articulos = [int(a) for _, _, (a, _) in localizados if a is not None]
    considerandos = [int(c) for _, _, (_, c) in localizados if c is not None]
    nulos = [(f, art) for f, art, (a, c) in localizados if a is None and c is None]
    recuento = (len(articulos), len(considerandos), len(nulos))
    assert recuento == (1325, 53, 44), actualizar
    assert (max(articulos), max(considerandos)) == (203, 149), actualizar

    # Los nulos son, todos, las colisiones con una llamada de nota, y solo de dos guías.
    assert {art for _, art in nulos} == set(ENCABEZADOS_CON_NOTA), actualizar
    assert Counter(f for f, _ in nulos) == {RIESGOS: 28, ADECUACION_IA: 16}, actualizar
    assert Counter(_forma(art) for _, art in nulos) == {
        "Artículo N": 7,
        "Considerando N": 37,
    }, actualizar
