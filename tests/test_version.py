"""La versión de LegalDev: una sola cifra en pyproject.toml, el CHANGELOG, la API y el MCP.

El servidor MCP anuncia la versión en ``server/discover`` y en el ``initialize`` de la era
antigua, y es lo que distingue un ``tools/list`` de otro para un cliente que lo guarda en caché
(``mcp_server.TOOLS_LIST_TTL_MS``). La 0.4.0 siguió anunciándose con todo el servidor MCP
desplegado (revisión externa del 13/11/2026): estas pruebas impiden que vuelvan a divergir.
"""

import re
import tomllib
from pathlib import Path

from tests._mcp import message, rpc

RAIZ = Path(__file__).resolve().parent.parent


def test_version_is_the_same_in_pyproject_changelog_and_api(client):
    from app.main import VERSION, app

    proyecto = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    changelog = (RAIZ / "CHANGELOG.md").read_text(encoding="utf-8")
    ultima = re.search(r"^## \[(\d+\.\d+\.\d+)\] - \d{4}-\d{2}-\d{2}$", changelog, re.M)

    assert VERSION == "0.5.1"
    assert proyecto["project"]["version"] == VERSION
    assert ultima is not None and ultima.group(1) == VERSION
    assert app.version == VERSION
    assert client.get("/").json()["version"] == VERSION
    assert client.get("/openapi.json").json()["info"]["version"] == VERSION


def test_mcp_announces_the_version_in_both_eras(mcp_http):
    from app.main import VERSION

    discover = message(rpc(mcp_http, "server/discover"))["result"]
    assert discover["_meta"]["io.modelcontextprotocol/serverInfo"]["version"] == VERSION

    legacy = message(
        rpc(
            mcp_http,
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "cliente-antiguo", "version": "1"},
            },
            modern=False,
        )
    )["result"]
    assert legacy["serverInfo"]["version"] == VERSION
