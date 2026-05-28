import numpy as np
from typing import Tuple, List, Optional, Literal


def remove_null_values(
    time_array: np.ndarray,
    signals_array: np.ndarray,
    strategy: str = "remove",
    fill_value: Optional[float] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Removes or replaces null (NaN/Inf) values from sensor data.

    Parameters:
    - time_array: 1D numpy array of shape (n_samples,) containing time stamps.
    - signals_array: 2D numpy array of shape (n_samples, n_channels) containing
      raw sensor readings.
    - strategy: str, one of:
        * 'remove'  – drop every row that contains at least one NaN or Inf value
                      (default, safest option for time-series data).
        * 'forward' – propagate the last valid value forward (forward fill).
        * 'linear'  – linearly interpolate between surrounding valid values.
        * 'constant'– replace nulls with `fill_value` (requires fill_value != None).
    - fill_value: float, value used when strategy='constant'. Ignored otherwise.

    Returns:
    - clean_time: 1D numpy array with null rows removed / replaced.
    - clean_signals: 2D numpy array with null rows removed / replaced.

    Raises:
    - ValueError: if an unknown strategy is provided, or if fill_value is None
      when strategy='constant'.
    """
    valid_strategies = {"remove", "forward", "linear", "constant"}
    if strategy not in valid_strategies:
        raise ValueError(
            f"Unknown strategy '{strategy}'. Choose one of: {valid_strategies}."
        )
    if strategy == "constant" and fill_value is None:
        raise ValueError("fill_value must be provided when strategy='constant'.")

    time_array = np.asarray(time_array, dtype=float)
    signals_array = np.asarray(signals_array, dtype=float)

    # Identify rows containing NaN or Inf in either time or signals
    bad_in_time = ~np.isfinite(time_array)
    bad_in_signals = ~np.isfinite(signals_array).all(axis=1)
    bad_mask = bad_in_time | bad_in_signals  # True where row is invalid

    if not bad_mask.any():
        return time_array.copy(), signals_array.copy()

    # ── strategy: remove ─────────────────────────────────────────────────────
    if strategy == "remove":
        good_mask = ~bad_mask
        return time_array[good_mask], signals_array[good_mask]

    # ── strategies that keep the array shape ─────────────────────────────────
    clean_time = time_array.copy()
    clean_signals = signals_array.copy()

    if strategy == "constant":
        clean_time[bad_in_time] = fill_value
        clean_signals[bad_mask] = fill_value

    elif strategy == "forward":
        # Forward fill: copy previous valid value
        for idx in range(len(bad_mask)):
            if bad_mask[idx]:
                if idx == 0:
                    # No previous value – look for first valid row ahead
                    first_valid = np.argmax(~bad_mask)
                    clean_time[idx] = clean_time[first_valid]
                    clean_signals[idx] = clean_signals[first_valid]
                else:
                    clean_time[idx] = clean_time[idx - 1]
                    clean_signals[idx] = clean_signals[idx - 1]

    elif strategy == "linear":
        n = len(bad_mask)
        indices = np.arange(n)

        # Interpolate time
        valid = ~bad_in_time
        if valid.any():
            clean_time[bad_in_time] = np.interp(
                indices[bad_in_time], indices[valid], time_array[valid]
            )

        # Interpolate each channel independently
        for ch in range(signals_array.shape[1]):
            col = signals_array[:, ch]
            col_bad = ~np.isfinite(col)
            valid_ch = ~col_bad
            if valid_ch.any():
                clean_signals[col_bad, ch] = np.interp(
                    indices[col_bad], indices[valid_ch], col[valid_ch]
                )

    return clean_time, clean_signals


def report_null_summary(
    signals_array: np.ndarray,
    channels: Optional[List[str]] = None,
) -> dict:
    """
    Returns a summary of NaN/Inf counts per channel in the raw sensor array.

    Parameters:
    - signals_array: 2D numpy array of shape (n_samples, n_channels).
    - channels: optional list of channel names; defaults to ['CH0', 'CH1', ...].

    Returns:
    - summary: dict mapping channel name -> {'nan_count': int, 'inf_count': int,
               'total_bad': int, 'pct_bad': float}.
    """
    signals_array = np.asarray(signals_array, dtype=float)
    n_samples, n_channels = signals_array.shape

    if channels is None:
        channels = [f"CH{i}" for i in range(n_channels)]

    summary = {}
    for i, ch in enumerate(channels):
        col = signals_array[:, i]
        nan_count = int(np.isnan(col).sum())
        inf_count = int(np.isinf(col).sum())
        total_bad = nan_count + inf_count
        summary[ch] = {
            "nan_count": nan_count,
            "inf_count": inf_count,
            "total_bad": total_bad,
            "pct_bad": round(100.0 * total_bad / n_samples, 2),
        }

    return summary


# ─────────────────────────────────────────────────────────────────────────────
# Outlier detection & removal
# ─────────────────────────────────────────────────────────────────────────────

def detect_outliers(
    signals_array: np.ndarray,
    method: Literal["zscore", "iqr", "mad", "rolling"] = "mad",
    threshold: float = 3.5,
    window_size: int = 51,
) -> np.ndarray:
    """
    Returns a boolean mask indicating outlier positions in the signal array.

    Each method is applied **per channel** independently. A ``True`` value
    means that sample is considered an outlier in that channel.

    Parameters
    ----------
    signals_array : np.ndarray, shape (n_samples, n_channels)
        Raw or lightly pre-processed sensor readings.
    method : {'zscore', 'iqr', 'mad', 'rolling'}
        Detection algorithm:

        * ``'zscore'``  – flags samples whose absolute z-score exceeds
          ``threshold``. Assumes approximately Gaussian noise.
        * ``'iqr'``     – Tukey fences: flags samples outside
          ``[Q1 - threshold*IQR, Q3 + threshold*IQR]``.
          ``threshold`` is the fence multiplier (common value: 1.5).
        * ``'mad'``     – Modified z-score using the Median Absolute
          Deviation (Iglewicz & Hoaglin, 1993). Recommended for FBG
          data with isolated spikes; robust to the outliers themselves.
          Flags samples whose modified z-score exceeds ``threshold``
          (common value: 3.5).
        * ``'rolling'`` – Detects *local* outliers in a sliding window
          of ``window_size`` samples using the MAD criterion. Best for
          transient spikes that are large relative to their neighbourhood
          but not to the whole series.
    threshold : float
        Sensitivity threshold whose meaning depends on the chosen method
        (see above). Default is 3.5, suitable for ``'mad'``.
    window_size : int
        Half-window size used only by ``'rolling'``. Must be a positive odd
        integer. Default is 51.

    Returns
    -------
    outlier_mask : np.ndarray of bool, shape (n_samples, n_channels)
        ``True`` where a sample is flagged as an outlier.

    Raises
    ------
    ValueError
        If an unknown method is supplied or ``window_size`` is even / ≤ 0.
    """
    valid_methods = {"zscore", "iqr", "mad", "rolling"}
    if method not in valid_methods:
        raise ValueError(
            f"Unknown method '{method}'. Choose one of: {valid_methods}."
        )
    if method == "rolling":
        if window_size <= 0 or window_size % 2 == 0:
            raise ValueError("window_size must be a positive odd integer.")

    signals_array = np.asarray(signals_array, dtype=float)
    n_samples, n_channels = signals_array.shape
    outlier_mask = np.zeros((n_samples, n_channels), dtype=bool)

    for ch in range(n_channels):
        col = signals_array[:, ch]

        if method == "zscore":
            mu = np.nanmean(col)
            sigma = np.nanstd(col)
            if sigma == 0:
                continue
            outlier_mask[:, ch] = np.abs((col - mu) / sigma) > threshold

        elif method == "iqr":
            q1, q3 = np.nanpercentile(col, [25, 75])
            iqr = q3 - q1
            if iqr == 0:
                # Fallback: flag points beyond threshold * std from the mean
                sigma = np.nanstd(col)
                if sigma == 0:
                    continue
                mu = np.nanmean(col)
                outlier_mask[:, ch] = np.abs(col - mu) > threshold * sigma
            else:
                lower = q1 - threshold * iqr
                upper = q3 + threshold * iqr
                outlier_mask[:, ch] = (col < lower) | (col > upper)

        elif method == "mad":
            median = np.nanmedian(col)
            mad = np.nanmedian(np.abs(col - median))
            if mad == 0:
                # Fallback: use std-based z-score when MAD is zero
                # (nearly constant signal with isolated spikes)
                sigma = np.nanstd(col)
                if sigma == 0:
                    continue
                outlier_mask[:, ch] = np.abs((col - median) / sigma) > threshold
            else:
                # Iglewicz & Hoaglin modified z-score
                modified_z = 0.6745 * (col - median) / mad
                outlier_mask[:, ch] = np.abs(modified_z) > threshold

        elif method == "rolling":
            half = window_size // 2
            for i in range(n_samples):
                start = max(0, i - half)
                end = min(n_samples, i + half + 1)
                window = col[start:end]
                median = np.nanmedian(window)
                mad = np.nanmedian(np.abs(window - median))
                if mad == 0:
                    sigma = np.nanstd(window)
                    if sigma == 0:
                        continue
                    outlier_mask[i, ch] = abs(col[i] - median) / sigma > threshold
                else:
                    modified_z = abs(0.6745 * (col[i] - median) / mad)
                    outlier_mask[i, ch] = modified_z > threshold

    return outlier_mask


def remove_outliers(
    time_array: np.ndarray,
    signals_array: np.ndarray,
    method: Literal["zscore", "iqr", "mad", "rolling"] = "mad",
    threshold: float = 3.5,
    window_size: int = 51,
    strategy: Literal["remove", "linear", "forward", "constant"] = "linear",
    fill_value: Optional[float] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Detects and removes (or replaces) outliers in the sensor signal array.

    Detection is performed per-channel with ``detect_outliers()``. A row
    is considered *bad* if **any** channel is flagged as an outlier.
    Replacement follows the same strategies as ``remove_null_values()``.

    Compatible with ``OpticalPipeline.preprocess()``::

        pipeline.preprocess(remove_outliers, method='mad', threshold=3.5)

    Parameters
    ----------
    time_array : np.ndarray, shape (n_samples,)
        Time stamps associated with each sample row.
    signals_array : np.ndarray, shape (n_samples, n_channels)
        Sensor signal data.
    method : {'zscore', 'iqr', 'mad', 'rolling'}
        Outlier detection algorithm (see ``detect_outliers`` for details).
        ``'mad'`` (Modified Z-score) is recommended for FBG data.
    threshold : float
        Detection sensitivity. Default 3.5 works well with ``'mad'``.
        Use 1.5 for ``'iqr'`` and 2–3 for ``'zscore'``.
    window_size : int
        Only used when ``method='rolling'``. Must be a positive odd integer.
    strategy : {'remove', 'linear', 'forward', 'constant'}
        How to handle flagged rows:

        * ``'remove'``   – drop the row entirely (modifies time axis).
        * ``'linear'``   – interpolate from surrounding clean values
          **(recommended for FBG: preserves time axis and signal shape)**.
        * ``'forward'``  – forward-fill from the last clean value.
        * ``'constant'`` – replace with ``fill_value``.
    fill_value : float or None
        Required only when ``strategy='constant'``.

    Returns
    -------
    clean_time : np.ndarray, shape (n_clean,)
    clean_signals : np.ndarray, shape (n_clean, n_channels)

    Raises
    ------
    ValueError
        On unknown method / strategy, or missing fill_value.
    """
    valid_strategies = {"remove", "linear", "forward", "constant"}
    if strategy not in valid_strategies:
        raise ValueError(
            f"Unknown strategy '{strategy}'. Choose one of: {valid_strategies}."
        )
    if strategy == "constant" and fill_value is None:
        raise ValueError("fill_value must be provided when strategy='constant'.")

    time_array = np.asarray(time_array, dtype=float)
    signals_array = np.asarray(signals_array, dtype=float)

    outlier_mask = detect_outliers(
        signals_array,
        method=method,
        threshold=threshold,
        window_size=window_size,
    )

    # A row is bad if ANY channel is flagged
    bad_rows = outlier_mask.any(axis=1)

    if not bad_rows.any():
        return time_array.copy(), signals_array.copy()

    # ── strategy: remove ─────────────────────────────────────────────────────
    if strategy == "remove":
        good = ~bad_rows
        return time_array[good], signals_array[good]

    # ── strategies that preserve array shape ─────────────────────────────────
    clean_time = time_array.copy()
    clean_signals = signals_array.copy()

    if strategy == "constant":
        clean_signals[bad_rows] = fill_value

    elif strategy == "forward":
        for idx in range(len(bad_rows)):
            if bad_rows[idx]:
                if idx == 0:
                    first_valid = int(np.argmax(~bad_rows))
                    clean_signals[idx] = clean_signals[first_valid]
                else:
                    clean_signals[idx] = clean_signals[idx - 1]

    elif strategy == "linear":
        indices = np.arange(len(bad_rows))
        for ch in range(signals_array.shape[1]):
            # Interpolate only the channels that are actually outliers in each row
            bad_ch = outlier_mask[:, ch]
            valid_ch = ~bad_ch
            if bad_ch.any() and valid_ch.any():
                clean_signals[bad_ch, ch] = np.interp(
                    indices[bad_ch], indices[valid_ch], signals_array[valid_ch, ch]
                )

    return clean_time, clean_signals
