import pytest
from braggflow.sensors import Sensor, SensorSetup


def _setup():
    return SensorSetup(name="bancada", sensors=[
        Sensor("CH_1 Sensor_1 [nm]", "EFBG1", 1550.1, (1548.0, 1552.0)),
        Sensor("CH_2 Sensor_1 [nm]", "FBG"),
    ])


def test_names_and_bands_follow_file_channels():
    setup = _setup()
    channels = ["CH_1 Sensor_1 [nm]", "CH_2 Sensor_1 [nm]", "CH_3 Sensor_1 [nm]"]
    assert setup.names(channels) == ["EFBG1", "FBG", "CH_3 Sensor_1 [nm]"]
    assert setup.bands(channels) == [(1548.0, 1552.0), None, None]


def test_blank_name_falls_back_to_channel():
    assert Sensor("CH_1", "  ").label == "CH_1"


def test_invalid_band_raises():
    with pytest.raises(ValueError, match="band"):
        Sensor("CH_1", "EFBG1", band=(1552.0, 1548.0))


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "setups" / "bancada.json"
    _setup().save(path)
    loaded = SensorSetup.load(path)
    assert loaded == _setup()


def test_from_rename_map():
    setup = SensorSetup.from_rename_map({"CH_1": "A"})
    assert setup.names(["CH_1", "CH_2"]) == ["A", "CH_2"]


@pytest.mark.parametrize("band", [[None, None], [1548.0, None], ["", ""], [1548.0, ""], "1548", [1548.0]])
def test_incomplete_band_counts_as_no_band(band):
    """Projeto salvo duas vezes chegava com band=[null, null] e quebrava."""
    assert Sensor.from_dict({"channel": "CH_1", "name": "A", "band": band}).band is None


def test_empty_nominal_wavelength_is_accepted():
    assert Sensor.from_dict({"channel": "CH_1", "nominal_wavelength": ""}).nominal_wavelength is None
