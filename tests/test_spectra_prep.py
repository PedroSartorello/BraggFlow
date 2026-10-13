import numpy as np
import pytest

from braggflow.processing.spectra import (
    analyse_spectrum,
    default_spectrum_settings,
    prepare_spectrum,
    resolve_spectrum_settings,
)


@pytest.fixture
def spectrum():
    wavelength = np.linspace(1510, 1590, 2000)
    rng = np.random.default_rng(0)
    intensity = 10 * np.sin(wavelength * 2) + 60 + rng.normal(0, 1.0, len(wavelength))
    return wavelength, intensity


def test_defaults_do_not_change_the_spectrum(spectrum):
    wavelength, intensity = spectrum
    out_w, out_i = prepare_spectrum(wavelength, intensity, default_spectrum_settings())
    np.testing.assert_array_equal(out_w, wavelength)
    np.testing.assert_array_equal(out_i, intensity)


def test_wavelength_window_trims_both_ends(spectrum):
    wavelength, intensity = spectrum
    settings = resolve_spectrum_settings({"lambda_min": "1520", "lambda_max": 1530})
    out_w, out_i = prepare_spectrum(wavelength, intensity, settings)
    assert out_w.min() >= 1520 and out_w.max() <= 1530
    assert len(out_w) == len(out_i) < len(wavelength)


def test_window_without_points_is_rejected(spectrum):
    wavelength, intensity = spectrum
    with pytest.raises(ValueError, match="pontos suficientes"):
        prepare_spectrum(wavelength, intensity, resolve_spectrum_settings(
            {"lambda_min": 1600, "lambda_max": 1700}))


def test_inverted_window_is_rejected(spectrum):
    wavelength, intensity = spectrum
    with pytest.raises(ValueError, match="λ mínimo"):
        prepare_spectrum(wavelength, intensity, resolve_spectrum_settings(
            {"lambda_min": 1550, "lambda_max": 1520}))


def test_even_smoothing_window_is_made_odd(spectrum):
    wavelength, intensity = spectrum
    clean = 10 * np.sin(wavelength * 2) + 60
    _, smoothed = prepare_spectrum(wavelength, intensity, resolve_spectrum_settings(
        {"smooth_window": 40}))
    assert np.std(smoothed - clean) < np.std(intensity - clean) / 2


@pytest.mark.parametrize("mode, check", [
    ("max", lambda y: np.isclose(np.max(np.abs(y)), 1.0)),
    ("minmax", lambda y: np.isclose(y.min(), 0.0) and np.isclose(y.max(), 1.0)),
    ("baseline", lambda y: abs(np.median(y)) < 1e-9),
])
def test_normalizations(spectrum, mode, check):
    wavelength, intensity = spectrum
    _, out = prepare_spectrum(wavelength, intensity, resolve_spectrum_settings({"normalize": mode}))
    assert check(out)


def test_offset_shifts_the_curve(spectrum):
    wavelength, intensity = spectrum
    _, out = prepare_spectrum(wavelength, intensity, resolve_spectrum_settings({"offset": "2,5"}))
    np.testing.assert_allclose(out, intensity + 2.5)


def test_invalid_setting_names_the_field():
    with pytest.raises(ValueError, match="Normalização"):
        resolve_spectrum_settings({"normalize": "nada"})
    with pytest.raises(ValueError, match="Suavização"):
        resolve_spectrum_settings({"smooth_window": "1"})


# ── média móvel ───────────────────────────────────────────────────────────────

def test_moving_average_smooths_without_shifting_the_peak():
    wl = np.arange(1545, 1555, 0.01)
    rng = np.random.default_rng(1)
    limpo = np.exp(-0.5 * ((wl - 1550.0) / 0.3) ** 2)
    ruidoso = limpo + rng.normal(0, 0.05, len(wl))
    _, suave = prepare_spectrum(wl, ruidoso, {"smooth_method": "moving_average", "smooth_window": 9})
    assert np.std(suave - limpo) < 0.5 * np.std(ruidoso - limpo)
    # Sem ruído, a média centrada mantém o pico exatamente no lugar
    _, sem_ruido = prepare_spectrum(wl, limpo, {"smooth_method": "moving_average", "smooth_window": 9})
    assert wl[np.argmax(sem_ruido)] == pytest.approx(1550.0, abs=1e-9)


def test_old_settings_keep_savitzky_golay():
    assert resolve_spectrum_settings({"smooth_window": 11})["smooth_method"] == "savgol"


def test_smoothing_methods_differ_and_unknown_is_rejected(spectrum):
    wl, y = spectrum
    _, sg = prepare_spectrum(wl, y, {"smooth_method": "savgol", "smooth_window": 21})
    _, ma = prepare_spectrum(wl, y, {"smooth_method": "moving_average", "smooth_window": 21})
    assert not np.allclose(sg, ma)
    with pytest.raises(ValueError, match="Tipo de suavização"):
        resolve_spectrum_settings({"smooth_method": "mediana"})


# ── picos e vales ─────────────────────────────────────────────────────────────

GRADE = np.arange(1545, 1555, 0.01)
SIGMA_FWHM = 2 * np.sqrt(2 * np.log(2))


def _gauss(centro, fwhm, altura=1.0):
    return altura * np.exp(-0.5 * ((GRADE - centro) / (fwhm / SIGMA_FWHM)) ** 2)


def _analise(y, **settings):
    return analyse_spectrum(GRADE, y, resolve_spectrum_settings(settings))


def test_peak_position_is_refined_below_the_grid_step_and_fwhm_is_measured():
    [pico] = _analise(_gauss(1550.1234, 0.2), find_max=True)["extrema"]
    assert pico["type"] == "max"
    assert pico["wavelength"] == pytest.approx(1550.1234, abs=1e-4), "melhor que o passo de 10 pm"
    assert pico["fwhm"] == pytest.approx(0.2, rel=0.01)
    assert pico["q"] == pytest.approx(1550.1234 / 0.2, rel=0.01)
    assert pico["centroid"] == pytest.approx(1550.1234, abs=1e-3)
    assert pico["prominence"] == pytest.approx(1.0, rel=0.01)
    assert pico["level"] == pytest.approx(0.5, rel=0.01), "nível desenhado = meia altura"


def test_dip_in_db_uses_the_3db_band():
    profundidade, sigma = 20.0, 0.1
    y = -profundidade * np.exp(-0.5 * ((GRADE - 1549.5) / sigma) ** 2)
    [vale] = _analise(y, find_min=True, intensity_scale="db")["extrema"]
    esperado = 2 * sigma * np.sqrt(2 * np.log(profundidade / (profundidade - 3)))
    assert vale["type"] == "min"
    assert vale["intensity"] == pytest.approx(-20.0, abs=0.01)
    assert vale["prominence"] == pytest.approx(20.0, abs=0.01), "profundidade do vale"
    assert vale["fwhm"] == pytest.approx(esperado, rel=0.01)
    assert vale["level"] == pytest.approx(-17.0, abs=0.01), "3 dB acima do fundo"


def test_shallow_dip_in_db_has_no_3db_band():
    y = -2.0 * np.exp(-0.5 * ((GRADE - 1549.5) / 0.1) ** 2)
    [vale] = _analise(y, find_min=True, intensity_scale="db", prominence=1)["extrema"]
    assert vale["fwhm"] is None and vale["q"] is None


def test_side_lobe_suppression_spacing_and_fsr():
    y = _gauss(1548, 0.1, 1.0) + _gauss(1550, 0.1, 0.4) + _gauss(1552, 0.1, 0.2)
    resultado = _analise(y, find_max=True)
    picos = resultado["extrema"]
    assert [round(p["wavelength"], 2) for p in picos] == [1548.0, 1550.0, 1552.0]
    assert picos[0]["spacing"] is None
    assert picos[1]["spacing"] == pytest.approx(2.0, abs=1e-3)
    assert resultado["summary"]["side_lobe_suppression"] == pytest.approx(0.6, abs=0.01)
    assert resultado["summary"]["fsr_max"] == pytest.approx(2.0, abs=1e-3)
    assert resultado["summary"]["n_max"] == 3 and resultado["summary"]["n_min"] == 0


def test_max_peaks_keeps_the_most_prominent_in_wavelength_order():
    y = _gauss(1548, 0.1, 0.3) + _gauss(1550, 0.1, 1.0) + _gauss(1552, 0.1, 0.6)
    picos = _analise(y, find_max=True, max_peaks=2)["extrema"]
    assert [round(p["wavelength"]) for p in picos] == [1550, 1552]


def test_min_distance_merges_close_extrema():
    y = _gauss(1550.0, 0.05, 1.0) + _gauss(1550.3, 0.05, 0.8)
    assert len(_analise(y, find_max=True)["extrema"]) == 2
    assert len(_analise(y, find_max=True, min_distance=1.0)["extrema"]) == 1


def test_auto_prominence_ignores_noise_ripples():
    rng = np.random.default_rng(2)
    y = _gauss(1550, 0.3) + rng.normal(0, 0.005, len(GRADE))
    resultado = _analise(y, find_max=True)
    assert len(resultado["extrema"]) == 1
    assert resultado["summary"]["prominence"] == pytest.approx(0.05 * np.ptp(y))


def test_maxima_and_minima_together_and_global_extremes():
    y = _gauss(1548, 0.2) - _gauss(1552, 0.2, 0.7)
    resultado = _analise(y, find_max=True, find_min=True)
    assert [e["type"] for e in resultado["extrema"]] == ["max", "min"]
    resumo = resultado["summary"]
    assert resumo["global_max"]["wavelength"] == pytest.approx(1548, abs=0.01)
    assert resumo["global_min"]["intensity"] == pytest.approx(-0.7, abs=0.01)
    assert resumo["resolution"] == pytest.approx(0.01)


def test_nothing_is_detected_when_disabled():
    resultado = _analise(_gauss(1550, 0.2))
    assert resultado["extrema"] == []
    assert resultado["summary"]["global_max"] is not None, "os globais vêm sempre"
