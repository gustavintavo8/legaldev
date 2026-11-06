"""Identificador y referencia de un fragmento del índice, comunes a la API, MCP y la evidencia.

23-detalle, «Herramientas, identificadores y resultado». Módulo sin dependencias del motor
para que ``app.models``, ``app.rag`` y ``app.service`` lo importen sin ciclos.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import BaseModel


def fragment_id(texto: str) -> str:
    """Identificador de un fragmento: los 12 primeros hexadecimales del MD5 de su texto.

    Es el mismo resumen con el que ``rag._retrieve`` deduplica los candidatos
    (``rag._content_hash``), así que se conserva entre reconstrucciones del índice mientras el
    texto no cambie, a diferencia del UUID de ChromaDB. Es lo que compara PP-05 (CA-09).
    """
    return hashlib.md5(texto.encode()).hexdigest()[:12]


class FragmentoRef(BaseModel):
    """Fragmento tal como sale por las herramientas y la evidencia."""

    identificador: str  # fragment_id
    normativa: str  # raíz del nombre de fichero («RGPD», «LSSI»)
    pagina: int  # base 1, como en el prompt y el informe (metadata["page"] + 1)
    # Encabezado que guarda el divisor del índice («Artículo 22», «Considerando 32»); None si
    # el fragmento no lo tiene (todos los del RGPD con el índice actual).
    articulo: str | None = None
    texto: str | None = None  # solo en consultar_obligaciones

    @classmethod
    def from_doc(cls, doc, *, con_texto: bool) -> FragmentoRef:
        """Construye la referencia desde un ``Document`` de LangChain con los metadatos del
        índice (``source``, ``page`` en base 0 y, si existe, ``article``)."""
        meta = doc.metadata or {}
        page = meta.get("page")
        articulo = meta.get("article")
        return cls(
            identificador=fragment_id(doc.page_content),
            normativa=Path(meta.get("source", "")).stem,
            pagina=int(page) + 1 if isinstance(page, int) else 0,
            articulo=str(articulo) if articulo not in (None, "") else None,
            texto=doc.page_content if con_texto else None,
        )
