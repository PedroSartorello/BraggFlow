import numpy as np
import pytest
from braggflow.processing.filters import apply_lowpass_filter, apply_highpass_filter, estimate_sampling_rate


# ── helpers ───────────────────────────────────────────────────────────────────

def _sine(freq_hz: float, fs: float, duration_s: float, n_channels: int = 2) -> np.ndarray:
    """Generate a pure sinusoidal signal as a (n_samples, n_channels) array."""
    t = np.arange(int(fs * duration_s)) / fs
    wave = np.sin(2 * np.pi * freq_hz * t)
    return np.column_stack([wave] * n_channels)


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x ** 2)))


# ── apply_lowpass_filter ──────────────────────────────────────────────────────

class TestLowpassFilter:

    def test_output_shape(self):
        signals = _sine(5.0, fs=100.0, duration_s=2.0)
        out = apply_lowpass_filter(signals, fs=100.0, cutoff=20.0)
        assert out.shape == signals.shape

    def test_passes_low_frequency(self):
        """A 2 Hz sine well below the 20 Hz cutoff must pass through almost intact."""
        fs = 100.0
        signals = _sine(2.0, fs=fs, duration_s=5.0)
        out = apply_lowpass_filter(signals, fs=fs, cutoff=20.0)
        # RMS should be preserved (ratio close to 1)
        ratio = _rms(out[:, 0]) / _rms(signals[:, 0])
        assert ratio == pytest.approx(1.0, abs=0.05)

    def test_attenuates_high_frequency(self):
        """A 40 Hz sine (above 20 Hz cutoff, fs=100) must be strongly attenuated."""
        fs = 100.0
        signals = _sine(40.0, fs=fs, duration_s=5.0)
        out = apply_lowpass_filter(signals, fs=fs, cutoff=20.0)
        ratio = _rms(out[:, 0]) / _rms(signals[:, 0])
        assert ratio < 0.5, f"High-frequency signal should be attenuated; got ratio={ratio:.3f}"

    def test_multiple_channels_independent(self):
        """Each channel must be filtered independently and produce the same result."""
        fs = 100.0
        signals = _sine(2.0, fs=fs, duration_s=3.0, n_channels=3)
        out = apply_lowpass_filter(signals, fs=fs, cutoff=20.0)
        # All channels identical input → identical output
        np.testing.assert_allclose(out[:, 0], out[:, 1])
        np.testing.assert_allclose(out[:, 0], out[:, 2])

    def test_output_dtype_is_float(self):
        signals = np.ones((200, 2), dtype=int)
        out = apply_lowpass_filter(signals, fs=100.0, cutoff=20.0)
        assert out.dtype == float

    # ── validation ────────────────────────────────────────────────────────────

    def test_raises_invalid_fs(self):
        signals = _sine(5.0, fs=100.0, duration_s=1.0)
        with pytest.raises(ValueError, match="fs"):
            apply_lowpass_filter(signals, fs=0.0, cutoff=20.0)
        with pytest.raises(ValueError, match="fs"):
            apply_lowpass_filter(signals, fs=-10.0, cutoff=20.0)

    def test_raises_cutoff_above_nyquist(self):
        signals = _sine(5.0, fs=100.0, duration_s=1.0)
        with pytest.raises(ValueError, match="cutoff"):
            apply_lowpass_filter(signals, fs=100.0, cutoff=50.0)   # == Nyquist

    def test_raises_cutoff_zero(self):
        signals = _sine(5.0, fs=100.0, duration_s=1.0)
        with pytest.raises(ValueError, match="cutoff"):
            apply_lowpass_filter(signals, fs=100.0, cutoff=0.0)

    def test_raises_invalid_order(self):
        signals = _sine(5.0, fs=100.0, duration_s=1.0)
        with pytest.raises(ValueError, match="order"):
            apply_lowpass_filter(signals, fs=100.0, cutoff=20.0, order=0)

    def test_default_cutoff_is_20hz(self):
        """Calling with only fs should use cutoff=20 Hz by default."""
        fs = 200.0
        signals = _sine(50.0, fs=fs, duration_s=3.0)   # above 20 Hz → attenuated
        out = apply_lowpass_filter(signals, fs=fs)
        ratio = _rms(out[:, 0]) / _rms(signals[:, 0])
        assert ratio < 0.5


# ── apply_highpass_filter ─────────────────────────────────────────────────────

class TestHighpassFilter:

    def test_output_shape(self):
        signals = _sine(10.0, fs=100.0, duration_s=2.0)
        out = apply_highpass_filter(signals, fs=100.0, cutoff=5.0)
        assert out.shape == signals.shape

    def test_passes_high_frequency(self):
        """A 30 Hz sine well above the 5 Hz cutoff must pass through almost intact."""
        fs = 100.0
        signals = _sine(30.0, fs=fs, duration_s=5.0)
        out = apply_highpass_filter(signals, fs=fs, cutoff=5.0)
        ratio = _rms(out[:, 0]) / _rms(signals[:, 0])
        assert ratio == pytest.approx(1.0, abs=0.05)

    def test_attenuates_low_frequency(self):
        """A 0.5 Hz sine (below 5 Hz cutoff) must be strongly attenuated."""
        fs = 100.0
        signals = _sine(0.5, fs=fs, duration_s=10.0)
        out = apply_highpass_filter(signals, fs=fs, cutoff=5.0)
        ratio = _rms(out[:, 0]) / _rms(signals[:, 0])
        assert ratio < 0.5, f"Low-frequency signal should be attenuated; got ratio={ratio:.3f}"

    def test_removes_dc_offset(self):
        """A pure DC signal (f=0) must be suppressed to near zero."""
        fs = 100.0
        n = int(fs * 5)
        signals = np.ones((n, 2)) * 10.0   # DC offset of 10
        out = apply_highpass_filter(signals, fs=fs, cutoff=5.0)
        # After transient settling (drop first 20 % of samples), output ~ 0
        settled = out[n // 5 :, 0]
        assert _rms(settled) < 0.5

    def test_multiple_channels_independent(self):
        fs = 100.0
        signals = _sine(30.0, fs=fs, duration_s=3.0, n_channels=3)
        out = apply_highpass_filter(signals, fs=fs, cutoff=5.0)
        np.testing.assert_allclose(out[:, 0], out[:, 1])
        np.testing.assert_allclose(out[:, 0], out[:, 2])

    def test_output_dtype_is_float(self):
        signals = np.ones((200, 2), dtype=int)
        out = apply_highpass_filter(signals, fs=100.0, cutoff=5.0)
        assert out.dtype == float

    # ── validation ────────────────────────────────────────────────────────────

    def test_raises_invalid_fs(self):
        signals = _sine(10.0, fs=100.0, duration_s=1.0)
        with pytest.raises(ValueError, match="fs"):
            apply_highpass_filter(signals, fs=0.0, cutoff=5.0)

    def test_raises_cutoff_above_nyquist(self):
        signals = _sine(10.0, fs=100.0, duration_s=1.0)
        with pytest.raises(ValueError, match="cutoff"):
            apply_highpass_filter(signals, fs=100.0, cutoff=50.0)

    def test_raises_cutoff_zero(self):
        signals = _sine(10.0, fs=100.0, duration_s=1.0)
        with pytest.raises(ValueError, match="cutoff"):
            apply_highpass_filter(signals, fs=100.0, cutoff=0.0)

    def test_raises_invalid_order(self):
        signals = _sine(10.0, fs=100.0, duration_s=1.0)
        with pytest.raises(ValueError, match="order"):
            apply_highpass_filter(signals, fs=100.0, cutoff=5.0, order=0)

    def test_default_cutoff_is_5hz(self):
        """Calling with only fs should use cutoff=5 Hz by default."""
        fs = 100.0
        signals = _sine(0.5, fs=fs, duration_s=10.0)   # below 5 Hz → attenuated
        out = apply_highpass_filter(signals, fs=fs)
        ratio = _rms(out[:, 0]) / _rms(signals[:, 0])
        assert ratio < 0.5


# ── LP + HP complementarity ───────────────────────────────────────────────────

class TestLpHpComplementarity:

    def test_lowpass_highpass_sum_approximates_original(self):
        """
        For a signal with components at 2 Hz and 30 Hz (fs=100),
        LP(20 Hz) + HP(20 Hz) ≈ original (Butterworth is not a perfect
        complementary pair, but the sum should be very close).
        """
        pytest.importorskip("scipy")
        fs = 100.0
        n = int(fs * 10)
        t = np.arange(n) / fs
        col = np.sin(2 * np.pi * 2 * t) + np.sin(2 * np.pi * 30 * t)
        signals = col.reshape(-1, 1)

        lp = apply_lowpass_filter(signals, fs=fs, cutoff=20.0)
        hp = apply_highpass_filter(signals, fs=fs, cutoff=20.0)
        reconstructed = lp + hp

        # Ignore transient edges (first/last 5 %)
        edge = n // 20
        np.testing.assert_allclose(
            reconstructed[edge:-edge, 0],
            signals[edge:-edge, 0],
            atol=0.05,
        )


# ── estimate_sampling_rate ────────────────────────────────────────────────────

def test_estimate_sampling_rate_uniform():
    t = np.arange(1000) / 250.0
    assert estimate_sampling_rate(t) == pytest.approx(250.0)


def test_estimate_sampling_rate_robust_to_gaps():
    t = np.arange(1000) / 100.0
    t = np.delete(t, [100, 101, 500, 800])  # rows dropped by 'remove'
    assert estimate_sampling_rate(t) == pytest.approx(100.0)


def test_estimate_sampling_rate_invalid_time():
    with pytest.raises(ValueError):
        estimate_sampling_rate(np.array([1.0]))
    with pytest.raises(ValueError):
        estimate_sampling_rate(np.array([3.0, 2.0, 1.0]))
