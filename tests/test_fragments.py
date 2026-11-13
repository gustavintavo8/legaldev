"""Localización de un fragmento: ``articulo`` y ``considerando`` de ``FragmentoRef``.

El índice guarda en ``metadata["article"]`` el encabezado con que empieza el fragmento
(``app/legal_splitter.py``), no el número. Los casos son las formas que tiene el índice real
(consulta de solo lectura a una copia de ``chroma_db``, 13/11/2026: 1.422 fragmentos con
``article``):

- «Artículo N»: 1.308; «ARTÍCULO N»: 23 (la guía de privacidad desde el diseño copia los
  artículos del RGPD en mayúsculas); «Artículo \\nN»: 1 (el salto de línea de pypdf entre la
  palabra y el número);
- «Considerando N»: 90, todos de guías de la AEPD que citan considerandos del RGPD;
- siete encabezados con el número pegado a una llamada de nota de la guía (44 fragmentos):
  «Artículo 2918» es el «Artículo 29» de la nota 18, «Considerando 49127» es el 49 de la
  nota 127. Ninguna norma del corpus pasa de 999 artículos ni considerandos (el máximo real
  del índice es 203 y 149), así que un número de cuatro o más cifras no localiza nada.

El metadato nunca lleva «(cont.)»: ese prefijo va en el texto de los sub-fragmentos. Se acepta
igualmente, por si un índice futuro lo guardara así.
"""

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
