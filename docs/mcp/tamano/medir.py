"""Tamaño en caracteres de los resultados MCP (0.4.0 frente a 0.5.0). Sin LLM ni red.

Uso, desde un directorio sin ``.env`` y con los modelos ya descargados::

    HF_HUB_OFFLINE=1 python docs/mcp/tamano/medir.py <repositorio> <copia de chroma_db> <salida.json>

Llama en proceso, con el cliente del SDK, a ``consultar_obligaciones`` con las 8 consultas de
``tools/medir_latencia_mcp.py`` y a ``analizar_proyecto`` con un cuestionario propio de IA
generativa (``CUESTIONARIO``, un SaaS con datos personales, cookies y acceso público; no es
ninguno de los de ese script) y un modelo simulado (el informe no cuenta para el JSON del
texto). Cuenta los caracteres del
texto de ``content`` y del ``structuredContent``, y cuántas veces aparece en ``content`` el
texto de cada fragmento (en crudo o escapado como cadena JSON). Se ejecutó con el código de
``44039c8`` (0.4.0, ``resultado-0.4.0.json``) y con el arreglo (``resultado-0.5.0.json``).
Resultados en ``docs/mcp/README.md``, «Texto y contenido estructurado de los resultados».
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

CONSULTAS = (
    ("RGPD", "registro de usuarios con email"),
    ("LSSI", "envío de comunicaciones comerciales por email"),
    ("EU AI Act", "sistema de IA generativa que redacta textos"),
    ("LOPDGDD", "consentimiento de menores de edad"),
    (
        "Guía sobre uso de cookies - AEPD",
        "banner de consentimiento para cookies analíticas",
    ),
    ("RGPD", "notificación de una brecha de seguridad"),
    ("Directiva NIS2", "gestión de incidentes de ciberseguridad"),
    ("LSSI", "información que debe mostrar la web del prestador"),
)
CUESTIONARIO = {
    "tipo_proyecto": "saas",
    "descripcion_breve": "Asistente que redacta textos con IA generativa para pymes",
    "tiene_usuarios_registrados": True,
    "acceso_publico": True,
    "tipos_datos_personales": ["email", "nombre"],
    "usuarios_menores": False,
    "usuarios_ue": True,
    "transferencia_datos_terceros": True,
    "usa_ia": True,
    "tipo_ia": "generativa",
    "usa_cookies": True,
    "monetizacion": "suscripcion",
    "contenido_digital": False,
    "ccaa": "Galicia",
    "es_empresa": True,
    "colegiado": None,
}


def apariciones(texto: str, fragmento: str) -> int:
    """Veces que ``fragmento`` está en ``texto``, en crudo o escapado como cadena JSON."""
    escapado = json.dumps(fragmento, ensure_ascii=False)[1:-1]
    return texto.count(fragmento) + (
        texto.count(escapado) if escapado != fragmento else 0
    )


def texto_de(resultado) -> str:
    return "".join(getattr(c, "text", "") for c in resultado.content)


async def medir(state, build_mcp_server, client_cls) -> list[dict]:
    filas = []
    async with client_cls(build_mcp_server(state)) as c:
        for normativa, contexto in CONSULTAS:
            r = await c.call_tool(
                "consultar_obligaciones", {"normativa": normativa, "contexto": contexto}
            )
            texto, estructurado = texto_de(r), r.structured_content
            fragmentos = estructurado["fragmentos"]
            filas.append(
                {
                    "herramienta": "consultar_obligaciones",
                    "normativa": normativa,
                    "fragmentos": len(fragmentos),
                    "content_caracteres": len(texto),
                    "structured_caracteres": len(
                        json.dumps(estructurado, ensure_ascii=False)
                    ),
                    "texto_fragmentos_caracteres": sum(
                        len(f["texto"]) for f in fragmentos
                    ),
                    "apariciones_texto_en_content": [
                        apariciones(texto, f["texto"]) for f in fragmentos
                    ],
                    "articulos": [f.get("articulo") for f in fragmentos],
                    "considerandos": [f.get("considerando") for f in fragmentos],
                }
            )
        r = await c.call_tool("analizar_proyecto", CUESTIONARIO)
        texto, estructurado = texto_de(r), r.structured_content
        filas.append(
            {
                "herramienta": "analizar_proyecto",
                "fragmentos": len(estructurado["fragmentos"]),
                "content_caracteres": len(texto),
                "informe_caracteres": len(estructurado["informe"]),
                "apendice_caracteres": len(texto) - len(estructurado["informe"]),
                "nulos_en_content": texto.count(": null"),
                "structured_caracteres": len(
                    json.dumps(estructurado, ensure_ascii=False)
                ),
            }
        )
    return filas


def main() -> None:
    repo, chroma, salida = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    sys.path.insert(0, str(repo))
    os.environ.setdefault("GROQ_API_KEY", "medir-sin-llm")

    from langchain_chroma import Chroma
    from langchain_huggingface import HuggingFaceEmbeddings
    from mcp import Client

    from app import store
    from app.corpus import EMBEDDING_MODEL
    from app.mcp_server import build_mcp_server

    vs = Chroma(
        persist_directory=chroma,
        embedding_function=HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL, encode_kwargs={"normalize_embeddings": True}
        ),
        collection_name="legaldev",
    )
    modelo = MagicMock()
    modelo.invoke.return_value = MagicMock(content="Informe simulado (sin LLM).")
    state = SimpleNamespace(
        vectorstore=vs,
        indexed_normativas=frozenset(Path(s).stem for s in store.list_sources(vs)),
        corpus_version=store.read_corpus_version(chroma),
        groq_client=modelo,
        groq_fallback_client=None,
    )
    filas = asyncio.run(medir(state, build_mcp_server, Client))
    salida.write_text(json.dumps(filas, ensure_ascii=False, indent=1), encoding="utf-8")
    for fila in filas:
        print(
            {k: v for k, v in fila.items() if k not in ("articulos", "considerandos")}
        )


if __name__ == "__main__":
    main()
