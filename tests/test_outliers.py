import numpy as np
import pytest
from braggflow.processing.preprocessing import detect_outliers, remove_outliers


# ── helpers ───────────────────────────────────────────────────────────────────

def _signal_with_spike(n=100, spike_pos=50, spike_value=100.0, n_channels=2):
    """Clean signal (constant 1.0) with a single spike injected."""
    signals = np.ones((n, n_channels))
    signals[spike_pos, 0] = spike_value   # spike only in channel 0
    return signals


def _signal_clean(n=100, n_channels=2):
    return np.ones((n, n_channels))


# ── detect_outliers ───────────────────────────────────────────────────────────

class TestDetectOutliers:

    @pytest.mark.parametrize("method", ["zscore", "iqr", "mad"])
    def test_detects_spike_global_methods(self, method):
        signals = _signal_with_spike(spike_value=1000.0)
        threshold = {"zscore": 2.0, "iqr": 1.5, "mad": 3.5}[method]
        mask = detect_outliers(signals, method=method, threshold=threshold)

        assert mask.shape == signals.shape
        assert mask[50, 0], f"method='{method}' should flag the spike at row 50, ch 0"
        assert not mask[50, 1], "ch 1 has no spike and must not be flagged"
        # Most clean rows must NOT be flagged
        assert mask[:, 0].sum() <= 5, "Only spike rows should be flagged"

    def test_detects_spike_rolling(self):
        signals = _signal_with_spike(n=200, spike_pos=100, spike_value=500.0)
        mask = detect_outliers(signals, method="rolling", threshold=3.5, window_size=21)
        assert mask[100, 0], "Rolling MAD must flag the local spike"
        assert not mask[100, 1]

    def test_no_outliers_returns_all_false(self):
        signals = _signal_clean()
        for method in ("zscore", "iqr", "mad"):
            mask = detect_outliers(signals, method=method)
            assert not mask.any(), f"Clean signal must produce no outliers with method='{method}'"

    def test_constant_channel_skipped(self):
        """A channel with zero variance must not crash and return all-False."""
        signals = np.ones((50, 1))
        for method in ("zscore", "iqr", "mad"):
            mask = detect_outliers(signals, method=method)
            assert not mask.any()

    def test_unknown_method_raises(self):
        with pytest.raises(ValueError, match="Unknown method"):
            detect_outliers(np.ones((10, 2)), method="bad_method")

    def test_rolling_even_window_raises(self):
        with pytest.raises(ValueError, match="positive odd integer"):
            detect_outliers(np.ones((20, 2)), method="rolling", window_size=10)

    def test_rolling_zero_window_raises(self):
        with pytest.raises(ValueError, match="positive odd integer"):
            detect_outliers(np.ones((20, 2)), method="rolling", window_size=0)

    def test_output_shape(self):
        signals = np.random.randn(80, 3)
        mask = detect_outliers(signals, method="mad")
        assert mask.shape == (80, 3)
        assert mask.dtype == bool

    def test_iqr_threshold_sensitivity(self):
        """Lower IQR threshold flags more points; higher flags fewer."""
        signals = _signal_with_spike(n=100, spike_value=10.0)
        mask_tight = detect_outliers(signals, method="iqr", threshold=0.5)
        mask_loose = detect_outliers(signals, method="iqr", threshold=5.0)
        assert mask_tight[:, 0].sum() >= mask_loose[:, 0].sum()


# ── remove_outliers ───────────────────────────────────────────────────────────

class TestRemoveOutliers:

    @pytest.fixture
    def spiked_data(self):
        np.random.seed(42)
        signals = _signal_with_spike(n=100, spike_pos=50, spike_value=500.0)
        time = np.linspace(0, 99, 100)
        return time, signals

    # ── strategy: remove ─────────────────────────────────────────────────────

    def test_strategy_remove_drops_bad_rows(self, spiked_data):
        time, signals = spiked_data
        ct, cs = remove_outliers(time, signals, method="mad", strategy="remove")
        assert len(ct) < len(time), "Spike row must have been removed"
        assert cs.shape[1] == signals.shape[1]
        # After removal the spike value must be gone
        assert not np.any(np.abs(cs[:, 0]) > 100)

    def test_strategy_remove_time_signals_aligned(self, spiked_data):
        time, signals = spiked_data
        ct, cs = remove_outliers(time, signals, method="mad", strategy="remove")
        assert len(ct) == len(cs), "Time and signal arrays must have the same length"

    # ── strategy: linear ─────────────────────────────────────────────────────

    def test_strategy_linear_preserves_shape(self, spiked_data):
        time, signals = spiked_data
        ct, cs = remove_outliers(time, signals, method="mad", strategy="linear")
        assert ct.shape == time.shape
        assert cs.shape == signals.shape

    def test_strategy_linear_spike_replaced(self, spiked_data):
        time, signals = spiked_data
        ct, cs = remove_outliers(time, signals, method="mad", strategy="linear")
        # After linear interpolation the spike at index 50 (constant signal = 1)
        # should be very close to 1.0
        assert cs[50, 0] == pytest.approx(1.0, abs=0.1)

    def test_strategy_linear_clean_values_unchanged(self, spiked_data):
        time, signals = spiked_data
        ct, cs = remove_outliers(time, signals, method="mad", strategy="linear")
        # All non-outlier rows must remain exactly 1.0
        mask = detect_outliers(signals, method="mad")
        bad = mask.any(axis=1)
        np.testing.assert_allclose(cs[~bad], signals[~bad])

    # ── strategy: forward ────────────────────────────────────────────────────

    def test_strategy_forward_preserves_shape(self, spiked_data):
        time, signals = spiked_data
        ct, cs = remove_outliers(time, signals, method="mad", strategy="forward")
        assert cs.shape == signals.shape

    def test_strategy_forward_no_spike_value(self, spiked_data):
        time, signals = spiked_data
        ct, cs = remove_outliers(time, signals, method="mad", strategy="forward")
        assert not np.any(cs > 100), "Spike value must not appear after forward fill"

    # ── strategy: constant ───────────────────────────────────────────────────

    def test_strategy_constant_replaces_with_fill(self, spiked_data):
        time, signals = spiked_data
        ct, cs = remove_outliers(
            time, signals, method="mad", strategy="constant", fill_value=0.0
        )
        assert cs.shape == signals.shape
        assert np.any(cs == 0.0), "fill_value must appear in the output"

    def test_strategy_constant_requires_fill_value(self, spiked_data):
        time, signals = spiked_data
        with pytest.raises(ValueError, match="fill_value"):
            remove_outliers(time, signals, strategy="constant")

    # ── validation ───────────────────────────────────────────────────────────

    def test_unknown_strategy_raises(self, spiked_data):
        time, signals = spiked_data
        with pytest.raises(ValueError, match="Unknown strategy"):
            remove_outliers(time, signals, strategy="bad")

    def test_no_outliers_returns_copy(self):
        time = np.linspace(0, 9, 10)
        signals = np.ones((10, 2))
        ct, cs = remove_outliers(time, signals, method="mad")
        np.testing.assert_array_equal(ct, time)
        np.testing.assert_array_equal(cs, signals)
        assert ct is not time

    def test_all_methods_run_without_error(self, spiked_data):
        time, signals = spiked_data
        for method in ("zscore", "iqr", "mad"):
            ct, cs = remove_outliers(time, signals, method=method, strategy="linear")
            assert cs.shape == signals.shape

    def test_rolling_method_in_remove_outliers(self, spiked_data):
        time, signals = spiked_data
        ct, cs = remove_outliers(
            time, signals, method="rolling", window_size=11, strategy="linear"
        )
        assert cs.shape == signals.shape


# ── real level changes (FBG response) ─────────────────────────────────────────

def _step_response(n=10000, amplitude=0.2, seed=0):
    """Baseline at 1550 nm with 2 pm noise and a sustained +200 pm response
    covering 30% of the recording (e.g. gas exposure)."""
    rng = np.random.default_rng(seed)
    y = 1550.0 + rng.normal(0.0, 0.002, n)
    y[4000:7000] += amplitude
    return np.linspace(0, (n - 1) / 100, n), np.column_stack([y, y])


def _rolling_reference(col, window_size, threshold):
    """Original per-sample loop implementation of the rolling criterion."""
    n = len(col)
    half = window_size // 2
    mask = np.zeros(n, dtype=bool)
    for i in range(n):
        window = col[max(0, i - half):min(n, i + half + 1)]
        median = np.nanmedian(window)
        mad = np.nanmedian(np.abs(window - median))
        if mad == 0:
            sigma = np.nanstd(window)
            if sigma == 0:
                continue
            mask[i] = abs(col[i] - median) / sigma > threshold
        else:
            mask[i] = abs(0.6745 * (col[i] - median) / mad) > threshold
    return mask


class TestRealResponsePreserved:

    def test_default_method_preserves_sustained_step(self):
        time, signals = _step_response()
        _, cs = remove_outliers(time, signals, strategy="linear")
        response = cs[4100:6900, 0].mean() - cs[:3900, 0].mean()
        assert response == pytest.approx(0.2, abs=0.005)

    def test_default_method_still_removes_spike_on_step(self):
        time, signals = _step_response()
        signals[5500, 0] += 5.0
        _, cs = remove_outliers(time, signals, strategy="linear")
        assert abs(cs[5500, 0] - 1550.2) < 0.02

    def test_default_method_preserves_ramp(self):
        n = 2000
        rng = np.random.default_rng(1)
        y = np.concatenate([np.zeros(500), np.linspace(0, 0.3, 1000), np.full(500, 0.3)])
        y = y + rng.normal(0.0, 0.002, n)
        signals = y[:, None]
        mask = detect_outliers(signals)
        assert mask.sum() <= 5

    def test_vectorized_rolling_matches_reference(self):
        rng = np.random.default_rng(3)
        col = rng.normal(0, 1, 1500)
        col[[10, 700, 1490]] += 40
        col[200:260] = 5.0          # constant stretch -> MAD fallback
        col[[50, 900]] = np.nan     # missing samples
        signals = np.column_stack([col, np.ones(1500)])
        mask = detect_outliers(signals, method="rolling", threshold=3.5, window_size=21)
        np.testing.assert_array_equal(mask[:, 0], _rolling_reference(col, 21, 3.5))
        assert not mask[:, 1].any()
