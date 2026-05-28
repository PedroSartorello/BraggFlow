import numpy as np
import pytest
from src.processing.filters import apply_moving_average_filter, apply_savgol_filter

def test_moving_average_filter_constant_signal():
    """A constant signal must be unchanged everywhere, including the borders."""
    signals = np.full((10, 2), 5.0)
    filtered = apply_moving_average_filter(signals, window_size=3)

    np.testing.assert_allclose(filtered, signals, rtol=1e-10,
                               err_msg="Constant signal must remain unchanged after moving average.")


def test_moving_average_filter_known_values():
    """Verify a hand-calculated case: ramp [1,2,3,4,5] with window=3."""
    signals = np.array([[1.0], [2.0], [3.0], [4.0], [5.0]])
    filtered = apply_moving_average_filter(signals, window_size=3)

    # border (window not full yet): mean([1]) = 1, mean([1,2]) = 1.5
    # interior: mean([1,2,3])=2, mean([2,3,4])=3, mean([3,4,5])=4
    expected = np.array([[1.0], [1.5], [2.0], [3.0], [4.0]])
    np.testing.assert_allclose(filtered, expected, rtol=1e-10)


def test_moving_average_filter_window_size_1():
    """Window of 1 must return the original signal unchanged."""
    signals = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
    filtered = apply_moving_average_filter(signals, window_size=1)
    np.testing.assert_array_equal(filtered, signals)


def test_moving_average_filter_invalid_window():
    signals = np.ones((5, 2))
    with pytest.raises(ValueError):
        apply_moving_average_filter(signals, window_size=0)
    with pytest.raises(ValueError):
        apply_moving_average_filter(signals, window_size=10)  # larger than n_samples


def test_savgol_filter_linear():
    pytest.importorskip('scipy')

    signals = np.vstack([np.linspace(0, 1, 11), np.linspace(1, 2, 11)]).T
    filtered = apply_savgol_filter(signals, window_length=5, polyorder=1)

    np.testing.assert_allclose(filtered, signals, rtol=1e-6, atol=1e-6)
