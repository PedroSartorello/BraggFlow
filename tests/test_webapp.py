import io
from pathlib import Path

import numpy as np
import pytest

import braggflow.webapp
from braggflow.io.processed import read_metadata
from braggflow.webapp.app import API_BUILD, create_app

WEBAPP = Path(braggflow.webapp.__file__).parent


@pytest.fixture
def webapp(tmp_path):
    data = tmp_path / "data"
    app = create_app(data, create=False)        # pasta e caches só deste teste

    raw = data / "raw"
    raw.mkdir(parents=True)
    rng = np.random.default_rng(0)
    lines = ["Time [s]\tCH_1 Sensor_1 [nm]\tCH_2 Sensor_1 [nm]"]
    for i in range(500):
        a = 1550.0 + rng.normal(0, 0.002)
        b = 1545.0 + rng.normal(0, 0.002)
        if i in (100, 101):
            a = 0.0
        if 300 <= i < 320:
            b += 0.9                       # peak jump
        t = i / 50 + (0.004 if i % 7 == 0 else 0.0)   # timestamp jitter
        lines.append(f"{t:.3f}\t{a:.6f}\t{b:.6f}".replace(".", ","))
    (raw / "ensaio.ASC").write_text("\n".join(lines) + "\n", encoding="utf-8")

    app.config["TESTING"] = True
    return app.extensions["braggflow"].data, app.test_client()


SENSORS = [
    {"channel": "CH_1 Sensor_1 [nm]", "name": "S1", "band_min": "1548", "band_max": "1552"},
    {"channel": "CH_2 Sensor_1 [nm]", "name": "S2", "band_min": "1543", "band_max": "1547"},
]


def _process(client, **overrides):
    options = {
        "file": "data/raw/ensaio.ASC",
        "sensors": SENSORS,
        "cleaning": {"enabled": True, "zeros": True, "bands": True,
                     "jump_threshold": "0.1", "jump_duration": ""},
        "timebase": {"enabled": True, "duplicates": "mean", "resample": True,
                     "fs": "", "max_gap": ""},
        "nulls": {"enabled": True, "strategy": "linear"},
        "savgol": {"enabled": True, "window_length": "11", "polyorder": "2"},
    }
    options.update(overrides)
    return client.post("/api/process", json=options)


def test_channels_endpoint_reports_nominal_and_fs(webapp):
    _, client = webapp
    data = client.get("/api/channels?file=data/raw/ensaio.ASC").get_json()
    assert data["channels"] == ["CH_1 Sensor_1 [nm]", "CH_2 Sensor_1 [nm]"]
    assert data["nominal"]["CH_1 Sensor_1 [nm]"] == pytest.approx(1550.0, abs=0.01)
    assert data["fs"] == pytest.approx(50.0)
    assert data["n_samples"] == 500


def test_process_cleans_resamples_and_saves_with_metadata(webapp):
    dados, client = webapp
    resp = _process(client)
    data = resp.get_json()
    assert resp.status_code == 200, data

    assert data["channels"] == ["S1", "S2"]
    assert data["units"] == {"S1": "nm", "S2": "nm"}
    assert "Limpeza: S1 2 (0,4%), S2 20 (4%)" in data["report"]
    assert any(r.startswith("Reamostrado a 50 Hz") for r in data["report"])
    assert not data["warnings"]
    assert max(data["signals"]["S2"]) < 1545.1, "peak jump must be removed"

    csv = dados.processed / "ensaio_processado.csv"
    assert csv.read_text(encoding="utf-8").splitlines()[0] == "Time [s],S1 [nm],S2 [nm]"
    meta = read_metadata(csv)
    assert meta["sampling"]["uniform"] is True
    assert [c["name"] for c in meta["channels"]] == ["S1", "S2"]
    assert not list(dados.processed.glob("*.tmp"))


def test_filters_warn_about_remaining_invalid_readings(webapp):
    _, client = webapp
    resp = _process(client, timebase={"enabled": False}, nulls={"enabled": False})
    warnings = resp.get_json()["warnings"]
    assert any("inválida" in w for w in warnings)


def test_incomplete_band_is_rejected(webapp):
    _, client = webapp
    sensors = [dict(SENSORS[0], band_max=""), SENSORS[1]]
    resp = _process(client, sensors=sensors)
    assert resp.status_code == 400
    assert "Banda incompleta" in resp.get_json()["error"]


def test_setup_save_list_and_load(webapp):
    _, client = webapp
    resp = client.post("/api/setups", json={"setup_name": "Bancada 1", "sensors": SENSORS})
    assert resp.get_json() == {"name": "Bancada 1"}
    assert client.get("/api/setups").get_json() == {"setups": ["Bancada 1"]}

    setup = client.get("/api/setups/Bancada 1").get_json()
    assert setup["sensors"][0] == {"channel": "CH_1 Sensor_1 [nm]", "name": "S1",
                                   "nominal_wavelength": None, "band": [1548.0, 1552.0],
                                   "temp_sensitivity": None}
    assert client.get("/api/setups/..%2Fsecret").status_code == 404


def test_visualization_reads_units_and_builds_figure(webapp):
    _, client = webapp
    _process(client, delta_lambda={"enabled": True, "baseline_samples": "20"})

    info = client.get("/api/processed-channels?file=data/processed/ensaio_processado.csv").get_json()
    assert info == {"channels": ["S1", "S2"], "units": {"S1": "nm", "S2": "nm"},
                    "quantities": {"S1": "wavelength_shift", "S2": "wavelength_shift"}}

    resp = client.post("/api/figure", json={"file": "data/processed/ensaio_processado.csv",
                                            "channels": ["S1", "S2"]})
    assert resp.status_code == 200 and resp.get_json()["image"]


def test_download_csv_has_units(webapp):
    _, client = webapp
    resp = client.post("/api/download", json={"file": "data/raw/ensaio.ASC", "sensors": SENSORS})
    assert resp.status_code == 200
    assert resp.data.decode().splitlines()[0] == "Time [s],S1 [nm],S2 [nm]"


def test_preview_does_not_overwrite_saved_result(webapp):
    dados, client = webapp
    _process(client)
    csv = dados.processed / "ensaio_processado.csv"
    saved = csv.read_bytes()

    resp = _process(client, save=False, cleaning={"enabled": False})
    assert resp.get_json()["processed_file"] is None
    assert csv.read_bytes() == saved


def test_figure_endpoint_uses_style_and_reports_size(webapp):
    _, client = webapp
    _process(client)
    style = {"figure": {"width": "8.89", "height": "6", "unit": "cm"},
             "export": {"preview_dpi": "100", "dpi": "300"},
             "channels": {"S1": {"label": "Grade 1", "color": "#aa0000"}}}
    resp = client.post("/api/figure", json={"file": "data/processed/ensaio_processado.csv",
                                            "channels": ["S1"], "style": style})
    data = resp.get_json()
    assert resp.status_code == 200, data
    assert data["info"]["width_cm"] == pytest.approx(8.89, abs=0.01)
    assert data["info"]["width_px"] == round(8.89 / 2.54 * 300)


def test_figure_endpoint_rejects_invalid_style(webapp):
    _, client = webapp
    _process(client)
    resp = client.post("/api/figure", json={"file": "data/processed/ensaio_processado.csv",
                                            "style": {"figure": {"width": "-1"}}})
    assert resp.status_code == 400
    assert "Largura da figura" in resp.get_json()["error"]


@pytest.mark.parametrize("fmt, mimetype", [("tiff", "image/tiff"), ("eps", "application/postscript")])
def test_figure_download_format_from_style(webapp, fmt, mimetype):
    _, client = webapp
    _process(client)
    resp = client.post("/api/figure/download", json={
        "file": "data/processed/ensaio_processado.csv",
        "style": {"export": {"format": fmt, "dpi": 100}}})
    assert resp.status_code == 200
    assert resp.mimetype == mimetype
    assert resp.headers["Content-Disposition"].endswith(f"ensaio_figura.{fmt}")


def test_figure_options_and_styles_roundtrip(webapp):
    _, client = webapp
    options = client.get("/api/figure/options").get_json()
    assert options["style"]["figure"]["layout"] == "stacked"
    assert "publicacao" in options["palettes"] and options["fonts"]

    style = {"figure": {"font_size": 9}, "channels": {"S1": {"color": "#112233"}}}
    assert client.post("/api/styles", json={"name": "Artigo IEEE", "style": style}).get_json() == {"name": "Artigo IEEE"}
    assert client.get("/api/styles").get_json() == {"styles": ["Artigo IEEE"]}
    saved = client.get("/api/styles/Artigo IEEE").get_json()
    assert saved["style"]["figure"]["font_size"] == 9
    assert saved["style"]["channels"]["S1"]["color"] == "#112233"

    bad = client.post("/api/styles", json={"name": "x", "style": {"legend": {"ncol": "0"}}})
    assert bad.status_code == 400
    assert client.get("/api/styles/nao-existe").status_code == 404


# ── projetos ──────────────────────────────────────────────────────────────────

PROJECT = {
    "name": "Ensaio 1",
    "file": "data/raw/ensaio.ASC",
    "sensors": [{"channel": "CH_1 Sensor_1 [nm]", "name": "S1", "band": ["1548", "1552"]},
                {"channel": "CH_2 Sensor_1 [nm]", "name": "S2", "band": None}],
    "processing": {"cleaning": {"enabled": True, "jump_threshold": "0.1"},
                   "nulls": {"enabled": True, "strategy": "linear"}},
    "markers": [{"time": "5", "label": "N2", "color": "#4682B4"}],
    "channels": ["S1"],
    "style": {"figure": {"layout": "combined", "width": "9"}},
}


def test_project_save_list_open_and_delete(webapp):
    dados, client = webapp
    saved = client.post("/api/projects", json=PROJECT).get_json()
    assert saved["name"] == "Ensaio 1" and saved["n_markers"] == 1

    listed = client.get("/api/projects").get_json()["projects"]
    assert [p["name"] for p in listed] == ["Ensaio 1"]
    assert listed[0]["file"] == "data/raw/ensaio.ASC"

    project = client.get("/api/projects/Ensaio 1").get_json()
    assert project["markers"] == [{"time": 5.0, "label": "N2", "color": "#4682B4"}]
    assert project["channels"] == ["S1"]
    assert project["sensors"][0]["band"] == [1548.0, 1552.0]
    assert project["processing"]["nulls"] == {"enabled": True, "strategy": "linear"}
    assert project["style"]["figure"]["layout"] == "combined"

    # A figura e o processamento aceitam o que o projeto guardou
    assert _process(client, sensors=[
        {"channel": s["channel"], "name": s["name"],
         "band_min": (s["band"] or ["", ""])[0], "band_max": (s["band"] or ["", ""])[1]}
        for s in project["sensors"]], **project["processing"]).status_code == 200

    assert client.delete("/api/projects/Ensaio 1").get_json() == {"deleted": "Ensaio 1"}
    assert client.get("/api/projects").get_json() == {"projects": []}
    assert client.delete("/api/projects/Ensaio 1").status_code == 404


def test_project_keeps_creation_date_when_replaced(webapp):
    _, client = webapp
    client.post("/api/projects", json=PROJECT)
    created = client.get("/api/projects/Ensaio 1").get_json()["created"]
    client.post("/api/projects", json={**PROJECT, "description": "revisado"})
    updated = client.get("/api/projects/Ensaio 1").get_json()
    assert updated["created"] == created and updated["description"] == "revisado"


@pytest.mark.parametrize("payload, message", [
    ({"name": "  "}, "nome"),
    ({"name": "x", "markers": [{"time": "abc"}]}, "Tempo inválido"),
    ({"name": "x", "style": {"legend": {"position": "nowhere"}}}, "Posição da legenda"),
])
def test_invalid_project_is_rejected(webapp, payload, message):
    _, client = webapp
    resp = client.post("/api/projects", json=payload)
    assert resp.status_code == 400 and message in resp.get_json()["error"]


def test_broken_project_file_does_not_break_the_list(webapp):
    dados, client = webapp
    client.post("/api/projects", json=PROJECT)
    (dados.projects / "quebrado.json").write_text("{isto não é json", encoding="utf-8")
    assert [p["name"] for p in client.get("/api/projects").get_json()["projects"]] == ["Ensaio 1"]
    assert client.get("/api/projects/quebrado").status_code == 404


# ── espectros ─────────────────────────────────────────────────────────────────

@pytest.fixture
def spectrum_file(webapp):
    """Exportação de OSA (UTF-16, sem cabeçalho, traço vazio no fim) em data/raw."""
    dados, _ = webapp
    lines = []
    for i in range(500):
        lines.append(f"CH 1\t{i + 1}\t{1510 + i * 0.02:.3f}\t{60 + (i % 9):.5f}".replace(".", ","))
    lines += [f"Subset 2\t{i + 1}\t\t" for i in range(500)]
    path = dados.raw / "AR.dat"
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("utf-16"))
    return "data/raw/AR.dat"


def test_file_list_reports_the_kind_of_each_file(webapp, spectrum_file):
    _, client = webapp
    files = {f["path"]: f["kind"] for f in client.get("/api/files").get_json()["files"]}
    assert files == {"data/raw/ensaio.ASC": "timeseries", "data/raw/AR.dat": "spectrum"}


def test_spectrum_traces_endpoint(webapp, spectrum_file):
    _, client = webapp
    data = client.get("/api/spectra/traces?file=" + spectrum_file).get_json()
    assert [t["name"] for t in data["traces"]] == ["CH 1"], "traço vazio descartado"
    trace = data["traces"][0]
    assert trace["key"] == "AR" and trace["n_points"] == 500
    assert trace["range"] == [1510.0, 1519.98]


def test_file_info_reports_detected_format(webapp, spectrum_file):
    _, client = webapp
    info = client.get("/api/file-info?file=" + spectrum_file).get_json()
    assert info["kind"] == "spectrum" and "utf-16" in info["format"]


def test_processing_a_spectrum_explains_the_mistake(webapp, spectrum_file):
    _, client = webapp
    resp = _process(client, file=spectrum_file, sensors=[])
    assert resp.status_code == 400
    assert "espectro" in resp.get_json()["error"]


def test_figure_from_spectra(webapp, spectrum_file):
    _, client = webapp
    options = {
        "source": "spectra",
        "spectra": [{"file": spectrum_file, "trace": "CH 1"}],
        "style": {"figure": {"layout": "combined", "width": "12"},
                  "data": {"smooth_window": "21", "x_min": "1512", "x_max": "1518"},
                  "channels": {"AR": {"label": "Ar", "color": "#2a78d6"}}},
    }
    resp = client.post("/api/figure", json=options)
    data = resp.get_json()
    assert resp.status_code == 200, data
    assert data["info"]["width_cm"] == pytest.approx(12.0, abs=0.01)

    download = client.post("/api/figure/download",
                           json={**options, "style": {**options["style"], "export": {"format": "png"}}})
    assert download.status_code == 200 and download.mimetype == "image/png"
    assert download.headers["Content-Disposition"].endswith("AR_figura.png")


def test_project_keeps_the_spectrum_selection(webapp, spectrum_file):
    _, client = webapp
    project = {**PROJECT, "name": "Espectros", "source": "spectra",
               "spectra": [{"file": spectrum_file, "trace": "CH 1"}], "channels": ["AR"]}
    assert client.post("/api/projects", json=project).status_code == 200
    saved = client.get("/api/projects/Espectros").get_json()
    assert saved["source"] == "spectra"
    assert saved["spectra"] == [{"file": spectrum_file, "trace": "CH 1"}]


def test_figure_combines_channels_from_two_processed_files(webapp):
    dados, client = webapp
    second = dados.raw / "ensaio2.ASC"
    second.write_bytes((dados.raw / "ensaio.ASC").read_bytes())
    _process(client)
    _process(client, file="data/raw/ensaio2.ASC")

    options = {
        "source": "series",
        "series": [{"file": "data/processed/ensaio_processado.csv", "channel": "S1"},
                   {"file": "data/processed/ensaio2_processado.csv", "channel": "S2"}],
        "style": {"figure": {"layout": "combined"},
                  "channels": {"ensaio · S1": {"label": "Antes"},
                               "ensaio2 · S2": {"label": "Depois"}}},
    }
    resp = client.post("/api/figure", json=options)
    assert resp.status_code == 200, resp.get_json()

    download = client.post("/api/figure/download", json=options)
    assert download.headers["Content-Disposition"].endswith("ensaio_figura.pdf")


def test_missing_channel_in_series_is_reported(webapp):
    _, client = webapp
    _process(client)
    resp = client.post("/api/figure", json={
        "source": "series",
        "series": [{"file": "data/processed/ensaio_processado.csv", "channel": "S9"}]})
    assert resp.status_code == 400
    assert "S9" in resp.get_json()["error"]


def test_spectrum_preview_applies_per_file_settings(webapp, spectrum_file):
    _, client = webapp
    resp = client.post("/api/spectra/preview", json={
        "file": spectrum_file,
        "settings": {"lambda_min": 1512, "lambda_max": 1516, "normalize": "minmax", "offset": 1},
    })
    data = resp.get_json()
    assert resp.status_code == 200, data
    trace = data["traces"][0]
    assert trace["key"] == "AR"
    assert min(trace["wavelength"]) >= 1512 and max(trace["wavelength"]) <= 1516
    assert min(trace["intensity"]) == pytest.approx(1.0)   # 0–1 deslocado de +1
    assert max(trace["intensity"]) == pytest.approx(2.0)


def test_spectrum_preview_reports_peaks_and_dips(webapp, spectrum_file):
    _, client = webapp
    data = client.post("/api/spectra/preview", json={
        "file": spectrum_file,
        "settings": {"find_max": True, "find_min": True, "max_peaks": 3},
    }).get_json()
    trace = data["traces"][0]
    tipos = {e["type"] for e in trace["extrema"]}
    assert tipos == {"max", "min"}, "o espectro do fixture oscila (dente de serra de 9 pontos)"
    assert trace["summary"]["n_max"] == 3 and trace["summary"]["n_min"] == 3
    assert all(1510 <= e["wavelength"] <= 1520 for e in trace["extrema"])
    assert trace["summary"]["global_max"]["intensity"] == pytest.approx(68.0)


def test_spectrum_preview_without_detection_has_no_extrema(webapp, spectrum_file):
    _, client = webapp
    trace = client.post("/api/spectra/preview", json={"file": spectrum_file}).get_json()["traces"][0]
    assert trace["extrema"] == []


def test_spectrum_settings_are_independent_per_file(webapp, spectrum_file):
    dados, client = webapp
    other = dados.raw / "H2O.dat"
    other.write_bytes((dados.raw / "AR.dat").read_bytes())

    options = {
        "source": "spectra",
        "spectra": [
            {"file": spectrum_file, "trace": "CH 1", "settings": {"normalize": "minmax"}},
            {"file": "data/raw/H2O.dat", "trace": "CH 1", "settings": {"offset": 5}},
        ],
        "style": {"figure": {"layout": "combined"}},
    }
    assert client.post("/api/figure", json=options).status_code == 200

    bad = client.post("/api/figure", json={**options, "spectra": [
        {**options["spectra"][0], "settings": {"normalize": "errado"}}]})
    assert bad.status_code == 400
    assert "[AR] Normalização" in bad.get_json()["error"]


def test_catman_descriptor_upload_points_to_the_data_file(webapp):
    """O .TSX do catman descreve o ensaio e não tem os dados dentro."""
    _, client = webapp
    descriptor = (
        "CATMAN TEST FILE\n"
        "Data file=Teste1_ar_comp_medida1.txt\n"
        "Default sample rate=50 Hz\n"
        "Number of samples default sample rate=104119\n"
        "Start time=15/09/2026 15:17:30\n"
    ).encode("utf-8")
    resp = client.post("/api/upload", data={"file": (io.BytesIO(descriptor), "Teste1.TSX")},
                       content_type="multipart/form-data")
    assert resp.status_code == 400
    error = resp.get_json()["error"]
    assert "não contém os dados" in error and "Teste1_ar_comp_medida1.txt" in error


def test_unsupported_extension_lists_what_is_accepted(webapp):
    _, client = webapp
    resp = client.post("/api/upload", data={"file": (io.BytesIO(b"x"), "dados.xyz")},
                       content_type="multipart/form-data")
    assert resp.status_code == 400
    assert ".asc" in resp.get_json()["error"]


def test_version_endpoint_matches_the_page(webapp):
    """A página compara este valor com o seu para avisar sobre servidor antigo."""
    dados, client = webapp
    data = client.get("/api/version").get_json()
    assert data["api_build"] == API_BUILD
    core = (WEBAPP / "static" / "js" / "core.js").read_text(encoding="utf-8")
    assert f'const API_BUILD = "{API_BUILD}"' in core


def test_project_with_empty_sensor_bands_is_saved(webapp):
    """Salvar de novo um projeto aberto mandava band=[null, null] e dava 500."""
    _, client = webapp
    project = {
        "name": "Reaberto",
        "file": "data/raw/ensaio.ASC",
        "series": [{"file": "data/raw/ensaio.ASC",
                    "sensors": [{"channel": "CH_1 Sensor_1 [nm]", "name": "S1",
                                 "band": [None, None], "nominal_wavelength": None}],
                    "processing": {"nulls": {"strategy": "linear"}}}],
    }
    resp = client.post("/api/projects", json=project)
    assert resp.status_code == 200, resp.get_json()
    assert client.get("/api/projects/Reaberto").get_json()["series"][0]["sensors"][0]["band"] is None


def test_malformed_project_answers_json_not_an_html_error_page(webapp):
    _, client = webapp
    resp = client.post("/api/projects", json={
        "name": "Quebrado",
        "series": [{"file": "data/raw/ensaio.ASC", "sensors": [{"name": "sem canal"}]}],
    })
    assert resp.status_code == 400
    assert resp.mimetype == "application/json"
    assert "Projeto inválido" in resp.get_json()["error"]


# ── estatísticas ──────────────────────────────────────────────────────────────

def _analysis(client, **overrides):
    options = {
        "source": "series",
        "series": [{"file": "data/processed/ensaio_processado.csv", "channel": "S1"}],
        "markers": [{"time": "4", "label": "N2"}, {"time": "7", "label": "CO2"}],
        "style": {"data": {"relative_first": False, "to_pm": False}},
        "analysis": {"settle_window": "1", "step_window": "1", "reference": "previous"},
    }
    options.update(overrides)
    return client.post("/api/analysis", json=options)


def test_analysis_reports_intervals_and_steps(webapp):
    _, client = webapp
    _process(client)
    data = _analysis(client).get_json()

    assert data["unit"] == "nm" and data["n_markers"] == 2
    curva = data["curves"][0]
    assert curva["key"] == "S1"
    assert [linha["label"] for linha in curva["intervals"]] == ["antes da 1ª marcação", "N2", "CO2"]

    primeiro = curva["intervals"][0]
    assert primeiro["n"] > 0 and primeiro["mean"] == pytest.approx(1550.0, abs=0.01)
    assert primeiro["delta"] is None, "o primeiro intervalo não tem referência"
    assert curva["intervals"][1]["reference"] == "antes da 1ª marcação"

    degraus = curva["steps"]
    assert [d["label"] for d in degraus] == ["N2", "CO2"]
    assert degraus[0]["step"] == pytest.approx(0.0, abs=0.01), "sinal sem degrau real"
    assert degraus[0]["before_n"] > 0 and degraus[0]["after_n"] > 0


def test_analysis_follows_the_figure_transformations(webapp):
    """Em pm e relativo ao início, as estatísticas mudam de escala junto."""
    _, client = webapp
    _process(client)
    data = _analysis(client, style={"data": {"relative_first": True, "to_pm": True}}).get_json()
    assert data["unit"] == "pm"
    assert abs(data["curves"][0]["intervals"][0]["mean"]) < 50


def test_analysis_without_markers_uses_the_whole_signal(webapp):
    _, client = webapp
    _process(client)
    data = _analysis(client, markers=[]).get_json()
    intervalos = data["curves"][0]["intervals"]
    assert len(intervalos) == 1 and intervalos[0]["label"] == "todo o sinal"
    assert data["curves"][0]["steps"] == []


def test_analysis_rejects_spectra_and_empty_selection(webapp, spectrum_file):
    _, client = webapp
    _process(client)
    resp = _analysis(client, source="spectra",
                     spectra=[{"file": spectrum_file, "trace": "CH 1"}])
    assert resp.status_code == 400 and "séries no tempo" in resp.get_json()["error"]

    vazio = _analysis(client, series=[])
    assert vazio.status_code == 400 and "curva" in vazio.get_json()["error"]


# ── concatenação ──────────────────────────────────────────────────────────────

@pytest.fixture
def segundo_arquivo(webapp):
    """Continuação do ensaio: mesmos canais, valores deslocados."""
    dados, _ = webapp
    linhas = ["Time [s]\tCH_1 Sensor_1 [nm]\tCH_2 Sensor_1 [nm]"]
    for i in range(300):
        linhas.append(f"{i / 50:.3f}\t{1550.5:.6f}\t{1545.5:.6f}".replace(".", ","))
    (dados.raw / "ensaio_parte2.ASC").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return "data/raw/ensaio_parte2.ASC"


def test_processing_two_files_as_one_signal(webapp, segundo_arquivo):
    dados, client = webapp
    resp = _process(client, files=["data/raw/ensaio.ASC", segundo_arquivo],
                    timebase={"enabled": True, "duplicates": "mean", "resample": False})
    data = resp.get_json()
    assert resp.status_code == 200, data

    assert data["n_samples"] == 800, "500 amostras do primeiro mais 300 do segundo"
    assert data["joins"] == [pytest.approx(10.0, abs=0.01)]
    assert any("2 arquivos juntos" in linha for linha in data["report"])
    assert data["time"] == sorted(data["time"]), "o tempo segue crescendo na emenda"

    # o resultado sai num CSV próprio, sem sobrescrever o do primeiro arquivo
    assert data["processed_file"] == "data/processed/ensaio_juntos_processado.csv"
    meta = read_metadata(dados.processed / "ensaio_juntos_processado.csv")
    assert [fonte["file"] for fonte in meta["source"]] == ["ensaio.ASC", "ensaio_parte2.ASC"]
    assert meta["joins"] == [pytest.approx(10.0, abs=0.01)]


def test_joining_files_with_different_channels_is_refused(webapp, spectrum_file):
    dados, client = webapp
    outro = dados.raw / "outro.ASC"
    outro.write_text("Time [s]\tCH_9 Sensor_1 [nm]\n0\t1550,1\n0,02\t1550,2\n0,04\t1550,3\n",
                     encoding="utf-8")
    resp = _process(client, files=["data/raw/ensaio.ASC", "data/raw/outro.ASC"])
    assert resp.status_code == 400
    assert "mesmos canais" in resp.get_json()["error"]


def test_joined_download_is_named_after_the_first_file(webapp, segundo_arquivo):
    _, client = webapp
    resp = client.post("/api/download", json={
        "files": ["data/raw/ensaio.ASC", segundo_arquivo], "sensors": SENSORS})
    assert resp.status_code == 200
    assert resp.headers["Content-Disposition"].endswith("ensaio_juntos_processado.csv")


def test_concat_preview_says_where_each_file_lands(webapp, segundo_arquivo):
    _, client = webapp
    resp = client.post("/api/concat/preview",
                       json={"files": ["data/raw/ensaio.ASC", segundo_arquivo]})
    data = resp.get_json()
    assert resp.status_code == 200, data

    primeiro, segundo = data["parts"]
    assert primeiro["name"] == "ensaio.ASC" and primeiro["index"] == 0
    assert primeiro["start"] == 0 and primeiro["n_samples"] == 500
    assert segundo["start"] == pytest.approx(10.0, abs=0.01), "entra onde o primeiro parou"
    assert segundo["end"] == pytest.approx(15.98, abs=0.03), "5,98 s de sinal a partir daí"
    assert segundo["source"] == "sequência"
    assert data["joins"] == [pytest.approx(10.0, abs=0.01)]
    assert data["n_samples"] == 800
    assert data["total_duration"] == pytest.approx(15.98, abs=0.03)
    assert data["warnings"] == []
    assert primeiro["file"] == "data/raw/ensaio.ASC"


def test_concat_preview_matches_the_processed_signal(webapp, segundo_arquivo):
    """A prévia promete o mesmo que o processamento entrega."""
    _, client = webapp
    arquivos = ["data/raw/ensaio.ASC", segundo_arquivo]
    previa = client.post("/api/concat/preview", json={"files": arquivos}).get_json()
    processado = _process(client, files=arquivos,
                          timebase={"enabled": True, "duplicates": "mean", "resample": False}
                          ).get_json()
    assert previa["joins"] == pytest.approx(processado["joins"])
    assert previa["n_samples"] == processado["n_samples"]


def test_concat_preview_warns_about_different_sampling_rates(webapp):
    dados, client = webapp
    linhas = ["Time [s]\tCH_1 Sensor_1 [nm]\tCH_2 Sensor_1 [nm]"]
    for i in range(200):
        linhas.append(f"{i / 1000:.4f}\t1550,1\t1545,1")          # 1 kHz, não 50 Hz
    (dados.raw / "rapido.ASC").write_text("\n".join(linhas) + "\n", encoding="utf-8")

    data = client.post("/api/concat/preview", json={
        "files": ["data/raw/ensaio.ASC", "data/raw/rapido.ASC"]}).get_json()
    assert len(data["warnings"]) == 1
    aviso = data["warnings"][0]
    assert "taxas de amostragem diferentes" in aviso
    assert "50 Hz" in aviso and "1000 Hz" in aviso


def test_concat_preview_needs_two_files(webapp):
    _, client = webapp
    resp = client.post("/api/concat/preview", json={"files": ["data/raw/ensaio.ASC"]})
    assert resp.status_code == 400
    assert "dois ou mais" in resp.get_json()["error"]

    vazio = client.post("/api/concat/preview", json={"files": []})
    assert vazio.status_code == 400 and "Nenhum arquivo" in vazio.get_json()["error"]


def test_concat_preview_refuses_files_with_other_channels(webapp):
    dados, client = webapp
    (dados.raw / "outro.ASC").write_text(
        "Time [s]\tCH_9 Sensor_1 [nm]\n0\t1550,1\n0,02\t1550,2\n", encoding="utf-8")
    resp = client.post("/api/concat/preview", json={
        "files": ["data/raw/ensaio.ASC", "data/raw/outro.ASC"]})
    assert resp.status_code == 400 and "mesmos canais" in resp.get_json()["error"]


def test_project_remembers_the_join_option(webapp):
    _, client = webapp
    client.post("/api/projects", json={**PROJECT, "name": "Juntos", "join_series": True})
    assert client.get("/api/projects/Juntos").get_json()["join_series"] is True


# ── um CSV processado por projeto ─────────────────────────────────────────────

def test_processed_csv_goes_to_the_project_folder(webapp):
    dados, client = webapp
    data = _process(client, project="Ensaio A").get_json()
    assert data["processed_file"] == "data/processed/Ensaio A/ensaio_processado.csv"
    assert (dados.processed / "Ensaio A" / "ensaio_processado.csv").is_file()
    assert (dados.processed / "Ensaio A" / "ensaio_processado.json").is_file()
    assert not (dados.processed / "ensaio_processado.csv").exists()


def test_two_projects_do_not_overwrite_each_other(webapp):
    dados, client = webapp
    _process(client, project="Bruto")
    _process(client, project="Filtrado",
             moving_average={"enabled": True, "window": "25"})
    bruto = (dados.processed / "Bruto" / "ensaio_processado.csv").read_bytes()
    filtrado = (dados.processed / "Filtrado" / "ensaio_processado.csv").read_bytes()
    assert bruto != filtrado, "cada projeto mantém o próprio resultado"


def test_project_name_cannot_escape_the_processed_folder(webapp):
    dados, client = webapp
    data = _process(client, project="../../fora").get_json()
    salvo = dados.root.joinpath(*Path(data["processed_file"]).parts[1:]).resolve()
    assert dados.processed.resolve() in salvo.parents


def test_preview_does_not_write_and_reports_the_saved_csv(webapp):
    dados, client = webapp
    vazio = _process(client, project="P", save=False).get_json()
    assert vazio["processed_file"] is None and vazio["existing_file"] is None
    assert not (dados.processed / "P").exists(), "pré-visualizar não grava nada"

    _process(client, project="P")
    csv = dados.processed / "P" / "ensaio_processado.csv"
    antes = csv.stat().st_mtime_ns
    previa = _process(client, project="P", save=False).get_json()
    assert previa["processed_file"] is None
    assert previa["existing_file"] == "data/processed/P/ensaio_processado.csv"
    assert csv.stat().st_mtime_ns == antes


def test_new_project_does_not_claim_another_projects_csv(webapp):
    dados, client = webapp
    _process(client)                                   # CSV solto, de antes das pastas
    data = _process(client, project="Novo", save=False).get_json()
    assert data["existing_file"] is None


def test_opening_an_old_project_copies_its_loose_csvs(webapp):
    dados, client = webapp
    _process(client)                                   # CSV solto, de antes das pastas
    solto = dados.processed / "ensaio_processado.csv"
    original = solto.read_bytes()
    client.post("/api/projects", json=PROJECT)

    assert client.get("/api/projects/Ensaio 1").status_code == 200
    copia = dados.processed / "Ensaio 1" / "ensaio_processado.csv"
    assert copia.read_bytes() == original
    assert (dados.processed / "Ensaio 1" / "ensaio_processado.json").is_file()
    assert solto.read_bytes() == original, "o original fica onde estava"

    data = _process(client, project="Ensaio 1", save=False).get_json()
    assert data["existing_file"] == "data/processed/Ensaio 1/ensaio_processado.csv"


def test_opening_a_project_never_overwrites_its_own_csv(webapp):
    dados, client = webapp
    client.post("/api/projects", json=PROJECT)
    _process(client, project="Ensaio 1")
    _process(client)                                   # um CSV solto diferente
    meu = dados.processed / "Ensaio 1" / "ensaio_processado.csv"
    antes = meu.read_bytes()
    client.get("/api/projects/Ensaio 1")
    assert meu.read_bytes() == antes


def test_processed_list_includes_the_project_folder(webapp):
    dados, client = webapp
    _process(client)
    _process(client, project="Ensaio A")
    _process(client, project="Outro")
    data = client.get("/api/processed?project=Ensaio A").get_json()
    assert data["folder"] == "data/processed/Ensaio A"
    assert "data/processed/Ensaio A/ensaio_processado.csv" in data["files"]
    assert not any("Outro" in f for f in data["files"]), "não mistura projetos"
    assert "data/processed/ensaio_processado.csv" not in data["files"]

    sem_projeto = client.get("/api/processed").get_json()
    assert sem_projeto["files"] == ["data/processed/ensaio_processado.csv"]


# ── sinal bruto na mesma escala do processado ────────────────────────────────

def _medianas(data, canal="S1"):
    bruto = np.array([v for v in data["raw"]["signals"][canal] if v is not None])
    proc = np.array([v for v in data["signals"][canal] if v is not None])
    return np.median(bruto), np.median(proc)


def test_raw_overlay_follows_the_delta_lambda_baseline(webapp):
    _, client = webapp
    data = _process(client, include_raw=True,
                    delta_lambda={"enabled": True, "baseline_samples": "20"}).get_json()
    bruto, proc = _medianas(data)
    assert abs(proc) < 0.01, "Δλ fica perto de zero"
    assert abs(bruto - proc) < 0.01, "o bruto perde a mesma linha de base"


def test_raw_overlay_is_shifted_when_a_step_removes_the_dc_level(webapp):
    _, client = webapp
    data = _process(client, include_raw=True,
                    highpass={"enabled": True, "cutoff": "1", "order": "2"}).get_json()
    bruto, proc = _medianas(data)
    assert abs(bruto - proc) < 0.01
    assert any("deslocado pela mediana" in r for r in data["report"])


def test_raw_overlay_is_untouched_without_level_changes(webapp):
    _, client = webapp
    data = _process(client, include_raw=True).get_json()
    bruto, _ = _medianas(data)
    assert bruto == pytest.approx(1550.0, abs=0.01)


# ── páginas servidas pelo pacote instalado ────────────────────────────────────

def test_index_is_served_from_the_package():
    client = create_app(create=False).test_client()
    assert client.get("/").status_code == 200


def test_page_modules_and_styles_are_served():
    """Cada módulo importado pela página existe e é servido como JavaScript."""
    import re

    client = create_app(create=False).test_client()
    page = client.get("/").get_data(as_text=True)
    assert '<script type="module" src="/static/js/main.js">' in page
    assert client.get("/static/css/app.css").mimetype == "text/css"

    pendentes, vistos = ["main.js"], set()
    while pendentes:
        nome = pendentes.pop()
        if nome in vistos:
            continue
        vistos.add(nome)
        resp = client.get(f"/static/js/{nome}")
        assert resp.status_code == 200, nome
        assert resp.mimetype == "text/javascript", nome
        pendentes += re.findall(r'from "\./([\w-]+\.js)"', resp.get_data(as_text=True))
    feitos = {p.name for p in (WEBAPP / "static" / "js").glob("*.js")}
    assert vistos == feitos, "todo módulo da pasta é alcançado a partir de main.js"


# ── uma instância por create_app ─────────────────────────────────────────────

def test_two_apps_do_not_share_the_data_folder(tmp_path):
    a, b = create_app(tmp_path / "a"), create_app(tmp_path / "b")
    (tmp_path / "a" / "raw" / "so_em_a.ASC").write_text("x", encoding="utf-8")
    arquivos = lambda app: [f["path"] for f in app.test_client().get("/api/files").get_json()["files"]]
    assert arquivos(a) == ["data/raw/so_em_a.ASC"]
    assert arquivos(b) == []


def test_create_app_without_create_makes_no_folders(tmp_path):
    create_app(tmp_path / "dados", create=False)
    assert not (tmp_path / "dados").exists()


def test_file_cache_reloads_a_changed_file(tmp_path):
    from braggflow.webapp.state import FileCache

    leituras = []
    cache = FileCache(lambda p: leituras.append(p) or p.read_text(), size=1)
    arquivo, outro = tmp_path / "a.txt", tmp_path / "b.txt"
    arquivo.write_text("1")
    outro.write_text("x")

    assert cache.get(arquivo) == "1" and cache.get(arquivo) == "1"
    assert len(leituras) == 1, "a segunda leitura vem do cache"
    arquivo.write_text("22")                     # tamanho novo = versão nova
    assert cache.get(arquivo) == "22"
    cache.get(outro)                             # size=1: tira o arquivo a.txt
    cache.get(arquivo)
    assert len(leituras) == 4


# ── espectros LMR: transmissão a partir do bruto e evolução entre arquivos ────

LMR_PREPARO = {"lambda_min": 450, "lambda_max": 950, "smooth_window": 21, "detrend": 2}


def test_spectra_evolution_endpoint(webapp):
    from .lmr_synthetic import lmr_series

    dados, client = webapp
    caminhos = lmr_series(dados.raw, resonances=(870.0, 866.0, 862.0))
    items = [{"file": f"data/raw/{c.name}", "settings": LMR_PREPARO} for c in reversed(caminhos)]
    resp = client.post("/api/spectra/evolution", json={"items": items, "kind": "min"})
    data = resp.get_json()
    assert resp.status_code == 200, data
    assert data["x"] == "time" and data["unit"] == "%" and data["warnings"] == []
    assert [f["file"] for f in data["files"]] == [f"data/raw/{c.name}" for c in caminhos]
    assert data["files"][1]["acquired"] == "2026-03-02T09:31:30.500"
    lams = [p["wavelength"] for p in data["tracks"][0]["points"]]
    assert lams == pytest.approx([870, 866, 862], abs=1.5)

    resp = client.post("/api/spectra/evolution", json={"items": items[:1]})
    assert resp.status_code == 400 and "dois ou mais" in resp.get_json()["error"]


def test_spectra_evolution_warns_about_files_without_date(webapp):
    from datetime import datetime

    from .lmr_synthetic import lmr_series

    dados, client = webapp
    com = lmr_series(dados.raw / "com", resonances=(870.0, 866.0))
    sem = lmr_series(dados.raw / "sem", resonances=(862.0,), header=False,
                     start=datetime(2026, 3, 2, 9, 41, 11))
    items = [{"file": f"data/raw/{c.parent.name}/{c.name}", "settings": LMR_PREPARO} for c in com + sem]
    data = client.post("/api/spectra/evolution", json={"items": items}).get_json()
    assert any("mesmo dia" in a for a in data["warnings"])
    # o arquivo sem cabeçalho (09:41) ganha a data dos outros e fica por último
    assert data["files"][-1]["file"].endswith("09-41-11-000.txt")
    assert data["files"][-1]["acquired"] == "09:41:11.000", "sem cabeçalho: só a hora"
    assert data["files"][-1]["elapsed_s"] == pytest.approx(656.0)


def test_preview_converts_raw_counts_with_source_and_dark(webapp):
    from .lmr_synthetic import (DARK_COUNTS, WAVELENGTH, sample_counts, source_counts,
                                transmission, write_oceanview)

    dados, client = webapp
    dados.raw.mkdir(parents=True, exist_ok=True)
    write_oceanview(dados.raw / "amostra.txt", sample_counts(transmission(780.0)))
    write_oceanview(dados.raw / "fonte.txt", source_counts())
    write_oceanview(dados.raw / "fundo.txt", np.full(WAVELENGTH.size, DARK_COUNTS))

    bruto = client.post("/api/spectra/preview", json={
        "file": "data/raw/amostra.txt", "settings": {**LMR_PREPARO, "find_min": True}}).get_json()
    assert bruto["unit"] == "a.u." and bruto["acquired_from"] == "header"

    data = client.post("/api/spectra/preview", json={
        "file": "data/raw/amostra.txt",
        "settings": {**LMR_PREPARO, "find_min": True, "prominence": 0.5,
                     "reference_file": "data/raw/fonte.txt", "dark_file": "data/raw/fundo.txt"},
    }).get_json()
    assert data["unit"] == "%"
    principal = max(data["traces"][0]["extrema"], key=lambda e: e["prominence"])
    assert principal["wavelength"] == pytest.approx(780.0, abs=1.5)

    resp = client.post("/api/spectra/preview", json={
        "file": "data/raw/amostra.txt", "settings": {"reference_file": "data/../fora.txt"}})
    assert resp.status_code == 400 and "fora de data/" in resp.get_json()["error"]


# ── medição de um trecho do gráfico ───────────────────────────────────────────

def test_series_stats_measures_the_processed_signal_without_reprocessing(webapp, monkeypatch):
    import braggflow.webapp.app as app_module
    from braggflow.analysis import selection_statistics

    dados, client = webapp
    opcoes = {"file": "data/raw/ensaio.ASC", "sensors": SENSORS,
              "cleaning": {"enabled": True}, "nulls": {"enabled": True},
              "savgol": {"enabled": True, "window_length": "11", "polyorder": "2"}}
    processado = client.post("/api/process", json={**opcoes, "save": False}).get_json()

    chamadas = []
    original = app_module.run_recipe
    monkeypatch.setattr(app_module, "run_recipe", lambda *a, **k: chamadas.append(1) or original(*a, **k))
    resp = client.post("/api/series/stats", json={"options": {**opcoes, "save": True, "include_raw": True},
                                                  "start": 2.0, "end": 6.0})
    data = resp.get_json()
    assert resp.status_code == 200, data
    assert chamadas == [], "o resultado mostrado no gráfico é reaproveitado"
    assert [c["channel"] for c in data["channels"]] == processado["channels"]
    assert data["duration"] == pytest.approx(4.0)
    s1 = data["channels"][0]
    assert s1["unit"] == "nm" and s1["n"] > 150, "medido no sinal inteiro, não no decimado"
    assert s1["mean"] == pytest.approx(1550.0, abs=0.01)

    # outra receita: processa uma vez e confere com o cálculo direto
    outra = {**opcoes, "savgol": {"enabled": False}}
    resp = client.post("/api/series/stats", json={"options": outra, "start": 2.0, "end": 6.0,
                                                  "relative": True}).get_json()
    assert chamadas == [1]
    pipeline, _, _ = original([dados.raw / "ensaio.ASC"], outra)
    t, sig, _ = pipeline.get_data()
    esperado = selection_statistics(t, sig[:, 1], 2.0, 6.0, relative=True)
    s2 = resp["channels"][1]
    for chave in ("mean", "std", "delta", "value_start", "slope", "n"):
        assert s2[chave] == pytest.approx(esperado[chave]), chave


def test_series_stats_rejects_bad_ranges(webapp):
    _, client = webapp
    resp = client.post("/api/series/stats", json={"options": {"file": "data/raw/ensaio.ASC"},
                                                  "start": 5, "end": 5})
    assert resp.status_code == 400 and "início e fim" in resp.get_json()["error"]
    resp = client.post("/api/series/stats", json={"options": {}, "start": 1, "end": 5})
    assert resp.status_code == 400
