"""Mapeo determinista obligación -> controles (esqueleto; sin uso en producción).

Requisitos: RF-26 (mapeo a controles del Anexo A de ISO/IEC 27001:2022 y medidas del Anexo II
del ENS, RD 311/2022) y RNF-17 (identificadores exactos, tabla con versión y fecha,
validación contra un catálogo). Prueba: PP-09. Caso de uso: CU-08. Formato de la tabla:
23-detalle.tex, lst:det-mapeo.

La asociación la aplica el código a partir de ``data/mapeo_controles.yaml``; el modelo de
lenguaje no decide ningún control. Cada entrada define un tipo de obligación por su normativa
(identificador canónico, p. ej. «RGPD») y una lista de artículos o rangos («32», «13-14»).
Una obligación tipificada sin entrada en la tabla se devuelve «sin mapeo» (CU-08, flujo 3b).
Una obligación «sin control técnico aplicable» (CA-10) solo la acredita, como mucho, el
control de requisitos legales A.5.31 (por cotejar con el texto de la norma) y ninguna medida
del ENS (tab:det-mapeo-ejemplo, LSSI 10); su justificación empieza por
``SIN_CONTROL_TECNICO``. El art. 21 LSSI no entra en ese caso: es un control organizativo
con verificación técnica posible (la baja en cada envío).

Módulo puro: no importa FastAPI, la biblioteca MCP ni LangChain.
"""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel

from app.obligations import ObligacionTipificada

# Raíz del repositorio / data. También la usa app/evidence.py (esquema de la evidencia).
# TODO(PT3/RF-26): COPY data/ en el Dockerfile. Hoy la imagen (y el Space de Hugging Face)
# solo copia app/ y chroma_db/, así que en cuanto main.py importe este módulo o
# app/evidence.py la carga fallará en producción aunque pase en local y en la CI. La memoria
# (30-manual-instalacion) prevé que la tabla «viajará en la misma imagen». Alternativa: mover
# los ficheros a app/data/ y resolverlos desde el paquete.
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
# Artículo o rango de artículos de una entrada: "32", "13-14".
ARTICULOS_ID: Final = re.compile(r"^\d+(?:-\d+)?$")


class Marco(StrEnum):
    ISO27001 = "iso27001"
    ENS = "ens"


class ControlRef(BaseModel):
    """Referencia a un control (ISO/IEC 27001) o a una medida (ENS)."""

    marco: Marco
    id: str


class EntradaMapeo(BaseModel):
    """Una entrada de ``data/mapeo_controles.yaml`` (lst:det-mapeo)."""

    id: str  # identificador del tipo de obligación, p. ej. "rgpd.art32.seguridad"
    normativa: str  # identificador canónico: raíz del nombre de fichero del corpus
    articulos: list[str]  # números o rangos, como cadenas: ["32"], ["13-14"]
    resumen: str
    iso27001: list[str] = []
    ens: list[str] = []
    justificacion: str
    # Origen de la correspondencia, p. ej. «propuesta del autor, pendiente de revisión por un
    # perfil SGSI».
    fuente: str
    verificacion: Literal["automática", "documental", "manual"]


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
    """Carga y valida la estructura de la tabla (no los identificadores: ver ``validate_mapping``).

    Una tabla o un catálogo inválidos al arrancar son ``TablaMapeoInvalida`` en la memoria
    (tab:det-mcp-errores): ``app.service.InvalidMappingError``.
    """
    # TODO(PT3/RF-26): implementar con yaml.safe_load (PyYAML aún no es dependencia explícita).
    raise NotImplementedError


def load_catalog(path: Path = CATALOG_PATH) -> Catalogo:
    # TODO(PT3/RNF-17): implementar.
    raise NotImplementedError


def validate_mapping(
    tabla: TablaMapeo, catalogo: Catalogo, normativas_indexadas: frozenset[str]
) -> list[str]:
    """Errores de la tabla; lista vacía si es válida (PP-09; 23-detalle, «Tabla de mapeo»).

    Comprueba: identificadores de entrada únicos; cada normativa existe en el índice; cada
    entrada tiene artículos con formato válido y justificación; los rangos de una misma
    normativa no se solapan (``resolve_controls`` es determinista); todo control y toda
    medida tienen formato válido y existen en el catálogo; y una entrada marcada
    ``SIN_CONTROL_TECNICO`` no lleva más control que A.5.31 ni ninguna medida del ENS.
    """
    # TODO(PT3/PP-09): implementar.
    raise NotImplementedError


def resolve_controls(
    obligacion: ObligacionTipificada, tabla: TablaMapeo
) -> EntradaMapeo | None:
    """Única entrada cuyo rango contiene el artículo, o ``None`` si queda «sin mapeo».

    Es ``tabla.resolver(n, art)`` de lst:det-alg-tipificacion.
    """
    # TODO(PT3/RF-26): implementar; determinista (misma entrada -> misma salida, sin LLM).
    raise NotImplementedError
