"""
publication.py – Utilidades compartilhadas para figuras de publicação
=====================================================================
Concentra o que era duplicado entre ``mainPlot.py``, ``mainPlotFluke.py`` e
``mainPlotVazao.py``: estilo rcParams IEEE/Elsevier, paleta de sensores,
estilos de gás e carregamento dos CSVs de sensor e de eventos de gás.
"""

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from braggflow.io.processed import read_processed_csv


# ─────────────────────────────────────────────────────────────────────────────
# Estilo global para publicação científica (IEEE / Elsevier)
# ─────────────────────────────────────────────────────────────────────────────

def apply_publication_style(
    font_size: int = 16,
    tick_label_size: int | None = None,
    minor_ticks: bool = False,
) -> None:
    """
    Configura rcParams para padrão IEEE/Elsevier.

    Parameters
    ----------
    font_size       : tamanho base (título, rótulos de eixo).
    tick_label_size : tamanho dos rótulos de tick. None = igual a font_size.
    minor_ticks     : se True, define também o tamanho dos minor ticks
                      (usado nas figuras isoladas de vazão).
    """
    if tick_label_size is None:
        tick_label_size = font_size

    params = {
        # Fonte
        "font.family":        "serif",
        "font.serif":         ["Times New Roman", "DejaVu Serif"],
        "font.size":          font_size,
        "axes.titlesize":     font_size,
        "axes.labelsize":     font_size,
        "xtick.labelsize":    tick_label_size,
        "ytick.labelsize":    tick_label_size,
        # Linhas
        "axes.linewidth":     0.8,
        "grid.linewidth":     0.5,
        "lines.linewidth":    1.2,
        # Grid discreto
        "axes.grid":          True,
        "grid.color":         "#CCCCCC",
        "grid.linestyle":     "--",
        "grid.alpha":         0.6,
        # Bordas – padrão científico: apenas esquerda e baixo
        "axes.spines.top":    False,
        "axes.spines.right":  False,
        # Ticks voltados para dentro
        "xtick.direction":    "in",
        "ytick.direction":    "in",
        "xtick.major.size":   4,
        "ytick.major.size":   4,
        # Figura
        "figure.dpi":         150,
        "savefig.dpi":        600,
        "savefig.bbox":       "tight",
        "savefig.pad_inches": 0.05,
    }
    if minor_ticks:
        params.update({
            "xtick.minor.size": 2,
            "ytick.minor.size": 2,
        })
    mpl.rcParams.update(params)


# ─────────────────────────────────────────────────────────────────────────────
# Paleta e estilos
# ─────────────────────────────────────────────────────────────────────────────

# Paleta dinâmica de sensores — atribui estilo automaticamente a qualquer canal
SENSOR_COLORS  = ["#000000", "#800000", "#003366", "#2E8B57", "#8B008B",
                  "#B8860B", "#4B0082", "#006400", "#8B0000", "#00008B"]
SENSOR_MARKERS = ["o", "s", "^", "D", "v", "P", "X", "p", "h", "*"]
SENSOR_LINES   = ["-", "-", "-.", "--", "-", "-.", "--", "-", "-.", "--"]
_sensor_style_cache: dict = {}

# Estilo visual de cada gás: cor da linha, cor do fundo, rótulo
GAS_STYLE = {
    "AR":  {"color": "#7F7F7F", "bg": "#F5F5F5", "label": "Ar"},
    "N2":  {"color": "#4682B4", "bg": "#EFF6FF", "label": "N₂"},
    "CO2": {"color": "#C05621", "bg": "#FFF7ED", "label": "CO₂"},
}
DEFAULT_GAS_STYLE = {"color": "#7F7F7F", "bg": "#F5F5F5", "label": "?"}

# Estilo do painel de temperatura do Fluke
FLUKE_COLOR = "#B22222"

# Faixas alternadas (todas as vazões são do mesmo gás — alternar ajuda a ler)
BAND_COLORS = ["#EFF6FF", "#DCE9F7"]
BAND_LINE   = "#4682B4"


def get_sensor_style(channel: str) -> dict:
    """Retorna estilo (color, ls, marker) para um canal, atribuindo dinamicamente."""
    if channel not in _sensor_style_cache:
        idx = len(_sensor_style_cache)
        _sensor_style_cache[channel] = {
            "color":  SENSOR_COLORS[idx % len(SENSOR_COLORS)],
            "ls":     SENSOR_LINES[idx % len(SENSOR_LINES)],
            "marker": SENSOR_MARKERS[idx % len(SENSOR_MARKERS)],
        }
    return _sensor_style_cache[channel]


# ─────────────────────────────────────────────────────────────────────────────
# Carregamento de dados
# ─────────────────────────────────────────────────────────────────────────────

def load_sensor_csv(path: Path) -> pd.DataFrame:
    """Carrega o CSV de sensor processado (Time + canais), sem as unidades do cabeçalho."""
    df, _, _ = read_processed_csv(path)
    if "Time" not in df.columns:
        raise ValueError(f"Coluna 'Time' não encontrada em {path}.")
    return df


def load_gas_table(path: Path, sensor_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Carrega a tabela de eventos de gás.

    Formatos aceitos (detecção automática):

    1. **Antigo**:     ``GAS, SEGUNDOS``
       SEGUNDOS é o tempo absoluto de início de cada evento.

    2. **Novo**:       ``GAS, SM_INDEX, SEGUNDOS, OBSERVACOES``
       Se SM_INDEX preenchido, calcula SEGUNDOS via ``Time[SM_INDEX]``.
       Linhas podem ter apenas SM_INDEX, apenas SEGUNDOS, ou ambos.
       Requer ``sensor_df`` para resolver os índices.

    3. **Intervalo**:  ``GAS, INTERVALO_LITERAL, SEGUNDOS_DURACAO, OBSERVACAO``
       INTERVALO_LITERAL contém "inicio-fim" (ex.: "376-750").
       O tempo absoluto de início é extraído do lado esquerdo do traço.

    Colunas opcionais reconhecidas: ``TEMP_FLUKE_C`` (temperatura do Fluke
    por evento) e ``VAZAO_L_MIN`` (vazão do patamar).

    Em todos os casos, a coluna ``SEGUNDOS`` resultante contém o **tempo
    absoluto de início** de cada evento, e o resultado é ordenado por ela.
    """
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip()
    if "GAS" in df.columns:
        df["GAS"] = df["GAS"].str.strip().str.upper()

    # ── Formato 3: INTERVALO_LITERAL ──────────────────────────────────────
    if "INTERVALO_LITERAL" in df.columns:
        starts = []
        for interval in df["INTERVALO_LITERAL"].astype(str):
            parts = interval.split("-")
            try:
                starts.append(float(parts[0]))
            except (ValueError, IndexError):
                starts.append(np.nan)
        df["SEGUNDOS"] = starts

    # ── Formato 2: SM_INDEX (pode coexistir com SEGUNDOS) ─────────────────
    elif "SM_INDEX" in df.columns:
        df["SM_INDEX"] = pd.to_numeric(df["SM_INDEX"], errors="coerce")

        # Garante que a coluna SEGUNDOS exista
        if "SEGUNDOS" not in df.columns:
            df["SEGUNDOS"] = np.nan
        else:
            df["SEGUNDOS"] = pd.to_numeric(df["SEGUNDOS"], errors="coerce")

        mask = df["SM_INDEX"].notna()
        if mask.any():
            if sensor_df is None:
                raise ValueError(
                    "Tabela de gás usa SM_INDEX; é necessário passar o "
                    "DataFrame do sensor para resolver os índices."
                )
            time_arr = sensor_df["Time"].to_numpy()
            indices = df.loc[mask, "SM_INDEX"].astype(int).values
            max_idx = len(time_arr) - 1
            if np.any(indices > max_idx) or np.any(indices < 0):
                bad = indices[(indices > max_idx) | (indices < 0)]
                raise ValueError(
                    f"SM_INDEX fora do intervalo [0, {max_idx}]: {bad.tolist()}"
                )
            df.loc[mask, "SEGUNDOS"] = time_arr[indices]

    # ── Formato 1: apenas GAS, SEGUNDOS ──────────────────────────────────
    elif "SEGUNDOS" in df.columns:
        df["SEGUNDOS"] = pd.to_numeric(df["SEGUNDOS"], errors="coerce")

    # ── Validação final ───────────────────────────────────────────────────
    if "SEGUNDOS" not in df.columns or df["SEGUNDOS"].isna().any():
        missing = df[df["SEGUNDOS"].isna()] if "SEGUNDOS" in df.columns else df
        raise ValueError(
            f"Eventos de gás sem tempo definido (nem SM_INDEX, nem SEGUNDOS, "
            f"nem INTERVALO_LITERAL):\n{missing.to_string()}"
        )

    df["SEGUNDOS"] = df["SEGUNDOS"].astype(float)

    for col in ("TEMP_FLUKE_C", "VAZAO_L_MIN"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df.sort_values("SEGUNDOS").reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# Marcações de gás nos eixos
# ─────────────────────────────────────────────────────────────────────────────

def event_label(ev: dict) -> str:
    """Rótulo do intervalo: vazão (se disponível) ou nome do gás."""
    vazao = ev.get("VAZAO_L_MIN")
    if vazao is not None and not pd.isna(vazao):
        return f"{vazao:g} L/min"
    style = GAS_STYLE.get(ev.get("GAS", ""), DEFAULT_GAS_STYLE)
    return style["label"]


def shade_gas_intervals(
    axes: list,
    df_gas: pd.DataFrame,
    x_max: float,
    time_divisor: float = 1.0,
) -> None:
    """
    Pinta faixas verticais coloridas entre eventos consecutivos e adiciona
    uma linha vertical tracejada em cada transição de gás.
    """
    events = df_gas.to_dict("records")
    n_events = len(events)

    for k, ev in enumerate(events):
        t_start = ev["SEGUNDOS"] / time_divisor
        t_end = (
            events[k + 1]["SEGUNDOS"] / time_divisor
            if k + 1 < n_events
            else x_max
        )
        style = GAS_STYLE.get(ev.get("GAS", ""), DEFAULT_GAS_STYLE)

        for ax in axes:
            # Faixa de fundo semitransparente
            ax.axvspan(
                t_start, t_end,
                color=style["bg"], alpha=0.45, zorder=0, linewidth=0,
            )
            # Linha de transição
            ax.axvline(
                t_start,
                color=style["color"],
                linestyle="--",
                linewidth=0.9,
                alpha=0.85,
                zorder=2,
            )


def add_gas_labels_top(
    ax_top: plt.Axes,
    df_gas: pd.DataFrame,
    x_max: float,
    y_label: float,
    time_divisor: float = 1.0,
) -> None:
    """
    Adiciona rótulos dos gases (ou vazões) centralizados no intervalo, no
    topo do primeiro painel.
    """
    events = df_gas.to_dict("records")
    n_events = len(events)

    for k, ev in enumerate(events):
        t_start = ev["SEGUNDOS"] / time_divisor
        t_end = (
            events[k + 1]["SEGUNDOS"] / time_divisor
            if k + 1 < n_events
            else x_max
        )
        t_mid = (t_start + t_end) / 2.0
        style = GAS_STYLE.get(ev.get("GAS", ""), DEFAULT_GAS_STYLE)

        ax_top.text(
            t_mid, y_label,
            event_label(ev),
            transform=ax_top.get_xaxis_transform(),
            color=style["color"],
            fontsize=8.5,
            fontweight="bold",
            ha="center",
            va="bottom",
            rotation=90,
            clip_on=False,
        )
