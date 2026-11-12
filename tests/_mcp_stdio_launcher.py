"""Proceso hijo de tests/test_mcp_stdio.py: ``app.mcp_stdio`` con el motor simulado.

Los ``patch`` de una prueba no cruzan el límite del proceso, así que se aplican aquí, con la
misma lista que ``tests/conftest.py`` (índice, embeddings, reordenador y Groq simulados; sin
red ni disco). Importar ``tests.conftest`` fija además las variables de entorno de las
pruebas antes de que se importe ``app``. La prueba lo lanza con un directorio de trabajo sin
``.env`` y ``PYTHONPATH`` apuntando al repositorio.

Los embeddings simulados escriben en stdout al construirse, como hacen algunas bibliotecas al
cargar: la prueba comprueba que eso acaba en stderr y no corrompe el protocolo.
"""

from unittest.mock import MagicMock, patch

from tests.conftest import _patched_app, fake_rerank, make_mock_doc

RUIDO_STDOUT = "ruido de la carga escrito en stdout"


def _embeddings_ruidosos(*args, **kwargs):
    print(RUIDO_STDOUT, flush=True)
    return MagicMock()


def main() -> None:
    with (
        _patched_app(make_mock_doc()),
        patch("app.main.HuggingFaceEmbeddings", side_effect=_embeddings_ruidosos),
        patch("app.reranker.rerank", side_effect=fake_rerank),
    ):
        from app import mcp_stdio

        mcp_stdio.main()


if __name__ == "__main__":
    main()
