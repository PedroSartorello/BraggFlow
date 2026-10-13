import struct

import numpy as np
import pandas as pd
import pytest

from braggflow.processing.spectra import prepare_spectrum, resolve_spectrum_settings
from braggflow.visualization.figure import (
    build_curve_figure,
    build_figure,
    render_curve_figure,
    spectrum_labels,
    default_style,
    parse_markers,
    render_figure,
    resolve_style,
    style_context,
    _tick_formatter,
)


@pytest.fixture
def data():
    t = np.arange(2000) / 50
    df = pd.DataFrame({
        "Time": t,
        "S1": 1550.0 + 0.01 * np.sin(t / 5),
        "S2": 1545.0 + 0.005 * np.cos(t / 3),
    })
    return df, {"S1": "nm", "S2": "nm"}, {}


def _png_size(image: bytes):
    return struct.unpack(">II", image[16:24])


# ── resolve_style ─────────────────────────────────────────────────────────────

def test_defaults_are_complete_and_valid():
    style = default_style()
    assert style["figure"]["width"] == 18.19 and style["figure"]["height"] is None
    assert style["export"]["format"] == "pdf" and style["channels"] == {}
    assert resolve_style(style) == style, "a resolved style must round-trip"


def test_values_from_form_are_coerced():
    style = resolve_style({
        "figure": {"width": "8,89", "height": "", "font_size": "8", "title_bold": "false"},
        "ticks": {"x_nbins": "5", "minor": True},
        "channels": {"S1": {"label": "Sensor 1", "color": "#ff0000", "linestyle": "", "marker": "s"}},
    })
    assert style["figure"]["width"] == pytest.approx(8.89)
    assert style["figure"]["height"] is None
    assert style["figure"]["title_bold"] is False
    assert style["ticks"]["x_nbins"] == 5
    assert style["channels"]["S1"] == {"label": "Sensor 1", "color": "#ff0000",
                                       "linestyle": None, "marker": "s", "width": None}


@pytest.mark.parametrize("user, message", [
    ({"figure": {"width": "0.2"}}, "Largura da figura"),
    ({"figure": {"layout": "grid"}}, "Layout"),
    ({"figure": {"font_family": "Fonte Que Não Existe"}}, "Fonte não instalada"),
    ({"axes": {"grid_color": "not-a-color"}}, "Cor da grade"),
    ({"ticks": {"x_decimals": "1.5"}}, "inteiro"),
    ({"legend": {"position": "somewhere"}}, "Posição da legenda"),
    ({"channels": {"S1": {"marker": "@"}}}, r"\[S1\] Marcador do canal"),
])
def test_invalid_values_name_the_field(user, message):
    with pytest.raises(ValueError, match=message):
        resolve_style(user)


def test_parse_markers_sorts_and_validates():
    markers = parse_markers([{"time": "30", "label": "B"}, {"time": "10,5", "label": "A"},
                             {"time": "", "label": "ignored"}])
    assert [m["time"] for m in markers] == [10.5, 30.0]
    with pytest.raises(ValueError, match="Tempo inválido"):
        parse_markers([{"time": "abc"}])


# ── desenho e exportação ──────────────────────────────────────────────────────

def test_exact_size_png(data):
    df, units, quantities = data
    style = resolve_style({"figure": {"width": 8.89, "height": 6.0, "unit": "cm"}})
    image, info = render_figure(df, units, quantities, ["S1", "S2"], [], style, fmt="png", dpi=300)
    width, height = _png_size(image)
    assert width == pytest.approx(8.89 / 2.54 * 300, abs=1)
    assert height == pytest.approx(6.0 / 2.54 * 300, abs=1)
    assert info["width_cm"] == pytest.approx(8.89, abs=0.01)
    assert info["height_cm"] == pytest.approx(6.0, abs=0.01)
    assert info["width_px"] == round(8.89 / 2.54 * 600)


def test_crop_reports_the_cropped_size(data):
    df, units, quantities = data
    style = resolve_style({"figure": {"width": 10, "height": 20}, "export": {"crop": True}})
    image, info = render_figure(df, units, quantities, ["S1"], [], style, fmt="png", dpi=100)
    width, height = _png_size(image)
    assert width == pytest.approx(info["width_in"] * 100, abs=2)
    assert height == pytest.approx(info["height_in"] * 100, abs=2)


@pytest.mark.parametrize("fmt, magic", [
    ("pdf", b"%PDF"), ("svg", b"<?xml"), ("eps", b"%!PS"), ("tiff", b"II*\x00"),
])
def test_export_formats(data, fmt, magic):
    df, units, quantities = data
    style = resolve_style({"export": {"format": fmt, "dpi": 100}})
    image, _ = render_figure(df, units, quantities, ["S1"], [], style)
    assert image.startswith(magic)


def test_channel_styles_and_data_transform(data):
    df, units, quantities = data
    style = resolve_style({
        "figure": {"layout": "combined"},
        "data": {"to_pm": True, "relative_first": True, "x_min": 5, "x_max": 20, "y_max": 50},
        "lines": {"show_markers": False},
        "channels": {"S1": {"label": "Grade A", "color": "#123456", "linestyle": ":", "width": 2.5}},
        "legend": {"position": "upper right", "ncol": 2, "title": "Sensores", "frame": True},
    })
    with style_context(style):
        fig = build_figure(df, units, quantities, ["S1", "S2"], [], style)
    ax = fig.axes[0]
    line = ax.get_lines()[0]
    assert line.get_label() == "Grade A"
    assert line.get_color() == "#123456" and line.get_linestyle() == ":" and line.get_linewidth() == 2.5
    assert line.get_marker().lower() == "none"
    assert ax.get_xlim() == (5.0, 20.0) and ax.get_ylim()[1] == 50.0
    assert line.get_ydata()[0] == 0.0, "relative to the first point"
    assert np.nanmax(np.abs(line.get_ydata())) > 5, "converted to pm"
    legend = ax.get_legend()
    assert legend.get_title().get_text() == "Sensores" and legend._ncols == 2
    assert ax.get_ylabel() == r"$\Delta\lambda$ (pm)"


def test_stacked_panels_labels_and_shared_ylabel(data):
    df, units, quantities = data
    markers = parse_markers([{"time": 10, "label": "N2"}, {"time": 25, "label": "CO2"}])
    style = resolve_style({
        "figure": {"panel_label_format": "(A)", "shared_ylabel": True, "sharey": True},
        "axes": {"ylabel": "Deslocamento", "spine_top": True},
        "data": {"time_unit": "min"},
    })
    with style_context(style):
        fig = build_figure(df, units, quantities, ["S1", "S2"], markers, style)
        fig.canvas.draw()
    axes = fig.axes
    assert len(axes) == 2
    assert fig.get_supylabel() == "Deslocamento" and axes[0].get_ylabel() == ""
    assert [t.get_text() for t in axes[0].texts if t.get_text().startswith("(")] == ["(A)"]
    assert {t.get_text() for t in axes[0].texts} >= {"N2", "CO2"}
    assert axes[1].get_xlabel() == "Time (min)"
    assert axes[0].spines["top"].get_visible()
    assert axes[0].get_shared_y_axes().joined(axes[0], axes[1])


def test_relative_window_uses_mean_of_first_seconds(data):
    df, units, quantities = data
    df = df.copy()
    df.loc[0, "S1"] = 1550.5                     # outlier on the very first sample
    style = resolve_style({"figure": {"layout": "combined"}, "data": {"relative_window": 2.0}})
    with style_context(style):
        fig = build_figure(df, units, quantities, ["S1"], [], style)
    y = fig.axes[0].get_lines()[0].get_ydata()
    assert abs(np.median(y[:100])) < 20, "baseline must not be pulled by one sample"


def test_decimal_comma_formatter():
    assert _tick_formatter(2, ",", False)(-1.5) == "−1,50"
    assert _tick_formatter(1, ",", False)(-0.01) == "0,0"
    assert _tick_formatter(0, ".", False)(1234.4) == "1234"


def test_invalid_limits_raise(data):
    df, units, quantities = data
    style = resolve_style({"data": {"x_min": 10, "x_max": 5}})
    with pytest.raises(ValueError, match="X mínimo"):
        render_figure(df, units, quantities, ["S1"], [], style, fmt="png")


# ── espectros ─────────────────────────────────────────────────────────────────

@pytest.fixture
def spectra():
    wavelength = np.linspace(1510, 1590, 4000)
    rng = np.random.default_rng(0)
    fringes = 10 * np.sin(wavelength * 2) + 60   # franjas largas o bastante para suavizar
    return [
        {"key": "AR", "label": "Ar", "wavelength": wavelength,
         "intensity": fringes + rng.normal(0, 1.5, len(wavelength))},
        {"key": "ALCOOL", "label": "Álcool", "wavelength": wavelength,
         "intensity": fringes - 3 + rng.normal(0, 1.5, len(wavelength))},
    ]


def _spectrum_items(spectra, settings=None):
    """Prepara cada espectro (como faz o app) e devolve as curvas."""
    items = []
    for item in spectra:
        wavelength, intensity = prepare_spectrum(
            item["wavelength"], item["intensity"], resolve_spectrum_settings(settings))
        items.append({"key": item["key"], "label": item["label"],
                      "x": wavelength, "y": intensity})
    return items


def test_spectrum_figure_labels_and_curves(spectra):
    style = resolve_style({"figure": {"layout": "combined"},
                           "data": {"intensity_unit": "u.a."},
                           "channels": {"AR": {"color": "#2a78d6"}}})
    with style_context(style):
        fig = build_curve_figure(_spectrum_items(spectra), [], style, *spectrum_labels(style))
    ax = fig.axes[0]
    assert ax.get_xlabel() == "Wavelength (nm)"
    assert ax.get_ylabel() == "Intensity (u.a.)"
    labels = [line.get_label() for line in ax.get_lines()]
    assert labels == ["Ar", "Álcool"]
    assert ax.get_lines()[0].get_color() == "#2a78d6"
    assert ax.get_xlim() == pytest.approx((1510.0, 1590.0))


def test_spectrum_smoothing_approaches_the_noiseless_signal(spectra):
    clean = 10 * np.sin(spectra[0]["wavelength"] * 2) + 60
    style = resolve_style({"figure": {"layout": "combined"}})
    with style_context(style):
        fig = build_curve_figure(_spectrum_items(spectra, {"smooth_window": 41}), [], style,
                                 *spectrum_labels(style))
    smoothed = fig.axes[0].get_lines()[0].get_ydata()
    assert np.std(smoothed - clean) < np.std(spectra[0]["intensity"] - clean) / 3


def test_spectrum_markers_are_in_nanometres(spectra):
    markers = parse_markers([{"time": "1520", "label": "pico"}])
    style = resolve_style({"figure": {"layout": "combined"},
                           "data": {"x_min": 1515, "x_max": 1525}})
    with style_context(style):
        fig = build_curve_figure(_spectrum_items(spectra), markers, style, *spectrum_labels(style))
        fig.canvas.draw()
    ax = fig.axes[0]
    vertical = [line for line in ax.get_lines() if len(line.get_xdata()) == 2
                and line.get_xdata()[0] == line.get_xdata()[1]]
    assert vertical and vertical[0].get_xdata()[0] == 1520.0
    assert "pico" in {t.get_text() for t in ax.texts}


def test_spectrum_stacked_panels_and_export(spectra):
    style = resolve_style({"figure": {"layout": "stacked", "width": 10, "height": 8},
                           "export": {"format": "png", "dpi": 100}})
    image, info = render_curve_figure(_spectrum_items(spectra), [], style, *spectrum_labels(style))
    assert image.startswith(b"\x89PNG")
    assert info["width_cm"] == pytest.approx(10.0, abs=0.01)


def test_empty_curve_list_is_rejected():
    with pytest.raises(ValueError, match="Nenhuma curva"):
        render_curve_figure([], [], default_style(), "x", "y", fmt="png")


# ── idioma dos rótulos automáticos ────────────────────────────────────────────

def test_automatic_labels_follow_the_chosen_language():
    from braggflow.visualization.figure import series_labels
    assert series_labels("pm", True, "s") == ("Time (s)", r"$\Delta\lambda$ (pm)")
    assert series_labels("pm", True, "min", "pt") == ("Tempo (min)", r"$\Delta\lambda$ (pm)")

    estilo = resolve_style({"axes": {"language": "pt"}, "data": {"intensity_unit": "u.a."}})
    assert spectrum_labels(estilo) == ("Comprimento de onda (nm)", "Intensidade (u.a.)")
    assert resolve_style({})["axes"]["language"] == "en", "figuras antigas não mudam"


def test_language_is_validated():
    with pytest.raises(ValueError):
        resolve_style({"axes": {"language": "fr"}})


def test_monochrome_markers_ignore_each_marker_color(data):
    from matplotlib.colors import to_hex
    df, units, quantities = data
    marcas = parse_markers([{"time": 10, "label": "A", "color": "#ff0000"}])

    def cores(estilo):
        with style_context(estilo):
            fig = build_figure(df, units, quantities, ["S1"], marcas, estilo)
            ax = fig.axes[0]
            linhas = [to_hex(l.get_color()) for l in ax.lines if l.get_xdata()[0] == 10]
            textos = [to_hex(t.get_color()) for t in ax.texts if t.get_text() == "A"]
        return linhas + textos

    assert set(cores(resolve_style({}))) == {"#ff0000"}
    assert set(cores(resolve_style({"markers": {"monochrome": True}}))) == {"#000000"}
