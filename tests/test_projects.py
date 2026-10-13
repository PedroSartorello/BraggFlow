import json

import pytest

from braggflow.projects import Project
from braggflow.sensors import Sensor


def _project(**overrides):
    data = {
        "name": "Ensaio CO2",
        "file": "data/raw/ensaio.ASC",
        "description": "teste de ciclos",
        "sensors": [Sensor("CH_1 Sensor_1 [nm]", "EFBG1", 1550.1, (1548.0, 1552.0))],
        "processing": {
            "cleaning": {"enabled": True, "jump_threshold": "0.1"},
            "nulls": {"enabled": True, "strategy": "linear"},
            "include_raw": False,
        },
        "markers": [{"time": "300", "label": "CO2", "color": "#C05621"},
                    {"time": "30", "label": "N2", "color": "#4682B4"}],
        "channels": ["EFBG1"],
        "style": {"figure": {"width": 8.89, "layout": "combined"}},
    }
    data.update(overrides)
    return Project(**data)


def test_project_normalizes_its_contents():
    project = _project()
    assert [m["time"] for m in project.markers] == [30.0, 300.0], "marcações ordenadas"
    assert project.style["figure"]["width"] == pytest.approx(8.89)
    assert project.style["export"]["format"] == "pdf", "estilo completado com os padrões"
    assert project.created and project.updated


def test_unknown_processing_sections_are_dropped():
    project = _project(processing={"nulls": {"strategy": "linear"}, "hack": {"x": 1},
                                   "outliers": {"method": "rolling", "callback": {"a": 1}}})
    assert set(project.processing) == {"nulls", "outliers"}
    assert project.processing["outliers"] == {"method": "rolling"}


def test_name_is_required():
    with pytest.raises(ValueError, match="nome"):
        _project(name="   ")


@pytest.mark.parametrize("field, value, message", [
    ("markers", [{"time": "x"}], "Tempo inválido"),
    ("style", {"figure": {"width": "-3"}}, "Largura da figura"),
    ("processing", "nada", "Opções de processamento"),
])
def test_invalid_content_is_rejected(field, value, message):
    with pytest.raises(ValueError, match=message):
        _project(**{field: value})


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "projects" / "ensaio.json"
    _project().save(path)
    loaded = Project.load(path)

    original = _project().to_dict()
    for key in ("file", "description", "sensors", "processing", "markers", "channels", "style"):
        assert loaded.to_dict()[key] == original[key]
    assert loaded.created == json.loads(path.read_text(encoding="utf-8"))["created"]


def test_summary_is_short():
    assert _project().summary() == {
        "name": "Ensaio CO2", "file": "data/raw/ensaio.ASC",
        "description": "teste de ciclos", "updated": _project().updated,
        "n_sensors": 1, "n_markers": 2, "n_series": 1, "n_spectra": 0,
    }


# ── um estado por arquivo ─────────────────────────────────────────────────────

def test_series_entries_keep_their_own_options():
    project = _project(series=[
        {"file": "data/raw/a.ASC", "include": True,
         "sensors": [{"channel": "CH_1", "name": "A", "band": [1548, 1552]}],
         "processing": {"savgol": {"enabled": True, "window_length": "11"}}},
        {"file": "data/raw/b.ASC", "include": False,
         "processing": {"savgol": {"enabled": False}}},
    ])
    first, second = project.series
    assert first["sensors"][0]["band"] == [1548.0, 1552.0]
    assert first["processing"]["savgol"]["window_length"] == "11"
    assert second["include"] is False and second["sensors"] == []
    assert second["processing"]["savgol"] == {"enabled": False}


def test_old_project_with_a_single_file_still_opens():
    """Projetos salvos antes das abas separadas viram uma entrada de série."""
    project = Project.from_dict({
        "name": "Antigo", "file": "data/raw/ensaio.ASC", "source": "timeseries",
        "sensors": [{"channel": "CH_1", "name": "EFBG1"}],
        "processing": {"nulls": {"strategy": "linear"}},
    })
    assert project.source == "series"
    assert [e["file"] for e in project.series] == ["data/raw/ensaio.ASC"]
    assert project.series[0]["sensors"][0]["name"] == "EFBG1"


def test_spectrum_settings_are_validated_per_file():
    project = _project(spectra_files=[
        {"file": "data/raw/AR.dat", "settings": {"smooth_window": "41", "normalize": "minmax"}},
        {"file": "data/raw/H2O.dat"},
    ])
    assert project.spectra_files[0]["settings"]["smooth_window"] == 41
    assert project.spectra_files[1]["settings"]["normalize"] == "none"

    with pytest.raises(ValueError, match=r"\[AR.dat\] Normalização"):
        _project(spectra_files=[{"file": "data/raw/AR.dat", "settings": {"normalize": "x"}}])


def test_viz_sources_are_kept():
    project = _project(viz_sources={"series": ["data/processed/a.csv"], "spectra": ["data/raw/AR.dat"]})
    assert project.to_dict()["viz_sources"] == {
        "series": ["data/processed/a.csv"], "spectra": ["data/raw/AR.dat"]}


def test_saving_an_opened_project_again_keeps_working():
    """Reproduz o erro: salvar um projeto que já tinha sido aberto."""
    original = _project(series=[{
        "file": "data/raw/a.ASC",
        "sensors": [{"channel": "CH_1", "name": "EFBG1", "band": [1548, 1552]},
                    {"channel": "CH_2", "name": "EFBG2", "band": None}],
        "processing": {"nulls": {"strategy": "linear"}},
    }])
    reaberto = Project.from_dict(original.to_dict())
    de_novo = Project.from_dict(reaberto.to_dict())

    sensores = de_novo.series[0]["sensors"]
    assert sensores[0]["band"] == [1548.0, 1552.0]
    assert sensores[1]["band"] is None


def test_sensor_without_band_values_does_not_break_the_project():
    project = _project(series=[{
        "file": "data/raw/a.ASC",
        "sensors": [{"channel": "CH_1", "name": "EFBG1", "band": [None, None],
                     "nominal_wavelength": None}],
    }])
    assert project.series[0]["sensors"][0]["band"] is None
