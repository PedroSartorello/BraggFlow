import numpy as np
import pytest
from braggflow.processing.filters import (
    apply_moving_average_filter, apply_savgol_filter, choose_savgol, savgol_cutoff,
)

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

    # centred window; borders average only the real samples available:
    # mean([1,2])=1.5, mean([1,2,3])=2, mean([2,3,4])=3, mean([3,4,5])=4, mean([4,5])=4.5
    expected = np.array([[1.5], [2.0], [3.0], [4.0], [4.5]])
    np.testing.assert_allclose(filtered, expected, rtol=1e-10)


def test_moving_average_filter_no_lag():
    """A step must stay centred on its original position (no time lag)."""
    signals = np.zeros((200, 1))
    signals[100:] = 1.0
    filtered = apply_moving_average_filter(signals, window_size=31)[:, 0]

    assert filtered[100] == pytest.approx(16 / 31)  # half-crossing at the step
    assert int(np.argmax(filtered >= 0.5)) == 100
    # Symmetric around the step edge (between samples 99 and 100)
    np.testing.assert_allclose(filtered[85:100], 1.0 - filtered[100:115][::-1])


def test_moving_average_filter_even_window():
    """Even windows are offset by at most half a sample."""
    signals = np.array([[1.0], [2.0], [3.0], [4.0], [5.0], [6.0]])
    filtered = apply_moving_average_filter(signals, window_size=4)
    # window covers [i-1, i+2]
    expected = np.array([[2.0], [2.5], [3.5], [4.5], [5.0], [5.5]])
    np.testing.assert_allclose(filtered, expected)


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


def test_moving_average_keeps_a_lost_reading_local():
    """Um NaN (pico perdido, sem a remoção de nulos) fica só onde estava."""
    x = np.ones((1000, 1))
    x[100] = np.nan
    y = apply_moving_average_filter(x, 30)
    assert np.isnan(y[100, 0]) and np.isnan(y).sum() == 1
    np.testing.assert_allclose(np.delete(y[:, 0], 100), 1.0)


# ── janela e ordem pelos dados (validação cruzada) ───────────────────────────

def _erro_real(y, limpo, janela, ordem):
    from scipy.signal import savgol_filter
    return np.mean((savgol_filter(y, janela, ordem) - limpo)[1001:-1001] ** 2)


@pytest.mark.parametrize("limpo, ruido", [
    (np.sin(2 * np.pi * np.arange(9001) / 1200), 0.2),                       # oscilação lenta
    (np.tanh((np.arange(9001) - 3000) / 80) - np.tanh((np.arange(9001) - 6000) / 80), 0.05),  # degraus
])
def test_choose_savgol_lands_near_the_true_optimum(limpo, ruido):
    """Sem conhecer o sinal limpo, a escolha fica a 10% do menor erro possível."""
    y = limpo + np.random.default_rng(1).normal(0, ruido, limpo.size)
    escolha = choose_savgol([y])
    melhor = min(_erro_real(y, limpo, n, p) for p in (2, 4) for n in range(7, 1001, 2))
    assert escolha["window"] % 2 == 1 and escolha["order"] in (2, 4)
    assert _erro_real(y, limpo, escolha["window"], escolha["order"]) <= 1.1 * melhor


def test_choose_savgol_handles_gaps_several_curves_and_the_moving_average():
    rng = np.random.default_rng(2)
    t = np.arange(5000)
    a = np.sin(t / 300) + rng.normal(0, 0.1, t.size)
    b = 3 * np.cos(t / 200) + rng.normal(0, 0.5, t.size)
    a[[100, 2500, 2501]] = np.nan                   # picos perdidos não derrubam a escolha
    escolha = choose_savgol([a, b])
    assert 7 <= escolha["window"] <= 1001
    media = choose_savgol([a], orders=(0,))
    assert media["order"] == 0 and media["window"] % 2 == 1


def test_choose_savgol_refuses_a_curve_too_short():
    with pytest.raises(ValueError, match="curta demais"):
        choose_savgol([np.arange(12.0)])


def test_savgol_cutoff_matches_the_frequency_response():
    assert savgol_cutoff(11, 2) * 10 == pytest.approx(0.985, abs=0.002)      # 10 Hz: o padrão do app
    assert savgol_cutoff(51, 3) == pytest.approx(savgol_cutoff(51, 2))        # ordem 3 = ordem 2
