"""Capa de servicio común a la API REST y al servidor MCP (RF-22; CU-01 y CU-07).

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

import asyncio
import json
import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

from app import cache as _cache
from app import metrics as _metrics
from app import rag as _rag
from app import store
from app.config import settings
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
from app.middleware import request_id_var
from app.models import PipelineResult, QuestionnaireInput

logger = logging.getLogger(__name__)

# consultar_obligaciones: candidatos que se piden a Chroma y fragmentos que se devuelven.
CONSULTA_FETCH_K = 30
CONSULTA_TOP_K = 6


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
    tipo: str  # metadato doc_type del índice; «desconocido» si falta
    paginas: int  # máximo de metadata["page"] + 1 entre sus fragmentos; 0 si falta


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

    Lee los metadatos de los fragmentos (``doc_type`` y el máximo de ``page`` por ``source``)
    sin importar ``app.ingest``. A diferencia de ``GET /normativas``, un fallo del índice se
    propaga en lugar de ocultarse como lista vacía.
    """
    por_fuente: dict[str, dict] = {}
    for meta in store.list_metadatas(state.vectorstore):
        source = meta.get("source")
        if not source:
            continue
        info = por_fuente.setdefault(Path(source).stem, {"tipo": None, "max_page": -1})
        if info["tipo"] is None and meta.get("doc_type"):
            info["tipo"] = str(meta["doc_type"])
        page = meta.get("page")
        if isinstance(page, int) and page > info["max_page"]:
            info["max_page"] = page
    return ListadoNormativas(
        normativas=[
            NormativaInfo(
                identificador=stem,
                tipo=info["tipo"] or "desconocido",
                paginas=info["max_page"] + 1,
            )
            for stem, info in sorted(por_fuente.items())
        ],
        corpus_version=state.corpus_version,
    )


async def consultar_obligaciones(
    normativa: str, contexto: str, state, *, via: Via
) -> ConsultaNormativa:
    """RF-25: fragmentos más pertinentes de una normativa para un contexto breve.

    Determinista y sin LLM: ``rag.retrieve_for_source`` (misma búsqueda y mismo reordenador
    que el análisis, filtrando por documento) y los fragmentos con su localización y su
    texto, en el orden del reordenador. No consume cuota del modelo ni envía el ``contexto``
    a Groq; aun así, el ``contexto`` es texto libre y no se registra (RNF-04; PP-08).

    El identificador se compara tal cual (sensible a mayúsculas, sin «.pdf»): uno que no está
    en el índice lanza ``UnknownNormativaError`` con los disponibles, para que el asistente
    corrija la llamada.
    """
    if normativa not in state.indexed_normativas:
        raise UnknownNormativaError(normativa, sorted(state.indexed_normativas))
    try:
        docs = await asyncio.wait_for(
            asyncio.to_thread(
                _rag.retrieve_for_source,
                contexto,
                state.vectorstore,
                normativa,
                fetch_k=CONSULTA_FETCH_K,
                top_k=CONSULTA_TOP_K,
            ),
            timeout=settings.retrieval_timeout,
        )
    except TimeoutError:
        logger.error(
            json.dumps(
                {
                    "event": "retrieval_timeout",
                    "request_id": request_id_var.get(),
                    "via": via.value,
                    "timeout_s": settings.retrieval_timeout,
                }
            )
        )
        raise RetrievalTimeoutError("Retrieval timed out. Please try again.") from None
    logger.info(
        json.dumps(
            {
                "event": "consulta_normativa",
                "request_id": request_id_var.get(),
                "via": via.value,
                "normativa": normativa,
                "contexto_length": len(contexto),
                "fragmentos": len(docs),
            }
        )
    )
    return ConsultaNormativa(
        normativa=normativa,
        fragmentos=[FragmentoRef.from_doc(doc, con_texto=True) for doc in docs],
    )


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
