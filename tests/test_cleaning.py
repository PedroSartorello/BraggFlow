import numpy as np
import pytest
from braggflow.processing.cleaning import mark_invalid_peaks


def _series(n=1000, fs=100.0, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(n) / fs
    signals = np.column_stack([
        1550.0 + rng.normal(0, 0.002, n),
        1545.0 + rng.normal(0, 0.002, n),
    ])
    return t, signals


def test_zero_and_negative_readings_become_nan():
    t, s = _series(10)
    s[3, 0] = 0.0
    s[5, 1] = -1.0
    _, out = mark_invalid_peaks(t, s)
    assert np.isnan(out[3, 0]) and np.isnan(out[5, 1])
    assert np.isnan(out).sum() == 2
    assert not np.isnan(s).any(), "input must not be modified"


def test_zero_as_missing_disabled():
    t, s = _series(10)
    s[3, 0] = 0.0
    _, out = mark_invalid_peaks(t, s, zero_as_missing=False)
    assert out[3, 0] == 0.0


def test_out_of_band_per_channel():
    t, s = _series(10)
    s[2, 0] = 1545.0     # channel 0 picked up the neighbouring grating
    s[4, 1] = 1552.0
    _, out = mark_invalid_peaks(t, s, bands=[(1548.0, 1552.0), None])
    assert np.isnan(out[2, 0])
    assert out[4, 1] == 1552.0, "channel without band must be untouched"
    assert np.isnan(out).sum() == 1


def test_bands_length_mismatch_raises():
    t, s = _series(10)
    with pytest.raises(ValueError, match="bands"):
        mark_invalid_peaks(t, s, bands=[(1548.0, 1552.0)])


def test_peak_jump_segment_marked():
    t, s = _series()
    s[300:340, 0] += 0.8          # peak locked on a side lobe for 0.4 s
    _, out = mark_invalid_peaks(t, s, jump_threshold=0.1)
    assert np.isnan(out[300:340, 0]).all()
    assert np.isnan(out).sum() == 40


def test_single_sample_spike_marked():
    t, s = _series()
    s[500, 1] -= 1.5
    _, out = mark_invalid_peaks(t, s, jump_threshold=0.1)
    assert np.isnan(out[500, 1])
    assert np.isnan(out).sum() == 1


def test_step_without_return_is_kept():
    """A sustained change may be real and must not be erased."""
    t, s = _series()
    s[600:, 0] += 0.5
    _, out = mark_invalid_peaks(t, s, jump_threshold=0.1)
    assert not np.isnan(out).any()


def test_jump_longer_than_max_duration_is_kept():
    t, s = _series()
    s[200:700, 0] += 0.8          # 5 s displacement
    _, out = mark_invalid_peaks(t, s, jump_threshold=0.1, max_jump_duration=1.0)
    assert not np.isnan(out).any()
    _, out = mark_invalid_peaks(t, s, jump_threshold=0.1, max_jump_duration=10.0)
    assert np.isnan(out[200:700, 0]).all()


def test_jump_detection_skips_missing_samples():
    t, s = _series()
    s[300:340, 0] += 0.8
    s[299, 0] = 0.0               # lost peak right before the jump
    _, out = mark_invalid_peaks(t, s, jump_threshold=0.1)
    assert np.isnan(out[299:340, 0]).all()
    assert not np.isnan(out[340:, 0]).any()


def test_threshold_below_noise_raises():
    t, s = _series()
    with pytest.raises(ValueError, match="noise"):
        mark_invalid_peaks(t, s, jump_threshold=0.0005)
