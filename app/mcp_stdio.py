"""Servidor MCP local por stdio (RF-22: «y por stdio en local»; CU-07).

Orden: ``uv run --directory <repositorio> python -m app.mcp_stdio`` (``make mcp-stdio``).
``.env`` y ``CHROMA_DB_PATH=./chroma_db`` se resuelven desde el directorio de trabajo, y los
clientes lanzan el proceso desde el del proyecto del usuario: ``--directory`` lo fija.

Es el mismo servidor que ``POST /mcp``: ``build_mcp_server`` (mismas herramientas, esquemas,
textos y capa de servicio) sobre el mismo índice y el mismo modelo, cargados con
``app.main.load_engine`` como en el ``lifespan``. Solo cambia el transporte:

* Sin clave de API, sin ``Origin`` y sin límites (ni el cupo por minuto ni el tope diario):
  el servidor es un proceso hijo del cliente, en la máquina de quien lo lanza, y gasta su
  propia clave de Groq (la de su ``.env``). Quien puede lanzarlo ya puede leer esa clave.
* stdout es del protocolo. Los registros van a stderr (los clientes lo guardan en su
  registro), y el motor se carga después de que el SDK desvíe el descriptor 1 a stderr, de
  modo que lo que escriban por stdout las bibliotecas al cargar (embeddings, Chroma, el
  reordenador) no corrompa los mensajes.
* Las dos eras, como por HTTP: la primera petición decide (``server/discover`` de la
  revisión 2026-07-28 o ``initialize`` de la 2025-11-25 y anteriores).

La primera respuesta espera a que termine la carga (decenas de segundos en CPU, la primera
vez más si hay que descargar los modelos): ``docs/mcp/README.md``, «Modo stdio».
"""

from __future__ import annotations

import logging
import sys
from types import SimpleNamespace

import anyio
import anyio.to_thread
from mcp.server.stdio import stdio_server

logger = logging.getLogger(__name__)


def configure_logging(level: str) -> None:
    """Todos los registros a stderr: stdout lleva solo mensajes del protocolo.

    ``force`` sustituye cualquier configuración previa; ``app.main`` llama después a
    ``logging.basicConfig`` al importarse, que ya no hace nada.
    """
    logging.basicConfig(
        stream=sys.stderr,
        level=getattr(logging, level.upper(), logging.INFO),
        force=True,
    )


def load_state() -> tuple[SimpleNamespace, str]:
    """El estado del motor (como ``app.state`` tras el ``lifespan``) y la versión de la app.

    Importa ``app.main`` aquí, y no al principio del módulo, para que también la importación
    (torch, Chroma, sentence-transformers) ocurra con stdout ya desviado.
    """
    from app import main

    state = SimpleNamespace()
    main.load_engine(state)
    return state, main.app.version


async def serve() -> None:
    """Atiende una conexión por stdio hasta que el cliente cierra la entrada."""
    async with stdio_server() as (read_stream, write_stream):
        # El cliente ya puede haber enviado su primera petición; espera en la tubería hasta
        # que el motor esté cargado. La carga va en un hilo para no bloquear el bucle.
        state, version = await anyio.to_thread.run_sync(load_state)
        from app.mcp_server import build_mcp_server

        server = build_mcp_server(state, version=version)
        logger.info("MCP server ready on stdio")
        # API privada del SDK (versión fijada, mcp==2.3.0), como _tool_manager en
        # mcp_server._register: MCPServer.run_stdio_async abre su propio stdio_server() y aquí
        # tiene que estar abierto antes de cargar el motor. run() sirve las dos eras.
        lowlevel = server._lowlevel_server
        await lowlevel.run(
            read_stream, write_stream, lowlevel.create_initialization_options()
        )


def main() -> None:
    from app.config import settings

    configure_logging(settings.log_level)
    try:
        anyio.run(serve)
    except KeyboardInterrupt:  # Ctrl+C al lanzarlo a mano desde una terminal
        pass


if __name__ == "__main__":
    main()
