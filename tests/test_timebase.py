import numpy as np
import pytest
from braggflow.processing.timebase import resample_uniform, sort_and_deduplicate


def test_sort_restores_time_order():
    t = np.array([0.0, 0.2, 0.1, 0.3])
    s = np.array([[0.0], [2.0], [1.0], [3.0]])
    ct, cs = sort_and_deduplicate(t, s)
    np.testing.assert_array_equal(ct, [0.0, 0.1, 0.2, 0.3])
    np.testing.assert_array_equal(cs[:, 0], [0.0, 1.0, 2.0, 3.0])


def test_duplicates_mean_ignores_nan():
    t = np.array([0.0, 0.1, 0.1, 0.2])
    s = np.array([[1.0, 5.0], [2.0, np.nan], [4.0, 7.0], [5.0, 8.0]])
    ct, cs = sort_and_deduplicate(t, s, duplicates="mean")
    np.testing.assert_array_equal(ct, [0.0, 0.1, 0.2])
    np.testing.assert_allclose(cs[1], [3.0, 7.0])


def test_duplicates_first():
    t = np.array([0.0, 0.1, 0.1])
    s = np.array([[1.0], [2.0], [4.0]])
    ct, cs = sort_and_deduplicate(t, s, duplicates="first")
    np.testing.assert_array_equal(cs[:, 0], [1.0, 2.0])


def test_nan_timestamps_dropped():
    t = np.array([0.0, np.nan, 0.2])
    s = np.array([[1.0], [2.0], [3.0]])
    ct, cs = sort_and_deduplicate(t, s)
    np.testing.assert_array_equal(ct, [0.0, 0.2])
    np.testing.assert_array_equal(cs[:, 0], [1.0, 3.0])


def test_resample_jittered_to_uniform_grid():
    rng = np.random.default_rng(0)
    t = np.arange(1000) / 100 + rng.uniform(-0.002, 0.002, 1000)
    t[0] = 0.0
    s = np.column_stack([2.0 * t, np.sin(t)])
    grid, out = resample_uniform(t, s, fs=100.0)
    np.testing.assert_allclose(np.diff(grid), 0.01)
    assert grid[0] == 0.0 and grid[-1] <= t[-1]
    np.testing.assert_allclose(out[:, 0], 2.0 * grid, atol=1e-9)


def test_resample_estimates_fs_and_bridges_nan():
    t = np.arange(11) / 10
    s = np.arange(11, dtype=float)[:, None]
    s[4:6, 0] = np.nan
    grid, out = resample_uniform(t, s)
    assert len(grid) == 11
    np.testing.assert_allclose(out[:, 0], np.arange(11))


def test_resample_max_gap_leaves_long_gaps_empty():
    t = np.array([0.0, 0.1, 0.2, 1.2, 1.3])   # 1 s without samples
    s = np.array([[0.0], [1.0], [2.0], [12.0], [13.0]])
    grid, out = resample_uniform(t, s, fs=10.0, max_gap=0.5)
    assert len(grid) == 14
    np.testing.assert_allclose(out[[0, 1, 2, 12, 13], 0], [0, 1, 2, 12, 13], atol=1e-9)
    assert np.isnan(out[3:12, 0]).all()


def test_resample_requires_increasing_time():
    with pytest.raises(ValueError, match="sort_and_deduplicate"):
        resample_uniform(np.array([0.0, 0.2, 0.1]), np.zeros((3, 1)))
