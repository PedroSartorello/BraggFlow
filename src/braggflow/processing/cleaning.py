import numpy as np
from typing import Optional, Sequence, Tuple

from ..i18n import tr


def mark_invalid_peaks(
    time_array: np.ndarray,
    signals_array: np.ndarray,
    zero_as_missing: bool = True,
    bands: Optional[Sequence[Optional[Tuple[float, float]]]] = None,
    jump_threshold: Optional[float] = None,
    max_jump_duration: Optional[float] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Marks peak readings that an interrogator exported but that cannot be
    valid Bragg peaks, replacing them with NaN (per channel, shape preserved).
    Use ``remove_null_values`` or ``resample_uniform`` afterwards to fill or
    drop them.

    Three independent criteria:

    * **Lost peak** (``zero_as_missing``) – interrogators write 0 (or a
      negative value) when no peak is detected in a channel.
    * **Out of band** (``bands``) – each grating is allocated a spectral band;
      a reading outside it belongs to another grating or to a spurious peak.
    * **Peak jump** (``jump_threshold``) – the detected peak switches to a
      side lobe or a neighbouring grating and comes back later. Detected as a
      step larger than ``jump_threshold`` between consecutive valid samples
      followed by a step of opposite sign that returns to within
      ``jump_threshold`` of the original level. The samples in between are
      marked. A step that never returns is kept, since it may be real.

    Parameters
    ----------
    time_array : np.ndarray, shape (n_samples,)
    signals_array : np.ndarray, shape (n_samples, n_channels)
        Peak wavelengths [nm].
    zero_as_missing : bool
        Treat readings <= 0 as lost peaks. Default True.
    bands : sequence of (min, max) or None, one entry per channel
        Allowed wavelength range of each channel [nm]; None skips a channel.
    jump_threshold : float or None
        Minimum step [nm] considered a peak jump. Must be well above the
        noise and above the largest real change between consecutive samples.
        None disables jump detection.
    max_jump_duration : float or None
        Longest displaced segment [s] still treated as a jump. None = no limit.

    Returns
    -------
    time_array : np.ndarray (unchanged)
    signals_array : np.ndarray with invalid readings set to NaN.
    """
    time_array = np.asarray(time_array, dtype=float)
    signals = np.array(signals_array, dtype=float)
    n_channels = signals.shape[1]

    if zero_as_missing:
        signals[signals <= 0] = np.nan

    if bands is not None:
        if len(bands) != n_channels:
            raise ValueError(tr("lib.entries", name="bands", n=len(bands), channels=n_channels))
        for ch, band in enumerate(bands):
            if band is None:
                continue
            low, high = band
            col = signals[:, ch]
            col[(col < low) | (col > high)] = np.nan

    if jump_threshold is not None:
        if jump_threshold <= 0:
            raise ValueError(tr("lib.positive", name="jump_threshold"))
        for ch in range(n_channels):
            mask = _peak_jump_mask(
                time_array, signals[:, ch], jump_threshold, max_jump_duration
            )
            signals[mask, ch] = np.nan

    return time_array, signals


def _peak_jump_mask(
    time_array: np.ndarray,
    col: np.ndarray,
    threshold: float,
    max_duration: Optional[float],
) -> np.ndarray:
    """Boolean mask of samples inside jump/return pairs for one channel."""
    mask = np.zeros(len(col), dtype=bool)
    valid_idx = np.flatnonzero(np.isfinite(col))
    if len(valid_idx) < 3:
        return mask

    values = col[valid_idx]
    times = time_array[valid_idx]
    steps = np.diff(values)
    jumps = np.flatnonzero(np.abs(steps) > threshold)

    # A threshold at noise level is exceeded by a good share of the steps;
    # a few real jumps (each with its return) are not, even in a short series
    if len(jumps) > max(0.05 * len(steps), 6):
        raise ValueError(tr("lib.jumpNoise", threshold=threshold, n=len(jumps), total=len(steps)))

    i = 0
    while i < len(jumps):
        k = jumps[i]
        for j in range(i + 1, len(jumps)):
            m = jumps[j]
            if max_duration is not None and times[m] - times[k + 1] > max_duration:
                break
            returns = np.sign(steps[m]) != np.sign(steps[k])
            if returns and abs(steps[k] + steps[m]) <= threshold:
                mask[valid_idx[k + 1:m + 1]] = True
                i = j
                break
        i += 1

    return mask
