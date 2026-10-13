import numpy as np
import pytest

from braggflow.io.reader import InterrogatorData, concat_plan, concatenate


def _dados(n=100, fs=50.0, valor=1550.0, origem=None):
    t = np.arange(n) / fs
    sinais = np.column_stack([np.full(n, valor), np.full(n, valor - 5)])
    return InterrogatorData(time=t, signals=sinais, channels=["CH_1", "CH_2"],
                            units=["nm", "nm"], time_origin=origem)


def test_files_continue_where_the_previous_stopped():
    juntos, juncoes = concatenate([_dados(), _dados(valor=1551.0)])

    assert len(juntos.time) == 200
    assert juncoes == [pytest.approx(2.0)]          # 100 amostras a 50 Hz + 1 passo
    np.testing.assert_allclose(np.diff(juntos.time), 0.02)
    assert juntos.signals[99, 0] == 1550.0 and juntos.signals[100, 0] == 1551.0


def test_absolute_timestamps_preserve_the_real_gap():
    """Entre as aquisições passaram 10 minutos; a emenda respeita isso."""
    primeiro = _dados(origem="2026-09-15T15:04:02")
    segundo = _dados(valor=1551.0, origem="2026-09-15T15:14:02")
    juntos, juncoes = concatenate([primeiro, segundo])

    assert juncoes == [pytest.approx(600.0)]
    assert juntos.time[100] == pytest.approx(600.0)
    assert juntos.time_origin == "2026-09-15T15:04:02"


def test_overlapping_timestamps_fall_back_to_sequential():
    """Horários incoerentes (o segundo começa antes do fim do primeiro)."""
    primeiro = _dados(origem="2026-09-15T15:04:02")
    segundo = _dados(valor=1551.0, origem="2026-09-15T15:04:03")
    _, juncoes = concatenate([primeiro, segundo])
    assert juncoes == [pytest.approx(2.0)]


def test_three_files_in_a_row():
    juntos, juncoes = concatenate([_dados(), _dados(valor=1551.0), _dados(valor=1552.0)])
    assert len(juntos.time) == 300
    assert juncoes == [pytest.approx(2.0), pytest.approx(4.0)]
    assert np.all(np.diff(juntos.time) > 0)


def test_different_channels_are_rejected():
    outro = _dados()
    outro.channels = ["CH_1", "CH_3"]
    with pytest.raises(ValueError, match="mesmos canais"):
        concatenate([_dados(), outro])


def test_a_single_file_is_returned_unchanged():
    dados = _dados()
    juntos, juncoes = concatenate([dados])
    assert juntos is dados and juncoes == []


def test_empty_input_is_rejected():
    with pytest.raises(ValueError, match="Nenhum arquivo"):
        concatenate([])


# ── plano da concatenação ─────────────────────────────────────────────────────

def test_plan_describes_where_each_file_lands():
    plano = concat_plan([_dados(), _dados(n=50), _dados(n=200)])

    assert [p["index"] for p in plano] == [0, 1, 2]
    assert [p["n_samples"] for p in plano] == [100, 50, 200]
    assert plano[0]["start"] == 0.0 and plano[0]["gap"] is None
    assert plano[0]["end"] == pytest.approx(1.98)      # 99 passos de 0,02 s
    assert plano[1]["start"] == pytest.approx(2.0) and plano[1]["source"] == "sequência"
    assert plano[1]["gap"] == pytest.approx(0.02)
    assert plano[2]["start"] == pytest.approx(3.0)


def test_plan_uses_the_clock_when_the_files_have_timestamps():
    plano = concat_plan([_dados(origem="2026-09-15T15:04:02"),
                         _dados(origem="2026-09-15T15:14:02")])
    assert plano[1]["source"] == "relógio"
    assert plano[1]["start"] == pytest.approx(600.0)
    assert plano[1]["gap"] == pytest.approx(598.02)


def test_plan_matches_the_concatenated_signal():
    partes = [_dados(), _dados(n=50), _dados(n=200)]
    plano = concat_plan(partes)
    juntos, juncoes = concatenate(partes)

    assert juncoes == [pytest.approx(p["start"]) for p in plano[1:]]
    assert juntos.time[0] == pytest.approx(plano[0]["start"])
    assert juntos.time[-1] == pytest.approx(plano[-1]["end"])


def test_plan_reports_the_sampling_step_of_each_file():
    plano = concat_plan([_dados(fs=50.0), _dados(fs=1000.0)])
    assert plano[0]["step"] == pytest.approx(0.02)
    assert plano[1]["step"] == pytest.approx(0.001)
