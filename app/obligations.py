"""Extracción y tipificación de las obligaciones de un informe (esqueleto; sin uso en producción).

Requisitos: RF-26 (tipificación previa al mapeo) y RF-27 (contenido de la evidencia); caso de
uso CU-08 (flujos 3a y 3b). Algoritmo: 23-detalle.tex, lst:det-alg-tipificacion.

La clave de una obligación no puede ser su redacción, que el LLM cambia entre ejecuciones
(22-arquitectura, «Tipificación de las obligaciones y mapeo a controles»). El tipo es el par
(normativa, artículo) del fragmento que contiene la cita verificada: la raíz de
``metadata["source"]`` («RGPD», el identificador canónico de 23-detalle, «Herramientas,
identificadores y resultado») y el número del artículo como cadena («13»). El índice guarda en
``metadata["article"]`` el encabezado («Artículo 13», «Considerando 4»); el número lo saca
``parse_article_number`` con el mismo analizador que da ``FragmentoRef.articulo``
(``app.fragments.localizador``). Una obligación cuya cita no se verifica, cuya cita se reparte
entre varios fragmentos o cuyo fragmento no tiene artículo (también los considerandos) queda
«sin tipificar» y no recibe controles.

Hallazgo medido (índice de 9f173ce): solo 1 422 de 13 756 fragmentos llevan
``metadata["article"]`` (10,3 %). En el RGPD es el 0 % (0 de 962), igual que en otras ocho
normas de EUR-Lex (la ePrivacy consolidada llega al 40,5 %), porque pypdf extrae
«Ar tículo» con un espacio y ``app/legal_splitter.py`` no lo reconoce. Con el índice actual
ninguna obligación del RGPD podría tipificarse; ver la prueba xfail de
``tests/test_legal_splitter.py``. Es la parte incompleta de RF-18 (20-requisitos: «RF-18 está
implementado en parte») y la corrige el paquete PT10 (segmentador v3), del que depende PT3;
PT10 incluye también la localización de cada cita en su fragmento (``locate_citations``).

Segundo hallazgo (copia del índice, 13/11/2026): en las guías de la AEPD el encabezado es casi
siempre una mención a otra norma con la que empieza el fragmento. «ARTÍCULO 5» en la guía de
privacidad desde el diseño es el art. 5 del RGPD copiado, y los 90 «Considerando N» del índice
son menciones a considerandos del RGPD en cuatro guías: 45 en la de análisis de riesgos, 42 en
la de adecuación de la IA, 2 en el índice de contenidos de la de privacidad desde el diseño y 1
en la de IA agéntica. En 37 de ellos el número lleva pegada una llamada de nota y el
localizador da nulos; los otros 53 dan ``considerando``. El par (guía, «5») no es un artículo
de la guía, así que ``tipificar`` no puede fiarse solo de que haya número: las guías tienen
que seguir «sin tipificar» mientras no se decida su clave (TODO de ``ObligacionTipificada``).
Las cifras las comprueba ``tests/test_fragments.py`` contra el índice.

Reparto entre módulos: la memoria (fig:det-mcp-clases) pone el analizador de bloques y la
tipificación en ``controls.py`` y ``locate_citations`` en ``citations.py``. Aquí se separan
en este módulo para que ``controls.py`` sea una consulta pura de la tabla y
``citations.py`` (producción) no cambie hasta PT10. Módulo puro: no importa FastAPI, la
biblioteca MCP ni LangChain (``app.fragments`` tampoco).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.fragments import localizador


class Obligacion(BaseModel):
    """Un bloque de obligación del informe (``analizar_bloques`` en 23-detalle).

    Cita con su atribución, interpretación y acciones de implementación, hasta la siguiente
    cita o encabezado. La atribución que escribe el modelo no se usa como clave.
    """

    texto: str  # interpretación redactada por el modelo
    cita: str  # cita literal del blockquote
    atribucion: str  # «LSSI-1, Artículo 22, p. 17» tal como la escribe el informe
    # Viñetas de «Implementación» (acción_técnica en fig:ana-dominio-extension).
    acciones: list[str] = []


class CitaLocalizada(BaseModel):
    """Resultado de localizar una cita en los fragmentos del contexto (``locate_citations``)."""

    cita: str
    verificada: bool
    # Posición del fragmento de respaldo en el contexto: el primero que contiene todos los
    # segmentos de la cita. None si no se verifica o si la cita se reparte entre fragmentos.
    chunk_index: int | None = None
    # Metadatos de ese fragmento, tal como los guarda el índice.
    source: str | None = None
    # Encabezado tal como lo guarda el segmentador, p. ej. "Artículo 13" o "Considerando 4"
    # («(cont.)» va en el texto de los sub-fragmentos, no en el metadato).
    article: str | None = None
    page: int | None = None  # metadata["page"], base 0 como lo guarda pypdf


class ObligacionTipificada(BaseModel):
    """Obligación con tipo (normativa, artículo) lista para el mapeo (RF-26)."""

    obligacion: Obligacion
    cita: CitaLocalizada
    normativa: str  # identificador canónico: raíz del nombre de fichero, p. ej. "RGPD"
    # Número de artículo como cadena («13»); un considerando no es un artículo.
    # TODO(PT3/RF-26): clave de las guías de la AEPD, que no se articulan. La memoria
    # (21-analisis, sec:ana-dominio-ext) propone la sección o un vocabulario controlado; el
    # andamiaje anterior proponía las páginas, que solo valen para una corpus_version. Mientras
    # no se decida, sus obligaciones quedan «sin tipificar» con «fragmento sin artículo».
    articulo: str
    pagina: int  # base 1, como en el prompt y en el informe (metadata["page"] + 1)
    fragmento: str  # identificador del fragmento (app.service.fragment_id)


# Motivos de lst:det-alg-tipificacion (23-detalle), en el orden en que se comprueban.
MotivoSinTipificar = Literal[
    "cita no verificada",
    "cita repartida en varios fragmentos",
    "fragmento sin artículo",
]


class ObligacionSinTipificar(BaseModel):
    """CU-08, flujo 3a: se lista aparte en la evidencia, sin controles."""

    obligacion: Obligacion
    motivo: MotivoSinTipificar


def extract_obligations(answer: str) -> list[Obligacion]:
    """Divide el informe en bloques de obligación (``analizar_bloques`` en 23-detalle).

    Sigue el formato fijado por ``SYSTEM_PROMPT`` e ignora el sumario y las dos secciones que
    añade el código (cobertura y verificación de citas).
    """
    # TODO(PT3/RF-26): implementar reutilizando citations.extract_quotes para la cita.
    raise NotImplementedError


def locate_citations(citas: list[str], docs: list) -> list[CitaLocalizada]:
    """Como ``citations.verify_citations``, pero dice qué fragmento respalda cada cita.

    Criterio de 23-detalle («Tipificación de las obligaciones»): una cita está verificada si
    cada segmento aparece en algún fragmento (el mismo criterio de ``verify_citations``), y su
    fragmento de respaldo es el primero, en el orden del contexto, que contiene todos sus
    segmentos. Si ninguno los contiene todos, queda verificada pero sin fragmento
    (``chunk_index`` None) y la tipificación la deja «sin tipificar». No sustituye a
    ``verify_citations``, que sigue siendo la que usa producción.
    """
    # TODO(PT10/RF-18): implementar (en app/citations.py, como prevé fig:det-mcp-clases)
    # aplicando citations.normalize y citations._segment_found fragmento a fragmento, y
    # comprobar con una prueba que da el mismo número de verificadas que verify_citations para
    # las mismas entradas (misma normalización y misma tolerancia en los extremos).
    raise NotImplementedError


def parse_article_number(heading: str | None) -> str | None:
    """``"Artículo 13"`` -> ``"13"``; ``"Artículo 35 (cont.)"`` -> ``"35"``; sin número -> ``None``.

    Los considerandos no son artículos (devuelven ``None``), ni los números de más de tres
    cifras, que en el índice son llamadas de nota pegadas al número (``app.fragments``)."""
    return localizador(heading)[0]


def tipificar(
    obligaciones: list[Obligacion], citas: list[CitaLocalizada], docs: list
) -> tuple[list[ObligacionTipificada], list[ObligacionSinTipificar]]:
    """Asigna a cada obligación el tipo del fragmento de su cita (CU-08, paso 3 y flujo 3a).

    Es la primera mitad de lst:det-alg-tipificacion; la búsqueda en la tabla (flujo 3b, «sin
    mapeo») la hace ``controls.resolve_controls``.
    """
    # TODO(PT3/CU-08): implementar; depende de PT10 (el segmentador v3 reconoce «Ar tículo»).
    raise NotImplementedError
