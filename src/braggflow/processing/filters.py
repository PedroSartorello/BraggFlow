from typing import Sequence

import numpy as np

from ..i18n import tr


def apply_savgol_filter(signals: np.ndarray, window_length: int, polyorder: int) -> np.ndarray:
    """
    Applies the Savitzky-Golay filter to the input signals.
    
    Parameters:
    - signals: 2D numpy array of shape (n_samples, n_channels) containing the signal data.
    - window_length: int, the length of the filter window (must be a positive odd integer).
    - polyorder: int, the order of the polynomial used to fit the samples (must be less than window_length).
    
    Returns:
    - filtered_signals: 2D numpy array of the same shape as input containing the filtered signals.
    """
    from scipy.signal import savgol_filter
    
    if window_length % 2 == 0 or window_length <= 0:
        raise ValueError("window_length must be a positive odd integer.")
    if polyorder >= window_length:
        raise ValueError("polyorder must be less than window_length.")

    filtered_signals = np.empty_like(signals, dtype=float)

    for i in range(signals.shape[1]):  # Apply filter to each channel
        filtered_signals[:, i] = savgol_filter(signals[:, i].astype(float), window_length, polyorder)

    return filtered_signals

def apply_moving_average_filter(signals: np.ndarray, window_size: int) -> np.ndarray:
    """
    Applies a centred moving average filter to the input signals.

    Each output sample is the mean of the ``window_size`` samples centred on
    it, so the filter introduces no time lag (for an even ``window_size`` the
    window extends one sample further forward, a half-sample offset).
    Uses a cumulative sum without zero-padding: border samples are averaged
    over the available (real) data points only. Missing samples (NaN) stay
    missing and are left out of their neighbours' windows, so one lost
    reading does not blank the rest of the channel.

    Parameters:
    - signals: 2D numpy array of shape (n_samples, n_channels) containing the signal data.
    - window_size: int, the size of the moving average window (must be a positive integer).

    Returns:
    - filtered_signals: 2D numpy array of the same shape as input containing the filtered signals.
    """
    if window_size <= 0:
        raise ValueError("window_size must be a positive integer.")

    n_samples = signals.shape[0]
    if window_size > n_samples:
        raise ValueError("window_size must not be greater than the number of samples.")

    # Sums and counts of the valid samples: cumsum[k] = sum of the first k
    values = signals.astype(float)
    valid = np.isfinite(values)
    cumsum = np.zeros((n_samples + 1, signals.shape[1]))
    counts = np.zeros((n_samples + 1, signals.shape[1]))
    np.cumsum(np.where(valid, values, 0.0), axis=0, out=cumsum[1:])
    np.cumsum(valid, axis=0, out=counts[1:])

    idx = np.arange(n_samples)
    lo = np.maximum(idx - (window_size - 1) // 2, 0)
    hi = np.minimum(idx + window_size // 2 + 1, n_samples)

    with np.errstate(invalid="ignore", divide="ignore"):
        mean = (cumsum[hi] - cumsum[lo]) / (counts[hi] - counts[lo])
    return np.where(valid, mean, np.nan)    # a valid sample is in its own window: never 0/0


def estimate_sampling_rate(time_array: np.ndarray) -> float:
    """
    Estimates the sampling frequency (in Hz, assuming ``time_array`` is in
    seconds) as the inverse of the median interval between samples. The
    median keeps the estimate robust to a few gaps left by row removal.
    """
    time_array = np.asarray(time_array, dtype=float)
    if len(time_array) < 2:
        raise ValueError("At least two samples are needed to estimate fs.")
    dt = np.median(np.diff(time_array))
    if not np.isfinite(dt) or dt <= 0:
        raise ValueError("Time axis must be strictly increasing to estimate fs.")
    return float(1.0 / dt)


def _apply_butterworth(
    signals: np.ndarray,
    fs: float,
    cutoff: float,
    order: int,
    btype: str,
) -> np.ndarray:
    """Shared validation + zero-phase SOS Butterworth filtering."""
    from scipy.signal import butter, sosfiltfilt

    if fs <= 0:
        raise ValueError("fs must be a positive number.")
    if order <= 0:
        raise ValueError("order must be a positive integer.")
    nyquist = fs / 2.0
    if not (0 < cutoff < nyquist):
        raise ValueError(
            f"cutoff must be in (0, fs/2) = (0, {nyquist}). Got {cutoff}."
        )

    sos = butter(order, cutoff / nyquist, btype=btype, output="sos")
    filtered_signals = np.empty_like(signals, dtype=float)

    for i in range(signals.shape[1]):
        filtered_signals[:, i] = sosfiltfilt(sos, signals[:, i].astype(float))

    return filtered_signals


def apply_lowpass_filter(
    signals: np.ndarray,
    fs: float,
    cutoff: float = 20.0,
    order: int = 4,
) -> np.ndarray:
    """
    Applies a zero-phase Butterworth low-pass filter to the input signals.

    Frequencies **below** ``cutoff`` are preserved; frequencies above are
    attenuated. Uses second-order sections (SOS) with ``sosfiltfilt`` for
    forward-backward (zero-phase) filtering, which avoids phase distortion
    and is numerically more stable than the direct ``ba`` form.

    Parameters
    ----------
    signals : np.ndarray, shape (n_samples, n_channels)
        Signal data to filter.
    fs : float
        Sampling frequency in Hz. Must match the acquisition rate of the
        instrument (e.g. 100.0 for a 100 Hz interrogator).
    cutoff : float
        Cutoff frequency in Hz. Default is **20 Hz**. Because the filter is
        applied forward and backward, the attenuation at ``cutoff`` is
        -6 dB (not the -3 dB of a single pass).
        Must satisfy ``0 < cutoff < fs / 2`` (Nyquist limit).
    order : int
        Butterworth filter order. Higher order → steeper roll-off but
        greater ringing risk. Default is 4.

    Returns
    -------
    filtered_signals : np.ndarray, shape (n_samples, n_channels)

    Raises
    ------
    ValueError
        If ``cutoff`` is outside ``(0, fs/2)``, ``fs <= 0``, or
        ``order <= 0``.
    """
    return _apply_butterworth(signals, fs, cutoff, order, btype="low")


def apply_highpass_filter(
    signals: np.ndarray,
    fs: float,
    cutoff: float = 5.0,
    order: int = 4,
) -> np.ndarray:
    """
    Applies a zero-phase Butterworth high-pass filter to the input signals.

    Frequencies **above** ``cutoff`` are preserved; frequencies below are
    attenuated. Uses second-order sections (SOS) with ``sosfiltfilt`` for
    forward-backward (zero-phase) filtering, which avoids phase distortion
    and is numerically more stable than the direct ``ba`` form.

    Parameters
    ----------
    signals : np.ndarray, shape (n_samples, n_channels)
        Signal data to filter.
    fs : float
        Sampling frequency in Hz. Must match the acquisition rate of the
        instrument.
    cutoff : float
        Cutoff frequency in Hz (-6 dB, see ``apply_lowpass_filter``).
        Default is **5 Hz**. Removes the static level: use only for dynamic
        measurements (vibration, acoustics), never for quasi-static ones.
        Must satisfy ``0 < cutoff < fs / 2`` (Nyquist limit).
    order : int
        Butterworth filter order. Default is 4.

    Returns
    -------
    filtered_signals : np.ndarray, shape (n_samples, n_channels)

    Raises
    ------
    ValueError
        If ``cutoff`` is outside ``(0, fs/2)``, ``fs <= 0``, or
        ``order <= 0``.
    """
    return _apply_butterworth(signals, fs, cutoff, order, btype="high")


# A high-pass removes the static level: the output is a variation, not an
# absolute wavelength.
apply_highpass_filter.output_quantity = "wavelength_shift"


def choose_savgol(curves: Sequence[np.ndarray], orders: Sequence[int] = (2, 4),
                  max_window: int = 1001, n_windows: int = 30) -> dict:
    """
    Savitzky-Golay window and order chosen from the data by leave-one-out
    cross-validation: the pair that best predicts each sample from its
    neighbours. The filter is linear, so the leave-one-out error of a sample
    comes straight from the filtered curve, ``(y - y_hat) / (1 - h0)`` with
    ``h0`` the centre weight of the kernel; nothing is refitted.

    Odd windows from ``min(orders) + 3`` up to ``max_window`` (and a quarter
    of the shortest curve) are tried on a geometric grid, with each order in
    ``orders``. Only even orders are worth trying: for smoothing, order 3 gives
    the same filter as order 2. Order 0 is the moving average. With several
    curves (channels, traces) each error is divided by that curve's smallest
    one, so every curve weighs the same; missing samples (NaN) are bridged for
    the convolution and their neighbourhood is left out of the score.

    Assumes noise uncorrelated from one sample to the next; with correlated
    noise (resampling, interpolation) the window comes out too short.

    References: Savitzky & Golay (1964), Anal. Chem. 36, 1627; Krishnan &
    Seelamantula (2013), IEEE Trans. Signal Process. 61, 380 (MSE-optimal
    S-G filters).

    Returns ``{"window", "order", "tried"}``.
    """
    from scipy.signal import oaconvolve, savgol_coeffs

    curvas = [np.asarray(c, dtype=float) for c in curves]
    curvas = [c for c in curvas if np.isfinite(c).sum() >= 10]
    if not curvas:
        raise ValueError(tr("filters.autoNoData"))
    menor_janela = min(orders) + 3 + (min(orders) % 2)        # odd and > order + 1 (h0 < 1)
    curta = min(len(c) for c in curvas)
    maior = min(int(max_window), curta // 4)
    maior -= 1 - maior % 2
    if maior < menor_janela:
        raise ValueError(tr("filters.autoTooShort", n=curta, needed=4 * menor_janela))
    janelas = sorted({int(j) // 2 * 2 + 1 for j in np.geomspace(menor_janela, maior, n_windows)})

    # The same samples score every window: without the edges of the largest
    # one and without the neighbourhood of missing samples
    preparadas = []
    for c in curvas:
        valido = np.isfinite(c)
        usar = np.zeros(len(c), dtype=bool)
        usar[maior // 2:len(c) - maior // 2] = True
        if not valido.all():
            indice = np.arange(len(c))
            c = np.interp(indice, indice[valido], c[valido])
            usar &= oaconvolve((~valido).astype(float), np.ones(maior), mode="same") < 0.5
        preparadas.append((c, usar))

    candidatos, erros = [], []
    for ordem in orders:
        for janela in janelas:
            if janela < ordem + 3:
                continue
            kernel = savgol_coeffs(janela, ordem)
            h0 = kernel[janela // 2]
            linha = []
            for c, usar in preparadas:
                residuo = (c - oaconvolve(c, kernel, mode="same"))[usar] / (1.0 - h0)
                linha.append(np.mean(residuo ** 2) if len(residuo) else np.nan)
            candidatos.append((janela, ordem))
            erros.append(linha)

    erros = np.array(erros)                                   # candidate × curve
    with np.errstate(invalid="ignore", divide="ignore"):
        relativos = erros / np.nanmin(erros, axis=0)
    relativos = relativos[:, np.isfinite(relativos).any(axis=0)]
    if not relativos.size:
        raise ValueError(tr("filters.autoNoData"))
    janela, ordem = candidatos[int(np.nanargmin(np.nanmean(relativos, axis=1)))]
    return {"window": int(janela), "order": int(ordem), "tried": len(candidatos)}


def savgol_cutoff(window: int, order: int) -> float:
    """-3 dB cut-off of a Savitzky-Golay smoothing filter, in cycles per sample (0-0.5)."""
    from scipy.signal import freqz, savgol_coeffs

    freq, resposta = freqz(savgol_coeffs(window, order), worN=1 << 15, fs=1.0)
    abaixo = np.flatnonzero(np.abs(resposta) < 10 ** (-3 / 20))
    return float(freq[abaixo[0]]) if len(abaixo) else 0.5
