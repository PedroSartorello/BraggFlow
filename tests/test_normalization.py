import numpy as np
import pytest
from braggflow.processing.normalization import to_delta_lambda


def test_delta_lambda_subtracts_baseline_mean():
    signals = np.array([[1.0, 10.0], [3.0, 12.0], [5.0, 20.0]])
    out = to_delta_lambda(signals, baseline_samples=2)
    np.testing.assert_allclose(out, [[-1.0, -1.0], [1.0, 1.0], [3.0, 9.0]])


def test_delta_lambda_ignores_nan_in_baseline():
    """A single NaN in the baseline window must not invalidate the channel."""
    signals = np.array([[1.0], [np.nan], [3.0], [7.0]])
    out = to_delta_lambda(signals, baseline_samples=3)
    assert np.isnan(out[1, 0])
    np.testing.assert_allclose(out[[0, 2, 3], 0], [-1.0, 1.0, 5.0])


def test_delta_lambda_all_nan_baseline_raises():
    signals = np.array([[np.nan, 1.0], [np.nan, 2.0], [5.0, 3.0]])
    with pytest.raises(ValueError, match="baseline"):
        to_delta_lambda(signals, baseline_samples=2)
