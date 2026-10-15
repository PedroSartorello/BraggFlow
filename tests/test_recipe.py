from pathlib import Path

import numpy as np
import pytest

from braggflow import OpticalPipeline
from braggflow.cli import process_file
from braggflow.processing import (
    apply_moving_average_filter,
    apply_savgol_filter,
    mark_invalid_peaks,
    remove_null_values,
    remove_outliers,
    sort_and_deduplicate,
)
from braggflow.recipe import STANDARD_RECIPE, as_float, default_setup, run_recipe, setup_from_options

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "data" / "synthetic_interrogator.asc"


def test_cli_matches_the_fluent_recipe_of_the_example(tmp_path):
    """
    ``braggflow process`` (STANDARD_RECIPE via run_recipe) e a cadeia fluente
    de examples/01_process_file.py precisam continuar dando o mesmo CSV.
    """
    fluente = tmp_path / "fluente.csv"
    pipeline = OpticalPipeline(EXAMPLE)
    pipeline.load_data().apply_setup(default_setup())
    (pipeline
     .delimit_time_window(start_time=None, end_time=None)
     .preprocess(mark_invalid_peaks, zero_as_missing=True, bands=pipeline.sensor_bands())
     .preprocess(sort_and_deduplicate, duplicates="mean")
     .preprocess(remove_null_values, strategy="linear")
     .preprocess(remove_outliers, method="rolling", threshold=3.5, window_size=51, strategy="linear")
     .apply_filter(apply_savgol_filter, window_length=11, polyorder=2)
     .apply_filter(apply_moving_average_filter, window_size=30)
     .save_processed_data(fluente))

    cli = process_file(EXAMPLE, out=tmp_path / "cli.csv", plot=False)
    assert cli.read_bytes() == fluente.read_bytes()


def test_steps_follow_the_options():
    pipeline, _, messages = run_recipe([EXAMPLE], STANDARD_RECIPE)
    steps = [entry["step"] for entry in pipeline.history]
    assert steps == ["apply_setup", "mark_invalid_peaks", "sort_and_deduplicate",
                     "remove_null_values", "remove_outliers", "apply_savgol_filter",
                     "apply_moving_average_filter"]
    assert pipeline.channels == ["EFBG1", "EFBG2", "FBG"]
    assert messages["report"][0].startswith("Limpeza:")


def test_explicit_setup_wins_over_the_options():
    setup = setup_from_options({"sensors": [
        {"channel": "CH_1 Sensor_1 [nm]", "name": "A"},
        {"channel": "CH_2 Sensor_1 [nm]", "name": "B"},
        {"channel": "CH_3 Sensor_1 [nm]", "name": "C"},
    ]})
    pipeline, _, _ = run_recipe([EXAMPLE], {"sensors": [], "rename": {"x": "y"}}, setup=setup)
    assert pipeline.channels == ["A", "B", "C"]


def test_custom_loader_is_used():
    lidos = []

    def load(path):
        from braggflow.recipe import load_file
        lidos.append(path)
        return load_file(path)

    run_recipe([EXAMPLE], {}, load=load)
    assert lidos == [EXAMPLE]


def test_no_files_is_an_error():
    with pytest.raises(ValueError, match="Nenhum arquivo"):
        run_recipe([], STANDARD_RECIPE)


def test_incomplete_band_is_refused():
    with pytest.raises(ValueError, match="Banda incompleta"):
        setup_from_options({"sensors": [{"channel": "CH_1", "band_min": "1549", "band_max": ""}]})


@pytest.mark.parametrize("valor, esperado", [(None, 7.0), ("", 7.0), ("2.5", 2.5), (3, 3.0)])
def test_as_float_treats_blank_as_default(valor, esperado):
    assert as_float(valor, 7.0) == esperado


# ── compensação de temperatura ───────────────────────────────────────────────

COMP = {
    "cleaning": {"enabled": True},
    "timebase": {"enabled": True},
    "nulls": {"enabled": True},
    "delta_lambda": {"enabled": True, "baseline_samples": 20},
    "temp_comp": {"enabled": True, "channel": "FBG"},
}


def _deriva(pipeline, canal=0):
    """
    Variação do canal entre o começo e o fim do trecho sem CO2 (antes de
    300 s), por medianas de 30 s: o sintético tem outliers de propósito.
    """
    t, sig, _ = pipeline.get_data()
    inicio = np.nanmedian(sig[(t > 10) & (t < 40), canal])
    fim = np.nanmedian(sig[(t > 260) & (t < 290), canal])
    return abs(fim - inicio)


def test_compensation_removes_the_thermal_drift_of_the_synthetic_data():
    """No sintético todas as redes derivam 10 pm/°C: com k = 1 sobra o ruído."""
    sem, _, _ = run_recipe([EXAMPLE], {**COMP, "temp_comp": {"enabled": False}})
    com, _, messages = run_recipe([EXAMPLE], COMP)
    assert _deriva(sem) > 10 * _deriva(com)
    assert any("EFBG1 k = 1 (k informado)" in r for r in messages["report"])


def test_each_sensor_uses_its_thermal_sensitivity():
    setup = setup_from_options({"sensors": [
        {"channel": "CH_1 Sensor_1 [nm]", "name": "EFBG1", "temp_sensitivity": "20"},
        {"channel": "CH_2 Sensor_1 [nm]", "name": "EFBG2"},
        {"channel": "CH_3 Sensor_1 [nm]", "name": "FBG", "temp_sensitivity": "10"},
    ]})
    sem, _, _ = run_recipe([EXAMPLE], {**COMP, "temp_comp": {"enabled": False}}, setup=setup)
    com, _, messages = run_recipe([EXAMPLE], {**COMP, "temp_comp": {
        "enabled": True, "channel": "FBG", "k_coeff": "0.5"}}, setup=setup)

    _, s, _ = sem.get_data()
    _, c, _ = com.get_data()
    np.testing.assert_allclose(c[:, 0], s[:, 0] - 2.0 * s[:, 2])      # 20 / 10
    np.testing.assert_allclose(c[:, 1], s[:, 1] - 0.5 * s[:, 2])      # sem K_T: k informado
    np.testing.assert_array_equal(c[:, 2], s[:, 2])                   # referência intacta
    relatorio = next(r for r in messages["report"] if r.startswith("Compensação"))
    assert "EFBG1 k = 2 (K_T 20 / 10 pm/°C)" in relatorio
    assert "EFBG2 k = 0,5 (k informado)" in relatorio
    assert com.history[-1]["params"]["thermal_sensitivities"] == [20.0, None, 10.0]


def test_compensation_needs_delta_lambda():
    with pytest.raises(ValueError, match="ative a etapa Δλ"):
        run_recipe([EXAMPLE], {**COMP, "delta_lambda": {"enabled": False}})


def test_reference_without_thermal_sensitivity_is_explained():
    setup = setup_from_options({"sensors": [
        {"channel": "CH_1 Sensor_1 [nm]", "name": "EFBG1", "temp_sensitivity": "20"},
        {"channel": "CH_2 Sensor_1 [nm]", "name": "EFBG2"},
        {"channel": "CH_3 Sensor_1 [nm]", "name": "FBG"},
    ]})
    with pytest.raises(ValueError, match=r"K_T da referência \(FBG\)"):
        run_recipe([EXAMPLE], COMP, setup=setup)


def test_unknown_reference_channel_is_explained():
    with pytest.raises(ValueError, match="Canal de referência 'X'"):
        run_recipe([EXAMPLE], {**COMP, "temp_comp": {"enabled": True, "channel": "X"}})
