import numpy as np
import pytest
from src.processing.filters import apply_moving_average_filter, apply_savgol_filter

def test_moving_average_filter():
    signals = np.array([[1.0, 2.0], [1.0, 2.0], [1.0, 2.0], [1.0, 2.0], [1.0, 2.0]])
    filtered = apply_moving_average_filter(signals, window_size=3)

    expected = np.empty_like(signals)
    for i in range(signals.shape[1]):
        expected[:, i] = np.convolve(signals[:, i], np.ones(3) / 3, mode='same')

    np.testing.assert_allclose(filtered, expected)


def test_savgol_filter_linear():
    pytest.importorskip('scipy')

    signals = np.vstack([np.linspace(0, 1, 11), np.linspace(1, 2, 11)]).T
    filtered = apply_savgol_filter(signals, window_length=5, polyorder=1)

    np.testing.assert_allclose(filtered, signals, rtol=1e-6, atol=1e-6)
