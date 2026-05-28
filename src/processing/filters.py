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
    
    filtered_signals = np.empty_like(signals)
    
    for i in range(signals.shape[1]):  # Apply filter to each channel
        filtered_signals[:, i] = savgol_filter(signals[:, i], window_length, polyorder)
    
    return filtered_signals

def apply_moving_average_filter(signals: np.ndarray, window_size: int) -> np.ndarray:
    """
    Applies a moving average filter to the input signals.

    Uses a cumulative sum approach to correctly compute the moving average
    without zero-padding at the borders. Border samples are averaged over
    the available (real) data points only.
    
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

    filtered_signals = np.empty_like(signals, dtype=float)

    for i in range(signals.shape[1]):  # Apply filter to each channel
        channel = signals[:, i].astype(float)
        cumsum = np.cumsum(channel)

        # Full windows: indices [window_size-1 .. n_samples-1]
        filtered_signals[window_size - 1:, i] = (
            cumsum[window_size - 1:]
            - np.concatenate([[0.0], cumsum[: n_samples - window_size]])
        ) / window_size

        # Leading edge: average over the first 1..window_size-1 real samples
        for j in range(window_size - 1):
            filtered_signals[j, i] = cumsum[j] / (j + 1)

    return filtered_signals

def detrend_signal(signals: np.ndarray) -> np.ndarray:
    """
    Removes the linear trend from the input signals.
    
    Parameters:
    - signals: 2D numpy array of shape (n_samples, n_channels) containing the signal data.
    
    Returns:
    - detrended_signals: 2D numpy array of the same shape as input containing the detrended signals.
    """
    from scipy.signal import detrend
    
    detrended_signals = np.empty_like(signals)
    
    for i in range(signals.shape[1]):  # Apply detrending to each channel
        detrended_signals[:, i] = detrend(signals[:, i])
    
    return detrended_signals