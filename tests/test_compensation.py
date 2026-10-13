"""
Tests for temperature_compensation in src/braggflow/processing/compensation.py

Physical model:
    Δλ_comp[i] = Δλ_sensor[i]  -  k · Δλ_ref
where Δλ_ref is the temperature-reference channel (temp_channel_idx).
"""

import numpy as np
import pytest
from braggflow.processing.compensation import temperature_compensation


# ── fixtures ──────────────────────────────────────────────────────────────────

def _make_signals(n_samples: int = 10, n_channels: int = 3) -> np.ndarray:
    """
    Returns a deterministic (n_samples, n_channels) array where each column
    is a simple ramp so compensation results are easy to verify by hand.
    """
    rng = np.random.default_rng(42)
    return rng.standard_normal((n_samples, n_channels))


# ── basic correctness ─────────────────────────────────────────────────────────

class TestBasicCorrectness:

    def test_output_shape_preserved(self):
        sig = _make_signals(20, 3)
        out = temperature_compensation(sig, temp_channel_idx=2, k_coeff=1.0)
        assert out.shape == sig.shape

    def test_compensation_formula_k1(self):
        """With k=1: comp[i] = sig[i] - sig[ref]  for i != ref."""
        sig = _make_signals(15, 3)
        ref = 2
        out = temperature_compensation(sig, temp_channel_idx=ref, k_coeff=1.0)
        for ch in range(3):
            if ch != ref:
                expected = sig[:, ch] - sig[:, ref]
                np.testing.assert_allclose(out[:, ch], expected, rtol=1e-10)

    def test_compensation_formula_arbitrary_k(self):
        """With k=0.9: comp[i] = sig[i] - 0.9 * sig[ref]."""
        sig = _make_signals(15, 3)
        ref = 1
        k   = 0.9
        out = temperature_compensation(sig, temp_channel_idx=ref, k_coeff=k)
        for ch in range(3):
            if ch != ref:
                expected = sig[:, ch] - k * sig[:, ref]
                np.testing.assert_allclose(out[:, ch], expected, rtol=1e-10)

    def test_reference_channel_is_preserved(self):
        """The temperature-reference column must be unchanged in the output."""
        sig = _make_signals(10, 3)
        for ref in range(3):
            out = temperature_compensation(sig, temp_channel_idx=ref, k_coeff=1.0)
            np.testing.assert_array_equal(out[:, ref], sig[:, ref])

    def test_does_not_modify_input(self):
        """Function must return a copy and leave the original array untouched."""
        sig      = _make_signals(10, 3)
        sig_orig = sig.copy()
        temperature_compensation(sig, temp_channel_idx=0, k_coeff=1.0)
        np.testing.assert_array_equal(sig, sig_orig)

    def test_zero_ref_signal_leaves_sensors_unchanged(self):
        """
        If the reference channel is all zeros (no thermal drift),
        compensated signals must equal the original sensing channels.
        """
        sig = _make_signals(12, 3)
        sig[:, 0] = 0.0          # reference channel is flat (zero Δλ)
        out = temperature_compensation(sig, temp_channel_idx=0, k_coeff=1.0)
        for ch in [1, 2]:
            np.testing.assert_allclose(out[:, ch], sig[:, ch], rtol=1e-12)

    def test_first_channel_as_reference(self):
        sig = _make_signals(10, 4)
        out = temperature_compensation(sig, temp_channel_idx=0, k_coeff=1.0)
        assert out.shape == (10, 4)
        np.testing.assert_array_equal(out[:, 0], sig[:, 0])

    def test_last_channel_as_reference(self):
        sig = _make_signals(10, 4)
        out = temperature_compensation(sig, temp_channel_idx=3, k_coeff=1.0)
        assert out.shape == (10, 4)
        np.testing.assert_array_equal(out[:, 3], sig[:, 3])


# ── validation / error handling ───────────────────────────────────────────────

class TestValidation:

    def test_raises_k_coeff_zero(self):
        sig = _make_signals(5, 2)
        with pytest.raises(ValueError, match="k_coeff"):
            temperature_compensation(sig, temp_channel_idx=0, k_coeff=0.0)

    def test_raises_k_coeff_negative(self):
        sig = _make_signals(5, 2)
        with pytest.raises(ValueError, match="k_coeff"):
            temperature_compensation(sig, temp_channel_idx=0, k_coeff=-0.5)

    def test_raises_temp_channel_out_of_range_high(self):
        sig = _make_signals(5, 3)
        with pytest.raises(ValueError, match="temp_channel_idx"):
            temperature_compensation(sig, temp_channel_idx=3)

    def test_raises_temp_channel_negative(self):
        sig = _make_signals(5, 3)
        with pytest.raises(ValueError, match="temp_channel_idx"):
            temperature_compensation(sig, temp_channel_idx=-1)

    def test_k_coeff_very_small_positive_is_valid(self):
        """Any k > 0 must be accepted, even very small values."""
        sig = _make_signals(5, 2)
        out = temperature_compensation(sig, temp_channel_idx=0, k_coeff=1e-6)
        assert out.shape == sig.shape

    def test_k_coeff_large_is_valid(self):
        sig = _make_signals(5, 2)
        out = temperature_compensation(sig, temp_channel_idx=0, k_coeff=10.0)
        assert out.shape == sig.shape


# ── physical edge cases ───────────────────────────────────────────────────────

class TestPhysicalEdgeCases:

    def test_identical_signals_with_k1_yields_zero_sensors(self):
        """
        If all sensing channels have exactly the same response as the reference
        (pure thermal, no gas signal) and k=1, compensation should yield zero.
        The reference channel itself keeps its original values.
        """
        ref_signal = np.linspace(0, 0.01, 50)
        sig = np.column_stack([ref_signal, ref_signal, ref_signal])
        out = temperature_compensation(sig, temp_channel_idx=2, k_coeff=1.0)
        np.testing.assert_allclose(out[:, 0], 0.0, atol=1e-15)
        np.testing.assert_allclose(out[:, 1], 0.0, atol=1e-15)
        # Reference column must remain untouched
        np.testing.assert_array_equal(out[:, 2], ref_signal)

    def test_gas_response_plus_thermal_drift(self):
        """
        Sensor = thermal_drift + gas_response.
        Reference = thermal_drift only.
        After compensation (k=1): result should equal gas_response.
        """
        n = 100
        t = np.linspace(0, 1, n)
        thermal_drift = 0.005 * t                    # linear thermal ramp (nm)
        gas_response  = 0.002 * np.sin(2 * np.pi * t)  # oscillating gas signal

        sensor    = thermal_drift + gas_response
        reference = thermal_drift.copy()

        sig = np.column_stack([sensor, reference])   # col 0 = sensor, col 1 = ref
        out = temperature_compensation(sig, temp_channel_idx=1, k_coeff=1.0)

        np.testing.assert_allclose(out[:, 0], gas_response, atol=1e-12)

    def test_partial_k_leaves_residual(self):
        """
        If k < 1, some thermal drift remains in the compensated signal.
        """
        n    = 20
        drift = np.ones(n) * 0.01    # constant thermal offset
        sensor = drift.copy()         # sensor == drift (no gas signal)
        sig = np.column_stack([sensor, drift])

        k   = 0.8
        out = temperature_compensation(sig, temp_channel_idx=1, k_coeff=k)
        expected_residual = sensor - k * drift   # = (1 - k) * drift
        np.testing.assert_allclose(out[:, 0], expected_residual, atol=1e-14)
