import numpy as np
from typing import Optional, Tuple

from .filters import estimate_sampling_rate


def sort_and_deduplicate(
    time_array: np.ndarray,
    signals_array: np.ndarray,
    duplicates: str = "mean",
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Puts samples in time order and merges repeated timestamps.

    Interrogator exports can contain out-of-order rows (buffered acquisition,
    concatenated files) and repeated timestamps (limited clock resolution).
    Rows whose timestamp is NaN/Inf cannot be placed and are dropped.

    Parameters
    ----------
    duplicates : {'mean', 'first'}
        ``'mean'`` averages the valid readings sharing a timestamp (per
        channel, ignoring NaN); ``'first'`` keeps the first row.

    Returns
    -------
    time_array : strictly increasing timestamps.
    signals_array : matching rows.
    """
    if duplicates not in {"mean", "first"}:
        raise ValueError("duplicates must be 'mean' or 'first'.")

    time_array = np.asarray(time_array, dtype=float)
    signals_array = np.asarray(signals_array, dtype=float)

    finite = np.isfinite(time_array)
    time_array, signals_array = time_array[finite], signals_array[finite]

    order = np.argsort(time_array, kind="stable")
    time_sorted = time_array[order]
    signals_sorted = signals_array[order]

    unique_times, starts = np.unique(time_sorted, return_index=True)
    if len(unique_times) == len(time_sorted):
        return time_sorted, signals_sorted

    if duplicates == "first":
        return unique_times, signals_sorted[starts]

    valid = np.isfinite(signals_sorted)
    sums = np.add.reduceat(np.where(valid, signals_sorted, 0.0), starts, axis=0)
    counts = np.add.reduceat(valid.astype(int), starts, axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        means = sums / counts
    means[counts == 0] = np.nan
    return unique_times, means


def resample_uniform(
    time_array: np.ndarray,
    signals_array: np.ndarray,
    fs: Optional[float] = None,
    max_gap: Optional[float] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Linearly interpolates every channel onto a uniform time grid.

    Digital filters (Savitzky-Golay, moving average, Butterworth) assume a
    constant sampling interval; interrogator timestamps may have jitter or
    gaps. Missing readings (NaN) are ignored and bridged by interpolation.

    Parameters
    ----------
    time_array : np.ndarray, strictly increasing
        Apply ``sort_and_deduplicate`` first if needed.
    fs : float or None
        Output sampling rate [Hz]. None estimates it from the median interval.
    max_gap : float or None
        Longest stretch without valid readings [s] that may be bridged.
        Grid points inside longer gaps are left as NaN. None = no limit.

    Returns
    -------
    grid : np.ndarray, uniform timestamps from the first to the last sample.
    resampled : np.ndarray, shape (len(grid), n_channels)
    """
    time_array = np.asarray(time_array, dtype=float)
    signals_array = np.asarray(signals_array, dtype=float)

    if len(time_array) < 2:
        raise ValueError("At least two samples are needed to resample.")
    if np.any(np.diff(time_array) <= 0):
        raise ValueError(
            "time_array must be strictly increasing; apply sort_and_deduplicate first."
        )
    if fs is None:
        fs = estimate_sampling_rate(time_array)
    if fs <= 0:
        raise ValueError("fs must be positive.")

    n_points = int(np.floor((time_array[-1] - time_array[0]) * fs + 1e-9)) + 1
    grid = time_array[0] + np.arange(n_points) / fs
    resampled = np.full((n_points, signals_array.shape[1]), np.nan)
    tolerance = 0.01 / fs

    for ch in range(signals_array.shape[1]):
        col = signals_array[:, ch]
        valid = np.isfinite(col)
        if valid.sum() < 2:
            continue
        t_valid, v_valid = time_array[valid], col[valid]
        out = np.interp(grid, t_valid, v_valid, left=np.nan, right=np.nan)

        if max_gap is not None:
            right = np.clip(np.searchsorted(t_valid, grid), 1, len(t_valid) - 1)
            t_left, t_right = t_valid[right - 1], t_valid[right]
            inside = (grid > t_left + tolerance) & (grid < t_right - tolerance)
            out[inside & (t_right - t_left > max_gap)] = np.nan

        resampled[:, ch] = out

    return grid, resampled
