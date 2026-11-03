"""
Interface bilíngue: o dicionário da página (static/js/strings.js), as chaves
que o HTML e os módulos usam e as mensagens do servidor no idioma pedido.
"""

import json
import re
from pathlib import Path

import pytest

import braggflow.webapp
from braggflow import i18n
from braggflow.i18n import FIELD_LABELS_EN, MESSAGES, tr, use_language
from braggflow.processing.spectra import EVENT_SPEC, EVOLUTION_SPEC, SPECTRUM_SPEC
from braggflow.visualization.figure import CHANNEL_SPEC, STYLE_SPEC
from braggflow.webapp.app import create_app

WEBAPP = Path(braggflow.webapp.__file__).parent
JS = WEBAPP / "static" / "js"
HTML = (WEBAPP / "templates" / "index.html").read_text(encoding="utf-8")


def _strings() -> dict:
    texto = (JS / "strings.js").read_text(encoding="utf-8")
    return json.loads(texto[re.search(r"^export default", texto, re.M).end():].strip().rstrip(";"))


STRINGS = _strings()
PLACEHOLDER = re.compile(r"\{\w+(?::\d+)?\}")


def _formas(valor) -> list:
    return valor if isinstance(valor, list) else [valor]


def _marcas(valor) -> tuple:
    formas = _formas(valor)
    return (sorted({m for f in formas for m in PLACEHOLDER.findall(f)}),
            sorted(re.findall(r"</?\w+", " ".join(formas))))


# ── Dicionário da página ─────────────────────────────────────────────────────

def test_every_text_has_portuguese_and_english_with_the_same_placeholders():
    for chave, entrada in STRINGS.items():
        assert set(entrada) == {"pt", "en"}, chave
        for forma in _formas(entrada["pt"]) + _formas(entrada["en"]):
            assert isinstance(forma, str) and forma.strip(), chave
        assert _marcas(entrada["pt"]) == _marcas(entrada["en"]), chave


def test_plural_forms_have_two_entries():
    for chave, entrada in STRINGS.items():
        for forma in (entrada["pt"], entrada["en"]):
            if isinstance(forma, list):
                assert len(forma) == 2, chave


def test_every_key_in_the_page_has_a_text():
    chaves = re.findall(r'data-i18n(?:-[a-z-]+)?="([^"]+)"', HTML)
    assert chaves, "a página marca os textos com data-i18n"
    assert sorted(set(chaves) - set(STRINGS)) == []


def _js_keys() -> set:
    """Literais com cara de chave nos módulos (menos os caminhos data-style e afins)."""
    caminhos = set(re.findall(r'data-(?:style|opt|spec|evo)="([^"]+)"', HTML))
    prefixos = {chave.split(".")[0] for chave in STRINGS}
    usadas = set()
    for modulo in JS.glob("*.js"):
        if modulo.name == "strings.js":
            continue
        for literal in re.findall(r'"([a-z][A-Za-z]*\.[A-Za-z0-9.]+)"', modulo.read_text(encoding="utf-8")):
            if literal.split(".")[0] in prefixos and literal not in caminhos:
                usadas.add(literal)
    return usadas


def test_every_key_in_the_modules_has_a_text():
    assert sorted(_js_keys() - set(STRINGS)) == []


def test_every_text_is_used_somewhere():
    no_html = set(re.findall(r'data-i18n(?:-[a-z-]+)?="([^"]+)"', HTML))
    assert sorted(set(STRINGS) - no_html - _js_keys()) == []


def test_units_and_symbols_keep_their_case_in_english():
    """The Case Is Meaning Rule: λ, nm, Δλ, FWHM e K_T ficam como são."""
    for chave, entrada in STRINGS.items():
        for termo in ("λ", "Δλ", "FWHM", "K_T", "pm/°C"):
            if any(termo in forma for forma in _formas(entrada["pt"])):
                assert all(termo in forma for forma in _formas(entrada["en"])), (chave, termo)
        assert not re.search(r"\bNM\b|\bFwhm\b", " ".join(_formas(entrada["en"]))), chave


# ── Mensagens do servidor ────────────────────────────────────────────────────

def test_server_messages_have_both_languages_and_the_same_fields():
    campos = re.compile(r"\{(\w+)\}")
    for chave, entrada in MESSAGES.items():
        assert set(entrada) == {"pt", "en"}, chave
        assert sorted(campos.findall(entrada["pt"])) == sorted(campos.findall(entrada["en"])), chave


def test_every_option_label_has_an_english_name():
    rotulos = {campo[3] for spec in (SPECTRUM_SPEC, EVOLUTION_SPEC, EVENT_SPEC, CHANNEL_SPEC, *STYLE_SPEC.values())
               for campo in spec.values()}
    assert sorted(rotulos - set(FIELD_LABELS_EN)) == []


def test_portuguese_is_the_default_and_english_only_inside_the_block():
    assert i18n.language() == "pt"
    assert tr("recipe.noFile") == "Nenhum arquivo selecionado."
    with use_language("en-US"):
        assert tr("recipe.noFile") == "No file selected."
        assert i18n.num(2.5) == "2.5" and i18n.count(12996) == "12,996"
    assert i18n.num(2.5) == "2,5" and i18n.count(12996) == "12.996"
    with use_language("fr"):
        assert i18n.language() == "pt", "idioma que o BraggFlow não fala: português"


def test_option_errors_name_the_field_in_the_request_language():
    from braggflow.processing.spectra import resolve_spectrum_settings

    with pytest.raises(ValueError, match="Ordem da suavização: valor deve ser"):
        resolve_spectrum_settings({"smooth_order": "40"})
    with use_language("en"), pytest.raises(ValueError, match="Smoothing order: the value must be between 1 and 10"):
        resolve_spectrum_settings({"smooth_order": "40"})


# ── Web app: o idioma vem do cabeçalho que a página envia ────────────────────

@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / "data")
    app.config["TESTING"] = True
    raw = app.extensions["braggflow"].data.raw
    linhas = ["Time [s]\tCH_1 Sensor_1 [nm]"] + [f"{i / 50:.3f}\t{1550 + 0.001 * (i % 5):.6f}" for i in range(200)]
    (raw / "ensaio.ASC").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return app.test_client()


def test_errors_follow_the_accept_language_header(client):
    sem_arquivo = {"savgol": {"enabled": True}}
    assert client.post("/api/process", json=sem_arquivo).get_json()["error"] == "Requisição sem arquivo selecionado."
    resp = client.post("/api/process", json=sem_arquivo, headers={"Accept-Language": "en"})
    assert resp.get_json()["error"] == "The request has no file selected."
    resp = client.post("/api/process", json=sem_arquivo, headers={"Accept-Language": "fr, en-US;q=0.8"})
    assert resp.get_json()["error"] == "The request has no file selected.", "o primeiro idioma que o BraggFlow fala"


def test_recipe_and_report_follow_the_request_language(client):
    pedido = {"file": "data/raw/ensaio.ASC", "savgol": {"enabled": True, "window_length": "4"}}
    erro = client.post("/api/process", json=pedido, headers={"Accept-Language": "en"}).get_json()["error"]
    assert erro == "Savitzky-Golay: the window must be an odd number, 3 or more (got 4)."

    pedido = {"file": "data/raw/ensaio.ASC", "save": False,
              "timebase": {"enabled": True, "resample": True, "fs": "25"}}
    report = client.post("/api/process", json=pedido, headers={"Accept-Language": "en"}).get_json()["report"]
    assert "Resampled at 25 Hz (100 samples)" in report
    report = client.post("/api/process", json=pedido).get_json()["report"]
    assert "Reamostrado a 25 Hz (100 amostras)" in report


def test_the_language_does_not_outlive_the_request(client):
    client.post("/api/process", json={}, headers={"Accept-Language": "en"})
    assert i18n.language() == "pt"
    assert tr("recipe.noFile") == "Nenhum arquivo selecionado."


def test_track_names_follow_the_interface_and_legends_follow_the_figure(client, monkeypatch):
    import braggflow.webapp.app as modulo

    from .lmr_synthetic import lmr_series

    raw = client.application.extensions["braggflow"].data.raw
    caminhos = lmr_series(raw, resonances=(870.0, 866.0, 862.0))
    evolucao = {"items": [{"file": f"data/raw/{c.name}"} for c in caminhos],
                "settings": {"lambda_min": 450, "lambda_max": 950, "smooth_window": 21, "detrend": 2},
                "mode": "reference", "reference": "870.4", "window": "20"}
    ingles = {"Accept-Language": "en"}

    trilha = client.post("/api/spectra/evolution", json=evolucao, headers=ingles).get_json()["tracks"][0]
    assert trilha["name"] == "valley near 870.4 nm"
    assert trilha["key"] == "vale em λ ref", "a chave não muda com o idioma: o projeto a guarda"

    legendas = []
    original = modulo.render_curve_figure
    monkeypatch.setattr(modulo, "render_curve_figure",
                        lambda items, *a, **k: legendas.append([i["label"] for i in items]) or original(items, *a, **k))
    resp = client.post("/api/figure", headers=ingles,
                       json={"source": "evolution", "evolution": evolucao, "style": {"axes": {"language": "pt"}}})
    assert resp.status_code == 200, resp.get_json()
    assert legendas == [["vale perto de 870,4 nm"]], "a figura segue o idioma dela, não o da interface"


def test_unnamed_traces_keep_their_key_and_show_a_translated_name(client):
    raw = client.application.extensions["braggflow"].data.raw
    linhas = [f"{1500 + 0.5 * i:.1f}\t{1 - 0.5 * (abs(i - 100) < 5):.3f}" for i in range(200)]
    (raw / "sem_cabecalho.txt").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    pedido = {"file": "data/raw/sem_cabecalho.txt"}

    traco = client.post("/api/spectra/preview", json=pedido, headers={"Accept-Language": "en"}).get_json()["traces"][0]
    assert (traco["name"], traco["label"]) == ("Traço 1", "Trace 1"), "o nome é a chave; o rótulo, o que se mostra"
    traco = client.post("/api/spectra/preview", json=pedido).get_json()["traces"][0]
    assert traco["label"] == "Traço 1"
