"""
Receita de processamento descrita como um dicionário de opções.

A interface web monta esse dicionário a partir dos cartões de etapa
(``{"cleaning": {"enabled": true, ...}, "savgol": {...}, ...}``) e o comando
``braggflow process`` não liga nenhuma etapa. Os dois passam por
``run_recipe``, que traduz as opções em chamadas ao ``OpticalPipeline`` — a
mesma regra num lugar só.

Os valores podem chegar como texto (vêm de formulários); vazio significa
"padrão" ou "automático", conforme o campo.
"""

from pathlib import Path
from typing import Callable, Optional, Sequence

import numpy as np

from .i18n import count, num, tr
from .io.reader import concatenate, file_fingerprint, load_interrogator_file, with_time_unit
from .pipeline import OpticalPipeline
from .processing import (
    apply_highpass_filter,
    apply_lowpass_filter,
    apply_moving_average_filter,
    apply_savgol_filter,
    estimate_sampling_rate,
    mark_invalid_peaks,
    remove_null_values,
    remove_outliers,
    resample_uniform,
    sort_and_deduplicate,
    temperature_compensation,
    to_delta_lambda,
)
from .processing.compensation import compensation_ratios
from .sensors import Sensor, SensorSetup

# Mapeamento usado quando nenhum setup de sensores é informado. A interface
# o sugere como ponto de partida e permite editar por arquivo.
def as_float(value, default=None):
    """Converte para float aceitando None/'' como ausente."""
    if value is None or value == "":
        return default
    return float(value)


def setup_from_options(options: dict) -> SensorSetup:
    """
    Setup de sensores enviado pela interface. Sem ele, usa o mapeamento
    ``rename`` (formato antigo); sem nenhum dos dois, os canais ficam com o
    nome do arquivo.
    """
    raw = options.get("sensors")
    if not raw:
        return SensorSetup.from_rename_map(options.get("rename") or {})

    sensors = []
    for s in raw:
        low, high = as_float(s.get("band_min")), as_float(s.get("band_max"))
        name = (s.get("name") or "").strip() or None
        if (low is None) != (high is None):
            raise ValueError(tr("recipe.bandIncomplete", name=name or s["channel"]))
        sensors.append(Sensor(
            channel=s["channel"],
            name=name,
            nominal_wavelength=as_float(s.get("nominal_wavelength")),
            band=(low, high) if low is not None else None,
            temp_sensitivity=as_float(s.get("temp_sensitivity")),
            hidden=s.get("hidden") in (True, "true", "1", 1),
        ))
    return SensorSetup(name=str(options.get("setup_name") or ""), sensors=sensors)


def load_file(path: Path):
    """Lê um arquivo do interrogador. Retorna (InterrogatorData, fingerprint da origem)."""
    return load_interrogator_file(path), file_fingerprint(path)


def _invalid_report(entry: dict) -> str:
    """Resumo por canal das leituras marcadas como inválidas numa etapa."""
    n = max(entry["samples_after"], 1)
    parts = []
    for ch, nan_after in entry["nan_after"].items():
        added = nan_after - entry["nan_before"][ch]
        if added > 0:
            parts.append(f"{ch} {count(added)} ({num(100 * added / n, '.2g')}%)")
    return tr("recipe.cleaning", parts=", ".join(parts) if parts else tr("recipe.cleaningNone"))


def _apply_time_unit(caminhos, partes, unidade, messages):
    """
    A unidade da coluna de tempo: escolhida (``time_unit`` = ms, s, min ou
    h) ou a do cabeçalho (``'auto'``, vazio). Devolve as partes convertidas
    e a unidade escolhida, que fica registrada no JSON (None em automático).
    """
    if unidade in (None, "", "auto"):
        lidas = sorted({dados.time_unit for dados, _ in partes} - {None, "s"})
        if lidas:
            messages["report"].append(tr("recipe.timeUnitFromHeader",
                                         unit=", ".join(tr(f"unit.{u}") for u in lidas)))
        return partes, None
    datas = [c.name for c, (dados, _) in zip(caminhos, partes) if dados.time_unit is None]
    if datas:
        messages["warnings"].append(tr("recipe.timeUnitIgnored", names=", ".join(datas)))
    partes = [(with_time_unit(dados, unidade), origem) for dados, origem in partes]
    messages["report"].append(tr("recipe.timeUnit", unit=tr(f"unit.{unidade}")))
    return partes, unidade


def run_recipe(files: Sequence[Path], options: dict, *,
               setup: Optional[SensorSetup] = None,
               load: Callable = load_file):
    """
    Executa o OpticalPipeline com as etapas habilitadas em ``options``.

    ``files`` tem um arquivo, ou vários a juntar em sequência. ``setup``
    substitui o setup descrito nas opções; ``load`` lê um arquivo e devolve
    ``(InterrogatorData, fingerprint)`` (o web app passa a sua versão com
    cache).

    Retorna (pipeline, (raw_time, raw_signals), messages). O bruto é
    capturado após o recorte temporal e a limpeza do interrogador — leituras
    descartadas aparecem como lacunas no overlay. ``messages`` tem as listas
    ``report`` (informativo) e ``warnings`` (atenção do usuário).
    """
    messages = {"report": [], "warnings": []}
    caminhos = [Path(f) for f in files]
    if not caminhos:
        raise ValueError(tr("recipe.noFile"))

    partes = [load(caminho) for caminho in caminhos]
    partes, unidade = _apply_time_unit(caminhos, partes, options.get("time_unit"), messages)
    if len(partes) == 1:
        data, source = partes[0]
        juncoes = []
    else:
        data, juncoes = concatenate([parte[0] for parte in partes])
        source = [parte[1] for parte in partes]
        nomes = ", ".join(caminho.name for caminho in caminhos)
        messages["report"].append(tr("recipe.joined", n=len(partes), names=nomes,
                                     joins=", ".join(f"{num(t)} s" for t in juncoes)))

    pipeline = OpticalPipeline.from_data(data, str(caminhos[0]), source)
    pipeline.joins = juncoes
    if unidade:
        pipeline._record("time_unit", "time", {"unit": unidade}, None)
    setup = setup if setup is not None else setup_from_options(options)

    # Colunas ocultas saem antes de tudo: para o resto, é como se não existissem
    ocultos = setup.hidden_channels(pipeline.source_channels)
    if ocultos:
        if len(ocultos) == len(pipeline.source_channels):
            raise ValueError(tr("recipe.allHidden"))
        pipeline.drop_channels(ocultos)
        messages["report"].append(tr("recipe.hiddenColumns", names=", ".join(setup.names(ocultos))))
    pipeline.apply_setup(setup)

    # Recorte temporal
    window = options.get("window") or {}
    start = as_float(window.get("start"))
    end = as_float(window.get("end"))
    if start is not None or end is not None:
        pipeline.delimit_time_window(start_time=start, end_time=end)

    cleaning = options.get("cleaning") or {}
    if cleaning.get("enabled"):
        pipeline.preprocess(
            mark_invalid_peaks,
            zero_as_missing=bool(cleaning.get("zeros", True)),
            bands=pipeline.sensor_bands() if cleaning.get("bands", True) else None,
            jump_threshold=as_float(cleaning.get("jump_threshold")),
            max_jump_duration=as_float(cleaning.get("jump_duration")),
        )
        messages["report"].append(_invalid_report(pipeline.history[-1]))

    # Bruto (pós-recorte e limpeza) para overlay
    raw_time = pipeline.time_array.copy()
    raw_signals = pipeline.signals_array.copy()

    timebase = options.get("timebase") or {}
    if timebase.get("enabled"):
        pipeline.preprocess(sort_and_deduplicate,
                            duplicates=timebase.get("duplicates", "mean"))
        entry = pipeline.history[-1]
        merged = entry["samples_before"] - entry["samples_after"]
        if merged:
            messages["report"].append(tr("recipe.timebaseMerged", n=count(merged)))
        if timebase.get("resample"):
            fs = _sampling_rate(timebase.get("fs"), pipeline, messages)
            pipeline.preprocess(resample_uniform, fs=fs,
                                max_gap=as_float(timebase.get("max_gap")))
            messages["report"].append(tr("recipe.resampled", fs=num(fs), n=count(len(pipeline.time_array))))

    nulls = options.get("nulls") or {}
    if nulls.get("enabled"):
        pipeline.preprocess(
            remove_null_values,
            strategy=nulls.get("strategy", "linear"),
            fill_value=as_float(nulls.get("fill_value")),
        )

    outliers = options.get("outliers") or {}
    if outliers.get("enabled"):
        pipeline.preprocess(
            remove_outliers,
            method=outliers.get("method", "rolling"),
            threshold=as_float(outliers.get("threshold"), 3.5),
            window_size=int(as_float(outliers.get("window_size"), 51)),
            strategy=outliers.get("strategy", "linear"),
            fill_value=as_float(outliers.get("fill_value")),
        )

    # Etapas que supõem amostragem uniforme e dados completos: avisa sobre
    # lacunas no eixo de tempo e leituras inválidas remanescentes.
    uniform_steps = [name for name, key in (
        ("Savitzky-Golay", "savgol"), (tr("recipe.stepMovingAverage"), "moving_average"),
        (tr("recipe.stepLowpass"), "lowpass"), (tr("recipe.stepHighpass"), "highpass"),
    ) if (options.get(key) or {}).get("enabled")]
    if uniform_steps and len(pipeline.time_array) > 2:
        dt = np.diff(pipeline.time_array)
        n_gaps = int((dt > 1.5 * np.median(dt)).sum())
        if n_gaps:
            messages["warnings"].append(tr("recipe.gaps", n=count(n_gaps), steps=", ".join(uniform_steps)))
        n_nan = int(np.isnan(pipeline.signals_array).sum())
        if n_nan:
            messages["warnings"].append(tr("recipe.nanReachFilters", n=count(n_nan)))

    savgol = options.get("savgol") or {}
    if savgol.get("enabled"):
        janela = int(as_float(savgol.get("window_length"), 11))
        ordem = int(as_float(savgol.get("polyorder"), 2))
        # O scipy recusa em inglês e sem dizer onde; aqui a mensagem nomeia a etapa
        if janela < 3 or janela % 2 == 0:
            raise ValueError(tr("recipe.savgolOdd", window=janela))
        if janela <= ordem:
            raise ValueError(tr("recipe.savgolOrder", window=janela, order=ordem))
        pipeline.apply_filter(apply_savgol_filter, window_length=janela, polyorder=ordem)

    movavg = options.get("moving_average") or {}
    if movavg.get("enabled"):
        pipeline.apply_filter(
            apply_moving_average_filter,
            window_size=int(as_float(movavg.get("window_size"), 30)),
        )

    lowpass = options.get("lowpass") or {}
    if lowpass.get("enabled"):
        pipeline.apply_filter(
            apply_lowpass_filter,
            fs=_sampling_rate(lowpass.get("fs"), pipeline, messages),
            cutoff=as_float(lowpass.get("cutoff"), 20.0),
            order=int(as_float(lowpass.get("order"), 4)),
        )

    highpass = options.get("highpass") or {}
    if highpass.get("enabled"):
        pipeline.apply_filter(
            apply_highpass_filter,
            fs=_sampling_rate(highpass.get("fs"), pipeline, messages),
            cutoff=as_float(highpass.get("cutoff"), 5.0),
            order=int(as_float(highpass.get("order"), 4)),
        )

    delta = options.get("delta_lambda") or {}
    linha_de_base = None
    if delta.get("enabled"):
        n_base = int(as_float(delta.get("baseline_samples"), 20))
        # A mesma linha de base que o Δλ subtrai, para o bruto ir junto
        with np.errstate(all="ignore"):
            linha_de_base = np.nanmean(pipeline.signals_array[:max(n_base, 1)], axis=0)
        pipeline.apply_filter(to_delta_lambda, baseline_samples=n_base)

    tempcomp = options.get("temp_comp") or {}
    if tempcomp.get("enabled"):
        if not delta.get("enabled"):
            raise ValueError(tr("recipe.tempcompNeedsDelta"))
        _compensate_temperature(pipeline, tempcomp, messages)

    raw_signals = _align_raw(raw_signals, pipeline.signals_array, linha_de_base,
                             highpass.get("enabled") or tempcomp.get("enabled"), messages)
    return pipeline, (raw_time, raw_signals), messages


def _compensate_temperature(pipeline: OpticalPipeline, tempcomp: dict, messages: dict) -> None:
    """
    Compensação pela rede de referência: k = K_T,s / K_T,r para cada sensor com
    sensibilidade térmica no setup; ``k_coeff`` para os que não têm.
    """
    referencia = tempcomp.get("channel", "FBG")
    if referencia not in pipeline.channels:
        ocultos = []
        if pipeline.setup:
            ocultos = [s.label for s in pipeline.setup.sensors if s.hidden]
        if referencia in ocultos:
            raise ValueError(tr("recipe.referenceHidden", ref=referencia))
        raise ValueError(tr("recipe.referenceMissing", ref=referencia, channels=", ".join(pipeline.channels)))
    k_padrao = as_float(tempcomp.get("k_coeff"), 1.0)
    sens = pipeline.setup.temp_sensitivities(pipeline.source_channels) if pipeline.setup else []
    kwargs = {"temp_channel_idx": referencia, "k_coeff": k_padrao}
    if any(v is not None for v in sens):
        kwargs["thermal_sensitivities"] = sens
    else:
        sens = [None] * len(pipeline.channels)

    ref = pipeline.channels.index(referencia)
    try:
        ratios = compensation_ratios(len(pipeline.channels), ref, k_padrao,
                                     kwargs.get("thermal_sensitivities"))
    except ValueError:
        if sens[ref] is None:
            raise ValueError(tr("recipe.referenceNeedsKt", ref=referencia)) from None
        raise
    pipeline.apply_filter(temperature_compensation, **kwargs)

    partes = []
    for nome, k, kt in zip(pipeline.channels, ratios, sens):
        if k is None:
            continue
        origem = (f"K_T {num(kt, '.4g')} / {num(sens[ref], '.4g')} pm/°C" if kt is not None
                  else tr("recipe.kGiven"))
        partes.append(f"{nome} k = {num(k, '.4g')} ({origem})")
    messages["report"].append(tr("recipe.tempcompReport", ref=referencia, parts="; ".join(partes)))


def _align_raw(raw: np.ndarray, processed: np.ndarray, linha_de_base, sem_dc: bool,
               messages: dict) -> np.ndarray:
    """
    Põe o sinal bruto do overlay na escala do processado. O Δλ subtrai uma
    linha de base: o bruto perde a mesma. Passa-alta e compensação de
    temperatura também tiram o nível DC; aí o bruto é deslocado pela
    diferença das medianas (aproximado, só para comparar a forma).
    """
    if raw.shape[1] != processed.shape[1]:
        return raw
    if sem_dc:
        with np.errstate(all="ignore"):
            deslocamento = np.nanmedian(raw, axis=0) - np.nanmedian(processed, axis=0)
        messages["report"].append(tr("recipe.rawShifted"))
    elif linha_de_base is not None:
        deslocamento = linha_de_base
    else:
        return raw
    return raw - np.where(np.isfinite(deslocamento), deslocamento, 0.0)


def _sampling_rate(value, pipeline: OpticalPipeline, messages: dict) -> float:
    """fs informado pelo usuário ou, se vazio, estimado do vetor de tempo."""
    fs = as_float(value)
    if fs is None:
        fs = estimate_sampling_rate(pipeline.time_array)
        msg = tr("recipe.fsEstimated", fs=num(fs))
        if msg not in messages["report"]:
            messages["report"].append(msg)
    return fs
