import warnings

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

    The shape-preserving strategies ('forward', 'linear', 'constant') are
    applied **per channel**: valid readings in other channels of the same row
    are never overwritten. Invalid timestamps are always repaired by linear
    interpolation over the sample index, regardless of strategy, so the time
    axis stays monotonic.

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

    indices = np.arange(len(bad_mask))

    # Time axis: a corrupted timestamp is always repaired by linear
    # interpolation over the sample index — filling it with a constant or the
    # previous timestamp would break the monotonic time axis.
    if bad_in_time.any():
        valid_t = ~bad_in_time
        if valid_t.any():
            clean_time[bad_in_time] = np.interp(
                indices[bad_in_time], indices[valid_t], time_array[valid_t]
            )

    # Signals: apply the strategy per channel so that valid readings in other
    # channels of the same row are preserved.
    for ch in range(signals_array.shape[1]):
        col = signals_array[:, ch]
        col_bad = ~np.isfinite(col)
        valid_ch = ~col_bad
        if not col_bad.any() or not valid_ch.any():
            continue

        if strategy == "constant":
            clean_signals[col_bad, ch] = fill_value

        elif strategy == "forward":
            clean_signals[:, ch] = _forward_fill(col, valid_ch)

        elif strategy == "linear":
            clean_signals[col_bad, ch] = np.interp(
                indices[col_bad], indices[valid_ch], col[valid_ch]
            )

    return clean_time, clean_signals


def _forward_fill(col: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """
    Vectorized forward fill of a single channel: each invalid sample takes the
    last valid value before it; leading invalid samples are back-filled from
    the first valid one. ``valid`` must have at least one True entry.
    """
    indices = np.arange(len(col))
    last_valid = np.maximum.accumulate(np.where(valid, indices, -1))
    first_valid = int(np.argmax(valid))
    last_valid[last_valid == -1] = first_valid
    return col[last_valid]


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
    method: Literal["zscore", "iqr", "mad", "rolling"] = "rolling",
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

        .. warning::
           ``'zscore'``, ``'iqr'`` and ``'mad'`` are **global**: they compare
           every sample with statistics of the whole channel. A genuine level
           change that lasts for a large part of the recording (e.g. the
           Bragg shift during gas exposure) is flagged as outliers and then
           erased by the replacement strategy. Prefer ``'rolling'`` for FBG
           acquisitions with real responses.

        * ``'zscore'``  – flags samples whose absolute z-score exceeds
          ``threshold``. Assumes approximately Gaussian noise.
        * ``'iqr'``     – Tukey fences: flags samples outside
          ``[Q1 - threshold*IQR, Q3 + threshold*IQR]``.
          ``threshold`` is the fence multiplier (common value: 1.5).
        * ``'mad'``     – Modified z-score using the Median Absolute
          Deviation (Iglewicz & Hoaglin, 1993) over the whole channel.
          Robust to the outliers themselves, but only suitable for signals
          without sustained level changes.
          Flags samples whose modified z-score exceeds ``threshold``
          (common value: 3.5).
        * ``'rolling'`` – Detects *local* outliers in a sliding window
          of ``window_size`` samples using the MAD criterion. Best for
          transient spikes that are large relative to their neighbourhood
          but not to the whole series. **Default**: preserves real level
          changes, since each sample is judged only against its neighbours.
    threshold : float
        Sensitivity threshold whose meaning depends on the chosen method
        (see above). Default is 3.5, suitable for ``'mad'`` and ``'rolling'``.
    window_size : int
        Full window length (in samples, centred on each sample) used only by
        ``'rolling'``. Must be a positive odd integer. Default is 51.

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
            outlier_mask[:, ch] = _rolling_outlier_mask(col, window_size, threshold)

    return outlier_mask


def _rolling_outlier_mask(
    col: np.ndarray,
    window_size: int,
    threshold: float,
    chunk_size: int = 20000,
) -> np.ndarray:
    """
    Vectorized local MAD criterion for a single channel.

    Each sample is compared with the ``window_size`` samples centred on it
    (truncated at the borders). Falls back to the window standard deviation
    when the MAD is zero, and never flags a sample whose window is constant.
    Processed in chunks to bound memory use on long acquisitions.
    """
    n_samples = len(col)
    half = window_size // 2
    # NaN padding makes the border windows behave as truncated windows,
    # since every statistic below ignores NaN.
    padded = np.pad(col, half, constant_values=np.nan)
    windows = np.lib.stride_tricks.sliding_window_view(padded, window_size)

    mask = np.zeros(n_samples, dtype=bool)
    for start in range(0, n_samples, chunk_size):
        w = windows[start:start + chunk_size]
        x = col[start:start + chunk_size]

        median = _row_stat(w, np.median, np.nanmedian)
        mad = _row_stat(np.abs(w - median[:, None]), np.median, np.nanmedian)
        sigma = _row_stat(w, np.std, np.nanstd)

        deviation = np.abs(x - median)
        with np.errstate(divide="ignore", invalid="ignore"):
            score = np.where(mad > 0, 0.6745 * deviation / mad, deviation / sigma)
        # NaN scores (constant window or NaN sample) compare as False
        mask[start:start + chunk_size] = score > threshold

    return mask


def _row_stat(windows: np.ndarray, func, nan_func) -> np.ndarray:
    """
    Row-wise statistic using the fast ``func`` for rows without NaN and the
    NaN-aware ``nan_func`` only where needed (borders / missing samples).
    """
    has_nan = np.isnan(windows).any(axis=1)
    out = np.full(len(windows), np.nan)
    if (~has_nan).any():
        out[~has_nan] = func(windows[~has_nan], axis=1)
    if has_nan.any():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN windows
            out[has_nan] = nan_func(windows[has_nan], axis=1)
    return out


def remove_outliers(
    time_array: np.ndarray,
    signals_array: np.ndarray,
    method: Literal["zscore", "iqr", "mad", "rolling"] = "rolling",
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

        pipeline.preprocess(remove_outliers, method='rolling', threshold=3.5)

    Parameters
    ----------
    time_array : np.ndarray, shape (n_samples,)
        Time stamps associated with each sample row.
    signals_array : np.ndarray, shape (n_samples, n_channels)
        Sensor signal data.
    method : {'zscore', 'iqr', 'mad', 'rolling'}
        Outlier detection algorithm (see ``detect_outliers`` for details).
        ``'rolling'`` (local modified z-score, default) is recommended for
        FBG data: the global methods erase sustained real responses.
    threshold : float
        Detection sensitivity. Default 3.5 works well with ``'rolling'``
        and ``'mad'``.
        Use 1.5 for ``'iqr'`` and 2–3 for ``'zscore'``.
    window_size : int
        Only used when ``method='rolling'``. Must be a positive odd integer.
    strategy : {'remove', 'linear', 'forward', 'constant'}
        How to handle flagged samples:

        * ``'remove'``   – drop the whole row if **any** channel is flagged
          (modifies time axis).
        * ``'linear'``   – interpolate from surrounding clean values
          **(recommended for FBG: preserves time axis and signal shape)**.
        * ``'forward'``  – forward-fill from the last clean value.
        * ``'constant'`` – replace with ``fill_value``.

        The shape-preserving strategies ('linear', 'forward', 'constant')
        are applied **per channel**: only the flagged samples of each channel
        are replaced, so clean readings in other channels of the same row are
        preserved.
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

    # Replace only the flagged samples of each channel, preserving clean
    # readings in the other channels of the same row.
    indices = np.arange(len(bad_rows))
    for ch in range(signals_array.shape[1]):
        bad_ch = outlier_mask[:, ch]
        valid_ch = ~bad_ch
        if not bad_ch.any() or not valid_ch.any():
            continue

        if strategy == "constant":
            clean_signals[bad_ch, ch] = fill_value

        elif strategy == "forward":
            clean_signals[:, ch] = _forward_fill(signals_array[:, ch], valid_ch)

        elif strategy == "linear":
            clean_signals[bad_ch, ch] = np.interp(
                indices[bad_ch], indices[valid_ch], signals_array[valid_ch, ch]
            )

    return clean_time, clean_signals
