"""Fluxos principais da interface, clicando como o usuário clica."""

import re

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

    expect(app.locator("#transmission-state")).to_have_text("não usada")
    app.locator("#card-transmission > summary").click()        # recolhido enquanto não é usado
    app.select_option('[data-spec="reference_file"]', "data/raw/bruto_fonte.txt")
    app.select_option('[data-spec="dark_file"]', "data/raw/bruto_fundo.txt")
    expect(app.locator("#transmission-state")).to_have_text("fonte e fundo")
    preparar_lmr(app)
    app.wait_for_function(f"{titulo} === 'Transmissão (%)'")
    principal = app.evaluate("""() => {
        const t = document.querySelector('#spectra-plot').data.find((d) => d.mode === 'markers');
        return t.x[t.y.indexOf(Math.min(...t.y))];
    }""")
    assert principal == pytest.approx(780.0, abs=1.5)


def test_evolution_belongs_to_the_open_project(lmr, app):
    """Trocar de projeto não pode deixar na tela a evolução do anterior."""
    def adicionar_espectros(nomes):
        app.click('#tabs .tab[data-tab="spectra"]')
        app.locator("#spectra-empty-files .empty-file", has_text=nomes[0]).click()
        expect(app.locator("#spectra-status")).to_contain_text("pontos")
        if nomes[1:]:
            app.locator("#tab-spectra-sidebar details.advanced > summary").click()
            for nome in nomes[1:]:
                app.check(f'.pick-spectrum[value="data/raw/{nome}"]')
            app.click("#btn-add-spectra")
        expect(app.locator("#spectra-files .file-name")).to_have_count(len(nomes))
        preparar_lmr(app)
        app.click("#btn-copy-spectrum")

    def arquivos_da_evolucao():
        return app.locator("#evolution-table tbody tr td:nth-child(1)").all_inner_texts()

    nomes_a = [c.name for c in lmr]
    novo_projeto(app, "A")
    adicionar_espectros(nomes_a)
    app.locator("#spectra-evolution > summary").click()
    expect(app.locator("#evolution-table tbody tr")).to_have_count(3)
    salvar_projeto(app)

    app.click("#btn-projects")
    novo_projeto(app, "B")
    app.click('#tabs .tab[data-tab="spectra"]')
    expect(app.locator("#evolution-table tbody tr")).to_have_count(0)
    assert curvas(app, "evolution-plot") == []

    # B com outros arquivos: a evolução mostra os de B, e só eles
    import shutil
    pasta = lmr[0].parent
    nomes_b = []
    for i, caminho in enumerate(lmr[:2]):
        destino = pasta / f"b{i}_{caminho.name}"
        shutil.copy(caminho, destino)
        nomes_b.append(destino.name)
    app.reload()
    novo_projeto(app, "B")
    adicionar_espectros(nomes_b)
    app.locator("#spectra-evolution > summary").click()          # a página recarregada fecha o cartão
    expect(app.locator("#evolution-table tbody tr")).to_have_count(2)
    assert arquivos_da_evolucao() == nomes_b
    salvar_projeto(app)

    # De volta ao A, com o cartão ainda aberto: recalcula com os arquivos de A
    app.click("#btn-projects")
    import re
    app.locator("#gate-projects .gate-row").filter(       # nome exato: "A" também está em "aberto"
        has=app.locator("strong", has_text=re.compile(r"^A$"))).click()
    expect(app.locator("#project-name")).to_have_value("A")
    app.click('#tabs .tab[data-tab="spectra"]')
    expect(app.locator("#evolution-table tbody tr")).to_have_count(3)
    assert arquivos_da_evolucao() == nomes_a


# ── disposição do gráfico e medição de trechos ───────────────────────────────

def layout_do_grafico(page: Page) -> dict:
    return page.evaluate(r"""() => {
        const gd = document.getElementById('plot');
        const ys = Object.keys(gd.layout).filter((k) => /^yaxis\d*$/.test(k)).sort();
        const efbg = gd.data.find((t) => t.name === 'EFBG1');
        return {
            grade: Boolean(gd.layout.grid), eixosY: ys.length,
            faixa: gd.layout.yaxis.range,
            primeiro: efbg.y.find((v) => v !== null),
            eixoDoEfbg2: gd.data.find((t) => t.name === 'EFBG2').yaxis || 'y',
        };
    }""")


def test_plot_shows_channels_apart_or_together(app):
    novo_projeto(app, "Vistas")
    adicionar_serie(app, "ensaio_a.asc")

    vista = layout_do_grafico(app)
    assert vista["grade"] and vista["eixosY"] == 3, "padrão: um painel por canal"
    assert vista["eixoDoEfbg2"] == "y2"
    assert vista["faixa"][1] - vista["faixa"][0] < 0.2, "escala pelo processado, não pelos picos do bruto"

    app.keyboard.press("2")                                  # mesmo gráfico
    expect(app.locator('input[name="plot-layout"][value="overlay"]')).to_be_checked()
    vista = layout_do_grafico(app)
    assert not vista["grade"] and vista["eixosY"] == 1 and vista["eixoDoEfbg2"] == "y"
    assert vista["primeiro"] == pytest.approx(1550.0, abs=0.01)

    app.check("#plot-relative")                              # só a exibição muda
    vista = layout_do_grafico(app)
    assert vista["primeiro"] == 0
    assert "Δλ" in app.evaluate("document.getElementById('plot').layout.yaxis.title.text")

    app.reload()                                             # a preferência fica
    expect(app.locator("#project-gate")).to_be_visible()
    novo_projeto(app, "Vistas 2")
    adicionar_serie(app, "ensaio_a.asc")
    expect(app.locator('input[name="plot-layout"][value="overlay"]')).to_be_checked()
    expect(app.locator("#plot-relative")).to_be_checked()


def arrastar_no_grafico(page: Page, de: float, ate: float) -> None:
    """Arrasta no 1º painel, de ``de`` a ``ate`` (frações da largura)."""
    caixa = page.locator("#plot .nsewdrag").first.bounding_box()
    y = caixa["y"] + caixa["height"] / 2
    page.mouse.move(caixa["x"] + caixa["width"] * de, y)
    page.mouse.down()
    page.mouse.move(caixa["x"] + caixa["width"] * ate, y, steps=8)
    page.mouse.up()


def test_dragging_measures_a_stretch_of_every_channel(app):
    novo_projeto(app, "Medir")
    adicionar_serie(app, "ensaio_a.asc")
    app.keyboard.press("m")
    expect(app.locator('input[name="plot-tool"][value="select"]')).to_be_checked()
    expect(app.locator("#plot-hint")).to_contain_text("medir trecho")

    arrastar_no_grafico(app, 1 / 3, 1 / 2)                   # ≈ 300–450 s
    linhas = app.locator("#selection-table tbody tr")
    expect(linhas).to_have_count(3)
    expect(app.locator("#selection-range")).to_contain_text("Δt")
    expect(app.locator("#selection-note")).to_contain_text("Sinal processado inteiro")
    assert linhas.nth(0).locator("td").first.inner_text() == "EFBG1"
    assert app.evaluate("document.getElementById('plot').layout.shapes[0].type") == "rect"

    # mudar o processamento mede de novo o mesmo trecho
    app.uncheck("#savgol-enabled")
    app.uncheck("#movavg-enabled")
    expect(app.locator("#status-text")).to_contain_text("amostras")
    expect(linhas).to_have_count(3)

    app.keyboard.press("Escape")
    expect(app.locator("#selection-panel")).to_be_hidden()
    assert not app.evaluate("(document.getElementById('plot').layout.shapes || []).some((s) => s.type === 'rect')")


def test_switching_file_clears_the_measured_stretch(app):
    novo_projeto(app, "Trocar")
    adicionar_serie(app, "ensaio_a.asc")
    app.keyboard.press("m")
    arrastar_no_grafico(app, 0.2, 0.4)
    expect(app.locator("#selection-table tbody tr")).to_have_count(3)

    app.locator("#tab-series-sidebar details.advanced > summary").first.click()
    app.check("#series-picker .pick-series[value='data/raw/ensaio_b.asc']")
    app.click("#btn-add-series")
    expect(app.locator("#series-files .file-name")).to_have_count(2)
    app.locator("#series-files .file-name", has_text="ensaio_a.asc").click()
    expect(app.locator("#status-text")).to_contain_text("amostras")
    expect(app.locator("#selection-panel")).to_be_hidden()


# ── marcações no gráfico e barra lateral na ordem do trabalho ────────────────

def ponto_no_tempo(page: Page, t: float, t_max: float = 900.0) -> tuple[float, float]:
    caixa = page.locator("#plot .nsewdrag").first.bounding_box()
    return caixa["x"] + caixa["width"] * t / t_max, caixa["y"] + caixa["height"] / 2


def instante_da_linha(page: Page) -> float:
    return page.evaluate("document.getElementById('plot').layout.shapes.find((s) => s.type === 'line').x0")


def test_markers_are_made_and_moved_with_the_mark_tool(app):
    novo_projeto(app, "Marcas")
    adicionar_serie(app, "ensaio_a.asc")
    expect(app.locator("#card-markers")).not_to_have_attribute("open", "")

    app.mouse.click(*ponto_no_tempo(app, 300))               # zoom: um clique não marca
    app.wait_for_timeout(500)
    expect(app.locator(".marker-row")).to_have_count(0)

    app.keyboard.press("a")
    expect(app.locator('input[name="plot-tool"][value="mark"]')).to_be_checked()
    app.mouse.click(*ponto_no_tempo(app, 300))
    expect(app.locator(".marker-row")).to_have_count(1)
    expect(app.locator("#card-markers")).to_have_attribute("open", "")
    expect(app.locator("#marker-count")).to_have_text("(1)")
    assert float(app.locator(".marker-time").input_value()) == pytest.approx(300, abs=3)
    app.locator(".marker-label").fill("troca")
    app.keyboard.press("Tab")

    x, y = ponto_no_tempo(app, instante_da_linha(app))      # arrastar a linha
    app.mouse.move(x, y)
    app.mouse.down()
    app.mouse.move(*ponto_no_tempo(app, 450), steps=10)
    app.mouse.up()
    expect(app.locator(".marker-row")).to_have_count(1)     # mover não cria outra
    assert float(app.locator(".marker-time").input_value()) == pytest.approx(450, abs=3)
    assert instante_da_linha(app) == pytest.approx(450, abs=3)

    app.locator(".marker-time").fill("600")                  # editar no painel move a linha
    app.keyboard.press("Tab")
    app.wait_for_function("document.getElementById('plot').layout.shapes.some((s) => s.x0 === 600)")
    expect(app.locator("#project-dirty")).to_be_visible()

    app.click("#btn-process")
    expect(app.locator("#status-text")).to_contain_text("CSV salvo")
    app.click('#tabs .tab[data-tab="viz"]')
    expect(app.locator("#viz-status")).to_contain_text("1 marcação(ões)")


def test_concatenation_card_appears_with_two_files(app):
    novo_projeto(app, "Lote")
    adicionar_serie(app, "ensaio_a.asc")
    expect(app.locator("#card-concat")).to_be_hidden()
    app.locator("#tab-series-sidebar details.advanced > summary").first.click()
    app.check("#series-picker .pick-series[value='data/raw/ensaio_b.asc']")
    app.click("#btn-add-series")
    expect(app.locator("#series-files .file-name")).to_have_count(2)
    expect(app.locator("#card-concat")).to_be_visible()


# ── aba Figura ───────────────────────────────────────────────────────────────

def abrir_figura(page: Page) -> None:
    adicionar_serie(page, "ensaio_a.asc")
    page.click("#btn-process")
    expect(page.locator("#status-text")).to_contain_text("CSV salvo")
    page.click('#tabs .tab[data-tab="viz"]')
    expect(page.locator("#viz-img")).to_be_visible()


def test_figure_tab_fits_summarizes_and_finds_options(app):
    novo_projeto(app, "Figura")
    abrir_figura(app)
    expect(app.locator('#tabs .tab[data-tab="viz"]')).to_have_text("Figura")

    app.select_option("#viz-preset", "ieee1")                 # figura alta, uma coluna
    expect(app.locator("#viz-status")).to_contain_text("8,89")
    caber = app.evaluate("""() => { const i = document.getElementById('viz-img').getBoundingClientRect(),
        a = document.getElementById('viz-figure').getBoundingClientRect();
        return i.height <= a.height && i.width <= a.width; }""")
    assert caber, "ajustar à tela mostra a figura inteira"

    expect(app.locator('[data-summary="figura"]')).to_contain_text("8,89 × auto cm")
    expect(app.locator('[data-summary="curvas"]')).to_contain_text("3 curvas")
    expect(app.locator('details[data-card="figura"]')).not_to_have_attribute("open", "")

    app.locator('[data-style="lines.width"]').fill("2.5")
    app.keyboard.press("Tab")
    expect(app.locator('[data-summary="curvas"]')).to_contain_text("1 alterada")
    expect(app.locator('[data-style="lines.width"]').locator("xpath=ancestor::label[1]")).to_have_class(re.compile("changed"))
    app.click('.card-reset[data-reset="curvas"]')
    expect(app.locator('[data-style="lines.width"]')).to_have_value("1.2")
    expect(app.locator('[data-summary="curvas"]')).not_to_contain_text("alterada")

    app.fill("#viz-search", "tick")                            # acha também a seção Ticks
    direcao = app.locator('[data-style="ticks.direction"]')
    expect(direcao).to_be_visible()
    expect(app.locator('[data-style="legend.position"]')).to_be_hidden()
    app.press("#viz-search", "Escape")
    expect(app.locator('[data-style="legend.position"]')).to_be_visible()
    expect(direcao).to_be_hidden()                             # o "Avançado" volta a fechar
    app.fill("#viz-search", "xyzw")
    expect(app.locator("#viz-search-empty")).to_be_visible()


def test_copy_figure_puts_a_png_on_the_clipboard(app):
    app.context.grant_permissions(["clipboard-read", "clipboard-write"])
    novo_projeto(app, "Copiar")
    abrir_figura(app)
    app.click("#btn-fig-copy")
    expect(app.locator("#viz-status")).to_contain_text("Figura copiada")
    tipos = app.evaluate("async () => (await navigator.clipboard.read()).flatMap((i) => i.types)")
    assert "image/png" in tipos


def test_interval_statistics_live_under_the_series_plot(app):
    novo_projeto(app, "Intervalos")
    adicionar_serie(app, "ensaio_a.asc")
    app.locator("#card-markers > summary").click()             # sem marcações, o painel começa fechado
    app.click("#btn-add-marker")
    app.locator(".marker-time").fill("300")
    app.keyboard.press("Tab")
    app.locator("#analysis-panel > summary").click()
    tabela = app.locator("#analysis-result table").first
    expect(tabela.locator("tbody tr")).to_have_count(6)       # 2 intervalos × 3 canais
    expect(app.locator("#analysis-result")).to_contain_text("Intervalos (nm)")

    app.click("#btn-add-marker")                               # nova marcação: recalcula
    app.locator(".marker-time").nth(1).fill("660")
    app.keyboard.press("Tab")
    expect(tabela.locator("tbody tr")).to_have_count(9)

    app.check("#plot-relative")
    expect(app.locator("#analysis-result")).to_contain_text("relativo ao início")

    app.click("#btn-projects")
    app.click("#leave-discard")
    novo_projeto(app, "Outro")
    expect(app.locator("#analysis-result table")).to_have_count(0)
