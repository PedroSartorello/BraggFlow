"""
Testes de ponta a ponta: o web app de verdade, num servidor local, aberto num
Chromium pelo Playwright, com os dados sintéticos de examples/data.

Precisam de ``pip install -e ".[e2e]"`` e ``playwright install chromium``;
sem o Playwright, esta pasta é ignorada. A página busca o Plotly por CDN, então
também precisam de internet. Para pular só estes: ``pytest -m "not e2e"``.

``BF_CPU_THROTTLE=6`` deixa o Chromium 6× mais lento e ``BF_SERVER_DELAY=0.2``
atrasa cada resposta do servidor em 0,2 s, como uma máquina de CI fraca, para
reproduzir corridas que só aparecem lá.
"""

import os
import shutil
import threading
from pathlib import Path
from types import SimpleNamespace

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
    """Servidor do web app numa porta livre: ``url`` e ``erros`` (respostas 4xx/5xx)."""
    from werkzeug.serving import make_server

    from braggflow.webapp.app import create_app

    flask_app = create_app(data_dir)
    respostas_com_erro = []

    atraso = float(os.environ.get("BF_SERVER_DELAY") or 0)

    @flask_app.after_request
    def guardar_erro(response):
        if atraso:
            import time
            time.sleep(atraso)            # o corpo dos 4xx/5xx vai na mensagem da falha
        if response.status_code >= 400:
            from flask import request
            corpo = response.get_data(as_text=True)[:300] if response.is_json else ""
            respostas_com_erro.append(f"{response.status_code} {request.method} {request.path}: {corpo}")
        return response

    srv = make_server("127.0.0.1", 0, flask_app, threaded=True)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield SimpleNamespace(url=f"http://127.0.0.1:{srv.server_port}", erros=respostas_com_erro)
    srv.shutdown()
    thread.join(timeout=5)


@pytest.fixture
def app(page, server):
    """Página aberta, sem erros de JavaScript até o fim do teste."""
    erros = []
    page.on("pageerror", lambda exc: erros.append(str(exc)))
    page.on("console", lambda msg: msg.type == "error" and erros.append(msg.text))
    page.set_default_timeout(20_000)
    if os.environ.get("BF_CPU_THROTTLE"):
        cdp = page.context.new_cdp_session(page)
        cdp.send("Emulation.setCPUThrottlingRate", {"rate": float(os.environ["BF_CPU_THROTTLE"])})
    page.goto(server.url)
    yield page
    assert erros == [], {"navegador": erros, "servidor": server.erros}
