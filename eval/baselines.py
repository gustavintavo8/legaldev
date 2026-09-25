"""Configuraciones comparadas en la evaluación extendida (24-pruebas, «Sistemas comparados»).

Las cuatro se ejecutan con el mismo cuestionario, el mismo prompt, el mismo índice y el mismo
modelo de lenguaje a temperatura 0, y registran tokens de entrada y salida y latencia:

* **B1, modelo sin recuperación** (PI1): el modelo recibe el cuestionario y debe identificar
  la normativa y redactar las obligaciones con su conocimiento paramétrico.
* **B2, RAG sin reglas** (PI2): búsqueda vectorial, recorte y reordenador, sin búsquedas
  auxiliares, exclusiones ni inyecciones.
* **B3, solo reglas** (PI2): el contexto son solo los fragmentos de las normativas que activan
  las inyecciones, sin búsqueda semántica principal.
* **S, sistema híbrido**: producción, por la API REST y por ``analizar_proyecto`` (PI6).
"""

from __future__ import annotations

from enum import StrEnum

from app.models import QuestionnaireInput
from app.service import RetrievalConfig


class Configuracion(StrEnum):
    B1 = "B1"
    B2 = "B2"
    B3 = "B3"
    S = "S"


# B1 no tiene configuración de recuperación: no recupera.
RETRIEVAL_CONFIGS: dict[Configuracion, RetrievalConfig | None] = {
    Configuracion.B1: None,
    Configuracion.B2: RetrievalConfig(
        use_exclusions=False, use_aux=False, use_injections=False
    ),
    Configuracion.B3: RetrievalConfig(use_main_search=False, use_aux=False),
    Configuracion.S: RetrievalConfig(),
}


def build_b1_messages(inp: QuestionnaireInput) -> list:
    """Mensajes de B1: el mismo SYSTEM_PROMPT sin la sección de fragmentos recuperados.

    El prompt de producción exige citar solo lo recuperado; B1 necesita una variante que le
    permita citar de memoria, y esa variante debe documentarse en la memoria.
    """
    # TODO(PT5/PI1): implementar; fijar y versionar el prompt de B1 (hash, como el de S).
    raise NotImplementedError


def retrieve(inp: QuestionnaireInput, vs, config: RetrievalConfig, threshold: float):
    """Recuperación de B2, B3 o S con el mismo código que producción (``rag._retrieve``)."""
    # TODO(PT5/PI2): implementar cuando rag._retrieve acepte RetrievalConfig; B3 conserva las
    # exclusiones (use_exclusions=True): confirmar que la memoria lo entiende igual.
    raise NotImplementedError
