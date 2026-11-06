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

``POST /v1/analyze`` y la herramienta MCP ``analizar_proyecto`` pasan los dos por
``analyze``; las excepciones viven en ``app/errors.py`` y los identificadores de fragmento en
``app/fragments.py``, y este módulo los reexporta.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel

from app import cache as _cache
from app import metrics as _metrics
from app import rag as _rag
from app.errors import (  # noqa: F401  (reexportados: parte del contrato de la capa)
    HTTP_STATUS,
    InvalidMappingError,
    LegalDevError,
    LLMUnavailableError,
    NoCoverageError,
    RetrievalTimeoutError,
    UnknownNormativaError,
)
from app.fragments import FragmentoRef, fragment_id  # noqa: F401
from app.models import PipelineResult, QuestionnaireInput


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
# Modelos compartidos (23-detalle, «Herramientas, identificadores y resultado»)
# --------------------------------------------------------------------------------------


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


class ConsultaNormativa(BaseModel):
    """Resultado de ``consultar_obligaciones`` (RF-25; tab:det-mcp-herramientas)."""

    normativa: str
    fragmentos: list[FragmentoRef]  # en el orden del reordenador


# --------------------------------------------------------------------------------------
# Casos de uso
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Analysis:
    """Resultado de ``analyze``: el análisis (respuesta y fragmentos) y si vino de la caché."""

    result: PipelineResult
    cache_hit: bool


async def analyze(inp: QuestionnaireInput, state, *, via: Via) -> Analysis:
    """Caso de uso CU-01 común a ``POST /v1/analyze`` y a ``analizar_proyecto`` (RF-22, RF-23).

    * Una sola entrada de caché por cuestionario para todas las vías: la clave es
      ``cache.make_key(inp.model_dump_json())`` y el valor el ``PipelineResult`` completo,
      porque ``analizar_proyecto`` necesita los fragmentos además de la respuesta.
    * El motor lanza los errores de dominio de ``app.errors``; REST los traduce con
      ``HTTP_STATUS`` y MCP con resultados de herramienta.
    * ``via`` etiqueta la métrica ``legaldev_analyze_requests_total`` y el registro del
      pipeline (CU-07, postcondiciones).
    """
    _metrics.analyze_requests_total.labels(via=via.value).inc()
    key = _cache.make_key(inp.model_dump_json())
    cached = _cache.get(key)
    if cached is not None:
        return Analysis(result=cached, cache_hit=True)
    result = await _rag.run_pipeline_detailed(inp, state, via=via.value)
    _cache.set(key, result)
    return Analysis(result=result, cache_hit=False)


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
