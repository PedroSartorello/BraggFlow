import numpy as np
import pytest

from braggflow.analysis import (
    Interval,
    add_differences,
    analyse_curve,
    interval_statistics,
    intervals_from_markers,
    marker_steps,
)


@pytest.fixture
def degraus():
    """Sinal com três patamares: 0 pm, 20 pm (t=100 s) e 5 pm (t=200 s)."""
    t = np.arange(0, 300, 0.1)
    y = np.zeros_like(t)
    y[t >= 100] = 20.0
    y[t >= 200] = 5.0
    return t, y


MARCACOES = [{"time": 100.0, "label": "CO2"}, {"time": 200.0, "label": "N2"}]


# ── intervalos a partir das marcações ─────────────────────────────────────────

def test_markers_become_intervals(degraus):
    t, _ = degraus
    intervalos = intervals_from_markers(MARCACOES, t[0], t[-1])
    assert [i.label for i in intervalos] == ["antes da 1ª marcação", "CO2", "N2"]
    assert (intervalos[1].start, intervalos[1].end) == (100.0, 200.0)
    assert intervalos[-1].end == pytest.approx(t[-1])


def test_without_markers_the_whole_signal_is_one_interval(degraus):
    t, _ = degraus
    assert [i.label for i in intervals_from_markers([], t[0], t[-1])] == ["todo o sinal"]


def test_markers_outside_the_data_are_ignored(degraus):
    t, _ = degraus
    intervalos = intervals_from_markers([{"time": 5000, "label": "fora"}], t[0], t[-1])
    assert [i.label for i in intervalos] == ["todo o sinal"]


# ── estatísticas de um intervalo ──────────────────────────────────────────────

def test_interval_statistics_of_a_plateau(degraus):
    t, y = degraus
    linha = interval_statistics(t, y, Interval("CO2", 100, 200))
    assert linha["n"] == 1000
    assert linha["mean"] == pytest.approx(20.0)
    assert linha["peak_to_peak"] == pytest.approx(0.0)
    assert linha["slope"] == pytest.approx(0.0, abs=1e-9)
    assert linha["duration"] == pytest.approx(100.0)


def test_slope_and_noise_separate_drift_from_scatter():
    t = np.arange(0, 100, 0.01)
    rng = np.random.default_rng(0)
    y = 0.5 * t + rng.normal(0, 2.0, len(t))      # deriva de 0,5 por segundo
    linha = interval_statistics(t, y, Interval("rampa", 0, 100))
    assert linha["slope"] == pytest.approx(0.5, abs=0.01)
    assert linha["slope_error"] < 0.01
    assert linha["noise"] == pytest.approx(2.0, abs=0.1)
    assert linha["std"] > 10, "o desvio simples mistura deriva e ruído"


def test_settle_window_uses_only_the_end_of_the_interval():
    t = np.arange(0, 100, 0.1)
    y = np.where(t < 60, 0.0, 10.0)               # transitório até 60 s
    linha = interval_statistics(t, y, Interval("patamar", 0, 100), settle_window=20)
    assert linha["mean"] == pytest.approx(4.0)    # média do intervalo inteiro
    assert linha["settle_mean"] == pytest.approx(10.0)
    assert linha["settle_n"] == 200


def test_interval_without_samples_is_reported_as_empty(degraus):
    t, y = degraus
    linha = interval_statistics(t, y, Interval("vazio", 1000, 1100))
    assert linha["n"] == 0 and linha["mean"] is None


# ── diferença de amplitude entre intervalos ───────────────────────────────────

def test_difference_from_the_previous_interval(degraus):
    t, y = degraus
    resultado = analyse_curve(t, y, MARCACOES, reference="previous")
    deltas = [linha["delta"] for linha in resultado["intervals"]]
    assert deltas[0] is None, "o primeiro intervalo não tem com quem comparar"
    assert deltas[1] == pytest.approx(20.0)
    assert deltas[2] == pytest.approx(-15.0)
    assert resultado["intervals"][2]["reference"] == "CO2"


def test_difference_from_the_first_interval(degraus):
    t, y = degraus
    resultado = analyse_curve(t, y, MARCACOES, reference="first")
    deltas = [linha["delta"] for linha in resultado["intervals"]]
    assert deltas[1] == pytest.approx(20.0)
    assert deltas[2] == pytest.approx(5.0)
    assert resultado["intervals"][2]["reference"] == "antes da 1ª marcação"


def test_difference_uses_the_steady_state_mean_when_asked():
    t = np.arange(0, 200, 0.1)
    y = np.zeros_like(t)
    y[t >= 100] = 10.0 * (1 - np.exp(-(t[t >= 100] - 100) / 5))   # sobe devagar
    resultado = analyse_curve(t, y, [{"time": 100, "label": "gás"}], settle_window=20)
    linha = resultado["intervals"][1]
    assert linha["mean"] < 9.6, "a média do intervalo inclui o transitório"
    assert linha["settle_mean"] == pytest.approx(10.0, abs=0.01)
    assert linha["delta"] == pytest.approx(10.0, abs=0.01)


def test_unknown_reference_is_rejected():
    with pytest.raises(ValueError, match="Referência inválida"):
        add_differences([{"label": "a", "mean": 1.0, "settle_mean": None, "std": 0.0}], "qualquer")


# ── degrau em cada marcação ───────────────────────────────────────────────────

def test_step_at_each_marker(degraus):
    t, y = degraus
    degraus_calc = marker_steps(t, y, MARCACOES, window=10)
    assert [d["label"] for d in degraus_calc] == ["CO2", "N2"]
    assert degraus_calc[0]["before"] == pytest.approx(0.0)
    assert degraus_calc[0]["after"] == pytest.approx(20.0)
    assert degraus_calc[0]["step"] == pytest.approx(20.0)
    assert degraus_calc[1]["step"] == pytest.approx(-15.0)


def test_step_window_without_samples_before_the_start(degraus):
    t, y = degraus
    degrau = marker_steps(t, y, [{"time": 0.0, "label": "início"}], window=10)[0]
    assert degrau["before_n"] == 0 and degrau["step"] is None


def test_step_window_must_be_positive(degraus):
    t, y = degraus
    with pytest.raises(ValueError, match="janela"):
        marker_steps(t, y, MARCACOES, window=0)


def test_analyse_curve_ignores_missing_samples():
    t = np.arange(0, 100, 0.1)
    y = np.full_like(t, 5.0)
    y[100:200] = np.nan
    resultado = analyse_curve(t, y, [{"time": 50, "label": "meio"}])
    assert all(linha["mean"] == pytest.approx(5.0) for linha in resultado["intervals"])
    assert resultado["intervals"][0]["n"] == 400     # 500 amostras menos as 100 ausentes


# ── trecho escolhido no gráfico ───────────────────────────────────────────────

def test_selection_statistics_measures_the_edges_and_the_variation():
    from braggflow.analysis import selection_statistics

    t = np.arange(0.0, 100.0, 0.5)
    y = 1550.0 + 0.01 * t                          # rampa de 10 pm/s
    linha = selection_statistics(t, y, 20.25, 60.25)
    assert linha["value_start"] == pytest.approx(1550.2025)   # interpolado entre amostras
    assert linha["value_end"] == pytest.approx(1550.6025)
    assert linha["delta"] == pytest.approx(0.4)
    assert linha["delta_rate"] == pytest.approx(0.01)
    assert linha["slope"] == pytest.approx(0.01)
    assert linha["n"] == 80                        # [20,25; 60,25): 20,5 … 60,0
    assert linha["mean"] == pytest.approx(np.mean(y[(t >= 20.25) & (t < 60.25)]))


def test_selection_statistics_relative_shifts_levels_only():
    from braggflow.analysis import selection_statistics

    t = np.arange(0.0, 10.0, 0.1)
    y = np.where(t < 5, 1545.0, 1545.05) + np.where(np.arange(t.size) == 0, np.nan, 0.0)
    absoluto = selection_statistics(t, y, 4.0, 6.0)
    relativo = selection_statistics(t, y, 4.0, 6.0, relative=True)
    assert relativo["mean"] == pytest.approx(absoluto["mean"] - 1545.0)   # 1º valor válido
    assert relativo["value_start"] == pytest.approx(absoluto["value_start"] - 1545.0)
    for chave in ("std", "peak_to_peak", "delta", "slope"):
        assert relativo[chave] == pytest.approx(absoluto[chave])
    assert relativo["relative"] and not absoluto["relative"]


def test_selection_statistics_rejects_an_empty_range():
    from braggflow.analysis import selection_statistics

    with pytest.raises(ValueError, match="maior que o início"):
        selection_statistics(np.arange(5.0), np.arange(5.0), 3.0, 3.0)
