"""Capa de servicio común a la API REST y al servidor MCP (propuesta; no se usa en producción).

Hoy la lógica de los casos de uso vive repartida entre ``app/main.py`` (caché, claves de
API, límite) y ``app/rag.py`` (motor), y el motor señala sus fallos con
``fastapi.HTTPException`` (404 sin cobertura, 503 si caen el LLM o el retrieval). Eso sirve
a una sola vía de acceso, pero el servidor MCP necesita los mismos casos de uso con otra
traducción de errores: un «sin cobertura» no es un 404 sino un resultado de herramienta
(CU-07, flujo 5c), y un cuestionario inválido es un resultado con ``isError`` y no un error
del protocolo (RF-23, PP-04).

Este módulo fija el contrato de esa capa común (22-arquitectura, «Capa de servicio común
REST/MCP»; 23-detalle, «Capa de servicio y traducción de errores»):

* excepciones de dominio (``LegalDevError`` y derivadas) en lugar de ``HTTPException``; cada
  vía las traduce a su formato (``HTTP_STATUS`` para REST, resultado de error para MCP;
  tab:det-mcp-errores);
* una única entrada de caché por cuestionario, compartida por la web, la API y los
  asistentes;
* la etiqueta ``via`` que distingue la vía de acceso en métricas y registros (CU-07,
  postcondiciones);
* los identificadores comunes a las herramientas, la API y la evidencia (``fragment_id``;
  normativa como raíz del nombre de fichero);
* las firmas nuevas de recuperación que necesitan RF-25 (filtro por documento) y las líneas
  base B2/B3 de la evaluación (``RetrievalConfig``).

Nada de lo que hay aquí está conectado a ``app/main.py``: salvo ``fragment_id``, las
funciones lanzan ``NotImplementedError`` y el comportamiento de producción no cambia.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel

from app.models import QuestionnaireInput, RAGResponse


class Via(StrEnum):
    """Vía de acceso de una petición; etiqueta de métricas y campo de los registros.

    Los tres valores de 23-detalle («Capa de servicio»): ``rest``, ``mcp`` o ``ci``.
    """

    REST = "rest"
    MCP = "mcp"
    # TODO(PT6/RF-28): la acción de CI llama a la API REST, así que para etiquetarla hace
    # falta una señal propia de la petición (p. ej. una cabecera o el User-Agent que envíe la
    # acción); ver mcp_guard.request_via. Solo se usa si PT6 se ejecuta.
    CI = "ci"


# --------------------------------------------------------------------------------------
# Excepciones de dominio (ErrorDominio en fig:det-mcp-clases)
# --------------------------------------------------------------------------------------


class LegalDevError(Exception):
    """Base de los errores de dominio. No depende de FastAPI ni de la biblioteca MCP."""


class NoCoverageError(LegalDevError):
    """``SinCobertura``: ningún fragmento supera el umbral (hoy ``HTTPException(404)``).

    Por MCP no es un error: resultado con ``isError: false``, sin obligaciones y con las
    normativas indexadas no relevantes.
    """


class LLMUnavailableError(LegalDevError):
    """``ModeloNoDisponible``: fallan el principal y el de respaldo (hoy ``HTTPException(503)``)."""


class RetrievalTimeoutError(LegalDevError):
    """``TiempoAgotado``: el retrieval supera ``settings.retrieval_timeout`` (hoy 503)."""


class UnknownNormativaError(LegalDevError):
    """``NormativaDesconocida``: ``consultar_obligaciones`` recibe una normativa que no está
    en el índice (RF-25, PP-06). Solo existe por MCP."""

    def __init__(self, normativa: str, disponibles: list[str]) -> None:
        super().__init__(f"Normativa desconocida: {normativa!r}")
        self.normativa = normativa
        self.disponibles = disponibles


class InvalidMappingError(LegalDevError):
    """``TablaMapeoInvalida``: la tabla de mapeo o el catálogo no validan al arrancar.

    ``POST /v1/evidence`` responde 503; ``analizar_proyecto`` devuelve el resultado sin
    obligaciones tipificadas y ``/health/deep`` señala el fallo (tab:det-mcp-errores).
    """


# Traducción a la API REST (tab:det-mcp-errores). Los tres primeros reproducen los códigos que
# devuelve hoy run_pipeline. UnknownNormativaError no tiene equivalente REST.
HTTP_STATUS: dict[type[LegalDevError], int] = {
    NoCoverageError: 404,
    LLMUnavailableError: 503,
    RetrievalTimeoutError: 503,
    InvalidMappingError: 503,
}


# --------------------------------------------------------------------------------------
# Identificadores y modelos compartidos (23-detalle, «Herramientas, identificadores y
# resultado»)
# --------------------------------------------------------------------------------------


def fragment_id(texto: str) -> str:
    """Identificador de un fragmento: los 12 primeros hexadecimales del MD5 de su texto.

    Es el mismo resumen con el que ``rag._retrieve`` deduplica los candidatos
    (``rag._content_hash``), así que se conserva entre reconstrucciones del índice mientras el
    texto no cambie, a diferencia del UUID de ChromaDB. Es lo que compara PP-05 (CA-09).
    """
    return hashlib.md5(texto.encode()).hexdigest()[:12]


class NormativaInfo(BaseModel):
    """Un documento indexado tal como lo devuelve ``listar_normativas`` (RF-24)."""

    # Raíz del nombre de fichero («RGPD», «LSSI»): el identificador de las reglas, de
    # normativas_detectadas y del argumento de consultar_obligaciones. GET /normativas
    # devuelve hoy el nombre con «.pdf»; CA-09 compara los dos listados por la raíz.
    identificador: str
    tipo: str  # tipo de documento: metadato doc_type del índice
    paginas: int
    # TODO(PT2/RF-24): tipo y páginas salen de los metadatos de los fragmentos (doc_type y el
    # máximo de page + 1 por source), sin importar app.ingest (arrastra load_dotenv y
    # logging.basicConfig).


class ListadoNormativas(BaseModel):
    normativas: list[NormativaInfo]
    corpus_version: str


class FragmentoRef(BaseModel):
    """Fragmento tal como sale por las herramientas y la evidencia."""

    identificador: str  # fragment_id
    normativa: str  # raíz del nombre de fichero
    pagina: int  # base 1, como en el prompt y el informe (metadata["page"] + 1)
    articulo: str | None = None  # número como cadena; None si el fragmento no lo tiene
    texto: str | None = None  # solo en consultar_obligaciones


class ConsultaNormativa(BaseModel):
    """Resultado de ``consultar_obligaciones`` (RF-25; tab:det-mcp-herramientas)."""

    normativa: str
    fragmentos: list[FragmentoRef]  # en el orden del reordenador


# --------------------------------------------------------------------------------------
# Casos de uso
# --------------------------------------------------------------------------------------


async def analyze(inp: QuestionnaireInput, state, *, via: Via) -> RAGResponse:
    """Caso de uso CU-01 común a ``POST /v1/analyze`` y a ``analizar_proyecto`` (RF-23).

    Contrato previsto:
    * clave de caché ``app.cache.make_key(inp.model_dump_json())``, la misma que calcula hoy
      ``analyze_v1``, para que una petición idéntica por cualquier vía comparta entrada; la
      entrada guarda el análisis completo (respuesta y fragmentos del contexto), porque la
      tipificación y el resultado de ``analizar_proyecto`` necesitan los fragmentos;
    * ``run_pipeline`` lanza las excepciones de dominio de este módulo en sus cuatro puntos
      de error y ``main.py`` las traduce con ``HTTP_STATUS``, con los mismos códigos y
      mensajes que hoy;
    * ``via`` se propaga a métricas y a los registros estructurados.
    """
    # TODO(PT2/RF-22): implementar. El cambio de run_pipeline es de producción: lo protegen
    # tests/test_api.py y la prueba de equivalencia PP-05.
    raise NotImplementedError


def list_normativas(state) -> ListadoNormativas:
    """RF-24: documentos indexados con tipo, páginas y versión del corpus.

    Reutiliza ``store.list_sources`` como ``GET /normativas``; a diferencia de ese endpoint,
    un fallo del índice no debe ocultarse como lista vacía.
    """
    # TODO(PT2/RF-24): implementar sobre app.store.
    raise NotImplementedError


async def consultar_obligaciones(
    normativa: str, contexto: str, state, *, via: Via
) -> ConsultaNormativa:
    """RF-25: fragmentos más pertinentes de una normativa para un contexto breve.

    Determinista y sin LLM (20-requisitos, 22-arquitectura y tab:det-mcp-herramientas):
    recupera con ``_retrieve_for_source`` (misma búsqueda y mismo reordenador que el análisis,
    filtrando por documento) y devuelve los fragmentos con su localización, en el orden del
    reordenador. No consume cuota del modelo ni envía el ``contexto`` a Groq; aun así, el
    ``contexto`` es texto libre y los registros siguen la política de ``descripcion_breve``
    (RNF-04; PP-08). Una normativa desconocida lanza ``UnknownNormativaError`` con las
    disponibles.
    """
    # TODO(PT2/RF-25): implementar. Varios pasajes de la memoria describen aún la variante con
    # LLM («obligaciones ... con citas verificadas»): 31-manual-usuario (tabla de
    # herramientas), 21-analisis (objetivo y flujo 3a de CU-07: «obligaciones de una
    # normativa») y el orden de recorte de 05-metodologia («en una versión determinista sin
    # LLM»). Corregirlos.
    raise NotImplementedError


# --------------------------------------------------------------------------------------
# Recuperación parametrizada (firmas nuevas; no se llaman desde producción)
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RetrievalConfig:
    """Qué etapas de ``rag._retrieve`` se ejecutan. Los valores por defecto son el sistema S.

    Sirve a las líneas base de la evaluación extendida (24-pruebas, «Sistemas comparados»):
    * S: todo activado (producción);
    * B2, RAG sin reglas: ``use_aux=False, use_exclusions=False, use_injections=False``;
    * B3, solo reglas: ``use_main_search=False, use_aux=False`` y solo inyecciones;
    * B1 no recupera nada y no se expresa con esta clase (ver ``eval/baselines.py``).

    Las líneas base deben ejecutar el mismo código que S con etapas apagadas, no una copia:
    si no, la comparación mide diferencias de implementación y no de diseño.
    """

    # TODO(PT5/PI2): hacer que rag._retrieve acepte config: RetrievalConfig = RetrievalConfig()
    # y comprobar que el valor por defecto no altera ningún resultado de producción.
    use_main_search: bool = True
    use_exclusions: bool = True
    use_aux: bool = True
    use_reranker: bool = True
    # Tope por normativa de _select_diverse (settings.max_chunks_per_source).
    # TODO(PT5/PI2): decidir si el tope por fuente cuenta como «regla» (se apaga en B2) o como
    # parte del reordenado (se mantiene); la memoria no lo precisa.
    use_diversity_cap: bool = True
    use_injections: bool = True


def _retrieve_for_source(query: str, vs, source: str, *, k: int, threshold: float):
    """Recuperación filtrada por un documento para ``consultar_obligaciones`` (RF-25).

    Devolverá un ``app.rag.RetrievalResult``. El filtro usa la API de langchain_chroma
    ``filter={"source": source}`` (no ``where=``), como las inyecciones de ``rag._retrieve``;
    22-arquitectura («Qué cambia y qué se conserva») lo justifica: ``_retrieve`` exige un
    ``QuestionnaireInput`` completo y no admite filtro.
    """
    # TODO(PT2/RF-25): implementar junto a rag._retrieve (moverla a app/rag.py) reutilizando
    # el mismo reordenador; tests/test_rag.py y tests/test_retrieval_selection.py deben seguir
    # pasando sin cambios.
    raise NotImplementedError
