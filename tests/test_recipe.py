import json
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
from braggflow.recipe import as_float, run_recipe, setup_from_options
from braggflow.sensors import SensorSetup

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "data" / "synthetic_interrogator.asc"


# A cadeia de etapas de examples/01_process_file.py, como opções da receita
RECEITA_DO_EXEMPLO = {
    "cleaning": {"enabled": True, "zeros": True, "bands": True},
    "timebase": {"enabled": True, "duplicates": "mean"},
    "nulls": {"enabled": True, "strategy": "linear"},
    "outliers": {"enabled": True, "method": "rolling", "threshold": 3.5,
                 "window_size": 51, "strategy": "linear"},
    "savgol": {"enabled": True, "window_length": 11, "polyorder": 2},
    "moving_average": {"enabled": True, "window_size": 30},
}


def test_recipe_matches_the_fluent_chain_of_the_example(tmp_path):
    """
    As opções da receita (o que o web app envia) e a cadeia fluente de
    examples/01_process_file.py precisam dar o mesmo CSV.
    """
    fluente = tmp_path / "fluente.csv"
    pipeline = OpticalPipeline(EXAMPLE)
    pipeline.load_data().apply_setup(SensorSetup())
    (pipeline
     .delimit_time_window(start_time=None, end_time=None)
     .preprocess(mark_invalid_peaks, zero_as_missing=True, bands=pipeline.sensor_bands())
     .preprocess(sort_and_deduplicate, duplicates="mean")
     .preprocess(remove_null_values, strategy="linear")
     .preprocess(remove_outliers, method="rolling", threshold=3.5, window_size=51, strategy="linear")
     .apply_filter(apply_savgol_filter, window_length=11, polyorder=2)
     .apply_filter(apply_moving_average_filter, window_size=30)
     .save_processed_data(fluente))

    receita, _, _ = run_recipe([EXAMPLE], RECEITA_DO_EXEMPLO)
    receita.save_processed_data(tmp_path / "receita.csv")
    assert (tmp_path / "receita.csv").read_bytes() == fluente.read_bytes()


def test_cli_saves_the_file_with_no_step_and_names_from_the_columns(tmp_path):
    """Como um projeto novo do web app: nenhuma etapa ligada, nenhum nome inventado."""
    cli = process_file(EXAMPLE, out=tmp_path / "cli.csv", plot=False)
    assert cli.read_text(encoding="utf-8").splitlines()[0] == (
        "Time [s],CH_1 Sensor_1 [nm],CH_2 Sensor_1 [nm],CH_3 Sensor_1 [nm]")
    passos = [p["step"] for p in json.loads(cli.with_suffix(".json").read_text(encoding="utf-8"))["steps"]]
    assert passos == ["apply_setup"]


def test_steps_follow_the_options():
    pipeline, _, messages = run_recipe([EXAMPLE], RECEITA_DO_EXEMPLO)
    steps = [entry["step"] for entry in pipeline.history]
    assert steps == ["apply_setup", "mark_invalid_peaks", "sort_and_deduplicate",
                     "remove_null_values", "remove_outliers", "apply_savgol_filter",
                     "apply_moving_average_filter"]
    # Sem setup, cada canal fica com o nome da coluna, sem a unidade
    assert pipeline.channels == ["CH_1 Sensor_1", "CH_2 Sensor_1", "CH_3 Sensor_1"]
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
        run_recipe([], RECEITA_DO_EXEMPLO)


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
    # Sem setup, a referência é chamada pelo nome da coluna, sem a unidade
    com, _, messages = run_recipe([EXAMPLE], {**COMP, "temp_comp": {"enabled": True, "channel": "CH_3 Sensor_1"}})
    assert _deriva(sem) > 10 * _deriva(com)
    assert any("CH_1 Sensor_1 k = 1 (k informado)" in r for r in messages["report"])


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


# ── colunas ocultas ──────────────────────────────────────────────────────────

def _setup_com_oculto(*ocultos):
    return setup_from_options({"sensors": [
        {"channel": "CH_1 Sensor_1 [nm]", "name": "EFBG1", "hidden": "CH_1" in ocultos},
        {"channel": "CH_2 Sensor_1 [nm]", "name": "EFBG2", "hidden": "CH_2" in ocultos},
        {"channel": "CH_3 Sensor_1 [nm]", "name": "FBG", "hidden": "CH_3" in ocultos},
    ]})


def test_hidden_columns_are_left_out_of_everything(tmp_path):
    pipeline, (_, raw), messages = run_recipe([EXAMPLE], COMP | {"temp_comp": {"enabled": False}},
                                               setup=_setup_com_oculto("CH_2"))
    assert pipeline.channels == ["EFBG1", "FBG"]
    assert raw.shape[1] == 2, "o bruto do gráfico também não tem a coluna"
    assert "Colunas ocultas, fora do processamento: EFBG2" in messages["report"]
    assert pipeline.history[0]["step"] == "drop_channels"
    out = tmp_path / "x.csv"
    pipeline.save_processed_data(out)
    assert out.read_text(encoding="utf-8").splitlines()[0] == "Time [s],EFBG1 [nm],FBG [nm]"


def test_all_columns_hidden_is_explained():
    with pytest.raises(ValueError, match="Todas as colunas estão ocultas"):
        run_recipe([EXAMPLE], {}, setup=_setup_com_oculto("CH_1", "CH_2", "CH_3"))


def test_hidden_reference_is_explained():
    with pytest.raises(ValueError, match="referência 'FBG' está oculto"):
        run_recipe([EXAMPLE], COMP, setup=_setup_com_oculto("CH_3"))


@pytest.mark.parametrize("janela, ordem, trecho", [(2, 2, "ímpar a partir de 3"), (10, 2, "ímpar"),
                                                    (3, 3, "maior que a ordem (3)")])
def test_savgol_window_is_explained_in_the_step_terms(janela, ordem, trecho):
    with pytest.raises(ValueError, match=r"^Savitzky-Golay: ") as erro:
        run_recipe([EXAMPLE], {"savgol": {"enabled": True, "window_length": janela, "polyorder": ordem}})
    assert trecho in str(erro.value)


# ── unidade do tempo ─────────────────────────────────────────────────────────

def test_time_unit_option_reads_the_file_time_in_minutes(tmp_path):
    segundos, _, _ = run_recipe([EXAMPLE], {})
    minutos, _, messages = run_recipe([EXAMPLE], {"time_unit": "min"})
    np.testing.assert_allclose(minutos.time_array, segundos.time_array * 60)
    assert "Tempo do arquivo lido em minutos." in messages["report"]
    assert minutos.history[0] == {"step": "time_unit", "kind": "time", "params": {"unit": "min"}}


def test_cli_time_unit(tmp_path):
    cli = process_file(EXAMPLE, out=tmp_path / "h.csv", plot=False, time_unit="h")
    tempo = np.loadtxt(cli, delimiter=",", skiprows=1, usecols=0)
    assert tempo[-1] == pytest.approx(900 * 3600)


def test_a_unit_in_the_header_is_reported_and_dates_are_left_alone(tmp_path):
    arquivo = tmp_path / "min.asc"
    arquivo.write_text("Time [min]\tCH_1\n0\t1550.1\n1\t1550.2\n2\t1550.3\n", encoding="utf-8")
    pipeline, _, messages = run_recipe([arquivo], {})
    np.testing.assert_allclose(pipeline.time_array, [0, 60, 120])
    assert any("Tempo do arquivo em minutos, pelo cabeçalho" in r for r in messages["report"])

    datas = tmp_path / "datas.csv"
    datas.write_text("Timestamp;CH_1\n16/09/2026 10:23:38;1550,1\n16/09/2026 10:23:40;1550,3\n", encoding="utf-8")
    pipeline, _, messages = run_recipe([datas], {"time_unit": "h"})
    np.testing.assert_allclose(pipeline.time_array, [0, 2])
    assert messages["warnings"] == ["O tempo de datas.csv vem de datas e horas: a unidade escolhida não se aplica."]
