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
