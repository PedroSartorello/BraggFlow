"""
Binários do catman (HBM, ``.BIN``) sintéticos, para os testes.

Seguem o arranjo de um espectro gravado do FS22 pelo catman: identificador
5012, o deslocamento dos dados, um comentário, 32 textos reservados, o
cabeçalho de cada canal ("Spectrum CH1" em dB, "Wavelength CH1" em nm) e os
valores em float64, um canal após o outro. Os campos do cabeçalho que o
leitor não usa vão zerados.
"""

import struct
from datetime import datetime
from pathlib import Path

import numpy as np

OLE_EPOCH = datetime(1899, 12, 30)


def _text(valor: str) -> bytes:
    dados = valor.encode("cp1252")
    return struct.pack("<h", len(dados)) + dados


def fbg_spectrum(n: int = 4000, peaks=(1530.0, 1550.0), seed: int = 0):
    """Eixo de 1510 a 1590 nm e reflexão (dB) com um pico de FBG em cada ``peaks``."""
    wavelength = np.linspace(1510.0, 1590.0, n, endpoint=False)
    reflexao = 12.0 + np.random.default_rng(seed).normal(0.0, 0.2, n)
    for pico in peaks:
        reflexao += 28.0 * np.exp(-((wavelength - pico) / 0.12) ** 2)
    return wavelength, reflexao


def catman_bytes(channels, when: datetime = datetime(2026, 3, 2, 9, 30, 15),
                 file_id: int = 5012, width: int = 8) -> bytes:
    """``channels``: ``[(nome, unidade, valores), ...]`` → o arquivo .BIN inteiro."""
    dias = (when - OLE_EPOCH).total_seconds() / 86400.0
    inicio = struct.pack("<h", file_id)
    corpo = _text("") + _text("binário sintético") + b"".join(_text(" ") for _ in range(31))
    corpo += struct.pack("<hi", len(channels), max(len(v) for _, _, v in channels))
    # O índice aponta o número de valores de cada canal (o que o catman
    # atualiza enquanto grava); os cabeçalhos vêm logo depois dele
    base = len(inicio) + 4 + len(corpo) + 4 * len(channels) + 4
    cabecalhos, indice = b"", []
    for i, (nome, unidade, valores) in enumerate(channels):
        local = struct.pack("<h", i)
        indice.append(base + len(cabecalhos) + len(local))
        cabecalhos += (local + struct.pack("<i", len(valores)) + _text(nome) + _text(unidade) + _text("")
                       + struct.pack("<hhd", 0, width, dias) + struct.pack("<i", 148) + bytes(148)
                       + bytes(64))
    corpo += b"".join(struct.pack("<i", o) for o in indice) + struct.pack("<i", 0) + cabecalhos
    dados_em = -(-(len(inicio) + 4 + len(corpo)) // 512) * 512
    cabeca = inicio + struct.pack("<i", dados_em) + corpo
    cabeca += bytes(dados_em - len(cabeca))
    tipo = "<f8" if width == 8 else "<f4"
    valores = b"".join(np.asarray(v, dtype=tipo).tobytes() for _, _, v in channels)
    return cabeca + valores + bytes(512)


def fs22_spectrum(folder: Path, name: str = "espectro.BIN", **kwargs) -> Path:
    """Um espectro do FS22 como o catman grava: Spectrum CH1 (dB) e Wavelength CH1 (nm)."""
    when = kwargs.pop("when", datetime(2026, 3, 2, 9, 30, 15))
    wavelength, reflexao = fbg_spectrum(**kwargs)
    path = Path(folder) / name
    path.write_bytes(catman_bytes([("Spectrum CH1", "db", reflexao),
                                   ("Wavelength CH1", "nm", wavelength)], when=when))
    return path
