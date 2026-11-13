"""Identificador y referencia de un fragmento del índice, comunes a la API, MCP y la evidencia.

23-detalle, «Herramientas, identificadores y resultado». Módulo sin dependencias del motor
para que ``app.models``, ``app.rag`` y ``app.service`` lo importen sin ciclos.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Final

from pydantic import BaseModel, Field


def fragment_id(texto: str) -> str:
    """Identificador de un fragmento: los 12 primeros hexadecimales del MD5 de su texto.

    Es el mismo resumen con el que ``rag._retrieve`` deduplica los candidatos
    (``rag._content_hash``), así que se conserva entre reconstrucciones del índice mientras el
    texto no cambie, a diferencia del UUID de ChromaDB. Es lo que compara PP-05 (CA-09).
    """
    return hashlib.md5(texto.encode()).hexdigest()[:12]


# Encabezado que guarda el segmentador en metadata["article"] (app/legal_splitter.py):
# «Artículo 22», «ARTÍCULO 5», «Art. 5», «Considerando 32», con cualquier espacio en medio
# (pypdf deja a veces un salto de línea: «Artículo \n35»). «(cont.)» no llega al metadato,
# solo al texto de los sub-fragmentos; se acepta por si un índice futuro lo guardara.
_ENCABEZADO: Final = re.compile(
    r"\s*(?:(?P<art>art[ií]culo|art\.)|(?P<cons>considerando))\s+(?P<num>\d+)"
    r"(?:\s*\(cont\.\))?\s*",
    re.IGNORECASE,
)
# Ninguna norma del corpus pasa de 999 artículos ni considerandos (en el índice del
# 13/11/2026 el mayor artículo es el 203 y el mayor considerando, el 149). Los siete
# encabezados de cuatro o cinco cifras («Artículo 2918», «Considerando 49127»...) son el
# número pegado a una llamada de nota de una guía de la AEPD («Artículo 29» y la nota 18): no
# localizan nada, y un localizador falso es peor que ninguno.
_MAX_CIFRAS: Final = 3


def localizador(encabezado: str | None) -> tuple[str | None, str | None]:
    """``(articulo, considerando)``: el número como cadena en el campo que corresponde.

    ``"Artículo 22"`` -> ``("22", None)``; ``"Considerando 32"`` -> ``(None, "32")``;
    ``None``, un encabezado que no es exactamente uno de esos (``"Anexo III"``, ``"22"``,
    ``"Artículo 22 bis"``) o un número de más de tres cifras -> ``(None, None)``. Nunca
    rellena los dos.
    """
    if not isinstance(encabezado, str) or not encabezado:
        return None, None
    m = _ENCABEZADO.fullmatch(encabezado)
    if m is None or len(m["num"]) > _MAX_CIFRAS:
        return None, None
    numero = m["num"]
    return (numero, None) if m["art"] else (None, numero)


class FragmentoRef(BaseModel):
    """Fragmento tal como sale por las herramientas y la evidencia."""

    identificador: str  # fragment_id
    normativa: str  # raíz del nombre de fichero («RGPD», «LSSI»)
    pagina: int  # base 1, como en el prompt y el informe (metadata["page"] + 1)
    # El índice guarda el encabezado («Artículo 22», «Considerando 32»); aquí va solo el
    # número (``localizador``). El prompt sigue recibiendo el encabezado tal cual.
    articulo: str | None = Field(
        default=None,
        description=(
            "Número del artículo como cadena («22»), si el fragmento empieza por uno; nulo "
            "si no lo tiene o si es un considerando."
        ),
    )
    texto: str | None = None  # solo en consultar_obligaciones
    # Campo añadido después de la primera versión del contrato (0.5.0): opcional y al final.
    considerando: str | None = Field(
        default=None,
        description=(
            "Número del considerando como cadena («32»), si el fragmento empieza por uno; "
            "nulo en otro caso. Nunca va junto con articulo."
        ),
    )

    @classmethod
    def from_doc(cls, doc, *, con_texto: bool) -> FragmentoRef:
        """Construye la referencia desde un ``Document`` de LangChain con los metadatos del
        índice (``source``, ``page`` en base 0 y, si existe, ``article``)."""
        meta = doc.metadata or {}
        page = meta.get("page")
        articulo, considerando = localizador(meta.get("article"))
        return cls(
            identificador=fragment_id(doc.page_content),
            normativa=Path(meta.get("source", "")).stem,
            pagina=int(page) + 1 if isinstance(page, int) else 0,
            articulo=articulo,
            texto=doc.page_content if con_texto else None,
            considerando=considerando,
        )
