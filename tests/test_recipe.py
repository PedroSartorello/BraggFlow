from pathlib import Path

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
