import numpy as np
import pytest
from src.processing.delimiting import slice_time_window

def test_slice_time_window_basic():
    time_array = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    signals_array = np.arange(10).reshape(5, 2)

    sliced_time, sliced_signals = slice_time_window(time_array, signals_array, 1.0, 3.0)

    np.testing.assert_allclose(sliced_time, np.array([1.0, 2.0, 3.0]))
    np.testing.assert_allclose(sliced_signals, signals_array[1:4])


def test_slice_time_window_invalid():
    time_array = np.array([0.0, 1.0, 2.0])
    signals_array = np.zeros((3, 1))

    with pytest.raises(ValueError):
        slice_time_window(time_array, signals_array, 2.0, 1.0)
