"""Extracción y tipificación de las obligaciones de un informe (esqueleto; sin uso en producción).

Requisitos: RF-26 (tipificación previa al mapeo) y RF-27 (contenido de la evidencia); caso de
uso CU-08 (flujos 3a y 3b).

La clave de una obligación no puede ser su redacción, que el LLM cambia entre ejecuciones
(22-arquitectura, «Tipificación de las obligaciones»). El tipo es el par (documento,
artículo) del fragmento que contiene la cita verificada: ``metadata["source"]`` y
``metadata["article"]`` del índice (la memoria los llama ``doc`` y ``article``; en el índice
el primero es ``source``). Una obligación cuya cita no se verifica, o cuyo fragmento no tiene
artículo, queda «sin tipificar» y no recibe controles.

Hallazgo medido (índice de 9f173ce): solo 1 422 de 13 756 fragmentos llevan
``metadata["article"]`` (10,3 %). En el RGPD es el 0 % (0 de 962), igual que en otras ocho
normas de EUR-Lex (la ePrivacy consolidada llega al 40,5 %), porque pypdf extrae
«Ar tículo» con un espacio y ``app/legal_splitter.py`` no lo reconoce. Con el índice actual
ninguna obligación del RGPD podría tiparse; ver la prueba xfail de
``tests/test_legal_splitter.py``.

La memoria (tab:det-mcp-modulos) asigna la tipificación a ``controls.py``; aquí se separa para
que ``controls.py`` sea una consulta pura de la tabla. Módulo puro: no importa FastAPI, la
biblioteca MCP ni LangChain.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Obligacion(BaseModel):
    """Una obligación tal como aparece en el informe (bloque cita + interpretación + implementación)."""

    texto: str  # interpretación redactada por el modelo
    cita: str  # cita literal del blockquote
    normativa_citada: str  # atribución «— {Nombre normativa}, p. {página}»
    pagina_citada: int | None = None  # tal como la escribe el informe (base 1)
    accion_tecnica: list[str] = []  # bullets de «Implementación»


class CitaLocalizada(BaseModel):
    """Resultado de localizar una cita en los fragmentos recuperados."""

    cita: str
    verificada: bool
    # Metadatos del fragmento que la contiene; None si no se verifica.
    source: str | None = None
    article: str | None = None  # encabezado tal como lo guarda el segmentador
    page: int | None = None  # metadata["page"] (base 0, como lo guarda pypdf)
    chunk_index: int | None = None  # posición en la lista de docs recuperados


class ObligacionTipificada(BaseModel):
    """Obligación con tipo (documento, artículo o páginas) lista para el mapeo (RF-26)."""

    obligacion: Obligacion
    cita: CitaLocalizada
    normativa: str  # nombre de fichero del corpus, p. ej. "RGPD.pdf"
    articulo: int | None = None
    # Guías sin articulado (p. ej. la guía de cookies de la AEPD): se tipifican por página.
    pagina: int | None = None


MotivoSinTipificar = Literal["cita no verificada", "artículo desconocido"]


class ObligacionSinTipificar(BaseModel):
    """CU-08, flujo 3a: se lista aparte en la evidencia, sin controles."""

    obligacion: Obligacion
    motivo: MotivoSinTipificar


def extract_obligations(answer: str) -> list[Obligacion]:
    """Divide el informe en obligaciones siguiendo el formato fijado por ``SYSTEM_PROMPT``."""
    # TODO(PT3/RF-26): implementar reutilizando citations.extract_quotes para la cita.
    raise NotImplementedError


def locate_citations(answer: str, docs: list) -> list[CitaLocalizada]:
    """Como ``citations.verify_citations``, pero dice en qué fragmento está cada cita.

    Reutilizará ``citations.normalize`` y ``citations._segment_found`` fragmento a fragmento
    (hoy la verificación trabaja sobre el corpus concatenado y no sabe qué fragmento casa).
    Para una cita que abarque dos fragmentos, se toma el primero y se registra. No sustituye a
    ``verify_citations``, que sigue siendo la que usa producción.
    """
    # TODO(PT3/RF-26): implementar; comprobar que verificada coincide con verify_citations
    # para las mismas entradas (misma normalización y misma tolerancia en los extremos).
    raise NotImplementedError


def parse_article_number(heading: str | None) -> int | None:
    """``"Artículo 13"`` -> 13; ``"Artículo 35 (cont.)"`` -> 35; ``None`` o sin número -> ``None``."""
    # TODO(PT3/RF-26): implementar; los considerandos no son artículos (devuelven None).
    raise NotImplementedError


def tipificar(
    obligaciones: list[Obligacion], citas: list[CitaLocalizada]
) -> tuple[list[ObligacionTipificada], list[ObligacionSinTipificar]]:
    """Asigna a cada obligación el tipo del fragmento de su cita (CU-08, paso 3 y flujo 3a)."""
    # TODO(PT3/CU-08): implementar; depende de que el segmentador reconozca «Ar tículo».
    raise NotImplementedError
