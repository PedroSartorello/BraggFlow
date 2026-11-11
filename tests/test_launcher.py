"""Como o servidor web sobe: porta e navegador (``braggflow.webapp.app.main``)."""
import socket

import pytest
from flask import Flask

from braggflow.webapp import app as webapp


def test_requested_port_is_kept():
    assert webapp.choose_port(8123) == 8123


def test_busy_default_port_moves_to_the_next_free_one(monkeypatch):
    ocupadas = {webapp.DEFAULT_PORT, webapp.DEFAULT_PORT + 1}
    monkeypatch.setattr(webapp, "_port_free", lambda p: p not in ocupadas)
    assert webapp.choose_port() == webapp.DEFAULT_PORT + 2


def test_no_free_port_says_how_to_choose_one(monkeypatch):
    monkeypatch.setattr(webapp, "_port_free", lambda p: False)
    with pytest.raises(SystemExit, match="--port"):
        webapp.choose_port()


def test_port_free_sees_a_port_in_use():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        assert not webapp._port_free(s.getsockname()[1])


@pytest.fixture
def subida(monkeypatch):
    """Roda ``main`` sem servidor nem navegador e devolve o que ele faria."""
    feito = {}
    monkeypatch.setattr(Flask, "run", lambda self, **kw: feito.update(run=kw))
    monkeypatch.setattr(webapp, "choose_port", lambda pedida: pedida or 5123)

    class TimerImediato:
        def __init__(self, atraso, funcao, args):
            self.chamada = (funcao, args)

        def start(self):
            feito["browser"] = self.chamada[1][0]

    monkeypatch.setattr(webapp.threading, "Timer", TimerImediato)
    return feito


def test_main_opens_the_browser_on_the_port_it_serves(subida, tmp_path, capsys):
    webapp.main(["--data-dir", str(tmp_path)])
    assert subida["run"] == {"host": "127.0.0.1", "port": 5123, "debug": False}
    assert subida["browser"] == "http://127.0.0.1:5123"
    assert "http://127.0.0.1:5123" in capsys.readouterr().out


def test_main_without_browser(subida, tmp_path):
    webapp.main(["--data-dir", str(tmp_path), "--port", "5200", "--no-browser"])
    assert subida["run"]["port"] == 5200
    assert "browser" not in subida
