"""Mapeo determinista obligación -> controles (esqueleto; sin uso en producción).

Requisitos: RF-26 (mapeo a controles del Anexo A de ISO/IEC 27001:2022 y medidas del Anexo II
del ENS, RD 311/2022) y RNF-17 (identificadores exactos, tabla con versión y fecha,
validación contra un catálogo). Prueba: PP-09. Caso de uso: CU-08.

La asociación la aplica el código a partir de ``data/mapeo_controles.yaml``; el modelo de
lenguaje no decide ningún control. Cada entrada de la tabla se identifica por la normativa y
los artículos que la originan o, en las guías sin articulado, por las páginas. Una obligación
tipificada sin entrada en la tabla se devuelve «sin mapeo» (CU-08, flujo 3b); una entrada
que no admite control técnico lleva listas vacías y la justificación ``SIN_CONTROL_TECNICO``.

Módulo puro: no importa FastAPI, la biblioteca MCP ni LangChain.
"""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path
from typing import Final

from pydantic import BaseModel

from app.obligations import ObligacionTipificada

DATA_DIR: Final = Path(__file__).resolve().parent.parent / "data"
MAPPING_PATH: Final = DATA_DIR / "mapeo_controles.yaml"
CATALOG_PATH: Final = DATA_DIR / "catalogo_controles.yaml"

SIN_CONTROL_TECNICO: Final = "sin control técnico aplicable"

# Formato de los identificadores (RNF-17). Que un identificador tenga formato válido no
# significa que exista: eso lo comprueba el catálogo.
# ISO/IEC 27001:2022, Anexo A: A.5.1-A.5.37, A.6.1-A.6.8, A.7.1-A.7.14, A.8.1-A.8.34.
ISO27001_ID: Final = re.compile(r"^A\.[5-8]\.\d{1,2}$")
# ENS, Anexo II: marco organizativo (org.N), operacional (op.<grupo>.N) y medidas de
# protección (mp.<grupo>.N), p. ej. org.1, op.pl.1, mp.info.1.
ENS_ID: Final = re.compile(r"^(?:org\.\d+|op\.[a-z]+\.\d+|mp\.[a-z]+\.\d+)$")


class Marco(StrEnum):
    ISO27001 = "iso27001"
    ENS = "ens"


class ControlRef(BaseModel):
    """Referencia a un control (ISO/IEC 27001) o a una medida (ENS)."""

    marco: Marco
    id: str


class EntradaMapeo(BaseModel):
    """Una fila de ``data/mapeo_controles.yaml``."""

    id: str  # identificador del tipo de obligación, p. ej. "rgpd.informacion-interesado"
    normativa: str  # nombre de fichero del corpus
    articulos: list[int] = []
    # Clave alternativa para guías sin articulado. Base 1, como las cita el informe.
    # Frágil ante otra edición del PDF: solo es válida para la corpus_version de la tabla.
    paginas: list[int] = []
    resumen: str
    iso27001: list[str] = []
    ens: list[str] = []
    justificacion: str


class TablaMapeo(BaseModel):
    version: str
    fecha: str | None = None
    catalogos: dict[str, str]
    entradas: list[EntradaMapeo]


class Catalogo(BaseModel):
    """``data/catalogo_controles.yaml``: identificador -> paráfrasis propia o nombre del BOE."""

    version: str
    iso27001: dict[str, str]
    ens: dict[str, str]


def load_mapping(path: Path = MAPPING_PATH) -> TablaMapeo:
    """Carga y valida la estructura de la tabla (no los identificadores: ver ``validate_mapping``)."""
    # TODO(PT3/RF-26): implementar con yaml.safe_load (PyYAML aún no es dependencia explícita).
    raise NotImplementedError


def load_catalog(path: Path = CATALOG_PATH) -> Catalogo:
    # TODO(PT3/RNF-17): implementar.
    raise NotImplementedError


def validate_mapping(tabla: TablaMapeo, catalogo: Catalogo) -> list[str]:
    """Errores de la tabla; lista vacía si es válida (PP-09).

    Comprueba: todo identificador tiene formato válido y existe en el catálogo; cada entrada
    tiene normativa, artículos o páginas (no ambos vacíos) y justificación; no hay ``id``
    duplicados; ninguna pareja (normativa, artículo) o (normativa, página) cae en dos entradas.
    """
    # TODO(PT3/PP-09): implementar.
    raise NotImplementedError


def resolve_controls(
    obligacion: ObligacionTipificada, tabla: TablaMapeo
) -> EntradaMapeo | None:
    """Entrada de la tabla que corresponde a la obligación, o ``None`` si queda «sin mapeo»."""
    # TODO(PT3/RF-26): implementar; determinista (misma entrada -> misma salida, sin LLM).
    raise NotImplementedError
