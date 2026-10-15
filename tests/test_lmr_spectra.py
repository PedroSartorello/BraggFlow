"""Espectros de espectrômetro UV-VIS-NIR (LMR): leitura, transmissão, tendência e evolução."""

from datetime import datetime

import numpy as np
import pytest

from braggflow.io.reader import (
    acquisition_time,
    classify_file,
    detect_text_format,
    load_spectra,
)
from braggflow.processing.spectra import (
    analyse_spectrum,
    apply_transmission,
    prepare_spectrum,
    remove_trend,
    resolve_spectrum_settings,
    spectra_evolution,
    to_transmission,
    transmission_unit,
)

from .lmr_synthetic import (
    DARK_COUNTS,
    WAVELENGTH,
    lmr_series,
    sample_counts,
    source_counts,
    transmission,
    write_oceanview,
)


# ── leitura ──────────────────────────────────────────────────────────────────

def test_oceanview_file_with_header(tmp_path):
    path = write_oceanview(tmp_path / "amostra_Transmission__01__09-30-15-250.txt",
                           transmission(870.0), datetime(2026, 3, 2, 9, 30, 15))
    fmt = detect_text_format(path)
    assert not fmt.has_header, "'>>>>>Begin Spectral Data<<<<<' não é nome de coluna"
    assert fmt.skiprows == 14, "a linha em branco do cabeçalho também conta"
    assert classify_file(path) == "spectrum"

    spectra = load_spectra(path)
    spectrum = spectra.spectra[0]
    assert spectrum.n_points == WAVELENGTH.size
    assert spectrum.wavelength[0] == pytest.approx(199.949)
    assert spectra.intensity_unit == "%"
    assert spectra.metadata["Spectrometer"] == "XXX0000"
    assert spectra.acquired == datetime(2026, 3, 2, 9, 30, 15, 250000)
    assert spectra.acquired_from == "header+filename"


def test_oceanview_file_without_header_takes_the_time_from_the_name(tmp_path):
    path = write_oceanview(tmp_path / "amostra_Transmission__02__09-30-30-880.txt",
                           transmission(870.0), header=False)
    assert classify_file(path) == "spectrum"
    spectra = load_spectra(path)
    assert spectra.spectra[0].n_points == WAVELENGTH.size
    assert spectra.metadata == {}
    assert spectra.acquired == datetime(1900, 1, 1, 9, 30, 30, 880000)
    assert spectra.acquired_from == "filename"


def test_header_date_without_time_in_the_name(tmp_path):
    path = write_oceanview(tmp_path / "amostra.txt", transmission(870.0),
                           datetime(2026, 3, 2, 9, 5, 0))
    spectra = load_spectra(path)
    assert spectra.acquired == datetime(2026, 3, 2, 9, 5, 0)
    assert spectra.acquired_from == "header"
    assert spectra.intensity_unit == "a.u.", "sem 'Transmission' no nome, unidade desconhecida"


def test_header_and_name_that_disagree_keep_the_header(tmp_path):
    path = write_oceanview(tmp_path / "lmr__10-00-00-123.txt", transmission(870.0),
                           datetime(2026, 3, 2, 9, 5, 0))
    assert load_spectra(path).acquired == datetime(2026, 3, 2, 9, 5, 0)


@pytest.mark.parametrize("nome, esperado", [
    ("x_09-30-15-250", datetime(1900, 1, 1, 9, 30, 15, 250000)),
    ("x_09-30-15", datetime(1900, 1, 1, 9, 30, 15)),
    ("ensaio_3", None),
    ("x_25-61-15-250", None),
])
def test_time_in_the_file_name(nome, esperado):
    assert acquisition_time(f"{nome}.txt")[0] == esperado


def test_iso_date_in_the_header():
    quando, origem = acquisition_time("a.txt", {"Date": "2026-03-02T09:30:15"})
    assert quando == datetime(2026, 3, 2, 9, 30, 15) and origem == "header"


def test_visible_spectrum_without_header_is_a_spectrum(tmp_path):
    wl = np.arange(400.0, 900.0, 0.5)
    path = tmp_path / "vis.txt"
    path.write_text("\n".join(f"{w:.2f}\t{np.sin(w / 30):.4f}" for w in wl), encoding="utf-8")
    assert classify_file(path) == "spectrum"


@pytest.mark.parametrize("inicio", [0.0, 300.0])
def test_headerless_interrogator_file_stays_a_time_series(tmp_path, inicio):
    """Tempo em passos regulares parece eixo de λ; as colunas de FBG desempatam."""
    t = inicio + np.arange(600) * 0.5
    path = tmp_path / "fbg.txt"
    path.write_text("\n".join(f"{x:.2f}\t{1550.0 + 0.001 * np.sin(x):.4f}\t{1545.0:.4f}" for x in t),
                    encoding="utf-8")
    assert classify_file(path) == "timeseries"


@pytest.mark.parametrize("header", [True, False])
def test_dark_and_source_spectra_are_spectra(tmp_path, header):
    """Um dark fica parado perto de 1.200 contagens: não é um canal de FBG."""
    dark = write_oceanview(tmp_path / "dark.txt", np.full(WAVELENGTH.size, DARK_COUNTS), header=header)
    fonte = write_oceanview(tmp_path / "fonte.txt", source_counts(), header=header)
    assert classify_file(dark) == "spectrum"
    assert classify_file(fonte) == "spectrum"


# ── tendência e transmissão ──────────────────────────────────────────────────

def test_remove_trend_takes_out_a_line_and_keeps_the_dip():
    wl = np.linspace(400, 900, 501)
    dip = -2.0 * np.exp(-((wl - 650) / 20) ** 2)
    y = 10 + 0.03 * wl + dip
    plano = remove_trend(wl, y, 1)
    assert abs(np.polyfit(wl, plano, 1)[0]) < 1e-3
    assert wl[np.argmin(plano)] == pytest.approx(650, abs=1)
    np.testing.assert_array_equal(remove_trend(wl, y, None), y)


def test_transmission_from_raw_sample_source_and_dark():
    t = transmission(780.0, noise=0.0)
    resultado = to_transmission(WAVELENGTH, sample_counts(t),
                                reference=(WAVELENGTH, source_counts()),
                                dark=(WAVELENGTH, np.full(WAVELENGTH.size, DARK_COUNTS)))
    np.testing.assert_allclose(resultado, t, rtol=1e-9)


def test_reference_on_another_grid_is_interpolated_and_weak_source_is_nan():
    wl = np.linspace(400, 900, 101)
    fonte = np.where(wl < 850, 1000.0, 1.0)                # fonte apagada acima de 850 nm
    t = to_transmission(wl, 0.5 * fonte, reference=(wl[::-1], fonte[::-1]), output="fraction")
    assert np.allclose(t[wl < 850], 0.5)
    assert np.isnan(t[wl >= 850]).all()

    fora = to_transmission(wl, np.ones_like(wl), reference=(wl[10:], np.ones(91)))
    assert np.isnan(fora[:10]).all(), "fora da faixa da fonte não há transmissão"


@pytest.mark.parametrize("saida, esperado", [
    ("percent", 50.0), ("fraction", 0.5), ("db", 10 * np.log10(0.5)), ("absorbance", -np.log10(0.5)),
])
def test_transmission_outputs(saida, esperado):
    wl = np.linspace(400, 900, 11)
    r = to_transmission(wl, np.full(11, 50.0), reference=(wl, np.full(11, 100.0)), output=saida)
    np.testing.assert_allclose(r, esperado)


def test_dark_only_subtracts_the_background():
    wl = np.linspace(400, 900, 11)
    r = to_transmission(wl, np.full(11, 1500.0), dark=(wl, np.full(11, 1200.0)))
    np.testing.assert_allclose(r, 300.0)


def test_without_source_or_dark_the_raw_spectrum_is_analysed_as_it_is():
    settings = resolve_spectrum_settings({})
    y = sample_counts(transmission(780.0))
    assert apply_transmission(WAVELENGTH, y, settings, lambda _: pytest.fail("não lê nada")) is y
    assert transmission_unit(settings, "counts") == "counts"
    assert transmission_unit(resolve_spectrum_settings({"reference_file": "data/raw/r.txt"})) == "%"


def test_valley_of_the_raw_spectrum_and_of_the_transmission():
    """O vale aparece nos dois; na transmissão, sem a curva da lâmpada por cima."""
    settings = resolve_spectrum_settings({"lambda_min": 450, "lambda_max": 950, "smooth_window": 21,
                                          "detrend": 2, "find_min": True, "prominence": 0.5})
    t = transmission(780.0)
    for y in (t, apply_transmission(
            WAVELENGTH, sample_counts(t), {**settings, "reference_file": "r", "dark_file": "d"},
            lambda caminho: (WAVELENGTH, source_counts() if caminho == "r"
                             else np.full(WAVELENGTH.size, DARK_COUNTS)))):
        wl, yp = prepare_spectrum(WAVELENGTH, y, settings)
        vales = analyse_spectrum(wl, yp, settings)["extrema"]
        principal = max(vales, key=lambda v: v["prominence"])
        assert principal["wavelength"] == pytest.approx(780.0, abs=1.5)


# ── evolução entre arquivos ──────────────────────────────────────────────────

SETTINGS = resolve_spectrum_settings({"lambda_min": 450, "lambda_max": 950, "smooth_window": 21,
                                      "detrend": 2, "find_min": True})


def _entries(caminhos):
    entradas = []
    for caminho in caminhos:
        spectra = load_spectra(caminho)
        wl, y = prepare_spectrum(spectra.spectra[0].wavelength, spectra.spectra[0].intensity, SETTINGS)
        entradas.append({"key": caminho.stem, "acquired": spectra.acquired,
                         "extrema": analyse_spectrum(wl, y, SETTINGS)["extrema"]})
    return entradas


def test_evolution_of_the_most_prominent_valley_in_time_order(tmp_path):
    caminhos = lmr_series(tmp_path, resonances=(870.0, 866.0, 862.0, 858.0))
    entradas = _entries(caminhos)[::-1]                    # fora de ordem de propósito
    ev = spectra_evolution(entradas, kind="min", mode="prominent")
    assert ev["x"] == "time"
    assert [f["key"] for f in ev["files"]] == [c.stem for c in caminhos]
    assert [f["elapsed_s"] for f in ev["files"]] == pytest.approx([0, 75.5, 151, 226.5])
    pontos = ev["tracks"][0]["points"]
    assert [p["wavelength"] for p in pontos] == pytest.approx([870, 866, 862, 858], abs=1.5)
    assert [p["delta"] for p in pontos] == pytest.approx([0, -4, -8, -12], abs=1.5)


def test_follow_mode_leaves_gaps_beyond_the_tolerance():
    def vale(lam, prom=1.0):
        return {"type": "min", "wavelength": lam, "intensity": -prom, "prominence": prom, "fwhm": 30.0}
    entradas = [
        {"key": "a", "acquired": None, "extrema": [vale(600), vale(800)]},
        {"key": "b", "acquired": None, "extrema": [vale(605), vale(803)]},
        {"key": "c", "acquired": None, "extrema": [vale(690)]},          # salto grande: sem par
        {"key": "d", "acquired": None, "extrema": [vale(611), vale(806)]},
    ]
    ev = spectra_evolution(entradas, kind="min", mode="follow")
    assert ev["x"] == "order" and ev["tolerance"] == pytest.approx(100.0)
    ev = spectra_evolution(entradas, kind="min", mode="follow", tolerance=20)
    primeiro, segundo = ev["tracks"]
    assert [p and p["wavelength"] for p in primeiro["points"]] == [600, 605, None, 611]
    assert [p and p["wavelength"] for p in segundo["points"]] == [800, 803, None, 806]
    assert segundo["points"][3]["delta"] == 6


def test_evolution_errors():
    with pytest.raises(ValueError, match="Nenhum"):
        spectra_evolution([])
    with pytest.raises(ValueError, match="primeiro arquivo"):
        spectra_evolution([{"key": "a", "acquired": None, "extrema": []}], mode="follow")
    with pytest.raises(ValueError, match="Modo"):
        spectra_evolution([{"key": "a", "acquired": None, "extrema": []}], mode="x")
