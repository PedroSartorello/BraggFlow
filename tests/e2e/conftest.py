"""
Testes de ponta a ponta: o web app de verdade, num servidor local, aberto num
Chromium pelo Playwright, com os dados sintéticos de examples/data.

Precisam de ``pip install -e ".[e2e]"`` e ``playwright install chromium``;
sem o Playwright, esta pasta é ignorada. A página busca o Plotly por CDN, então
também precisam de internet. Para pular só estes: ``pytest -m "not e2e"``.
"""

import shutil
import threading
from pathlib import Path

import pytest

try:
    import playwright  # noqa: F401
except ImportError:
    collect_ignore_glob = ["test_*.py"]

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "data"


@pytest.fixture
def data_dir(tmp_path):
    """Pasta de dados com dois ensaios (cópias do sintético) e um espectro."""
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    shutil.copy(EXAMPLES / "synthetic_interrogator.asc", raw / "ensaio_a.asc")
    shutil.copy(EXAMPLES / "synthetic_interrogator.asc", raw / "ensaio_b.asc")
    shutil.copy(EXAMPLES / "synthetic_spectrum.txt", raw / "espectro.txt")
    return tmp_path / "data"


@pytest.fixture
def server(data_dir):
    """Servidor do web app numa porta livre; devolve a URL."""
    from werkzeug.serving import make_server

    from braggflow.webapp.app import create_app

    srv = make_server("127.0.0.1", 0, create_app(data_dir), threaded=True)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()
    thread.join(timeout=5)


@pytest.fixture
def app(page, server):
    """Página aberta, sem erros de JavaScript até o fim do teste."""
    erros = []
    page.on("pageerror", lambda exc: erros.append(str(exc)))
    page.on("console", lambda msg: msg.type == "error" and erros.append(msg.text))
    page.set_default_timeout(20_000)
    page.goto(server)
    yield page
    assert erros == [], erros
