"""Servidor MCP local por stdio (app/mcp_stdio.py; RF-22, CU-07).

Las pruebas de sesión lanzan el servidor como proceso hijo (``tests/_mcp_stdio_launcher.py``,
con el motor simulado) y le hablan con el cliente del SDK por su stdin y su stdout, como un
asistente real. Una sesión por era: ``server/discover`` (2026-07-28) e ``initialize``
(2025-11-25). El hijo arranca en un directorio sin ``.env``, sin red y con la clave de Groq
falsa.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from unittest.mock import patch

import anyio
import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

from app import mcp_stdio
from app.mcp_server import PROTOCOL_VERSION, TOOL_NAMES
from tests._mcp import text_of
from tests._mcp_stdio_launcher import RUIDO_STDOUT
from tests.conftest import _patched_app

REPO = Path(__file__).resolve().parent.parent
# Arranque en frío del hijo (importar torch, Chroma y el SDK) más las cuatro llamadas.
SESSION_TIMEOUT_S = 180


def _params(cwd: Path) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "tests._mcp_stdio_launcher"],
        cwd=str(cwd),
        # Se suman a las variables mínimas que hereda el hijo (PATH y poco más): nada del
        # entorno del autor ni de su .env.
        env={
            "PYTHONPATH": str(REPO),
            "PYTHONUTF8": "1",
            "GROQ_API_KEY": "test-key-not-real",
            "GROQ_VERIFY_MODEL_ON_STARTUP": "false",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            # DEBUG en todos los registradores: así la prueba de PP-08 ve todo lo que se
            # registra.
            "LOG_LEVEL": "DEBUG",
        },
    )


def _session(tmp_path: Path, mode: str, cuestionario: dict) -> tuple[dict, str]:
    """Una sesión completa por stdio; devuelve lo observado y lo que el hijo escribió en
    stderr."""
    errlog_path = tmp_path / "stderr.log"

    async def _run() -> dict:
        with (
            anyio.fail_after(SESSION_TIMEOUT_S),
            errlog_path.open("w", encoding="utf-8") as errlog,
        ):
            transport = stdio_client(_params(tmp_path), errlog=errlog)
            async with Client(transport, mode=mode) as c:
                return {
                    "version": c.protocol_version,
                    "tools": [t.name for t in (await c.list_tools()).tools],
                    "listar": await c.call_tool("listar_normativas", {}),
                    "consultar": await c.call_tool(
                        "consultar_obligaciones",
                        {"normativa": "RGPD", "contexto": "registro de usuarios"},
                    ),
                    "analizar": await c.call_tool("analizar_proyecto", cuestionario),
                }

    observado = anyio.run(_run)
    return observado, errlog_path.read_text(encoding="utf-8", errors="replace")


@pytest.mark.parametrize(
    ("mode", "version"),
    [("auto", PROTOCOL_VERSION), ("legacy", "2025-11-25")],
    ids=["discover-2026-07-28", "initialize-2025-11-25"],
)
def test_stdio_session_serves_the_three_tools(
    tmp_path, sample_input_dict, mode, version
):
    """Con ``mode="auto"`` el cliente negocia por ``server/discover``; con ``"legacy"``, por
    ``initialize``. En las dos eras: tools/list y una llamada a cada herramienta. El hijo
    arranca sin MCP_ENABLED ni claves (las vacía tests/conftest.py): stdio no pasa por la
    guarda de /mcp."""
    obs, stderr = _session(tmp_path, mode, sample_input_dict)

    assert obs["version"] == version
    assert obs["tools"] == list(TOOL_NAMES)

    listar = obs["listar"]
    assert not listar.is_error
    ids = [n["identificador"] for n in listar.structured_content["normativas"]]
    assert ids == ["LOPDGDD", "RGPD"]
    assert listar.structured_content["corpus_version"] == "abc123def456"

    consultar = obs["consultar"]
    assert not consultar.is_error
    assert consultar.structured_content["normativa"] == "RGPD"
    assert consultar.structured_content["fragmentos"]
    assert "Fragmentos de RGPD" in text_of(consultar)

    analizar = obs["analizar"]
    assert not analizar.is_error
    assert "Respuesta de prueba sobre RGPD" in analizar.structured_content["informe"]

    # stdout es del protocolo: lo que se escribe en stdout durante la carga del motor acaba en
    # stderr (si llegara al cliente, la sesión no habría funcionado), igual que los registros.
    assert RUIDO_STDOUT in stderr
    assert "MCP server ready on stdio" in stderr
    assert '"via": "mcp"' in stderr  # el registro del pipeline, con su etiqueta
    # PP-08 también por stdio: ni la descripción libre ni el contexto en los registros.
    assert sample_input_dict["descripcion_breve"] not in stderr
    assert "registro de usuarios" not in stderr


def test_load_state_loads_the_engine_like_the_lifespan(mock_doc):
    """El estado de stdio sale de app.main.load_engine, el mismo código que el lifespan."""
    with _patched_app(mock_doc):
        state, version = mcp_stdio.load_state()
    assert state.indexed_normativas == frozenset({"RGPD", "LOPDGDD"})
    assert state.corpus_version == "abc123def456"
    assert state.groq_client is not None
    assert state.groq_model_available is True
    assert version == "0.5.0"  # app.main.VERSION (tests/test_version.py)


def test_load_state_aborts_on_an_empty_index(mock_doc):
    with (
        _patched_app(mock_doc),
        patch("app.store.count", return_value=0),
        pytest.raises(RuntimeError, match="is empty"),
    ):
        mcp_stdio.load_state()


def test_configure_logging_sends_everything_to_stderr():
    root = logging.getLogger()
    antes = (root.level, list(root.handlers))
    # Sin manejadores previos: force=True cerraría los de pytest.
    root.handlers[:] = []
    try:
        mcp_stdio.configure_logging("debug")
        assert root.level == logging.DEBUG
        assert len(root.handlers) == 1
        assert root.handlers[0].stream is sys.stderr
        mcp_stdio.configure_logging("no-existe")
        assert root.level == logging.INFO
    finally:
        root.handlers[:] = antes[1]
        root.setLevel(antes[0])
