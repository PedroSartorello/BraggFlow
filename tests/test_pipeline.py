import json

import numpy as np
import pytest

from braggflow.io.processed import read_processed_csv, split_unit
from braggflow.pipeline import OpticalPipeline
from braggflow.processing import (
    apply_highpass_filter,
    apply_moving_average_filter,
    mark_invalid_peaks,
    remove_null_values,
    resample_uniform,
    sort_and_deduplicate,
    to_delta_lambda,
)
from braggflow.sensors import Sensor, SensorSetup


@pytest.fixture
def asc_file(tmp_path):
    rng = np.random.default_rng(0)
    lines = ["Time [s]\tCH_1 Sensor_1 [nm]\tCH_2 Sensor_1 [nm]"]
    for i in range(200):
        a = 1550.0 + rng.normal(0, 0.002)
        b = 1545.0 + rng.normal(0, 0.002)
        if i == 50:
            a = 0.0                 # lost peak
        if i == 80:
            b = 1552.0              # neighbouring grating
        lines.append(f"{i / 100:.2f}\t{a:.6f}\t{b:.6f}".replace(".", ","))
    path = tmp_path / "ensaio.ASC"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _setup():
    return SensorSetup(name="bancada", sensors=[
        Sensor("CH_1 Sensor_1 [nm]", "S1", band=(1548.0, 1552.0)),
        Sensor("CH_2 Sensor_1 [nm]", "S2", band=(1543.0, 1547.0)),
    ])


def _run(asc_file):
    pipeline = OpticalPipeline(str(asc_file))
    pipeline.load_data().apply_setup(_setup())
    (pipeline
        .preprocess(mark_invalid_peaks, bands=pipeline.sensor_bands())
        .preprocess(sort_and_deduplicate)
        .preprocess(resample_uniform, fs=None)
        .preprocess(remove_null_values, strategy="linear")
        .apply_filter(apply_moving_average_filter, window_size=5))
    return pipeline


def test_setup_renames_and_provides_bands(asc_file):
    pipeline = OpticalPipeline(str(asc_file)).load_data().apply_setup(_setup())
    assert pipeline.channels == ["S1", "S2"]
    assert pipeline.source_channels == ["CH_1 Sensor_1 [nm]", "CH_2 Sensor_1 [nm]"]
    assert pipeline.sensor_bands() == [(1548.0, 1552.0), (1543.0, 1547.0)]


def test_setup_with_duplicate_names_raises(asc_file):
    setup = SensorSetup(sensors=[Sensor("CH_1 Sensor_1 [nm]", "X"),
                                 Sensor("CH_2 Sensor_1 [nm]", "X")])
    with pytest.raises(ValueError, match="Duplicate"):
        OpticalPipeline(str(asc_file)).load_data().apply_setup(setup)


def test_history_counts_invalid_readings(asc_file):
    pipeline = _run(asc_file)
    cleaning = next(h for h in pipeline.history if h["step"] == "mark_invalid_peaks")
    assert cleaning["nan_after"] == {"S1": 1, "S2": 1}
    assert cleaning["params"]["bands"] == [[1548.0, 1552.0], [1543.0, 1547.0]]
    assert not np.isnan(pipeline.signals_array).any()


def test_quantity_changes_with_delta_lambda_and_highpass(asc_file):
    pipeline = OpticalPipeline(str(asc_file)).load_data()
    assert pipeline.quantities == ["wavelength", "wavelength"]
    pipeline.apply_filter(to_delta_lambda, baseline_samples=10)
    assert pipeline.quantities == ["wavelength_shift", "wavelength_shift"]

    pipeline = OpticalPipeline(str(asc_file)).load_data()
    pipeline.preprocess(remove_null_values).apply_filter(apply_highpass_filter, fs=100.0, cutoff=5.0)
    assert pipeline.quantities[0] == "wavelength_shift"


def test_save_writes_units_and_metadata(asc_file, tmp_path):
    pipeline = _run(asc_file)
    out = tmp_path / "out" / "ensaio_processado.csv"
    pipeline.save_processed_data(out)

    header = out.read_text(encoding="utf-8").splitlines()[0]
    assert header == "Time [s],S1 [nm],S2 [nm]"

    df, units, metadata = read_processed_csv(out)
    assert list(df.columns) == ["Time", "S1", "S2"]
    assert units == {"S1": "nm", "S2": "nm"}

    assert metadata == json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    assert metadata["source"]["file"] == "ensaio.ASC"
    assert len(metadata["source"]["sha256"]) == 64
    assert metadata["setup"]["name"] == "bancada"
    assert metadata["sampling"]["uniform"] is True
    assert metadata["sampling"]["fs_estimated_hz"] == pytest.approx(100.0)
    assert [c["source_channel"] for c in metadata["channels"]] == [
        "CH_1 Sensor_1 [nm]", "CH_2 Sensor_1 [nm]"]
    assert [s["step"] for s in metadata["steps"]] == [
        "apply_setup", "mark_invalid_peaks", "sort_and_deduplicate",
        "resample_uniform", "remove_null_values", "apply_moving_average_filter"]


def test_save_without_metadata(asc_file, tmp_path):
    out = tmp_path / "x.csv"
    OpticalPipeline(str(asc_file)).load_data().save_processed_data(out, metadata_path=None)
    assert out.exists() and not out.with_suffix(".json").exists()


def test_read_processed_csv_without_units(tmp_path):
    """CSVs produced before units were added still load."""
    path = tmp_path / "antigo.csv"
    path.write_text("Time,EFBG1\n0.0,1550.1\n", encoding="utf-8")
    df, units, metadata = read_processed_csv(path)
    assert list(df.columns) == ["Time", "EFBG1"]
    assert units == {"EFBG1": None} and metadata is None


@pytest.mark.parametrize("column, expected", [
    ("EFBG1 [nm]", ("EFBG1", "nm")),
    ("Time [s]", ("Time", "s")),
    ("CH_1 Sensor_1 [nm]", ("CH_1 Sensor_1", "nm")),
    ("FBG", ("FBG", None)),
])
def test_split_unit(column, expected):
    assert split_unit(column) == expected


def test_temperature_compensation_refuses_absolute_wavelengths(asc_file):
    """λs − k·λr carregaria a constante λs0 − k·λr0: só sobre Δλ."""
    from braggflow.processing import temperature_compensation

    pipeline = OpticalPipeline(str(asc_file)).load_data()
    with pytest.raises(ValueError, match="to_delta_lambda"):
        pipeline.apply_filter(temperature_compensation, temp_channel_idx=1)
    assert pipeline.history == [], "nada foi aplicado"

    pipeline.apply_filter(to_delta_lambda, baseline_samples=10)
    pipeline.apply_filter(temperature_compensation, temp_channel_idx=1,
                          thermal_sensitivities=[12.0, 10.0])
    assert pipeline.history[-1]["params"]["thermal_sensitivities"] == [12.0, 10.0]
