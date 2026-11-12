"""Fluxos principais da interface, clicando como o usuário clica."""

import re
import shutil

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


# As etapas que o projeto novo trazia ligadas até 0.1.0 (hoje começam desligadas)
ETAPAS_DO_EXEMPLO = ("cleaning", "timebase", "nulls", "outliers", "savgol", "movavg")


def ligar_etapas(page: Page, *etapas: str) -> None:
    """Liga as etapas (todas as do exemplo, sem argumento) e espera o processamento."""
    for etapa in etapas or ETAPAS_DO_EXEMPLO:
        page.check(f"#{etapa}-enabled")
    # "Gravar o CSV a cada mudança" vem ligado: o fim do processamento grava o CSV
    expect(page.locator("#status-text")).to_contain_text("CSV salvo")


def abrir_etapa(page: Page, etapa: str) -> None:
    """Mostra os parâmetros da etapa (ligar uma etapa já os mostra)."""
    corpo = page.locator(f'.step[data-step="{etapa}"] .step-body')
    if not corpo.is_visible():
        page.locator(f'.step[data-step="{etapa}"] .step-name').click()
    expect(corpo).to_be_visible()


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

    # Sem nomes inventados: cada sensor começa com o nome da coluna, sem a unidade
    expect(app.locator("#status-text")).to_contain_text("CH_1 Sensor_1, CH_2 Sensor_1, CH_3 Sensor_1")
    nomes = curvas(app)
    assert {"CH_1 Sensor_1", "CH_2 Sensor_1", "CH_3 Sensor_1"} <= set(nomes)
    assert "CH_1 Sensor_1 (bruto)" in nomes
    assert arquivos_do_projeto(app) == ["ensaio_a.asc"]
    # e nenhuma etapa vem ligada
    ligadas = app.evaluate("[...document.querySelectorAll('#tab-series-sidebar .step-switch')]"
                           ".filter((e) => e.checked).map((e) => e.id)")
    assert ligadas == []


def test_process_saves_the_csv_in_the_project_folder(app, data_dir):
    novo_projeto(app, "E2E")
    adicionar_serie(app, "ensaio_a.asc")
    app.click("#btn-process")

    expect(app.locator("#status-text")).to_contain_text("CSV salvo")
    csv = data_dir / "processed" / "E2E" / "ensaio_a_processado.csv"
    assert csv.is_file() and csv.with_suffix(".json").is_file()
    assert csv.read_text(encoding="utf-8").startswith("Time [s],CH_1 Sensor_1 [nm],CH_2 Sensor_1 [nm],CH_3 Sensor_1 [nm]")


def test_saved_project_reopens_with_steps_and_sensors(app):
    novo_projeto(app, "Ensaio A")
    adicionar_serie(app, "ensaio_a.asc")
    app.check("#movavg-enabled")
    sensor = app.locator('.sensor-row[data-channel="CH_1 Sensor_1 [nm]"] .sensor-name')
    sensor.fill("Sensor A")
    salvar_projeto(app)

    app.reload()                                 # salvo: recarregar não pergunta nada
    abrir_projeto(app, "Ensaio A")

    expect(app.locator("#project-name")).to_have_value("Ensaio A")
    expect(app.locator("#project-dirty")).to_be_hidden()
    expect(app.locator("#movavg-enabled")).to_be_checked()
    expect(app.locator("#savgol-enabled")).not_to_be_checked()
    expect(sensor).to_have_value("Sensor A")
    assert "Sensor A" in curvas(app)
    assert arquivos_do_projeto(app) == ["ensaio_a.asc"]


def test_a_new_project_does_not_inherit_the_steps_of_the_previous_one(app):
    novo_projeto(app, "Com etapas")
    adicionar_serie(app, "ensaio_a.asc")
    ligar_etapas(app, "savgol", "movavg")
    abrir_etapa(app, "movavg")
    app.fill("#movavg-window", "7")
    app.locator("#movavg-window").press("Tab")
    expect(app.locator("#save-state")).to_contain_text("salvo às")

    app.click("#btn-projects")
    novo_projeto(app, "Sem etapas")
    expect(app.locator("#savgol-enabled")).not_to_be_checked()
    expect(app.locator("#movavg-enabled")).not_to_be_checked()
    expect(app.locator("#movavg-window")).to_have_value("30")     # o valor que a página traz


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


def test_a_new_project_cannot_take_the_name_of_another(app):
    novo_projeto(app, "Ensaio A")
    adicionar_serie(app, "ensaio_a.asc")
    salvar_projeto(app)

    app.click("#btn-projects")
    expect(app.locator("#gate-projects .gate-row", has_text="Ensaio A")).to_be_visible()
    app.fill("#gate-name", "ensaio a")          # no Windows, o mesmo arquivo
    app.click("#btn-gate-new")
    expect(app.locator("#gate-error")).to_contain_text("Já existe o projeto Ensaio A")
    expect(app.locator("#project-gate")).to_be_visible()

    abrir_projeto(app, "Ensaio A")
    assert arquivos_do_projeto(app) == ["ensaio_a.asc"], "o projeto antigo continua inteiro"
    salvar_projeto(app)                          # e o projeto aberto segue salvando sobre si mesmo


def test_unsaved_changes_ask_before_leaving_the_project(app):
    novo_projeto(app, "Rascunho")
    app.uncheck("#autosave")                     # sem salvar sozinho, a pergunta volta
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


def test_savgol_window_and_order_are_chosen_from_the_data(app):
    novo_projeto(app, "Auto")
    adicionar_serie(app, "ensaio_a.asc")
    app.locator('.step[data-step="savgol"] .step-name').click()          # abre os parâmetros
    expect(app.locator("#savgol-window")).to_have_value("11")
    app.click("#btn-savgol-auto")
    expect(app.locator("#savgol-auto-note")).to_contain_text("Pelos dados: janela")
    janela = int(app.input_value("#savgol-window"))
    assert janela != 11 and janela % 2 == 1
    expect(app.locator("#savgol-auto-note")).to_contain_text(f"janela {janela:,}".replace(",", "."))
    expect(app.locator("#save-state")).to_contain_text("salvo às")     # mudou o projeto, como digitar


def test_spectrum_smoothing_window_is_chosen_from_the_data(app):
    novo_projeto(app, "Auto espectro")
    app.click('#tabs .tab[data-tab="spectra"]')
    app.locator("#spectra-empty-files .empty-file", has_text="espectro.txt").click()
    expect(app.locator("#spectra-status")).not_to_contain_text("Adicione")
    app.click("#btn-spec-smooth-auto")
    expect(app.locator("#spec-smooth-auto-note")).to_contain_text("Pelos dados: janela")
    assert int(app.input_value('[data-spec="smooth_window"]')) % 2 == 1


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


def test_a_file_in_a_folder_keeps_its_csv_apart_and_reaches_the_figure(app, data_dir):
    pasta = data_dir / "raw" / "dia1"
    pasta.mkdir()
    shutil.copy(data_dir / "raw" / "ensaio_a.asc", pasta / "ensaio_a.asc")   # mesmo nome do da raiz
    app.reload()
    novo_projeto(app, "Pastas")
    app.locator("#series-empty-files .empty-folder", has_text="dia1/").click()
    expect(app.locator("#status-text")).to_contain_text("pré-visualização")
    app.click("#btn-process")
    expect(app.locator("#status-text")).to_contain_text("CSV salvo")
    assert (data_dir / "processed" / "Pastas" / "raw__dia1__ensaio_a_processado.csv").is_file()

    app.click('#tabs .tab[data-tab="viz"]')
    fonte = app.locator(".viz-series-source")
    expect(fonte).to_have_count(1)
    expect(fonte).to_have_value("data/processed/Pastas/raw__dia1__ensaio_a_processado.csv")
    expect(fonte).to_be_checked()


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
    app.select_option("#tempcomp-channel", "CH_3 Sensor_1")
    app.fill("#tempcomp-k", "0.5")
    app.click("#btn-process")

    expect(app.locator("#status-text")).to_contain_text("CSV salvo")
    detalhes = app.locator("#status-details")
    expect(detalhes).to_contain_text("CH_1 Sensor_1 k = 2 (K_T 20 / 10 pm/°C)")
    expect(detalhes).to_contain_text("CH_2 Sensor_1 k = 0,5 (k informado)")

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


def lambdas_da_evolucao(page: Page) -> list[float]:
    textos = page.locator("#evolution-table tbody tr td:nth-child(4)").all_text_contents()
    return [float(t.replace(",", ".")) for t in textos]


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

    preparar_lmr(app)                          # o mesmo preparo vale para os três
    expect(app.locator("#spectra-results")).to_be_visible()
    expect(app.locator("#btn-copy-spectrum")).to_be_hidden()

    expect(app.locator("#evolution-status")).to_contain_text("3 espectro(s) · 1 trilha(s)")
    app.locator("#evolution-table-box > summary").click()
    linhas = app.locator("#evolution-table tbody tr")
    expect(linhas).to_have_count(3)
    expect(linhas.nth(0)).to_contain_text("09:30:15")
    assert lambdas_da_evolucao(app) == pytest.approx([870, 866, 862], abs=1.5)
    assert curvas(app, "evolution-plot")[0] == "vale mais proeminente"


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
        app.evaluate("document.getElementById('evolution-table-box').open = true")   # a tabela só existe aberta

    def arquivos_da_evolucao():
        return app.locator("#evolution-table tbody tr td:nth-child(1)").all_text_contents()

    nomes_a = [c.name for c in lmr]
    novo_projeto(app, "A")
    adicionar_espectros(nomes_a)
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
    expect(app.locator("#error-text")).to_be_empty()           # projeto só de espectros: nada faltando


@pytest.fixture
def pasta_lmr(data_dir):
    """Uma pasta de ensaio com três espectros: a ressonância anda e um 2º vale fica em 600 nm."""
    from ..lmr_synthetic import WAVELENGTH, lmr_series
    return lmr_series(data_dir / "raw" / "ensaio LMR", resonances=(870.0, 866.0, 862.0),
                      extra=2.5 / (1.0 + ((WAVELENGTH - 600.0) / 15.0) ** 2))


def clicar_no_espectro(page: Page, lam: float) -> None:
    """Clique no gráfico do espectro na altura de ``lam`` nm."""
    x, y = page.evaluate("""(lam) => {
        const gd = document.getElementById('spectra-plot');
        const xa = gd._fullLayout.xaxis, ya = gd._fullLayout.yaxis, r = gd.getBoundingClientRect();
        return [r.left + xa._offset + xa.l2p(lam), r.top + ya._offset + ya._length / 2];
    }""", lam)
    page.mouse.click(x, y)


def test_reference_wavelength_is_marked_on_the_spectrum_and_tracked(pasta_lmr, app):
    novo_projeto(app, "Referência")
    app.click('#tabs .tab[data-tab="spectra"]')
    app.locator("#spectra-empty-files .empty-folder", has_text="ensaio LMR").click()   # a pasta inteira
    expect(app.locator("#spectra-files .file-name")).to_have_count(3)
    expect(app.locator("#spectra-files-summary")).to_have_text("3 espectro(s)")
    preparar_lmr(app)
    expect(app.locator("#evolution-status")).to_contain_text("3 espectro(s)")
    app.locator("#evolution-table-box > summary").click()
    expect(app.locator("#evolution-table tbody tr")).to_have_count(3)
    assert lambdas_da_evolucao(app) == pytest.approx([870, 866, 862], abs=1)   # o mais proeminente

    app.click("#btn-evo-pick")
    expect(app.locator("#spectra-status")).to_contain_text("Clique no vale")
    clicar_no_espectro(app, 607)              # perto do vale: o clique vai para ele
    expect(app.locator("#evo-mode")).to_have_value("reference")
    assert float(app.input_value("#evo-ref")) == pytest.approx(600, abs=1)
    expect(app.locator("#evolution-state")).to_contain_text("vale perto de")
    app.wait_for_function("document.getElementById('evolution-status').textContent.includes('Δλ do 1º ao último 0')"
                          " || document.getElementById('evolution-status').textContent.includes('Δλ do 1º ao último -0')")
    assert lambdas_da_evolucao(app) == pytest.approx([600, 600, 600], abs=1)
    linha = "document.getElementById('spectra-plot').layout.shapes.filter((s) => s.type === 'line').length"
    assert app.evaluate(linha) == 1, "a linha do λ de referência fica no gráfico"

    salvar_projeto(app)
    app.reload()
    app.locator("#gate-projects .gate-row", has_text="Referência").click()
    app.click('#tabs .tab[data-tab="spectra"]')
    expect(app.locator("#evo-mode")).to_have_value("reference")
    expect(app.locator("#evolution-state")).to_contain_text("vale perto de")
    assert float(app.input_value("#evo-ref")) == pytest.approx(600, abs=1)
    expect(app.locator("#spectra-common")).to_be_checked()


def test_evolution_point_opens_its_spectrum_and_can_leave_the_evolution(pasta_lmr, app):
    novo_projeto(app, "Pontos")
    app.click('#tabs .tab[data-tab="spectra"]')
    app.locator("#spectra-empty-files .empty-folder").click()
    preparar_lmr(app)
    expect(app.locator("#evolution-status")).to_contain_text("3 espectro(s)")

    terceiro = pasta_lmr[2].name
    x, y = app.evaluate("""() => {
        const gd = document.getElementById('evolution-plot');
        const xa = gd._fullLayout.xaxis, ya = gd._fullLayout.yaxis;
        gd.scrollIntoView({block: 'center'});
        const r = gd.getBoundingClientRect();
        return [r.left + xa._offset + xa.l2p(gd.data[0].x[2]), r.top + ya._offset + ya.l2p(gd.data[0].y[2])];
    }""")
    app.mouse.click(x, y)
    expect(app.locator("#spectra-files .file-row.selected .file-name")).to_have_text(terceiro)
    expect(app.locator("#evolution-focus-text")).to_contain_text(terceiro)
    expect(app.locator("#evolution-focus-text")).to_contain_text("Δλ")

    app.click("#btn-evo-exclude")                       # tira da evolução, não do projeto
    expect(app.locator("#evolution-status")).to_contain_text("2 espectro(s)")
    expect(app.locator("#spectra-files .file-row.excluded")).to_have_count(1)
    expect(app.locator("#spectra-files-summary")).to_contain_text("1 fora da evolução")
    expect(app.locator("#btn-evo-exclude")).to_have_text("Devolver à evolução")
    app.click("#btn-evo-exclude")
    expect(app.locator("#evolution-status")).to_contain_text("3 espectro(s)")

    app.click("#btn-evo-prev")                           # ◀: o anterior, na ordem da evolução
    expect(app.locator("#spectra-files .file-row.selected .file-name")).to_have_text(pasta_lmr[1].name)


def test_evolution_becomes_a_figure(pasta_lmr, app):
    novo_projeto(app, "Figura da evolução")
    app.click('#tabs .tab[data-tab="spectra"]')
    app.locator("#spectra-empty-files .empty-folder").click()
    preparar_lmr(app)
    expect(app.locator("#evolution-status")).to_contain_text("3 espectro(s)")

    app.click("#btn-evolution-figure")
    expect(app.locator("#viz-source")).to_have_value("evolution")
    expect(app.locator("#viz-img")).to_be_visible()
    expect(app.locator("#viz-status")).to_contain_text("1 curva(s)")
    expect(app.locator(".viz-ch-row")).to_have_count(1)
    expect(app.locator("#viz-evo-y")).to_be_visible()
    expect(app.locator('[data-style="data.to_pm"]')).to_be_hidden()          # só para séries

    antes = app.get_attribute("#viz-img", "src")
    app.select_option("#viz-evo-y", "delta")                                # o mesmo eixo y da aba Espectros
    app.wait_for_function("(antes) => document.getElementById('viz-img').src !== antes", arg=antes)
    expect(app.locator("#evo-y")).to_have_value("delta")


def ponto_da_evolucao(page: Page, minutos: float) -> tuple[float, float]:
    """Pixel do gráfico da evolução no instante ``minutos`` (meia altura)."""
    return page.evaluate("""(t) => {
        const gd = document.getElementById('evolution-plot');
        gd.scrollIntoView({block: 'center'});
        const xa = gd._fullLayout.xaxis, ya = gd._fullLayout.yaxis, r = gd.getBoundingClientRect();
        return [r.left + xa._offset + xa.l2p(t), r.top + ya._offset + ya._length / 2];
    }""", minutos)


def eventos_no_grafico(page: Page) -> list:
    return page.evaluate("""() => {
        const l = document.getElementById('evolution-plot').layout;
        return (l.annotations || []).map((a, i) => [a.text, Math.round(l.shapes[i].x0 * 60)]);
    }""")


def test_events_are_marked_on_the_evolution_and_go_to_the_figure(pasta_lmr, app):
    novo_projeto(app, "Eventos")
    app.click('#tabs .tab[data-tab="spectra"]')
    app.locator("#spectra-empty-files .empty-folder").click()
    preparar_lmr(app)                                   # espectros às 09:30:15, 09:31:30,5 e 09:32:46
    expect(app.locator("#evolution-status")).to_contain_text("3 espectro(s)")

    app.click("#btn-evo-event")
    expect(app.locator("#btn-evo-event")).to_have_class(re.compile(r"\bon\b"))
    app.mouse.click(*ponto_da_evolucao(app, 0.8))       # 48 s depois do 1º
    expect(app.locator("#evolution-events .event-label")).to_be_focused()
    app.keyboard.type("Água")
    app.mouse.click(*ponto_da_evolucao(app, 2.0))       # o clique grava a legenda antes
    app.keyboard.type("Glicerina")
    app.keyboard.press("Enter")
    expect(app.locator("#evolution-events .event-row")).to_have_count(2)
    app.wait_for_function("document.getElementById('evolution-plot').layout.annotations?.[1]?.text === 'Glicerina'")
    eventos = eventos_no_grafico(app)
    assert [e[0] for e in eventos] == ["Água", "Glicerina"]
    assert [e[1] for e in eventos] == pytest.approx([48, 120], abs=3)
    hora = app.locator("#evolution-events .event-time").first.input_value()
    assert hora[:5] == "09:31", hora

    # Arrastar a linha da água para 0,3 min
    app.mouse.move(*ponto_da_evolucao(app, eventos[0][1] / 60))
    app.mouse.down()
    app.mouse.move(*ponto_da_evolucao(app, 0.3), steps=5)
    app.mouse.up()
    app.wait_for_function("Math.abs(document.getElementById('evolution-plot').layout.shapes[0].x0 - 0.3) < 0.05")

    app.locator("#evolution-table-box > summary").click()      # em que meio cada espectro foi gravado
    expect(app.locator("#evolution-table tbody tr td:last-child")).to_have_text(["—", "Água", "Glicerina"])

    app.keyboard.press("Escape")
    expect(app.locator("#btn-evo-event")).not_to_have_class(re.compile(r"\bon\b"))

    app.click("#btn-evolution-figure")
    expect(app.locator("#viz-status")).to_contain_text("2 evento(s)")
    expect(app.locator("#viz-evo-events .event-row")).to_have_count(2)
    antes = app.get_attribute("#viz-img", "src")
    app.locator("#viz-evo-events .event-label").first.fill("Água DI")
    app.locator("#viz-evo-events .event-label").first.press("Tab")
    app.wait_for_function("(antes) => document.getElementById('viz-img').src !== antes", arg=antes)
    expect(app.locator("#evolution-events .event-label").first).to_have_value("Água DI")

    salvar_projeto(app)
    app.reload()
    app.locator("#gate-projects .gate-row", has_text="Eventos").click()
    app.click('#tabs .tab[data-tab="spectra"]')
    expect(app.locator("#evolution-events .event-row")).to_have_count(2)
    expect(app.locator("#evolution-events .event-label").nth(1)).to_have_value("Glicerina")
    app.wait_for_function("""(document.getElementById('evolution-plot').layout?.shapes || [])
        .filter((s) => s.type === 'line').length === 2""")


def test_evolution_help_positions_and_the_spectrum_in_focus(pasta_lmr, app):
    """O "?" explica os campos, as técnicas novas de posição valem e o foco muda sem redesenhar a curva."""
    novo_projeto(app, "Ajuda")
    app.click('#tabs .tab[data-tab="spectra"]')
    app.locator("#spectra-empty-files .empty-folder").click()
    preparar_lmr(app)
    expect(app.locator("#evolution-status")).to_contain_text("3 espectro(s)")

    expect(app.locator("#evolution-help")).to_be_hidden()
    app.click("#btn-evolution-help")
    expect(app.locator("#evolution-help")).to_be_visible()
    expect(app.locator("#spectra-evolution")).to_have_attribute("open", "")      # o "?" não fecha o cartão
    for termo in ("Janela ± (nm)", "Salto máximo (nm)", "ajuste lorentziano", "centro da largura", "Eixo x"):
        expect(app.locator("#evolution-help dt", has_text=termo)).to_have_count(1)
    assert app.locator("#evolution-help dd").count() == app.locator("#evolution-help dt").count() >= 22
    app.click("#btn-evolution-help")
    expect(app.locator("#evolution-help")).to_be_hidden()

    # A tabela só é montada quando aberta
    expect(app.locator("#evolution-table-summary")).to_have_text("Tabela (3 linhas)")
    expect(app.locator("#evolution-table tbody tr")).to_have_count(0)
    app.locator("#evolution-table-box > summary").click()
    expect(app.locator("#evolution-table tbody tr")).to_have_count(3)
    ajuste = lambdas_da_evolucao(app)

    for tecnica in ("lorentzian", "gaussian", "midpoint"):
        with app.expect_response("**/api/spectra/evolution") as resposta:
            app.select_option("#evo-locate", tecnica)
        assert resposta.value.ok
        expect(app.locator("#evolution-table tbody tr")).to_have_count(3)
        app.wait_for_function("(v) => !document.querySelector('#evolution-table tbody td:nth-child(4)')"
                              ".textContent.startsWith(v)", arg=f"{ajuste[0]:.4f}".replace(".", ","))
        assert lambdas_da_evolucao(app) == pytest.approx([870, 866, 862], abs=1.5)
        assert lambdas_da_evolucao(app) != ajuste, tecnica

    # O espectro em foco é um anel no gráfico; passar para o seguinte move o anel, não refaz a curva
    def anel():
        return app.evaluate("""() => {
            const gd = document.getElementById('evolution-plot');
            const aneis = gd.layout.shapes.filter((s) => s.type === 'circle');
            return [gd.data.length, aneis.length, aneis[0]?.xanchor];
        }""")
    curvas_antes, aneis, x0 = anel()
    assert (curvas_antes, aneis) == (1, 1)
    app.evaluate("window.__curva = document.getElementById('evolution-plot').data[0]")
    app.click("#btn-evo-next")
    app.wait_for_function("(x) => document.getElementById('evolution-plot').layout.shapes"
                          ".find((s) => s.type === 'circle')?.xanchor > x", arg=x0)
    assert anel()[:2] == [1, 1]
    assert app.evaluate("window.__curva === document.getElementById('evolution-plot').data[0]")
    salvar_projeto(app)
    app.reload()
    app.locator("#gate-projects .gate-row", has_text="Ajuda").click()
    expect(app.locator("#evo-locate")).to_have_value("midpoint")


def test_a_folder_of_spectra_is_imported_at_once(data_dir, tmp_path, app):
    from ..lmr_synthetic import lmr_series
    pasta = tmp_path / "LMR 13-10"
    lmr_series(pasta, resonances=(870.0, 866.0, 862.0, 858.0))
    (pasta / "anotacoes.docx").write_bytes(b"x")         # fica de fora sem erro

    novo_projeto(app, "Pasta")
    app.click('#tabs .tab[data-tab="spectra"]')
    app.locator("#spectra-add > summary").click()
    app.set_input_files("#spectra-upload-dir", pasta)
    expect(app.locator("#spectra-files .file-name")).to_have_count(4)
    expect(app.locator("#spectra-status")).to_contain_text("1 arquivo(s) da pasta não são de dados")
    assert len(list((data_dir / "uploads" / "LMR 13-10").glob("*.txt"))) == 4
    expect(app.locator("#evolution-status")).to_contain_text("4 espectro(s)")


# ── disposição do gráfico e medição de trechos ───────────────────────────────

def layout_do_grafico(page: Page) -> dict:
    return page.evaluate(r"""() => {
        const gd = document.getElementById('plot');
        const ys = Object.keys(gd.layout).filter((k) => /^yaxis\d*$/.test(k)).sort();
        const efbg = gd.data.find((t) => t.name === 'CH_1 Sensor_1');
        return {
            grade: Boolean(gd.layout.grid), eixosY: ys.length,
            faixa: gd.layout.yaxis.range,
            primeiro: efbg.y.find((v) => v !== null),
            eixoDoEfbg2: gd.data.find((t) => t.name === 'CH_2 Sensor_1').yaxis || 'y',
        };
    }""")


def test_plot_shows_channels_apart_or_together(app):
    novo_projeto(app, "Vistas")
    adicionar_serie(app, "ensaio_a.asc")
    ligar_etapas(app)                       # a escala segue o processado, sem os picos do bruto

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
    assert linhas.nth(0).locator("td").first.inner_text() == "CH_1 Sensor_1"
    assert app.evaluate("document.getElementById('plot').layout.shapes[0].type") == "rect"

    # mudar o processamento mede de novo o mesmo trecho
    app.check("#savgol-enabled")
    app.check("#movavg-enabled")
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
    expect(app.locator("#save-state")).to_contain_text("salvo às")      # salvo sozinho

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


def test_joined_files_work_as_one_signal(app, data_dir):
    novo_projeto(app, "Junta")
    adicionar_serie(app, "ensaio_a.asc")
    app.locator("#tab-series-sidebar details.advanced > summary").first.click()
    app.check("#series-picker .pick-series[value='data/raw/ensaio_b.asc']")
    app.click("#btn-add-series")
    expect(app.locator("#series-files .file-name")).to_have_count(2)
    expect(app.locator("#status-text")).to_contain_text("9.001 amostras")

    app.locator("#card-concat > summary").click()                     # abrir junta os marcados
    expect(app.locator("#status-text")).to_contain_text("18.002 amostras")
    expect(app.locator("#status-text")).to_contain_text("2 arquivos juntos")
    app.click("#btn-process-join")
    expect(app.locator("#status-text")).to_contain_text("CSV salvo")
    assert (data_dir / "processed" / "Junta" / "ensaio_a_juntos_processado.csv").is_file()

    # Mudar o filtro reprocessa a junção, não só o primeiro arquivo
    app.locator('.step[data-step="savgol"] .step-name').click()
    with app.expect_response(lambda r: "/api/process" in r.url) as resposta:
        app.fill("#savgol-window", "31")
        app.locator("#savgol-window").press("Tab")
    assert resposta.value.request.post_data_json["files"] == ["data/raw/ensaio_a.asc", "data/raw/ensaio_b.asc"]
    expect(app.locator("#status-text")).to_contain_text("18.002 amostras")
    expect(app.locator("#save-state")).to_contain_text("salvo às")
    series = projeto_no_disco(data_dir, "Junta")["series"]
    assert [s["processing"]["savgol"]["window_length"] for s in series] == ["31", "31"], "um sinal: as mesmas etapas"

    app.locator("#card-concat > summary").click()                     # fechar volta a um arquivo
    expect(app.locator("#status-text")).to_contain_text("9.001 amostras")
    expect(app.locator("#status-text")).not_to_contain_text("juntos")


def test_processing_requests_run_one_at_a_time(app):
    novo_projeto(app, "Fila")
    adicionar_serie(app, "ensaio_a.asc")
    app.locator("#tab-series-sidebar details.advanced > summary").first.click()
    app.check("#series-picker .pick-series[value='data/raw/ensaio_b.asc']")
    app.click("#btn-add-series")
    expect(app.locator("#series-files .file-name")).to_have_count(2)
    expect(app.locator("#status-text")).to_contain_text("amostras")

    eventos = []
    app.on("request", lambda r: "/api/process" in r.url and eventos.append(("início", r.post_data_json["file"])))
    app.on("requestfinished", lambda r: "/api/process" in r.url and eventos.append(("fim", r.post_data_json["file"])))
    app.locator("#series-files .file-name", has_text="ensaio_a.asc").click()
    app.locator("#series-files .file-name", has_text="ensaio_b.asc").click()      # sem esperar o primeiro
    expect(app.locator("#status-text")).to_contain_text("amostras")
    app.wait_for_timeout(500)
    # Um de cada vez: cada pedido começa depois que o anterior terminou, e o último é o do arquivo b
    assert [tipo for tipo, _ in eventos] == ["início", "fim"] * (len(eventos) // 2), eventos
    assert eventos[-1] == ("fim", "data/raw/ensaio_b.asc"), eventos


# ── aba Figura ───────────────────────────────────────────────────────────────

def abrir_figura(page: Page) -> None:
    adicionar_serie(page, "ensaio_a.asc")
    page.click("#btn-process")
    expect(page.locator("#status-text")).to_contain_text("CSV salvo")
    page.click('#tabs .tab[data-tab="viz"]')
    expect(page.locator("#viz-img")).to_be_visible()


def test_markers_are_added_in_the_figure_tab_too(app, data_dir):
    novo_projeto(app, "Marcas na figura")
    abrir_figura(app)
    app.locator('#tab-viz-sidebar details[data-card="marcacoes"] > summary').click()
    expect(app.locator("#viz-marker-count")).to_contain_text("Nenhuma marcação: adicione aqui")
    app.click("#btn-add-marker")                         # o mesmo botão, agora no cartão da Figura
    linha = app.locator("#tab-viz-sidebar .marker-row")
    expect(linha).to_have_count(1)
    linha.locator(".marker-time").fill("300")
    linha.locator(".marker-label").fill("CO₂")
    linha.locator(".marker-label").press("Tab")
    expect(app.locator("#viz-status")).to_contain_text("1 marcação")
    expect(app.locator("#viz-marker-count")).to_contain_text("1 marcação(ões)")

    # A mesma marcação na aba Séries, no gráfico e no projeto salvo
    app.click('#tabs .tab[data-tab="series"]')
    expect(app.locator("#card-markers .marker-row")).to_have_count(1)
    expect(app.locator("#card-markers .marker-time")).to_have_value("300")
    assert app.evaluate("document.getElementById('plot').layout.shapes.some(s => s.x0 === 300)")
    expect(app.locator("#save-state")).to_contain_text("salvo às")
    assert [m["label"] for m in projeto_no_disco(data_dir, "Marcas na figura")["markers"]] == ["CO₂"]


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

    app.click("#btn-projects")                                  # salva sozinho e troca, sem perguntar
    novo_projeto(app, "Outro")
    expect(app.locator("#analysis-result table")).to_have_count(0)


# ── salvar sozinho e desfazer ────────────────────────────────────────────────

def projeto_no_disco(data_dir, nome: str) -> dict:
    import json
    caminho = data_dir / "projects" / f"{nome}.json"
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else {}


def test_project_saves_itself_and_switching_does_not_ask(app, data_dir):
    novo_projeto(app, "Sozinho")
    expect(app.locator("#autosave")).to_be_checked()
    adicionar_serie(app, "ensaio_a.asc")
    expect(app.locator("#save-state")).to_contain_text("salvo às")
    expect(app.locator("#project-dirty")).to_be_hidden()
    assert projeto_no_disco(data_dir, "Sozinho")["series"][0]["file"] == "data/raw/ensaio_a.asc"

    app.check("#movavg-enabled")
    expect(app.locator("#save-state")).to_contain_text("alterações")
    expect(app.locator("#save-state")).to_contain_text("salvo às")
    assert projeto_no_disco(data_dir, "Sozinho")["series"][0]["processing"]["moving_average"]["enabled"] is True

    app.click("#btn-projects")                                  # nada pendente: não pergunta
    expect(app.locator("#leave-dialog")).to_be_hidden()
    expect(app.locator("#project-gate")).to_be_visible()


def test_typing_a_new_name_saves_once_when_leaving_the_field(app, data_dir):
    novo_projeto(app, "Nome")
    adicionar_serie(app, "ensaio_a.asc")
    expect(app.locator("#save-state")).to_contain_text("salvo às")
    app.locator("#project-name").click()
    app.locator("#project-name").press("End")
    app.locator("#project-name").type(" final", delay=60)
    app.wait_for_timeout(2600)                                  # mais que o atraso do salvar sozinho
    assert not (data_dir / "projects" / "Nome f.json").exists(), "nenhuma cópia por letra"
    app.locator("#project-name").press("Enter")
    expect(app.locator("#status-text")).to_contain_text('Projeto "Nome final" salvo')
    nomes = sorted(p.stem for p in (data_dir / "projects").glob("*.json"))
    assert nomes == ["Nome", "Nome final"]


def test_undo_and_redo_walk_through_the_project_changes(app, data_dir):
    novo_projeto(app, "Desfazer")
    adicionar_serie(app, "ensaio_a.asc")
    expect(app.locator("#btn-undo")).to_be_enabled()
    expect(app.locator("#btn-redo")).to_be_disabled()

    app.check("#savgol-enabled")
    expect(app.locator("#status-text")).to_contain_text("amostras")
    app.wait_for_timeout(700)      # mudanças a menos de ~0,5 s viram um passo só (digitar um valor)
    app.locator("#card-markers > summary").click()
    app.click("#btn-add-marker")
    app.locator(".marker-time").fill("300")
    app.keyboard.press("Tab")
    expect(app.locator(".marker-row")).to_have_count(1)
    app.wait_for_timeout(700)                                   # a mudança entra no histórico

    app.locator("body").click(position={"x": 5, "y": 400})       # fora dos campos
    app.keyboard.press("Control+z")                             # tira a marcação
    expect(app.locator(".marker-row")).to_have_count(0)
    expect(app.locator("#savgol-enabled")).to_be_checked()
    app.click("#btn-undo")                                      # desliga de novo o Savitzky-Golay
    expect(app.locator("#savgol-enabled")).not_to_be_checked()
    expect(app.locator("#project-name")).to_have_value("Desfazer")

    app.keyboard.press("Control+Shift+z")                       # refaz
    expect(app.locator("#savgol-enabled")).to_be_checked()
    app.keyboard.press("Control+y")
    expect(app.locator(".marker-row")).to_have_count(1)
    expect(app.locator("#btn-redo")).to_be_disabled()
    expect(app.locator("#save-state")).to_contain_text("salvo às")
    assert len(projeto_no_disco(data_dir, "Desfazer")["markers"]) == 1

    # num campo de texto, Ctrl+Z é o do campo, não o do projeto
    app.locator(".marker-label").fill("evento")
    app.locator(".marker-label").press("Control+z")
    expect(app.locator(".marker-row")).to_have_count(1)


def test_undo_back_to_before_the_first_save_still_saves(app, data_dir):
    novo_projeto(app, "Desfazer cedo")
    adicionar_serie(app, "ensaio_a.asc")
    expect(app.locator("#save-state")).to_contain_text("salvo às")
    assert len(projeto_no_disco(data_dir, "Desfazer cedo")["series"]) == 1

    app.locator("body").click(position={"x": 5, "y": 400})       # fora dos campos
    app.keyboard.press("Control+z")                             # antes do arquivo: antes do 1º salvamento
    expect(app.locator("#series-files .file-name")).to_have_count(0)
    expect(app.locator("#save-state")).to_contain_text("alterações")
    expect(app.locator("#save-state")).to_contain_text("salvo às")
    assert projeto_no_disco(data_dir, "Desfazer cedo")["series"] == []


def test_deleting_the_open_project_does_not_bring_it_back(app, data_dir):
    novo_projeto(app, "Apagar")
    adicionar_serie(app, "ensaio_a.asc")
    expect(app.locator("#save-state")).to_contain_text("salvo às")
    app.click("#btn-projects")
    linha = app.locator("#gate-projects .gate-item", has_text="Apagar")
    linha.locator(".gate-delete").click()
    linha.locator(".gate-delete").click()
    expect(app.locator("#gate-projects .gate-item", has_text="Apagar")).to_have_count(0)
    app.wait_for_timeout(2600)
    assert not (data_dir / "projects" / "Apagar.json").exists()


# ── colunas ocultas ──────────────────────────────────────────────────────────

def test_hidden_column_disappears_from_the_program(app, data_dir):
    novo_projeto(app, "Ocultar")
    adicionar_serie(app, "ensaio_a.asc")
    linha = app.locator('.sensor-row[data-channel="CH_3 Sensor_1 [nm]"]')
    expect(app.locator("#hidden-sensors")).to_be_hidden()

    linha.locator(".sensor-hide").click()
    expect(app.locator("#hidden-sensors summary")).to_have_text("1 coluna oculta")
    expect(linha).to_be_hidden()                               # grupo recolhido
    app.wait_for_function("!document.getElementById('plot').data.some((t) => t.name.startsWith('CH_3'))")
    assert set(curvas(app)) == {"CH_1 Sensor_1", "CH_2 Sensor_1", "CH_1 Sensor_1 (bruto)", "CH_2 Sensor_1 (bruto)"}
    opcoes = app.locator("#tempcomp-channel option").all_inner_texts()
    assert "CH_3 Sensor_1" not in opcoes, "coluna oculta não serve de referência"
    expect(app.locator("#status-details")).to_contain_text("Colunas ocultas, fora do processamento: CH_3 Sensor_1")

    app.click("#btn-process")
    expect(app.locator("#status-text")).to_contain_text("CSV salvo")
    csv = data_dir / "processed" / "Ocultar" / "ensaio_a_processado.csv"
    assert csv.read_text(encoding="utf-8").splitlines()[0] == "Time [s],CH_1 Sensor_1 [nm],CH_2 Sensor_1 [nm]"
    app.click('#tabs .tab[data-tab="viz"]')
    expect(app.locator('[data-summary="curvas"]')).to_contain_text("2 curvas")

    app.click('#tabs .tab[data-tab="series"]')
    expect(app.locator("#save-state")).to_contain_text("salvo às")
    app.reload()                                               # o projeto lembra
    abrir_projeto(app, "Ocultar")
    expect(app.locator("#hidden-sensors summary")).to_have_text("1 coluna oculta")
    app.locator("#hidden-sensors summary").click()
    linha.locator(".sensor-hide").click()                      # mostrar de novo
    expect(app.locator("#hidden-sensors")).to_be_hidden()
    expect(linha.locator(".sensor-name")).to_be_visible()
    app.wait_for_function("document.getElementById('plot').data.some((t) => t.name === 'CH_3 Sensor_1')")


# ── erros perto do campo, teclado e leitores de tela ─────────────────────────

def test_an_invalid_field_is_marked_where_it_is_and_nothing_is_sent(app, server):
    novo_projeto(app, "Campos")
    adicionar_serie(app, "ensaio_a.asc")
    ligar_etapas(app, "savgol")                 # só a etapa ligada confere os seus campos
    pedidos = []
    app.on("request", lambda r: "/api/process" in r.url and pedidos.append(r.url))

    abrir_etapa(app, "savgol")
    app.fill("#savgol-window", "2")
    app.locator("#savgol-window").press("Tab")
    expect(app.locator("#savgol-window")).to_have_attribute("aria-invalid", "true")
    expect(app.locator('.field-error')).to_contain_text("ímpar a partir de 3")
    expect(app.locator("#status-text")).to_contain_text("Corrija o campo destacado: Janela (ímpar)")
    expect(app.locator("#plot")).to_have_class(re.compile(r"\bis-stale\b"))
    app.wait_for_timeout(700)                                  # o reprocessamento automático já teria ido
    assert pedidos == [], "um valor inválido não vai ao servidor"

    app.fill("#savgol-window", "21")                           # corrigiu: a mensagem sai na hora
    expect(app.locator(".field-error")).to_have_count(0)
    app.locator("#savgol-window").press("Tab")                 # e, ao sair do campo, processa
    expect(app.locator("#status-text")).to_contain_text("amostras")
    expect(app.locator("#plot")).not_to_have_class(re.compile(r"\bis-stale\b"))
    assert server.erros == []


def test_project_dialog_keeps_focus_and_tabs_answer_to_arrows(app):
    gate = app.locator("#project-gate")
    expect(gate).to_have_attribute("role", "dialog")
    expect(app.locator("#gate-name")).to_be_focused()          # sem projetos: o nome do novo
    for _ in range(6):                                         # Tab não sai do diálogo
        app.keyboard.press("Tab")
        assert app.evaluate("document.getElementById('project-gate').contains(document.activeElement)")
    novo_projeto(app, "Teclado")

    app.locator("#tabs .tab.active").focus()
    app.keyboard.press("ArrowRight")
    expect(app.locator("#tab-spectra")).to_have_attribute("aria-selected", "true")
    expect(app.locator("#tab-spectra-main")).to_be_visible()
    app.keyboard.press("ArrowRight")
    expect(app.locator("#tab-viz")).to_be_focused()
    expect(app.locator("#tab-series")).to_have_attribute("aria-selected", "false")


def test_symbols_and_units_keep_their_case(lmr, app):
    novo_projeto(app, "Símbolos")
    app.click('#tabs .tab[data-tab="spectra"]')
    app.locator("#spectra-empty-files .empty-file", has_text=lmr[0].name).click()
    preparar_lmr(app)
    expect(app.locator("#spectra-table th").first).to_be_attached()
    estilos = app.evaluate("""() => [...document.querySelectorAll('#spectra-table th, .section-label, .sub-label')]
        .map((el) => getComputedStyle(el).textTransform)""")
    assert set(estilos) == {"none"}, "λ, nm e σ não podem virar Λ, NM e Σ"
    assert "λ (nm)" in app.locator("#spectra-table th").all_inner_texts()
    rotulo = app.locator('.step[data-step="savgol"] .step-switch')
    expect(rotulo).to_have_attribute("aria-labelledby", re.compile(r"step-name-"))



# ── idioma da interface ──────────────────────────────────────────────────────

def textos_em_portugues(page: Page) -> list[str]:
    """
    Textos à vista e atributos (title, placeholder, aria-label) com acento do
    português: na interface em inglês, o que sobrou sem tradução. O seletor de
    idioma fica de fora (cada idioma é escrito nele mesmo).
    """
    return page.evaluate(r"""() => {
      const acento = /[ãõçáéíóúâêôàÃÕÇÁÉÍÓÚÂÊÔÀ]/;
      const fora = (el) => el.closest(".lang-switch, script, style, .icon-sprite");
      const achados = [];
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      for (let n = walker.nextNode(); n; n = walker.nextNode()) {
        const el = n.parentElement;
        if (!el || fora(el) || !acento.test(n.textContent)) continue;
        if (!(el.closest("select") || el).checkVisibility()) continue;
        achados.push(n.textContent.trim());
      }
      document.querySelectorAll("[title], [placeholder], [aria-label]").forEach((el) => {
        if (fora(el)) return;
        ["title", "placeholder", "aria-label"].forEach((attr) => {
          const valor = el.getAttribute(attr);
          if (valor && acento.test(valor)) achados.push(`${attr}: ${valor}`);
        });
      });
      return achados;
    }""")


def test_switching_to_english_translates_the_page_and_survives_a_reload(app):
    novo_projeto(app, "Idioma")
    adicionar_serie(app, "ensaio_a.asc")
    ligar_etapas(app)                           # o relatório da limpeza vem do servidor
    app.click("#btn-process")
    expect(app.locator("#status-text")).to_contain_text("CSV salvo")

    app.locator('#project-bar .lang-switch label[lang="en"]').click()
    expect(app.locator("html")).to_have_attribute("lang", "en")

    # cabeçalho
    expect(app.locator("#tab-series")).to_have_text("Time series")
    expect(app.locator("#tab-spectra")).to_have_text("Spectra")
    expect(app.locator("#btn-projects")).to_have_text("Projects")
    expect(app.locator("#btn-undo")).to_have_attribute("aria-label", "Undo")

    # a leitura do status é montada de novo no idioma (e os números com ele)
    expect(app.locator("#status-text")).to_contain_text("CSV saved")
    expect(app.locator("#status-text")).to_contain_text("samples")
    expect(app.locator("#status-details")).to_contain_text("Cleaning:")     # relatório do servidor

    # o servidor responde no idioma da página
    with app.expect_request(lambda r: r.url.endswith("/api/process")) as pedido:
        app.click("#btn-process")
    assert pedido.value.headers["accept-language"] == "en"
    expect(app.locator("#status-text")).to_contain_text("CSV saved")

    # erro de campo
    abrir_etapa(app, "savgol")
    app.fill("#savgol-window", "4")
    app.click("#btn-process")
    expect(app.locator(".field-error")).to_have_text("Use an odd number, 3 or more.")
    expect(app.locator("#status-text")).to_have_text("Fix the highlighted field: Window (odd).")
    expect(app.locator("#plot")).to_have_attribute("data-stale", "Out of date: fix the highlighted field in the sidebar")
    app.fill("#savgol-window", "11")
    expect(app.locator(".field-error")).to_have_count(0)
    app.click("#btn-process")
    expect(app.locator("#status-text")).to_contain_text("CSV saved")
    assert textos_em_portugues(app) == []

    app.click('#tabs .tab[data-tab="spectra"]')
    app.locator("#spectra-empty-files .empty-file", has_text="espectro.txt").click()
    app.check('[data-spec="find_max"]')
    expect(app.locator("#spectra-summary")).to_contain_text("global max")
    expect(app.locator("#spectra-status")).to_contain_text("points")
    expect(app.locator("#evolution-status")).to_have_text("Add more spectra to the project: the evolution needs "
                                                          "two or more (source, dark and the ones taken out do not count).")
    assert textos_em_portugues(app) == []

    app.click('#tabs .tab[data-tab="viz"]')
    expect(app.locator("#viz-img")).to_be_visible()
    expect(app.locator("#viz-status")).to_contain_text("3 curves")
    assert textos_em_portugues(app) == []

    # a escolha fica no navegador
    app.reload()
    expect(app.locator("html")).to_have_attribute("lang", "en")
    expect(app.locator('input[name="ui-language"][value="en"]')).to_be_checked()
    expect(app.locator('input[name="ui-language-gate"][value="en"]')).to_be_checked()
    expect(app.locator("#project-gate small")).to_have_text("Choose a project to continue, or start a new one")
    expect(app.locator("#tab-series")).to_have_text("Time series")
    projeto = app.locator("#gate-projects .gate-row", has_text="Idioma")
    expect(projeto).to_contain_text("1 series · 1 spectrum · 0 markers")
    assert textos_em_portugues(app) == []

    projeto.click()
    expect(app.locator("#status-text")).to_contain_text("samples")


def test_back_to_portuguese_restores_every_text(app):
    """O português do dicionário é o mesmo da página: ir e voltar não muda nada."""
    novo_projeto(app, "Volta")
    antes = app.evaluate("document.body.innerText")
    app.locator('#project-bar .lang-switch label[lang="en"]').click()
    expect(app.locator("#tab-series")).to_have_text("Time series")
    app.locator('#project-bar .lang-switch label[lang="pt-BR"]').click()
    expect(app.locator("html")).to_have_attribute("lang", "pt-BR")
    expect(app.locator("#tab-series")).to_have_text("Séries temporais")
    assert app.evaluate("document.body.innerText") == antes


def test_statistics_evolution_and_events_in_english(pasta_lmr, app):
    novo_projeto(app, "Language")
    adicionar_serie(app, "ensaio_a.asc")
    app.locator("#card-markers > summary").click()
    app.click("#btn-add-marker")
    app.locator(".marker-time").fill("300")
    app.keyboard.press("Tab")
    app.locator("#analysis-panel > summary").click()
    expect(app.locator("#analysis-result")).to_contain_text("marcação 1")
    app.keyboard.press("m")
    arrastar_no_grafico(app, 1 / 3, 1 / 2)
    expect(app.locator("#selection-note")).to_contain_text("Sinal processado inteiro")

    app.locator('#project-bar .lang-switch label[lang="en"]').click()
    expect(app.locator("#analysis-result")).to_contain_text("Intervals (nm)")
    expect(app.locator("#analysis-result")).to_contain_text("marker 1")      # rótulo do servidor, pedido de novo
    expect(app.locator("#selection-note")).to_contain_text("Whole processed signal")
    expect(app.locator("#selection-table th").first).to_have_text("Channel")
    expect(app.locator("#plot-hint")).to_have_text("drag = measure stretch · Esc clears")
    assert curvas(app)[0] == "CH_1 Sensor_1 (raw)"
    assert textos_em_portugues(app) == []

    app.click('#tabs .tab[data-tab="spectra"]')
    app.locator("#spectra-empty-files .empty-folder").click()
    preparar_lmr(app)
    expect(app.locator("#evolution-status")).to_contain_text("3 spectra · 1 track")
    expect(app.locator("#spectra-files-summary")).to_have_text("3 spectra")
    assert curvas(app, "evolution-plot")[0] == "most prominent valley"
    app.click("#btn-evo-event")
    expect(app.locator("#evolution-events-hint")).to_contain_text("Click the plot to mark an event")
    app.mouse.click(*ponto_da_evolucao(app, 0.8))
    expect(app.locator("#evolution-events .event-label")).to_be_focused()
    app.keyboard.type("Water")
    app.keyboard.press("Enter")
    app.keyboard.press("Escape")
    app.locator("#evolution-table-box > summary").click()
    expect(app.locator("#evolution-table-summary")).to_have_text("Table (3 rows)")
    expect(app.locator("#evolution-table th").last).to_have_text("Event")
    assert textos_em_portugues(app) == []

    app.click("#btn-evolution-figure")
    expect(app.locator("#viz-status")).to_contain_text("1 curve · 1 event")
    expect(app.locator('#tab-viz-sidebar [data-summary="dados"]')).to_have_text("evolution · y = λ · x in s · 1 event")
    assert textos_em_portugues(app) == []


def test_language_can_be_chosen_before_opening_a_project(app):
    """O diálogo de projetos cobre o cabeçalho ao abrir a página: ele tem o seu seletor."""
    app.locator('#project-gate .lang-switch label[lang="en"]').click()
    expect(app.locator("#btn-gate-new")).to_have_text("New project")
    expect(app.locator("#gate-name")).to_have_attribute("placeholder", "name of the new project")
    expect(app.locator('input[name="ui-language"][value="en"]')).to_be_checked()
    novo_projeto(app, "Gate")
    expect(app.locator("#status-text")).to_have_text('Project "Gate": add the time-series files.')
