"""Capa de servicio común a la API REST y al servidor MCP (propuesta; no se usa en producción).

Hoy la lógica de los casos de uso vive repartida entre ``app/main.py`` (caché, claves de
API, límite) y ``app/rag.py`` (motor), y el motor señala sus fallos con
``fastapi.HTTPException`` (404 sin cobertura, 503 si caen el LLM o el retrieval). Eso sirve
a una sola vía de acceso, pero el servidor MCP necesita los mismos casos de uso con otra
traducción de errores: un «sin cobertura» no es un 404 sino un resultado de herramienta
(CU-07, flujo 4d), y un cuestionario inválido es un resultado con ``isError`` y no un error
del protocolo (RF-23, PP-04).

Este módulo fija el contrato de esa capa común:

* excepciones de dominio (``LegalDevError`` y derivadas) en lugar de ``HTTPException``; cada
  vía las traduce a su formato (``HTTP_STATUS`` para REST, resultado de error para MCP);
* una única entrada de caché por cuestionario, compartida por la web, la API y los
  asistentes (22-arquitectura, flujo de una invocación, paso 4);
* la etiqueta ``via`` que distingue la vía de acceso en métricas y registros (CU-07,
  postcondiciones);
* las firmas nuevas de recuperación que necesitan RF-25 (filtro por documento) y las líneas
  base B2/B3 de la evaluación (``RetrievalConfig``).

Nada de lo que hay aquí está conectado a ``app/main.py``: las funciones lanzan
``NotImplementedError`` y el comportamiento de producción no cambia.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel

from app.models import QuestionnaireInput, RAGResponse


class Via(StrEnum):
    """Vía de acceso de una petición; etiqueta de métricas y campo de los registros."""

    REST = "rest"
    MCP = "mcp"


# --------------------------------------------------------------------------------------
# Excepciones de dominio
# --------------------------------------------------------------------------------------


class LegalDevError(Exception):
    """Base de los errores de dominio. No depende de FastAPI ni de la biblioteca MCP."""


class NoCoverageError(LegalDevError):
    """Ningún fragmento supera el umbral: hoy es ``HTTPException(404)`` en ``run_pipeline``."""


class LLMUnavailableError(LegalDevError):
    """Fallan el modelo principal y el de respaldo: hoy es ``HTTPException(503)`` en ``_invoke_llm``."""


class RetrievalTimeoutError(LegalDevError):
    """El retrieval supera ``settings.retrieval_timeout``: hoy es ``HTTPException(503)``."""


class UnknownNormativaError(LegalDevError):
    """``consultar_obligaciones`` recibe una normativa que no está en el índice (RF-25, PP-06)."""

    def __init__(self, normativa: str, disponibles: list[str]) -> None:
        super().__init__(f"Normativa desconocida: {normativa!r}")
        self.normativa = normativa
        self.disponibles = disponibles


# Traducción a la API REST. Los tres primeros reproducen los códigos que devuelve hoy
# run_pipeline; UnknownNormativaError solo se produce por MCP mientras no exista un
# endpoint REST equivalente a consultar_obligaciones.
HTTP_STATUS: dict[type[LegalDevError], int] = {
    NoCoverageError: 404,
    LLMUnavailableError: 503,
    RetrievalTimeoutError: 503,
    UnknownNormativaError: 404,
}


# --------------------------------------------------------------------------------------
# Modelos compartidos
# --------------------------------------------------------------------------------------


class NormativaInfo(BaseModel):
    """Un documento indexado tal como lo devuelve ``listar_normativas`` (RF-24)."""

    nombre: str  # nombre de fichero del corpus, p. ej. "RGPD.pdf" (clave de consultar_obligaciones)
    tipo: str  # normativa_europea | normativa_española | guia_aepd | deontologia | otro
    nivel: int  # tier 1-4 del SYSTEM_PROMPT
    # TODO(PT2/RF-24): el tipo sale hoy de app.ingest.get_doc_type (importar ingest arrastra
    # load_dotenv y logging.basicConfig) o del metadato doc_type de cada fragmento; el nivel
    # solo existe como texto dentro de SYSTEM_PROMPT. Extraer ambos a datos en app/corpus.py
    # sin tocar el prompt (su hash está fijado por test_system_prompt_snapshot).


class ListadoNormativas(BaseModel):
    normativas: list[NormativaInfo]
    total: int
    corpus_version: str


# --------------------------------------------------------------------------------------
# Casos de uso
# --------------------------------------------------------------------------------------


async def analyze(inp: QuestionnaireInput, state, *, via: Via) -> RAGResponse:
    """Caso de uso CU-01 común a ``POST /v1/analyze`` y a ``analizar_proyecto`` (RF-23).

    Contrato previsto:
    * clave de caché ``app.cache.make_key(inp.model_dump_json())``, la misma que calcula hoy
      ``analyze_v1``, para que una petición idéntica por cualquier vía comparta entrada;
    * ``run_pipeline`` intacto; sus ``HTTPException`` se sustituyen por las excepciones de
      dominio de este módulo y ``main.py`` las traduce con ``HTTP_STATUS``;
    * ``via`` se propaga a métricas y a los registros estructurados.
    """
    # TODO(PT2/RF-22): implementar. Opción recomendada: que rag.run_pipeline lance las
    # excepciones de dominio y main.py las traduzca (cambio de producción protegido por
    # tests/test_api.py y por la prueba de equivalencia PP-05), en vez de capturar aquí
    # HTTPException y reinterpretarla.
    raise NotImplementedError


def list_normativas(state) -> ListadoNormativas:
    """RF-24: lista de documentos indexados con tipo, nivel y versión del corpus.

    Reutiliza ``store.list_sources`` como ``GET /normativas``; a diferencia de ese endpoint,
    un fallo del índice no debe ocultarse como lista vacía.
    """
    # TODO(PT2/RF-24): implementar sobre app.store y los datos de tipo/nivel de app/corpus.py.
    raise NotImplementedError


async def consultar_obligaciones(
    normativa: str, contexto: str, state, *, via: Via
) -> RAGResponse:
    """RF-25: obligaciones de una única normativa para un contexto breve (máx. 500 caracteres).

    Recupera con ``_retrieve_for_source`` (misma búsqueda y mismo reordenador que el
    análisis, filtrando por documento) y redacta con el prompt del sistema restringido a esa
    normativa. Una normativa desconocida lanza ``UnknownNormativaError`` con las disponibles.
    """
    # TODO(PT2/RF-25): implementar; decidir si el contexto libre pasa por _detect_injection y
    # por la misma política de registros sin PII que descripcion_breve (RNF-04, RNF-15).
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
    ``filter={"source": source}`` (no ``where=``), como las inyecciones de ``rag._retrieve``.
    """
    # TODO(PT2/RF-25): implementar junto a rag._retrieve (moverla a app/rag.py) reutilizando
    # el mismo reordenador; tests/test_rag.py y tests/test_retrieval_selection.py deben seguir
    # pasando sin cambios.
    raise NotImplementedError
