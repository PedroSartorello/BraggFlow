import numpy as np
import pytest
from src.processing.preprocessing import remove_null_values, report_null_summary


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def clean_data():
    time = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    signals = np.array([
        [1.0, 10.0],
        [2.0, 20.0],
        [3.0, 30.0],
        [4.0, 40.0],
        [5.0, 50.0],
    ])
    return time, signals


@pytest.fixture
def data_with_nans():
    time = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    signals = np.array([
        [1.0,  10.0],
        [np.nan, 20.0],   # NaN in channel 0
        [3.0,  np.nan],   # NaN in channel 1
        [4.0,  40.0],
        [5.0,  50.0],
    ])
    return time, signals


@pytest.fixture
def data_with_infs():
    time = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    signals = np.array([
        [1.0,  10.0],
        [np.inf, 20.0],
        [3.0,  -np.inf],
        [4.0,  40.0],
        [5.0,  50.0],
    ])
    return time, signals


# ── remove_null_values ────────────────────────────────────────────────────────

class TestRemoveNullValues:

    def test_no_nulls_returns_copy(self, clean_data):
        time, signals = clean_data
        ct, cs = remove_null_values(time, signals, strategy="remove")
        np.testing.assert_array_equal(ct, time)
        np.testing.assert_array_equal(cs, signals)
        assert ct is not time  # must be a copy

    def test_strategy_remove_drops_bad_rows(self, data_with_nans):
        time, signals = data_with_nans
        ct, cs = remove_null_values(time, signals, strategy="remove")
        assert len(ct) == 3  # rows 0, 3, 4 survive
        assert not np.any(np.isnan(cs))

    def test_strategy_remove_handles_inf(self, data_with_infs):
        time, signals = data_with_infs
        ct, cs = remove_null_values(time, signals, strategy="remove")
        assert len(ct) == 3
        assert np.all(np.isfinite(cs))

    def test_strategy_constant(self, data_with_nans):
        time, signals = data_with_nans
        ct, cs = remove_null_values(time, signals, strategy="constant", fill_value=0.0)
        assert len(ct) == 5
        assert not np.any(np.isnan(cs))
        assert np.any(cs == 0.0)  # zeros were injected

    def test_strategy_constant_requires_fill_value(self, data_with_nans):
        time, signals = data_with_nans
        with pytest.raises(ValueError, match="fill_value"):
            remove_null_values(time, signals, strategy="constant")

    def test_strategy_forward_fill(self, data_with_nans):
        time, signals = data_with_nans
        ct, cs = remove_null_values(time, signals, strategy="forward")
        assert len(ct) == 5
        assert not np.any(np.isnan(cs))
        # row 1 is bad (ch0 is NaN) → entire row filled from row 0
        # row 0 ch0 = 1.0, row 0 ch1 = 10.0
        assert cs[1, 0] == pytest.approx(1.0)
        assert cs[1, 1] == pytest.approx(10.0)
        # row 2 is bad (ch1 is NaN) → entire row filled from row 1
        # after fill, row 1 ch0 = 1.0, row 1 ch1 = 10.0
        assert cs[2, 0] == pytest.approx(1.0)
        assert cs[2, 1] == pytest.approx(10.0)

    def test_strategy_linear_interpolation(self):
        time = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        signals = np.array([
            [0.0],
            [np.nan],
            [4.0],   # midpoint between 0 and 4 should be 2
            [np.nan],
            [8.0],
        ])
        ct, cs = remove_null_values(time, signals, strategy="linear")
        assert len(ct) == 5
        assert cs[1, 0] == pytest.approx(2.0, rel=1e-6)
        assert cs[3, 0] == pytest.approx(6.0, rel=1e-6)

    def test_unknown_strategy_raises(self, clean_data):
        time, signals = clean_data
        with pytest.raises(ValueError, match="Unknown strategy"):
            remove_null_values(time, signals, strategy="invalid")

    def test_output_shape_preserved_inplace_strategies(self, data_with_nans):
        time, signals = data_with_nans
        for strategy in ("forward", "linear", "constant"):
            kw = {"fill_value": -1.0} if strategy == "constant" else {}
            ct, cs = remove_null_values(time, signals, strategy=strategy, **kw)
            assert ct.shape == time.shape
            assert cs.shape == signals.shape


# ── report_null_summary ───────────────────────────────────────────────────────

class TestReportNullSummary:

    def test_no_nulls(self, clean_data):
        _, signals = clean_data
        summary = report_null_summary(signals, channels=["A", "B"])
        for ch in ["A", "B"]:
            assert summary[ch]["nan_count"] == 0
            assert summary[ch]["inf_count"] == 0
            assert summary[ch]["total_bad"] == 0
            assert summary[ch]["pct_bad"] == 0.0

    def test_counts_nans(self, data_with_nans):
        _, signals = data_with_nans
        summary = report_null_summary(signals, channels=["CH0", "CH1"])
        assert summary["CH0"]["nan_count"] == 1
        assert summary["CH1"]["nan_count"] == 1

    def test_counts_infs(self, data_with_infs):
        _, signals = data_with_infs
        summary = report_null_summary(signals)
        assert summary["CH0"]["inf_count"] == 1
        assert summary["CH1"]["inf_count"] == 1

    def test_default_channel_names(self, data_with_nans):
        _, signals = data_with_nans
        summary = report_null_summary(signals)
        assert "CH0" in summary
        assert "CH1" in summary

    def test_percentage_calculation(self):
        signals = np.array([
            [1.0],
            [np.nan],
            [3.0],
            [np.nan],
            [5.0],
        ])
        summary = report_null_summary(signals)
        assert summary["CH0"]["pct_bad"] == pytest.approx(40.0)
