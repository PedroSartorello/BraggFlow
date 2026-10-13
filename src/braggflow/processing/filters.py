import numpy as np

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
    over the available (real) data points only.

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

    # cumsum[k] = sum of the first k samples of each channel
    cumsum = np.zeros((n_samples + 1, signals.shape[1]))
    np.cumsum(signals.astype(float), axis=0, out=cumsum[1:])

    idx = np.arange(n_samples)
    lo = np.maximum(idx - (window_size - 1) // 2, 0)
    hi = np.minimum(idx + window_size // 2 + 1, n_samples)

    return (cumsum[hi] - cumsum[lo]) / (hi - lo)[:, None]

def detrend_signal(signals: np.ndarray) -> np.ndarray:
    """
    Removes the linear trend from the input signals.
    
    Parameters:
    - signals: 2D numpy array of shape (n_samples, n_channels) containing the signal data.
    
    Returns:
    - detrended_signals: 2D numpy array of the same shape as input containing the detrended signals.
    """
    from scipy.signal import detrend

    detrended_signals = np.empty_like(signals, dtype=float)

    for i in range(signals.shape[1]):  # Apply detrending to each channel
        detrended_signals[:, i] = detrend(signals[:, i].astype(float))

    return detrended_signals


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
