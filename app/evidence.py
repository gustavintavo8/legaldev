"""Evidencias de cumplimiento exportables en JSON y Markdown (esqueleto; sin uso en producción).

Requisitos: RF-27 (contenido de la evidencia; ``POST /v1/evidence`` y ``analizar_proyecto``)
y RNF-17 (versiones del corpus y del mapeo en cada evidencia). Prueba: PP-10. Caso de uso:
CU-08. Formato: 23-detalle.tex, lst:det-evidencia; esquema en ``data/evidence.schema.json``.

La evidencia identifica el proyecto por los campos cerrados del cuestionario y nunca incluye
``descripcion_breve`` (texto libre, posible PII). Por obligación tipificada guarda datos
deterministas (tipo, normativa, artículo, página, fragmento, cita y su verificación), los
controles, las acciones del informe y el estado; no guarda la interpretación redactada por el
modelo, que cambia entre ejecuciones. El servicio no la almacena (CU-08, postcondiciones).
Módulo puro: no importa FastAPI, la biblioteca MCP ni LangChain.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Final

from pydantic import BaseModel

from app.controls import DATA_DIR, TablaMapeo
from app.models import (
    ComunidadAutonoma,
    Monetizacion,
    QuestionnaireInput,
    RAGResponse,
    TipoDatoPersonal,
    TipoIA,
    TipoProyecto,
)
from app.obligations import MotivoSinTipificar

# Misma raíz que la tabla de mapeo: ver en app/controls.py el TODO de la imagen Docker.
SCHEMA_PATH: Final = DATA_DIR / "evidence.schema.json"

# Texto de lst:det-evidencia.
AVISO_EVIDENCIA: Final = (
    "Orientación; no constituye asesoramiento legal ni declaración de aplicabilidad."
)


class EstadoObligacion(StrEnum):
    """Campo que rellena el equipo (RF-27)."""

    NO_INICIADO = "no_iniciado"
    EN_CURSO = "en_curso"
    IMPLEMENTADO = "implementado"
    NO_APLICA = "no_aplica"


class Generador(BaseModel):
    servicio: str = "legaldev"
    version: str
    corpus_version: str
    mapeo_version: str
    llm_model: str


class ProyectoEvidencia(BaseModel):
    """Campos cerrados de ``QuestionnaireInput``: todos salvo ``descripcion_breve``.

    Se enumeran a mano (no se derivan del modelo) para que añadir un campo libre al
    cuestionario no lo filtre a la evidencia sin una decisión explícita; una prueba comprueba
    que los dos modelos siguen sincronizados.
    """

    tipo_proyecto: TipoProyecto
    tiene_usuarios_registrados: bool
    acceso_publico: bool
    tipos_datos_personales: list[TipoDatoPersonal]
    usuarios_menores: bool
    usuarios_ue: bool
    transferencia_datos_terceros: bool
    usa_ia: bool
    tipo_ia: TipoIA | None = None
    usa_cookies: bool
    monetizacion: Monetizacion | None = None
    contenido_digital: bool
    ccaa: ComunidadAutonoma
    es_empresa: bool
    colegiado: bool | None = None


class ControlesAsociados(BaseModel):
    iso27001: list[str] = []
    ens: list[str] = []


class ObligacionEvidencia(BaseModel):
    """Obligación tipificada y mapeada (lst:det-evidencia)."""

    id_tipo: str  # EntradaMapeo.id
    normativa: str  # identificador canónico, p. ej. "LSSI"
    articulo: str  # número como cadena, p. ej. "22"
    pagina: int  # base 1, como en el informe
    fragmento: str  # app.service.fragment_id del fragmento de respaldo
    cita: str  # literal, sin el prefijo sintético «(cont.)»
    cita_verificada: bool
    controles: ControlesAsociados
    acciones: list[str]  # viñetas de «Implementación», en su orden
    estado: EstadoObligacion = EstadoObligacion.NO_INICIADO


class SinTipificarEvidencia(BaseModel):
    """Entrada de ``sin_tipificar`` (CU-08, flujo 3a): la cita y el motivo (lst:det-evidencia)."""

    cita: str
    motivo: MotivoSinTipificar


class SinMapeoEvidencia(BaseModel):
    """Entrada de ``sin_mapeo`` (CU-08, flujo 3b): tipificada pero sin entrada en la tabla.

    Forma tomada de lst:det-alg-tipificacion, que añade a ``sin_mapeo`` el bloque, la
    normativa y el artículo.
    """

    # TODO(PT3/PP-10): confirmar la forma. lst:det-evidencia solo muestra la lista vacía; si
    # la revisión del SGSI necesita localizarla, añadir pagina y fragmento.
    normativa: str
    articulo: str
    cita: str


class EvidenceDocument(BaseModel):
    """Documento de evidencia (lst:det-evidencia)."""

    generador: Generador
    generado: datetime
    request_id: str
    proyecto: ProyectoEvidencia
    obligaciones: list[ObligacionEvidencia]
    sin_tipificar: list[SinTipificarEvidencia]
    sin_mapeo: list[SinMapeoEvidencia]
    aviso: str = AVISO_EVIDENCIA


class EvidenceResponse(BaseModel):
    """Respuesta prevista de ``POST /v1/evidence``: la misma evidencia en los dos formatos."""

    evidencia: EvidenceDocument
    markdown: str


def build_evidence(
    inp: QuestionnaireInput,
    response: RAGResponse,
    docs: list,
    tabla: TablaMapeo,
    *,
    request_id: str,
    generado: datetime,
) -> EvidenceDocument:
    """Ensambla la evidencia a partir del informe, los fragmentos recuperados y la tabla.

    ``generado`` se recibe como parámetro (no se lee el reloj aquí) para que la función sea
    pura y las pruebas deterministas: PP-10 exige que se reproduzca idéntica a partir del
    mismo informe.
    """
    # TODO(PT3/RF-27): implementar sobre obligations.extract_obligations, locate_citations,
    # tipificar y controls.resolve_controls. Necesita los docs recuperados, que hoy
    # run_pipeline no devuelve: la caché de la capa de servicio guardará el análisis completo
    # con los fragmentos (23-detalle, «Capa de servicio»), sin cambiar RAGResponse.
    raise NotImplementedError


def render_markdown(evidencia: EvidenceDocument) -> str:
    """Misma información que el JSON, para un repositorio de evidencias o el SGSI."""
    # TODO(PT3/RF-27): implementar; incluir versiones, aviso y las listas sin tipificar y sin mapeo.
    raise NotImplementedError


def validate_against_schema(document: dict, schema_path: Path = SCHEMA_PATH) -> None:
    """Valida contra ``data/evidence.schema.json`` (JSON Schema 2020-12); lanza si no valida."""
    # TODO(PT3/PP-10): implementar con jsonschema.Draft202012Validator (declarar la dependencia).
    raise NotImplementedError


# TODO(PT3/RF-27): añadir POST /v1/evidence en app/main.py (mismo limitador, clave de API y
# caché que /v1/analyze; responde EvidenceResponse; 503 si la tabla o el catálogo son
# inválidos, tab:det-mcp-errores) cuando build_evidence exista.
