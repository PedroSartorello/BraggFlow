"""Fluxos principais da interface, clicando como o usuário clica."""

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


# ── ações ────────────────────────────────────────────────────────────────────

def novo_projeto(page: Page, nome: str) -> None:
    expect(page.locator("#project-gate")).to_be_visible()
    page.fill("#gate-name", nome)
    page.click("#btn-gate-new")
    expect(page.locator("#project-gate")).to_be_hidden()


def adicionar_serie(page: Page, arquivo: str) -> None:
    """Usa um arquivo já enviado; a página mostra a pré-visualização."""
    page.locator("#series-empty-files .empty-file", has_text=arquivo).click()
    expect(page.locator("#status-text")).to_contain_text("pré-visualização")


def salvar_projeto(page: Page) -> None:
    page.click("#btn-project-save")
    expect(page.locator("#status-text")).to_contain_text("salvo em data/projects")


def abrir_projeto(page: Page, nome: str) -> None:
    page.locator("#gate-projects .gate-row", has_text=nome).click()
    expect(page.locator("#project-gate")).to_be_hidden()
    # O nome muda depois de limpar o projeto anterior; só então o status
    # "amostras" é deste projeto, e não o que já estava na tela
    expect(page.locator("#project-name")).to_have_value(nome)
    expect(page.locator("#status-text")).to_contain_text("amostras")


def curvas(page: Page, plot: str = "plot") -> list[str]:
    return page.evaluate(f"(document.getElementById('{plot}').data || []).map(t => t.name)")


def arquivos_do_projeto(page: Page) -> list[str]:
    return page.locator("#series-files .file-name").all_inner_texts()


# ── testes ───────────────────────────────────────────────────────────────────

def test_choosing_a_file_shows_raw_and_processed_curves(app):
    novo_projeto(app, "E2E")
    adicionar_serie(app, "ensaio_a.asc")

    expect(app.locator("#status-text")).to_contain_text("EFBG1, EFBG2, FBG")
    nomes = curvas(app)
    assert {"EFBG1", "EFBG2", "FBG"} <= set(nomes)
    assert "EFBG1 (bruto)" in nomes
    assert arquivos_do_projeto(app) == ["ensaio_a.asc"]


def test_process_saves_the_csv_in_the_project_folder(app, data_dir):
    novo_projeto(app, "E2E")
    adicionar_serie(app, "ensaio_a.asc")
    app.click("#btn-process")

    expect(app.locator("#status-text")).to_contain_text("CSV salvo")
    csv = data_dir / "processed" / "E2E" / "ensaio_a_processado.csv"
    assert csv.is_file() and csv.with_suffix(".json").is_file()
    assert csv.read_text(encoding="utf-8").startswith("Time [s],EFBG1 [nm],EFBG2 [nm],FBG [nm]")


def test_saved_project_reopens_with_steps_and_sensors(app):
    novo_projeto(app, "Ensaio A")
    adicionar_serie(app, "ensaio_a.asc")
    app.uncheck("#movavg-enabled")
    sensor = app.locator('.sensor-row[data-channel="CH_1 Sensor_1 [nm]"] .sensor-name')
    sensor.fill("Sensor A")
    salvar_projeto(app)

    app.reload()                                 # salvo: recarregar não pergunta nada
    abrir_projeto(app, "Ensaio A")

    expect(app.locator("#project-name")).to_have_value("Ensaio A")
    expect(app.locator("#project-dirty")).to_be_hidden()
    expect(app.locator("#movavg-enabled")).not_to_be_checked()
    expect(app.locator("#savgol-enabled")).to_be_checked()
    expect(sensor).to_have_value("Sensor A")
    assert "Sensor A" in curvas(app)
    assert arquivos_do_projeto(app) == ["ensaio_a.asc"]


def test_switching_projects_does_not_mix_their_files(app):
    novo_projeto(app, "Projeto A")
    adicionar_serie(app, "ensaio_a.asc")
    salvar_projeto(app)

    app.click("#btn-projects")
    novo_projeto(app, "Projeto B")
    assert arquivos_do_projeto(app) == [], "projeto novo começa vazio"
    adicionar_serie(app, "ensaio_b.asc")
    salvar_projeto(app)

    app.click("#btn-projects")
    abrir_projeto(app, "Projeto A")
    assert arquivos_do_projeto(app) == ["ensaio_a.asc"]

    app.click("#btn-projects")
    abrir_projeto(app, "Projeto B")
    assert arquivos_do_projeto(app) == ["ensaio_b.asc"]


def test_unsaved_changes_ask_before_leaving_the_project(app):
    novo_projeto(app, "Rascunho")
    adicionar_serie(app, "ensaio_a.asc")
    expect(app.locator("#project-dirty")).to_be_visible()

    app.click("#btn-projects")
    expect(app.locator("#leave-dialog")).to_be_visible()
    app.click("#leave-cancel")                   # ficar: nada muda
    expect(app.locator("#leave-dialog")).to_be_hidden()
    expect(app.locator("#project-gate")).to_be_hidden()
    assert arquivos_do_projeto(app) == ["ensaio_a.asc"]

    app.click("#btn-projects")
    app.click("#leave-save")                     # salvar e seguir
    expect(app.locator("#project-gate")).to_be_visible()
    expect(app.locator("#gate-projects .gate-row", has_text="Rascunho")).to_be_visible()


def test_spectrum_peaks_are_detected(app):
    novo_projeto(app, "Espectros")
    app.click('#tabs .tab[data-tab="spectra"]')
    app.locator("#spectra-empty-files .empty-file", has_text="espectro.txt").click()
    expect(app.locator("#spectra-status")).not_to_contain_text("Adicione")
    app.check('[data-spec="find_max"]')

    expect(app.locator("#spectra-results")).to_be_visible()
    expect(app.locator("#spectra-summary")).to_contain_text("máx. global")
    expect(app.locator("#spectra-table tbody tr")).to_have_count(3)   # três redes
    assert curvas(app, "spectra-plot")


def test_figure_is_drawn_from_the_processed_csv(app):
    novo_projeto(app, "Figura")
    adicionar_serie(app, "ensaio_a.asc")
    app.click("#btn-process")
    expect(app.locator("#status-text")).to_contain_text("CSV salvo")

    app.click('#tabs .tab[data-tab="viz"]')
    expect(app.locator(".viz-series-source")).to_be_checked()
    expect(app.locator("#viz-img")).to_be_visible()
    assert app.locator("#viz-img").get_attribute("src").startswith("data:image/png;base64,")
    expect(app.locator("#viz-status")).to_contain_text("3 curva(s)")


def test_temperature_compensation_uses_the_thermal_sensitivity_of_each_fbg(app):
    novo_projeto(app, "Compensação")
    adicionar_serie(app, "ensaio_a.asc")
    app.uncheck("#auto-process")
    kt = {"CH_1 Sensor_1 [nm]": "20", "CH_2 Sensor_1 [nm]": "", "CH_3 Sensor_1 [nm]": "10"}
    for canal, valor in kt.items():
        app.locator(f'.sensor-row[data-channel="{canal}"] .sensor-kt').fill(valor)

    app.check("#tempcomp-enabled")
    expect(app.locator("#delta-enabled")).to_be_checked()      # compensação precisa do Δλ
    expect(app.locator("#tempcomp-k")).to_be_visible()           # ligar a etapa abre o cartão
    expect(app.locator("#tempcomp-channel")).to_have_value("FBG")
    app.fill("#tempcomp-k", "0.5")
    app.click("#btn-process")

    expect(app.locator("#status-text")).to_contain_text("CSV salvo")
    detalhes = app.locator("#status-details")
    expect(detalhes).to_contain_text("EFBG1 k = 2 (K_T 20 / 10 pm/°C)")
    expect(detalhes).to_contain_text("EFBG2 k = 0,5 (k informado)")

    salvar_projeto(app)
    app.reload()
    abrir_projeto(app, "Compensação")
    for canal, valor in kt.items():
        expect(app.locator(f'.sensor-row[data-channel="{canal}"] .sensor-kt')).to_have_value(valor)
    expect(app.locator("#tempcomp-enabled")).to_be_checked()

    app.uncheck("#delta-enabled")                               # sem Δλ, sem compensação
    expect(app.locator("#tempcomp-enabled")).not_to_be_checked()


# ── espectros LMR ────────────────────────────────────────────────────────────

@pytest.fixture
def lmr(data_dir):
    """Três transmissões com a ressonância andando e um trio bruto (amostra, fonte, fundo)."""
    import numpy as np

    from ..lmr_synthetic import (DARK_COUNTS, WAVELENGTH, lmr_series, sample_counts,
                                 source_counts, transmission, write_oceanview)
    series = lmr_series(data_dir / "raw", resonances=(870.0, 866.0, 862.0))
    write_oceanview(data_dir / "raw" / "bruto_amostra.txt", sample_counts(transmission(780.0)))
    write_oceanview(data_dir / "raw" / "bruto_fonte.txt", source_counts())
    write_oceanview(data_dir / "raw" / "bruto_fundo.txt", np.full(WAVELENGTH.size, DARK_COUNTS))
    return series


def preparar_lmr(page: Page) -> None:
    page.fill('[data-spec="lambda_min"]', "450")
    page.fill('[data-spec="lambda_max"]', "950")
    page.fill('[data-spec="smooth_window"]', "21")
    page.select_option('[data-spec="detrend"]', "2")
    page.check('[data-spec="find_min"]')


def test_lmr_valleys_follow_the_files_in_time_order(lmr, app):
    novo_projeto(app, "LMR")
    app.click('#tabs .tab[data-tab="spectra"]')
    app.locator("#spectra-empty-files .empty-file", has_text=lmr[0].name).click()
    expect(app.locator("#spectra-status")).to_contain_text("gravado 2026-03-02 09:30:15")
    app.locator("#tab-spectra-sidebar details.advanced > summary").click()
    for caminho in lmr[1:]:
        app.check(f'.pick-spectrum[value="data/raw/{caminho.name}"]')
    app.click("#btn-add-spectra")
    expect(app.locator("#spectra-files .file-name")).to_have_count(3)

    preparar_lmr(app)
    expect(app.locator("#spectra-results")).to_be_visible()
    app.click("#btn-copy-spectrum")
    app.locator("#spectra-evolution > summary").click()

    expect(app.locator("#evolution-status")).to_contain_text("3 espectro(s) · 1 trilha(s)")
    linhas = app.locator("#evolution-table tbody tr")
    expect(linhas).to_have_count(3)
    expect(linhas.nth(0)).to_contain_text("09:30:15")
    lams = [float(t.replace(",", ".")) for t in app.locator(
        "#evolution-table tbody tr td:nth-child(4)").all_inner_texts()]
    assert lams == pytest.approx([870, 866, 862], abs=1.5)
    assert curvas(app, "evolution-plot") == ["vale mais proeminente"]


def test_raw_spectrum_becomes_transmission_with_source_and_dark(lmr, app):
    novo_projeto(app, "Bruto")
    app.click('#tabs .tab[data-tab="spectra"]')
    app.locator("#spectra-empty-files .empty-file", has_text="bruto_amostra.txt").click()
    expect(app.locator("#spectra-status")).to_contain_text("pontos")
    titulo = "document.querySelector('#spectra-plot').layout.yaxis.title.text"
    assert app.evaluate(titulo) == "Intensidade", "sem fonte nem fundo: o espectro bruto"

    app.select_option('[data-spec="reference_file"]', "data/raw/bruto_fonte.txt")
    app.select_option('[data-spec="dark_file"]', "data/raw/bruto_fundo.txt")
    preparar_lmr(app)
    app.wait_for_function(f"{titulo} === 'Transmissão (%)'")
    principal = app.evaluate("""() => {
        const t = document.querySelector('#spectra-plot').data.find((d) => d.mode === 'markers');
        return t.x[t.y.indexOf(Math.min(...t.y))];
    }""")
    assert principal == pytest.approx(780.0, abs=1.5)
