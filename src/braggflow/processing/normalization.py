import numpy as np

from ..i18n import tr

def to_delta_lambda(signals: np.ndarray, baseline_samples: int = 50) -> np.ndarray:
    """
    Converts the input signals to delta lambda (Δλ) format by normalizing each signal
    to its baseline value, which is calculated as the mean of the first `baseline_samples` samples.
    
    Parameters:
    - signals: A 2D numpy array of shape (n_samples, n_channels) containing the raw signal data.
    - baseline_samples: An integer specifying the number of initial samples to use for calculating the baseline.
    
    Returns:
    - A 2D numpy array of shape (n_samples, n_channels) containing the signals in Δλ format.
    """
    if baseline_samples <= 0 or baseline_samples > signals.shape[0]:
        raise ValueError(tr("lib.baselineSamples"))
    
    # Baseline per channel: mean of the first `baseline_samples` samples,
    # ignoring missing values so a single NaN does not invalidate the channel
    baseline = signals[:baseline_samples, :]
    if np.isnan(baseline).all(axis=0).any():
        raise ValueError(tr("lib.baselineEmpty"))
    baseline_values = np.nanmean(baseline, axis=0)

    # Shift each signal by its baseline value
    delta_signals = signals - baseline_values
    
    return delta_signals


to_delta_lambda.output_quantity = "wavelength_shift"
