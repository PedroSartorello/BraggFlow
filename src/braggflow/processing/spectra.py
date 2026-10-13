"""
Preparo e análise de espectros ópticos, independente para cada arquivo.

Cada espectro carregado pode ter o seu próprio recorte de comprimento de onda,
suavização (Savitzky-Golay ou média móvel), normalização e deslocamento
vertical, sem interferir nos demais. :func:`analyse_spectrum` encontra os
máximos e mínimos e mede, para cada um, a posição refinada, a proeminência,
a largura (FWHM ou banda de 3 dB), o fator Q, o centroide e o espaçamento ao
vizinho (FSR local).
"""

from typing import List, Optional, Tuple

import numpy as np

from ..options import resolve_section
from .filters import apply_moving_average_filter, apply_savgol_filter

NORMALIZATIONS = ("none", "max", "minmax", "baseline")
SMOOTH_METHODS = ("savgol", "moving_average")
INTENSITY_SCALES = ("linear", "db")
AUTO_PROMINENCE = 0.05      # fração da faixa de intensidade quando não informada

# campo: (tipo, padrão, limites ou opções, nome exibido)
SPECTRUM_SPEC = {
    "lambda_min": ("float?", None, (0.0, None), "λ mínimo do espectro"),
    "lambda_max": ("float?", None, (0.0, None), "λ máximo do espectro"),
    "smooth_method": ("choice", "savgol", SMOOTH_METHODS, "Tipo de suavização"),
    "smooth_window": ("int?", None, (3, 100001), "Suavização (pontos)"),
    "smooth_order": ("int", 3, (1, 10), "Ordem da suavização"),
    "normalize": ("choice", "none", NORMALIZATIONS, "Normalização"),
    "offset": ("float", 0.0, None, "Deslocamento vertical"),
    # Picos e vales
    "find_max": ("bool", False, None, "Detectar máximos"),
    "find_min": ("bool", False, None, "Detectar mínimos"),
    "intensity_scale": ("choice", "linear", INTENSITY_SCALES, "Escala da intensidade"),
    "prominence": ("float?", None, (0.0, None), "Proeminência mínima"),
    "min_distance": ("float?", None, (0.0, None), "Distância mínima entre extremos"),
    "max_peaks": ("int", 10, (1, 500), "Máximo de extremos por tipo"),
}


def default_spectrum_settings() -> dict:
    return resolve_section(SPECTRUM_SPEC, {})


def resolve_spectrum_settings(user: Optional[dict] = None, prefix: str = "") -> dict:
    """Valida o preparo de um espectro e completa com os padrões."""
    return resolve_section(SPECTRUM_SPEC, user, prefix)


def smooth_spectrum(intensity: np.ndarray, window: Optional[int], order: int,
                    method: str = "savgol") -> np.ndarray:
    """
    Suaviza com janela em pontos: ``'savgol'`` (Savitzky-Golay, preserva a
    altura e a largura de picos estreitos melhor) ou ``'moving_average'``
    (média móvel centrada, sem deslocar os picos). Janela que não cabe no
    espectro é ignorada.
    """
    if not window:
        return intensity
    window = int(window)
    if method == "moving_average":
        if window > len(intensity):
            return intensity
        return apply_moving_average_filter(intensity.reshape(-1, 1), window)[:, 0]
    if method != "savgol":
        raise ValueError(f"Suavização desconhecida: {method}.")
    if window % 2 == 0:
        window += 1
    if window <= order or window > len(intensity):
        return intensity
    return apply_savgol_filter(intensity.reshape(-1, 1), window, order)[:, 0]


def normalize_spectrum(intensity: np.ndarray, mode: str) -> np.ndarray:
    """
    ``'max'`` divide pelo máximo, ``'minmax'`` leva a 0–1 e ``'baseline'``
    subtrai a mediana (útil para comparar formas de espectros).
    """
    if mode == "none":
        return intensity
    finite = intensity[np.isfinite(intensity)]
    if not len(finite):
        return intensity
    if mode == "max":
        peak = np.max(np.abs(finite))
        return intensity / peak if peak else intensity
    if mode == "minmax":
        low, high = float(finite.min()), float(finite.max())
        return (intensity - low) / (high - low) if high > low else intensity - low
    if mode == "baseline":
        return intensity - float(np.median(finite))
    raise ValueError(f"Normalização desconhecida: {mode}.")


def prepare_spectrum(wavelength: np.ndarray, intensity: np.ndarray,
                     settings: Optional[dict] = None) -> Tuple[np.ndarray, np.ndarray]:
    """
    Aplica recorte, suavização, normalização e deslocamento a um espectro.
    ``settings`` vem de :func:`resolve_spectrum_settings`.
    """
    settings = settings if settings and "normalize" in settings else resolve_spectrum_settings(settings)
    wavelength = np.asarray(wavelength, dtype=float)
    intensity = np.asarray(intensity, dtype=float)

    low = settings["lambda_min"]
    high = settings["lambda_max"]
    if low is not None or high is not None:
        if low is not None and high is not None and not low < high:
            raise ValueError("λ mínimo do espectro deve ser menor que λ máximo.")
        inside = np.ones(len(wavelength), dtype=bool)
        if low is not None:
            inside &= wavelength >= low
        if high is not None:
            inside &= wavelength <= high
        if inside.sum() < 2:
            raise ValueError("O recorte de comprimento de onda não deixou pontos suficientes.")
        wavelength, intensity = wavelength[inside], intensity[inside]

    intensity = smooth_spectrum(intensity, settings["smooth_window"], settings["smooth_order"],
                                settings["smooth_method"])
    intensity = normalize_spectrum(intensity, settings["normalize"])
    return wavelength, intensity + settings["offset"]


# ─────────────────────────────────────────────────────────────────────────────
# Picos e vales
# ─────────────────────────────────────────────────────────────────────────────

def _refine_vertex(wl: np.ndarray, z: np.ndarray, i: int) -> Tuple[float, float]:
    """
    Posição e valor do extremo com resolução abaixo do passo da grade:
    parábola pelos três pontos em torno do índice ``i`` (interpolação usual
    em OSA e interrogadores). Nas bordas devolve o próprio ponto.
    """
    if i <= 0 or i >= len(z) - 1:
        return float(wl[i]), float(z[i])
    a, b, c = z[i - 1], z[i], z[i + 1]
    curvatura = a - 2.0 * b + c
    if curvatura == 0 or not np.isfinite(curvatura):
        return float(wl[i]), float(b)
    delta = float(np.clip(0.5 * (a - c) / curvatura, -1.0, 1.0))
    passo = (wl[i + 1] - wl[i - 1]) / 2.0
    return float(wl[i] + delta * passo), float(b - 0.25 * (a - c) * delta)


def _crossing(wl: np.ndarray, z: np.ndarray, i: int, level: float,
              limit: int, step: int) -> Optional[float]:
    """λ onde ``z`` desce abaixo de ``level`` andando de ``i`` até ``limit``
    (interpolação linear entre as duas amostras); ``None`` se não descer."""
    k = i
    while k != limit:
        nxt = k + step
        if z[nxt] <= level:
            z0, z1 = z[k], z[nxt]
            frac = (z0 - level) / (z0 - z1) if z0 != z1 else 0.0
            return float(wl[k] + frac * (wl[nxt] - wl[k]))
        k = nxt
    return None


def analyse_spectrum(wavelength: np.ndarray, intensity: np.ndarray,
                     settings: Optional[dict] = None) -> dict:
    """
    Máximos e mínimos de um espectro já preparado.

    Para cada extremo: λ refinado (parábola de 3 pontos), intensidade,
    proeminência (altura do pico ou profundidade do vale em relação à
    vizinhança), largura, Q = λ/largura, centroide da região acima do nível
    da largura e espaçamento ao extremo anterior do mesmo tipo (FSR local).

    A largura é a FWHM (metade da proeminência) na escala linear; na escala
    em dB é a banda de 3 dB: 3 dB abaixo do pico ou acima do fundo do vale
    (fica vazia quando a proeminência não chega a 3 dB).

    ``summary`` traz o máximo e o mínimo globais, a resolução do espectro, a
    proeminência usada, a supressão do lóbulo lateral (diferença entre os
    dois maiores picos) e o FSR médio de cada tipo.
    """
    from scipy.signal import find_peaks

    settings = settings if settings and "find_max" in settings else resolve_spectrum_settings(settings)
    wl = np.asarray(wavelength, dtype=float)
    y = np.asarray(intensity, dtype=float)
    validos = np.isfinite(wl) & np.isfinite(y)
    wl, y = wl[validos], y[validos]

    summary = {"n_max": 0, "n_min": 0, "resolution": None, "prominence": None,
               "global_max": None, "global_min": None, "side_lobe_suppression": None,
               "fsr_max": None, "fsr_min": None, "scale": settings["intensity_scale"]}
    if len(y) < 5:
        return {"extrema": [], "summary": summary}

    summary["resolution"] = float(np.median(np.diff(wl)))
    i_max, i_min = int(np.argmax(y)), int(np.argmin(y))
    summary["global_max"] = {"wavelength": float(wl[i_max]), "intensity": float(y[i_max])}
    summary["global_min"] = {"wavelength": float(wl[i_min]), "intensity": float(y[i_min])}

    tipos = [t for t, ligado in (("max", settings["find_max"]), ("min", settings["find_min"])) if ligado]
    faixa = float(np.ptp(y))
    if not tipos or faixa == 0:
        return {"extrema": [], "summary": summary}

    prominencia = settings["prominence"]
    if prominencia is None:
        prominencia = AUTO_PROMINENCE * faixa
    summary["prominence"] = float(prominencia)
    distancia = None
    if settings["min_distance"]:
        distancia = max(1, int(round(settings["min_distance"] / abs(summary["resolution"]))))

    db = settings["intensity_scale"] == "db"
    extremos: List[dict] = []
    for tipo in tipos:
        sinal = 1.0 if tipo == "max" else -1.0
        z = sinal * y                      # vale vira pico: o mesmo código mede os dois
        indices, props = find_peaks(z, prominence=prominencia, distance=distancia)
        if not len(indices):
            continue
        mais_fortes = np.argsort(-props["prominences"])[:settings["max_peaks"]]
        mais_fortes = mais_fortes[np.argsort(indices[mais_fortes])]   # em ordem de λ

        do_tipo = []
        for j in mais_fortes:
            i, prom = int(indices[j]), float(props["prominences"][j])
            esq_lim, dir_lim = int(props["left_bases"][j]), int(props["right_bases"][j])
            lam, pico = _refine_vertex(wl, z, i)

            queda = 3.0 if db else prom / 2.0
            nivel = pico - queda
            esquerda = dir_ = None
            if not db or prom >= 3.0:
                esquerda = _crossing(wl, z, i, nivel, esq_lim, -1)
                dir_ = _crossing(wl, z, i, nivel, dir_lim, +1)
            largura = (dir_ - esquerda) if esquerda is not None and dir_ is not None else None

            centroide = None
            if largura:
                dentro = (wl >= esquerda) & (wl <= dir_)
                pesos = np.clip(z[dentro] - nivel, 0.0, None)
                if pesos.sum() > 0:
                    centroide = float(np.sum(wl[dentro] * pesos) / pesos.sum())

            do_tipo.append({
                "type": tipo,
                "wavelength": lam,
                "intensity": sinal * pico,
                "prominence": prom,
                "fwhm": largura,
                "left": esquerda,
                "right": dir_,
                "level": sinal * nivel,
                "q": abs(lam / largura) if largura else None,
                "centroid": centroide,
                "spacing": None,
            })
        for anterior, atual in zip(do_tipo, do_tipo[1:]):
            atual["spacing"] = atual["wavelength"] - anterior["wavelength"]
        espacos = [e["spacing"] for e in do_tipo if e["spacing"] is not None]
        summary[f"n_{tipo}"] = len(do_tipo)
        summary[f"fsr_{tipo}"] = float(np.mean(espacos)) if espacos else None
        extremos += do_tipo

    picos = sorted((e["intensity"] for e in extremos if e["type"] == "max"), reverse=True)
    if len(picos) >= 2:
        summary["side_lobe_suppression"] = picos[0] - picos[1]
    extremos.sort(key=lambda e: e["wavelength"])
    return {"extrema": extremos, "summary": summary}
