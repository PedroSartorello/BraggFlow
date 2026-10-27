"""
figure.py – Figura de publicação estilizável
=============================================
Monta figuras a partir de um CSV processado (``Time`` + canais) com todo o
estilo descrito por um dicionário aninhado: tamanho e fontes da figura,
transformação dos dados, eixos, ticks, grade, curvas, legenda, marcações de
tempo e exportação.

* ``resolve_style(parcial)`` valida o dicionário e completa com os padrões
  (``default_style()``); erros viram ``ValueError`` com o nome do campo.
* ``render_figure(...)`` desenha e devolve os bytes no formato pedido, junto
  com o tamanho final da figura.
* ``build_figure(...)`` devolve a ``Figure`` do matplotlib; use dentro de
  ``style_context(style)`` até salvar, pois fontes e ticks são resolvidos no
  momento do desenho.

A figura usa *constrained layout*: por padrão o arquivo exportado tem
exatamente a largura e a altura pedidas (exigência comum de periódicos);
``export.crop`` recorta as margens em vez disso.
"""

import io
import math
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

import matplotlib
import numpy as np
import pandas as pd
from matplotlib import colors as mcolors
from matplotlib import font_manager
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.ticker import (
    AutoMinorLocator,
    FuncFormatter,
    MaxNLocator,
    MultipleLocator,
    ScalarFormatter,
)

from ..options import ANY_RANGE, resolve_section
from .publication import SENSOR_COLORS, SENSOR_LINES, SENSOR_MARKERS

LINESTYLES = ("-", "--", "-.", ":")
CHANNEL_LINESTYLES = LINESTYLES + ("none",)
MARKERS = ("none", "o", "s", "^", "v", "D", "x", "+", "*", "P", "X", "h", ".")
LEGEND_POSITIONS = (
    "outside top", "outside bottom", "outside right",
    "best", "upper right", "upper left", "lower right", "lower left",
    "center right", "center left", "upper center", "lower center",
)
GENERIC_FONTS = ("serif", "sans-serif", "monospace")
EXPORT_FORMATS = ("pdf", "png", "svg", "eps", "tiff")
TIME_DIVISORS = {"s": 1.0, "min": 60.0, "h": 3600.0}

PALETTES = {
    "publicacao": list(SENSOR_COLORS),
    "okabe_ito": ["#000000", "#E69F00", "#56B4E9", "#009E73", "#0072B2",
                  "#D55E00", "#CC79A7", "#F0E442"],
    "tableau": ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
                "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"],
    "cinza": ["#000000", "#595959", "#8c8c8c", "#b3b3b3"],
}

_SIZE = (1.0, 100.0)
_FONT = (4.0, 72.0)
_ANY = ANY_RANGE

# campo: (tipo, padrão, limites ou opções, nome exibido nos erros)
# Tipos terminados em "?" aceitam vazio (None = automático).
STYLE_SPEC = {
    "figure": {
        "layout": ("choice", "stacked", ("stacked", "combined"), "Layout"),
        "unit": ("choice", "cm", ("cm", "in"), "Unidade do tamanho"),
        "width": ("float", 18.19, _SIZE, "Largura da figura"),
        "height": ("float?", None, _SIZE, "Altura da figura"),
        "font_family": ("str", "serif", None, "Fonte"),
        "font_size": ("float?", None, _FONT, "Tamanho base da fonte"),
        "title": ("str", "", None, "Título"),
        "title_size": ("float?", None, _FONT, "Tamanho do título"),
        "title_bold": ("bool", True, None, "Título em negrito"),
        "background": ("color", "#ffffff", None, "Cor de fundo"),
        "panel_spacing": ("float", 0.02, (0.0, 1.0), "Espaço entre painéis"),
        "sharey": ("bool", False, None, "Mesma escala Y nos painéis"),
        "shared_ylabel": ("bool", False, None, "Rótulo Y único"),
        "panel_labels": ("bool", True, None, "Letras dos painéis"),
        "panel_label_format": ("choice", "a)", ("a)", "(a)", "a", "A)", "(A)", "A"),
                               "Formato das letras"),
    },
    "data": {
        "time_unit": ("choice", "s", tuple(TIME_DIVISORS), "Unidade do tempo"),
        "t0_first_marker": ("bool", False, None, "t = 0 na primeira marcação"),
        "to_pm": ("bool", True, None, "Converter nm → pm"),
        "relative_first": ("bool", True, None, "Δ relativo ao início"),
        "relative_window": ("float?", None, (0.0, None), "Janela da referência"),
        "intensity_unit": ("str", "a.u.", None, "Unidade da intensidade"),
        "x_min": ("float?", None, _ANY, "X mínimo"),
        "x_max": ("float?", None, _ANY, "X máximo"),
        "y_min": ("float?", None, _ANY, "Y mínimo"),
        "y_max": ("float?", None, _ANY, "Y máximo"),
    },
    "axes": {
        "xlabel": ("str", "", None, "Rótulo X"),
        "ylabel": ("str", "", None, "Rótulo Y"),
        "language": ("choice", "en", ("en", "pt"), "Idioma dos rótulos automáticos"),
        "label_size": ("float?", None, _FONT, "Tamanho dos rótulos"),
        "linewidth": ("float", 0.8, (0.0, 5.0), "Espessura dos eixos"),
        "spine_top": ("bool", False, None, "Borda superior"),
        "spine_right": ("bool", False, None, "Borda direita"),
        "grid": ("bool", True, None, "Grade principal"),
        "grid_minor": ("bool", False, None, "Grade secundária"),
        "grid_linestyle": ("choice", "--", LINESTYLES, "Estilo da grade"),
        "grid_color": ("color", "#cccccc", None, "Cor da grade"),
        "grid_alpha": ("float", 0.6, (0.0, 1.0), "Opacidade da grade"),
        "grid_linewidth": ("float", 0.5, (0.0, 5.0), "Espessura da grade"),
    },
    "ticks": {
        "direction": ("choice", "in", ("in", "out", "inout"), "Direção dos ticks"),
        "length": ("float", 4.0, (0.0, 20.0), "Comprimento dos ticks"),
        "width": ("float", 0.8, (0.0, 5.0), "Espessura dos ticks"),
        "label_size": ("float?", None, _FONT, "Tamanho do texto dos ticks"),
        "minor": ("bool", False, None, "Ticks secundários"),
        "mirror": ("bool", False, None, "Ticks no topo e à direita"),
        "decimal_separator": ("choice", ".", (".", ","), "Separador decimal"),
        "use_offset": ("bool", False, None, "Notação de offset"),
        "x_step": ("float?", None, (1e-12, None), "Passo dos ticks X"),
        "x_nbins": ("int?", None, (1, 50), "Nº de divisões X"),
        "x_decimals": ("int?", None, (0, 10), "Casas decimais X"),
        "x_rotation": ("float", 0.0, (-90.0, 90.0), "Rotação dos ticks X"),
        "y_step": ("float?", None, (1e-12, None), "Passo dos ticks Y"),
        "y_nbins": ("int?", None, (1, 50), "Nº de divisões Y"),
        "y_decimals": ("int?", None, (0, 10), "Casas decimais Y"),
    },
    "lines": {
        "width": ("float", 1.2, (0.05, 10.0), "Espessura das curvas"),
        "show_markers": ("bool", True, None, "Marcadores nas curvas"),
        "marker_size": ("float", 4.0, (0.5, 30.0), "Tamanho dos marcadores"),
        "marker_count": ("int", 25, (2, 1000), "Marcadores por curva"),
    },
    "legend": {
        "show": ("bool", True, None, "Mostrar legenda"),
        "position": ("choice", "outside top", LEGEND_POSITIONS, "Posição da legenda"),
        "ncol": ("int?", None, (1, 20), "Colunas da legenda"),
        "font_size": ("float?", None, _FONT, "Tamanho da legenda"),
        "frame": ("bool", False, None, "Moldura da legenda"),
        "title": ("str", "", None, "Título da legenda"),
    },
    "markers": {
        "linestyle": ("choice", "--", LINESTYLES, "Estilo das marcações"),
        "linewidth": ("float", 0.9, (0.05, 10.0), "Espessura das marcações"),
        "label_size": ("float?", None, _FONT, "Tamanho dos rótulos das marcações"),
        "label_rotation": ("float", 90.0, (-90.0, 90.0), "Rotação dos rótulos"),
        "label_position": ("choice", "above", ("above", "inside"), "Posição dos rótulos"),
        "monochrome": ("bool", False, None, "Marcações em preto"),
        "shade": ("bool", True, None, "Faixas alternadas"),
        "shade_color_1": ("color", "#EFF6FF", None, "Cor da faixa 1"),
        "shade_color_2": ("color", "#DCE9F7", None, "Cor da faixa 2"),
        "shade_alpha": ("float", 0.5, (0.0, 1.0), "Opacidade das faixas"),
    },
    "export": {
        "format": ("choice", "pdf", EXPORT_FORMATS, "Formato"),
        "dpi": ("int", 600, (50, 2400), "Resolução (dpi)"),
        "preview_dpi": ("int", 150, (50, 600), "Resolução da pré-visualização"),
        "transparent": ("bool", False, None, "Fundo transparente"),
        "crop": ("bool", False, None, "Recortar margens"),
    },
}

CHANNEL_SPEC = {
    "label": ("str", "", None, "Legenda do canal"),
    "color": ("color?", None, None, "Cor do canal"),
    "linestyle": ("choice?", None, CHANNEL_LINESTYLES, "Estilo da linha do canal"),
    "marker": ("choice?", None, MARKERS, "Marcador do canal"),
    "width": ("float?", None, (0.05, 10.0), "Espessura da linha do canal"),
}


# ─────────────────────────────────────────────────────────────────────────────
# Validação do estilo
# ─────────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def available_fonts() -> Tuple[str, ...]:
    """Famílias de fonte instaladas que o matplotlib consegue usar."""
    return tuple(sorted({f.name for f in font_manager.fontManager.ttflist}))


def resolve_style(user: Optional[dict] = None) -> dict:
    """
    Valida um estilo (possivelmente parcial) e completa com os padrões.

    ``user['channels']`` é um dicionário ``{canal: {label, color, linestyle,
    marker, width}}``; campos vazios usam a paleta e os estilos padrão.
    """
    user = user or {}
    style = {section: resolve_section(fields, user.get(section))
             for section, fields in STYLE_SPEC.items()}

    family = style["figure"]["font_family"].strip() or "serif"
    if family not in GENERIC_FONTS and family not in available_fonts():
        raise ValueError(f"Fonte não instalada: {family}.")
    style["figure"]["font_family"] = family

    channels = user.get("channels") or {}
    if not isinstance(channels, dict):
        raise ValueError("Estilo dos canais inválido.")
    style["channels"] = {
        str(name): resolve_section(CHANNEL_SPEC, given, prefix=f"[{name}] ")
        for name, given in channels.items()
    }
    return style


def default_style() -> dict:
    return resolve_style({})


# ─────────────────────────────────────────────────────────────────────────────
# Marcações de tempo
# ─────────────────────────────────────────────────────────────────────────────

def parse_markers(raw_markers: Optional[list]) -> List[dict]:
    """Valida e ordena marcações ``{time, label, color}`` (tempo em segundos)."""
    markers = []
    for m in raw_markers or []:
        t = str(m.get("time", "")).strip()
        if t == "":
            continue
        try:
            t = float(t.replace(",", "."))
        except ValueError:
            raise ValueError(f"Tempo inválido na marcação '{m.get('label', '')}': {t!r}") from None
        color = str(m.get("color", "")).strip() or "#4682B4"
        if not mcolors.is_color_like(color):
            raise ValueError(f"Cor inválida na marcação '{m.get('label', '')}': {color!r}")
        markers.append({"time": t, "label": str(m.get("label", "")).strip(), "color": color})
    markers.sort(key=lambda m: m["time"])
    return markers


# ─────────────────────────────────────────────────────────────────────────────
# Desenho
# ─────────────────────────────────────────────────────────────────────────────

def _is_serif(family: str) -> bool:
    keys = ("serif", "times", "georgia", "garamond", "palatino", "cambria",
            "stix", "computer modern", "cmu", "book antiqua", "century")
    name = family.lower()
    return name == "serif" or (any(k in name for k in keys) and "sans" not in name)


def _font_size(style: dict) -> float:
    size = style["figure"]["font_size"]
    if size is None:
        size = 16.0 if style["figure"]["layout"] == "stacked" else 12.0
    return size


@contextmanager
def style_context(style: dict):
    """rcParams do estilo (fonte e fórmulas); ative até salvar a figura."""
    family = style["figure"]["font_family"]
    params = {
        "font.size": _font_size(style),
        "mathtext.fontset": "stix" if _is_serif(family) else "dejavusans",
        "axes.unicode_minus": True,
        "path.simplify": True,
        "savefig.bbox": "standard",  # o recorte é controlado por export.crop
    }
    if family == "serif":
        params.update({"font.family": "serif",
                       "font.serif": ["Times New Roman", "STIXGeneral", "DejaVu Serif"]})
    elif family == "sans-serif":
        params.update({"font.family": "sans-serif",
                       "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"]})
    else:
        params["font.family"] = [family, "DejaVu Sans"]
    with matplotlib.rc_context(params):
        yield


def figure_size(style: dict, n_panels: int) -> Tuple[float, float]:
    """Largura e altura em polegadas (altura automática quando vazia)."""
    fig_s = style["figure"]
    scale = 1 / 2.54 if fig_s["unit"] == "cm" else 1.0
    width = fig_s["width"] * scale
    if fig_s["height"] is not None:
        height = fig_s["height"] * scale
    elif fig_s["layout"] == "stacked":
        height = 2.0 * n_panels + 0.6
    else:
        height = width * 0.56
    return width, height


class _SeparatorFormatter(ScalarFormatter):
    """ScalarFormatter com vírgula decimal."""

    def __call__(self, x, pos=None):
        return super().__call__(x, pos).replace(".", ",")

    def get_offset(self):
        return super().get_offset().replace(".", ",")


def _tick_formatter(decimals: Optional[int], separator: str, use_offset: bool):
    if decimals is None:
        cls = _SeparatorFormatter if separator == "," else ScalarFormatter
        return cls(useOffset=use_offset)

    def fmt(value, pos=None):
        if abs(value) < 0.5 * 10 ** -decimals:
            value = 0.0
        return f"{value:.{decimals}f}".replace("-", "−").replace(".", separator)

    return FuncFormatter(fmt)


def _panel_label(fmt: str, index: int) -> str:
    letter = chr(ord("A" if fmt[0].isupper() or fmt[:2] == "(A" else "a") + index)
    return fmt.replace("a", letter).replace("A", letter)


def marker_offset(markers: List[dict], data_s: dict) -> float:
    """Deslocamento do eixo quando t = 0 fica na primeira marcação."""
    return markers[0]["time"] if (data_s["t0_first_marker"] and markers) else 0.0


def shift_markers(markers: List[dict], offset: float) -> List[dict]:
    return [{**m, "time": m["time"] - offset} for m in markers] if offset else markers


def time_axis(df: pd.DataFrame, data_s: dict, offset: float = 0.0):
    """Eixo de tempo na unidade escolhida; devolve ``(x, divisor)``."""
    t = df["Time"].to_numpy(dtype=float) - offset
    divisor = TIME_DIVISORS[data_s["time_unit"]]
    return t / divisor, divisor


def channel_values(df: pd.DataFrame, units: Dict[str, Optional[str]],
                   quantities: Dict[str, Optional[str]], channel: str,
                   data_s: dict) -> Tuple[np.ndarray, str, bool]:
    """
    Valores de um canal já transformados: referência relativa (primeiro ponto
    ou média de uma janela) e conversão nm → pm. Devolve ``(y, unidade,
    é_deslocamento)``.
    """
    t = df["Time"].to_numpy(dtype=float)
    y = df[channel].to_numpy(dtype=float)
    unit = units.get(channel) or "nm"
    relative = data_s["relative_first"]

    if relative:
        if data_s["relative_window"]:
            window = np.isfinite(y) & (t - t[0] <= data_s["relative_window"])
        else:
            window = np.zeros(len(y), dtype=bool)
            finite = np.flatnonzero(np.isfinite(y))
            window[finite[:1]] = True
        if not window.any():
            raise ValueError(f"Canal {channel}: nenhuma leitura válida na janela de referência.")
        y = y - np.mean(y[window])

    if data_s["to_pm"] and unit == "nm":
        y, unit = y * 1000.0, "pm"
    return y, unit, relative or quantities.get(channel) == "wavelength_shift"


_LABELS = {
    "en": {"time": "Time", "wavelength": "Wavelength", "intensity": "Intensity",
           "transmission": "Transmission", "absorbance": "Absorbance", "spectrum": "Spectrum",
           "depth": "Depth", "height": "Height"},
    "pt": {"time": "Tempo", "wavelength": "Comprimento de onda", "intensity": "Intensidade",
           "transmission": "Transmissão", "absorbance": "Absorbância", "spectrum": "Espectro",
           "depth": "Profundidade", "height": "Altura"},
}
# Unidade da intensidade depois do preparo → o que ela mede
_INTENSITY_NAMES = {"%": "transmission", "": "transmission", "dB": "transmission",
                    "AU": "absorbance"}


def series_labels(unit: str, is_shift: bool, time_unit: str,
                  language: str = "en") -> Tuple[str, str]:
    """Rótulos padrão de uma figura de série no tempo, em inglês ou português."""
    nomes = _LABELS.get(language, _LABELS["en"])
    symbol = r"$\Delta\lambda$" if is_shift else r"$\lambda$"
    return f"{nomes['time']} ({time_unit})", f"{symbol} ({unit})"


def spectrum_labels(style: dict) -> Tuple[str, str]:
    """Rótulos padrão de uma figura de espectros, no idioma do estilo."""
    nomes = _LABELS.get(style["axes"].get("language", "en"), _LABELS["en"])
    return (f"{nomes['wavelength']} (nm)",
            f"{nomes['intensity']} ({style['data']['intensity_unit']})")


def evolution_labels(quantity: str, unit: str, kind: str = "min",
                     time_unit: Optional[str] = None, language: str = "en") -> Tuple[str, str]:
    """
    Rótulos de uma figura da evolução de um vale (``kind='min'``) ou pico
    entre espectros: x é o tempo (``time_unit``) ou, sem ele, o número do
    espectro; y é a grandeza acompanhada (``wavelength``, ``delta``,
    ``intensity``, ``prominence`` ou ``fwhm``) na unidade do preparo.
    """
    nomes = _LABELS.get(language, _LABELS["en"])
    xlabel = f"{nomes['time']} ({time_unit})" if time_unit else nomes["spectrum"]
    unidade = f" ({unit})" if unit and unit != "AU" else ""
    medida = nomes[_INTENSITY_NAMES.get(unit, "intensity")]
    ylabels = {
        "wavelength": r"$\lambda$ (nm)",
        "delta": r"$\Delta\lambda$ (nm)",
        "intensity": f"{medida}{unidade}",
        "prominence": f"{nomes['depth' if kind == 'min' else 'height']}{unidade}",
        "fwhm": "FWHM (nm)",
    }
    if quantity not in ylabels:
        raise ValueError(f"Grandeza desconhecida: {quantity}.")
    return xlabel, ylabels[quantity]


def _style_axes(ax, style: dict, tick_size: float) -> None:
    ax_s, tk = style["axes"], style["ticks"]
    ax.set_facecolor(style["figure"]["background"])
    ax.spines["top"].set_visible(ax_s["spine_top"])
    ax.spines["right"].set_visible(ax_s["spine_right"])
    for spine in ax.spines.values():
        spine.set_linewidth(ax_s["linewidth"])

    minor = tk["minor"] or ax_s["grid_minor"]
    for axis, prefix in ((ax.xaxis, "x"), (ax.yaxis, "y")):
        if tk[f"{prefix}_step"]:
            axis.set_major_locator(MultipleLocator(tk[f"{prefix}_step"]))
        elif tk[f"{prefix}_nbins"]:
            axis.set_major_locator(MaxNLocator(tk[f"{prefix}_nbins"]))
        if minor:
            axis.set_minor_locator(AutoMinorLocator())
        axis.set_major_formatter(_tick_formatter(
            tk[f"{prefix}_decimals"], tk["decimal_separator"], tk["use_offset"]))
        axis.get_offset_text().set_fontsize(tick_size)

    ax.tick_params(which="both", direction=tk["direction"], width=tk["width"],
                   labelsize=tick_size, top=tk["mirror"], right=tk["mirror"])
    ax.tick_params(which="major", length=tk["length"])
    ax.tick_params(which="minor", length=tk["length"] * 0.5 if tk["minor"] else 0)
    if tk["x_rotation"]:
        ax.tick_params(axis="x", labelrotation=tk["x_rotation"])

    if ax_s["grid"]:
        ax.grid(True, which="major", linestyle=ax_s["grid_linestyle"],
                color=ax_s["grid_color"], alpha=ax_s["grid_alpha"],
                linewidth=ax_s["grid_linewidth"])
    else:
        ax.grid(False, which="major")
    if ax_s["grid_minor"]:
        ax.grid(True, which="minor", linestyle=":", color=ax_s["grid_color"],
                alpha=ax_s["grid_alpha"] * 0.7, linewidth=ax_s["grid_linewidth"] * 0.7)
    ax.set_axisbelow(True)


def _draw_markers(axes: list, markers: List[dict], divisor: float,
                  x_range: Tuple[float, float], mk: dict, font_size: float) -> None:
    """Faixas alternadas, linhas verticais e rótulos das marcações."""
    x_lo, x_hi = x_range
    label_size = mk["label_size"] or max(6.0, round(font_size * 0.55, 1))
    shade_colors = (mk["shade_color_1"], mk["shade_color_2"])
    positions = [m["time"] / divisor for m in markers]

    for k, m in enumerate(markers):
        cor = "#000000" if mk["monochrome"] else m["color"]   # impressão sem cor
        x_start = positions[k]
        x_end = positions[k + 1] if k + 1 < len(positions) else x_hi
        for ax in axes:
            if mk["shade"]:
                ax.axvspan(x_start, x_end, color=shade_colors[k % 2],
                           alpha=mk["shade_alpha"], zorder=0, linewidth=0)
            ax.axvline(x_start, color=cor, linestyle=mk["linestyle"],
                       linewidth=mk["linewidth"], alpha=0.85, zorder=2)

        if not m["label"]:
            continue
        x_text = (max(x_start, x_lo) + min(x_end, x_hi)) / 2.0 if mk["shade"] else x_start
        if not x_lo <= x_text <= x_hi:
            continue
        above = mk["label_position"] == "above"
        axes[0].text(
            x_text, 1.02 if above else 0.98, m["label"],
            transform=axes[0].get_xaxis_transform(),
            color=cor, fontsize=label_size, fontweight="bold",
            ha="center", va="bottom" if above else "top",
            rotation=mk["label_rotation"],
            clip_on=False, zorder=4,
        )


@dataclass
class Curve:
    """Uma curva a desenhar: identificador para o estilo, x, y e legenda."""

    key: str
    x: np.ndarray
    y: np.ndarray
    label: Optional[str] = None


def _build_curves_figure(curves: List[Curve], markers: List[dict], style: dict,
                         xlabel: str, ylabel: str, divisor: float = 1.0) -> Figure:
    """
    Núcleo de desenho usado pelas séries no tempo e pelos espectros: painéis,
    curvas, eixos, marcações, letras dos painéis, legenda e título.
    """
    if not curves:
        raise ValueError("Nenhuma curva selecionada.")

    fig_s, ax_s, lg, ln = style["figure"], style["axes"], style["legend"], style["lines"]
    stacked = fig_s["layout"] == "stacked"
    n_panels = len(curves) if stacked else 1
    font_size = _font_size(style)
    label_size = ax_s["label_size"] or font_size
    tick_size = style["ticks"]["label_size"] or font_size
    legend_size = lg["font_size"] or font_size

    fig = Figure(figsize=figure_size(style, n_panels), layout="constrained",
                 facecolor=fig_s["background"])
    FigureCanvasAgg(fig)
    fig.get_layout_engine().set(hspace=fig_s["panel_spacing"])
    axes = list(fig.subplots(n_panels, 1, sharex=True,
                             sharey=stacked and fig_s["sharey"], squeeze=False)[:, 0])

    handles = []
    for i, curve in enumerate(curves):
        ax = axes[i] if stacked else axes[0]
        cs = style["channels"].get(curve.key, {})
        marker = (cs.get("marker") or SENSOR_MARKERS[i % len(SENSOR_MARKERS)]) if ln["show_markers"] else "none"
        line, = ax.plot(
            curve.x, curve.y,
            color=cs.get("color") or SENSOR_COLORS[i % len(SENSOR_COLORS)],
            linestyle=cs.get("linestyle") or SENSOR_LINES[i % len(SENSOR_LINES)],
            marker=marker, markevery=max(1, len(curve.x) // ln["marker_count"]),
            markersize=ln["marker_size"], linewidth=cs.get("width") or ln["width"],
            label=(cs.get("label") or "").strip() or curve.label or curve.key, zorder=3,
        )
        handles.append(line)

    for ax in axes:
        _style_axes(ax, style, tick_size)

    # Rótulos dos eixos
    axes[-1].set_xlabel(ax_s["xlabel"].strip() or xlabel, fontsize=label_size)
    ylabel = ax_s["ylabel"].strip() or ylabel
    if stacked and fig_s["shared_ylabel"] and n_panels > 1:
        fig.supylabel(ylabel, fontsize=label_size)
    else:
        for ax in axes:
            ax.set_ylabel(ylabel, fontsize=label_size)

    # Limites
    data_s = style["data"]
    finite_x = np.concatenate([c.x[np.isfinite(c.x)] for c in curves])
    if not len(finite_x):
        raise ValueError("Eixo X sem valores válidos.")
    x_lo = data_s["x_min"] if data_s["x_min"] is not None else float(finite_x.min())
    x_hi = data_s["x_max"] if data_s["x_max"] is not None else float(finite_x.max())
    if not x_lo < x_hi:
        raise ValueError("X mínimo deve ser menor que X máximo.")
    axes[-1].set_xlim(x_lo, x_hi)
    if (data_s["y_min"] is not None and data_s["y_max"] is not None
            and not data_s["y_min"] < data_s["y_max"]):
        raise ValueError("Y mínimo deve ser menor que Y máximo.")
    if data_s["y_min"] is not None or data_s["y_max"] is not None:
        for ax in axes:
            ax.set_ylim(bottom=data_s["y_min"], top=data_s["y_max"])

    if markers:
        _draw_markers(axes, markers, divisor, (x_lo, x_hi), style["markers"], font_size)

    # Letras a), b), c) alinhadas à esquerda do rótulo Y de cada painel
    if stacked and n_panels > 1 and fig_s["panel_labels"]:
        for i, ax in enumerate(axes):
            text = _panel_label(fig_s["panel_label_format"], i)
            common = dict(fontsize=label_size, fontweight="bold", va="bottom",
                          annotation_clip=False)
            if ax.yaxis.label.get_text():
                ax.annotate(text, xy=(0, 1), xycoords=(ax.yaxis.label, "axes fraction"),
                            xytext=(0, 2), textcoords="offset points", ha="left", **common)
            else:
                ax.annotate(text, xy=(0, 1), xycoords="axes fraction",
                            xytext=(-4, 2), textcoords="offset points", ha="right", **common)

    if lg["show"]:
        position = lg["position"]
        wide = position in ("outside top", "outside bottom")
        kwargs = dict(
            ncol=lg["ncol"] or (len(handles) if wide else 1),
            fontsize=legend_size, frameon=lg["frame"],
            title=lg["title"].strip() or None, title_fontsize=legend_size,
            handlelength=2.5,
        )
        if position.startswith("outside"):
            loc = {"outside top": "outside upper center",
                   "outside bottom": "outside lower center",
                   "outside right": "outside right center"}[position]
            fig.legend(handles=handles, loc=loc, **kwargs)
        elif stacked:
            for ax, handle in zip(axes, handles):
                ax.legend(handles=[handle], loc=position, **kwargs)
        else:
            axes[0].legend(handles=handles, loc=position, **kwargs)

    if fig_s["title"].strip():
        fig.suptitle(fig_s["title"].strip(), fontsize=fig_s["title_size"] or font_size * 1.15,
                     fontweight="bold" if fig_s["title_bold"] else "normal")
    return fig


def build_figure(df: pd.DataFrame, units: Dict[str, Optional[str]],
                 quantities: Dict[str, Optional[str]], channels: List[str],
                 markers: List[dict], style: dict) -> Figure:
    """
    Figura de uma série no tempo (CSV processado). ``style`` deve vir de
    ``resolve_style``; chame dentro de ``style_context(style)`` e salve antes
    de sair do contexto.
    """
    if not channels:
        raise ValueError("Nenhum canal selecionado.")
    missing = [ch for ch in channels if ch not in df.columns]
    if missing:
        raise ValueError(f"Canais ausentes no CSV: {missing}.")

    offset = marker_offset(markers, style["data"])
    markers = shift_markers(markers, offset)
    x, divisor = time_axis(df, style["data"], offset)
    curves, unit, is_shift = [], "nm", False
    for channel in channels:
        y, unit, is_shift = channel_values(df, units, quantities, channel, style["data"])
        curves.append(Curve(key=channel, x=x, y=y))

    xlabel, ylabel = series_labels(unit, is_shift, style["data"]["time_unit"],
                                   style["axes"]["language"])
    return _build_curves_figure(curves, markers, style, xlabel, ylabel, divisor=divisor)


def build_curve_figure(items: List[dict], markers: List[dict], style: dict,
                       xlabel: str, ylabel: str, divisor: float = 1.0) -> Figure:
    """
    Figura a partir de curvas já prontas — é o caminho usado quando elas vêm
    de vários arquivos (séries no tempo ou espectros).

    Cada item é ``{"key", "x", "y"}`` e, opcionalmente, ``"label"``; o estilo
    de cada curva sai de ``style['channels'][key]``.
    """
    if not items:
        raise ValueError("Nenhuma curva selecionada.")
    curves = [
        Curve(key=item["key"], label=item.get("label"),
              x=np.asarray(item["x"], dtype=float),
              y=np.asarray(item["y"], dtype=float))
        for item in items
    ]
    return _build_curves_figure(curves, markers, style, xlabel, ylabel, divisor=divisor)


def save_kwargs(style: dict, dpi: Optional[int] = None) -> dict:
    ex = style["export"]
    kwargs = {"dpi": dpi or ex["dpi"], "bbox_inches": "tight" if ex["crop"] else None,
              "pad_inches": 0.03}
    if ex["transparent"]:
        kwargs["transparent"] = True
    else:
        kwargs["facecolor"] = style["figure"]["background"]
    return kwargs


def render_curve_figure(items: List[dict], markers: List[dict], style: dict,
                        xlabel: str, ylabel: str, divisor: float = 1.0,
                        fmt: Optional[str] = None,
                        dpi: Optional[int] = None) -> Tuple[bytes, dict]:
    """Desenha e salva uma figura de curvas prontas (ver ``build_curve_figure``)."""
    return _render(
        lambda: build_curve_figure(items, markers, style, xlabel, ylabel, divisor),
        style, fmt, dpi,
    )


def render_figure(df: pd.DataFrame, units: Dict[str, Optional[str]],
                  quantities: Dict[str, Optional[str]], channels: List[str],
                  markers: List[dict], style: dict, fmt: Optional[str] = None,
                  dpi: Optional[int] = None) -> Tuple[bytes, dict]:
    """
    Desenha e salva a figura em memória.

    Retorna ``(bytes, info)``; ``info`` traz o tamanho final (cm, polegadas e
    pixels na resolução de exportação), já considerando o recorte de margens.
    """
    return _render(
        lambda: build_figure(df, units, quantities, channels, markers, style),
        style, fmt, dpi,
    )


def _render(make_figure, style: dict, fmt: Optional[str],
            dpi: Optional[int]) -> Tuple[bytes, dict]:
    fmt = fmt or style["export"]["format"]
    if fmt not in EXPORT_FORMATS:
        raise ValueError(f"Formato não suportado: {fmt}.")

    with style_context(style):
        fig = make_figure()
        kwargs = save_kwargs(style, dpi)
        buf = io.BytesIO()
        fig.savefig(buf, format=fmt, **kwargs)

        width_in, height_in = fig.get_size_inches()
        if kwargs["bbox_inches"] == "tight":
            bbox = fig.get_tightbbox(fig.canvas.get_renderer())
            width_in = bbox.width + 2 * kwargs["pad_inches"]
            height_in = bbox.height + 2 * kwargs["pad_inches"]

    export_dpi = style["export"]["dpi"]
    info = {
        "width_in": round(float(width_in), 3),
        "height_in": round(float(height_in), 3),
        "width_cm": round(float(width_in) * 2.54, 2),
        "height_cm": round(float(height_in) * 2.54, 2),
        "width_px": int(round(width_in * export_dpi)),
        "height_px": int(round(height_in * export_dpi)),
        "dpi": export_dpi,
    }
    return buf.getvalue(), info
