"""
Espectros LMR sintéticos no formato do OceanView/SpectraSuite, para os testes.

Transmissão (%) com linha de base inclinada e uma ressonância (vale
lorentziano) que se desloca de arquivo para arquivo; ou os três espectros
brutos (amostra, fonte e ruído de fundo) que dão essa transmissão.
"""

from datetime import datetime
from pathlib import Path

import numpy as np

WAVELENGTH = np.round(np.arange(199.949, 997.0, 0.7724), 3)
DARK_COUNTS = 1200.0


def transmission(resonance_nm: float, depth: float = 4.0, width: float = 40.0,
                 noise: float = 0.05, seed: int = 0) -> np.ndarray:
    """T (%) com base de 13% a 27% e um vale de ``depth`` pontos em ``resonance_nm``."""
    base = 13.0 + 0.0175 * (WAVELENGTH - 200.0)
    vale = depth / (1.0 + ((WAVELENGTH - resonance_nm) / (width / 2.0)) ** 2)
    return base - vale + np.random.default_rng(seed).normal(0.0, noise, WAVELENGTH.size)


def source_counts() -> np.ndarray:
    """Fonte halógena: curva larga, com o fundo somado."""
    return DARK_COUNTS + 40000.0 * np.exp(-((WAVELENGTH - 650.0) / 260.0) ** 2) + 500.0


def sample_counts(t_percent: np.ndarray) -> np.ndarray:
    """Contagens brutas da amostra que dão a transmissão ``t_percent``."""
    return DARK_COUNTS + (source_counts() - DARK_COUNTS) * t_percent / 100.0


def write_oceanview(path: Path, intensity: np.ndarray, when: datetime | None = None,
                    header: bool = True) -> Path:
    """Grava como o OceanView: cabeçalho, linha em branco, vírgula decimal, CRLF."""
    path = Path(path)
    linhas = []
    if header:
        when = when or datetime(2026, 3, 2, 9, 30, 15)
        dias = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
        meses = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
        linhas += [
            f"Data from {path.name} Node", "",
            f"Date: {dias[when.weekday()]} {meses[when.month - 1]} {when.day:02d} "
            f"{when:%H:%M:%S} BRT {when.year}",
            "User: SINTETICO", "Spectrometer: XXX0000", "Trigger mode: 4",
            "Integration Time (sec): 3,000000E-2", "Scans to average: 5",
            "Electric dark correction enabled: true", "Nonlinearity correction enabled: true",
            "Boxcar width: 0", "XAxis mode: Wavelengths",
            f"Number of Pixels in Spectrum: {WAVELENGTH.size}",
            ">>>>>Begin Spectral Data<<<<<",
        ]
    linhas += [f"{w:.3f}\t{y:.5f}".replace(".", ",") for w, y in zip(WAVELENGTH, intensity)]
    path.write_bytes(("\r\n".join(linhas) + "\r\n").encode("utf-8"))
    return path


def lmr_series(folder: Path, resonances=(870.0, 868.0, 780.0, 778.0), header: bool = True,
               start=datetime(2026, 3, 2, 9, 30, 15), step_s: float = 75.5) -> list[Path]:
    """Uma série de arquivos ``amostra_Transmission__NN__HH-MM-SS-mmm.txt``, um por ressonância."""
    from datetime import timedelta

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    caminhos = []
    for i, lam in enumerate(resonances):
        quando = start + timedelta(seconds=i * step_s)
        nome = f"amostra_Transmission__{1 + i:02d}__{quando:%H-%M-%S}-{quando.microsecond // 1000:03d}.txt"
        caminhos.append(write_oceanview(folder / nome, transmission(lam, seed=i), quando, header))
    return caminhos
