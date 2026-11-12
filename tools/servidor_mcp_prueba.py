"""API local con ``/mcp`` para probar clientes MCP y ver qué revisión negocia cada uno.

Arranca la API de este repositorio con ``/mcp`` activado, el índice real y una clave que llega
en ``LEGALDEV_API_KEY`` (no se imprime ni se guarda), y apunta en un fichero JSONL una fila por
cada petición a ``/mcp``:

* método HTTP, código de respuesta y milisegundos;
* método JSON-RPC y, en ``tools/call``, el nombre de la herramienta;
* la revisión que pide el cliente: cabecera ``MCP-Protocol-Version`` y, en el cuerpo,
  ``protocolVersion`` de ``initialize`` (2025-11-25 y anteriores) o el ``_meta`` de la
  2026-07-28;
* ``clientInfo`` (nombre y versión del cliente), si lo envía, y si trae clave.

Nunca la clave, los argumentos ni los resultados. Con ``--modelo-simulado`` no se llama a
Groq: el informe de ``analizar_proyecto`` es un texto fijo, y la recuperación es la real.
Sin él, la clave de Groq sale del ``.env`` y cada análisis gasta cuota.

Uso, desde la raíz del repositorio (los clientes se apuntan a ``http://127.0.0.1:8766/mcp``):

    LEGALDEV_API_KEY=<clave de prueba> uv run python tools/servidor_mcp_prueba.py --modelo-simulado

Se usó así con MCP Inspector el 12/11/2026 (``docs/mcp/README.md``, «MCP Inspector»). Al
terminar, ``chroma_db/chroma.sqlite3`` puede quedar modificado (Chroma lo abre en escritura):
se restaura con ``git checkout -- chroma_db/chroma.sqlite3``.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parent.parent
INFORME_SIMULADO = (
    "## RGPD\n\nInforme simulado: el modelo no se ha llamado (servidor de prueba de "
    "clientes MCP).\n"
)


def fila(
    metodo_http: str,
    cabeceras: dict[str, str],
    cuerpo: bytes,
    status: int | None,
    ms: int,
) -> dict[str, Any]:
    """La fila de registro de una petición: sin clave, argumentos ni resultado."""
    try:
        mensaje = json.loads(cuerpo or b"{}")
    except ValueError:
        mensaje = None
    mensaje = mensaje if isinstance(mensaje, dict) else {}
    params = mensaje.get("params") if isinstance(mensaje.get("params"), dict) else {}
    meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
    cliente = params.get("clientInfo") or meta.get("io.modelcontextprotocol/clientInfo")
    return {
        "http": metodo_http,
        "status": status,
        "ms": ms,
        "metodo": mensaje.get("method"),
        "herramienta": params.get("name")
        if mensaje.get("method") == "tools/call"
        else None,
        "cabecera_version": cabeceras.get("mcp-protocol-version"),
        "version_pedida": params.get("protocolVersion")
        or meta.get("io.modelcontextprotocol/protocolVersion"),
        "cliente": (
            {k: cliente.get(k) for k in ("name", "version")}
            if isinstance(cliente, dict)
            else None
        ),
        "con_clave": "x-api-key" in cabeceras,
    }


def con_registro(app, escribir: Callable[[dict[str, Any]], None]):
    """Envuelve la aplicación ASGI y llama a ``escribir`` con la fila de cada petición a /mcp."""

    async def _app(scope, receive, send):
        if scope["type"] != "http" or scope["path"] != "/mcp":
            await app(scope, receive, send)
            return
        cabeceras = {
            k.decode().lower(): v.decode("latin-1") for k, v in scope["headers"]
        }
        trozos: list[bytes] = []
        estado: dict[str, int] = {}

        async def _receive():
            mensaje = await receive()
            if mensaje["type"] == "http.request":
                trozos.append(mensaje.get("body", b""))
            return mensaje

        async def _send(mensaje):
            if mensaje["type"] == "http.response.start":
                estado["status"] = mensaje["status"]
            await send(mensaje)

        t0 = time.perf_counter()
        try:
            await app(scope, _receive, _send)
        finally:
            ms = round((time.perf_counter() - t0) * 1000)
            escribir(
                fila(
                    scope["method"],
                    cabeceras,
                    b"".join(trozos),
                    estado.get("status"),
                    ms,
                )
            )

    return _app


class _ModeloSimulado:
    def invoke(self, messages):
        return SimpleNamespace(content=INFORME_SIMULADO)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--puerto", type=int, default=8766)
    ap.add_argument(
        "--registro",
        default=str(Path(tempfile.gettempdir()) / "legaldev-mcp-peticiones.jsonl"),
        help="fichero JSONL (por defecto, en el directorio temporal)",
    )
    ap.add_argument("--modelo-simulado", action="store_true", help="no llama a Groq")
    args = ap.parse_args(argv)

    clave = os.environ.get("LEGALDEV_API_KEY", "").strip()
    if not clave:
        print("Falta LEGALDEV_API_KEY (la clave de prueba de /mcp).", file=sys.stderr)
        return 2
    # Antes de importar app: Settings lee el entorno al importarse.
    os.environ.update(
        MCP_ENABLED="true",
        MCP_API_KEYS=clave,
        MCP_ALLOWED_ORIGINS="",
        MCP_DAILY_LIMIT="",
        GROQ_VERIFY_MODEL_ON_STARTUP="false",
    )
    if args.modelo_simulado:
        os.environ.update(GROQ_API_KEY="clave-groq-falsa", GROQ_FALLBACK_MODEL="")
    registro = Path(args.registro).resolve()  # antes de cambiar de directorio
    os.chdir(RAIZ)
    sys.path.insert(0, str(RAIZ))
    print(f"Registro de peticiones: {registro}", file=sys.stderr)

    with registro.open("a", encoding="utf-8") as f:

        def escribir(datos: dict[str, Any]) -> None:
            f.write(json.dumps(datos, ensure_ascii=False) + "\n")
            f.flush()

        simulado = (
            patch(
                "app.main._make_groq_client", side_effect=lambda _m: _ModeloSimulado()
            )
            if args.modelo_simulado
            else contextlib.nullcontext()
        )
        with simulado:
            import uvicorn

            from app.main import app

            uvicorn.run(
                con_registro(app, escribir),
                host="127.0.0.1",
                port=args.puerto,
                log_level="warning",
                lifespan="on",
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
