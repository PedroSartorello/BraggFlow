"""
app.py – Front-end web do pipeline óptico (BraggFlow)
=====================================================
Servidor Flask que expõe o ``OpticalPipeline`` (o mesmo usado por
``main.py``) para processamento interativo no navegador: o usuário escolhe
o arquivo .ASC, liga/desliga etapas, ajusta parâmetros e vê o resultado em
um gráfico Plotly em tempo real.

Uso:
    python webapp/app.py
    # abra http://127.0.0.1:5000
"""

import base64
import io
import shutil
import threading
import uuid
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

import numpy as np
from flask import Flask, jsonify, render_template, request, send_file

import json

import matplotlib
matplotlib.use("Agg")  # backend sem janela — obrigatório em servidor

from braggflow.analysis import analyse_curve
from braggflow.io.processed import (
    channel_quantities,
    metadata_path_for,
    read_metadata,
    read_processed_csv,
    read_processed_header,
)
from braggflow.paths import resolve_data_dir
from braggflow.io.reader import (
    DESCRIPTOR_EXTENSIONS,
    classify_file,
    concat_plan,
    concatenate,
    describe_file,
    file_fingerprint,
    load_interrogator_file,
    load_spectra,
    read_descriptor,
)
from braggflow.pipeline import OpticalPipeline
from braggflow.projects import Project
from braggflow.sensors import Sensor, SensorSetup
from braggflow.processing.spectra import (
    NORMALIZATIONS,
    analyse_spectrum,
    default_spectrum_settings,
    prepare_spectrum,
    resolve_spectrum_settings,
)
from braggflow.visualization.figure import (
    CHANNEL_LINESTYLES,
    channel_values,
    marker_offset,
    render_curve_figure,
    series_labels,
    shift_markers,
    spectrum_labels,
    time_axis,
    EXPORT_FORMATS,
    LEGEND_POSITIONS,
    MARKERS,
    PALETTES,
    available_fonts,
    default_style,
    parse_markers,
    render_figure,
    resolve_style,
)
from braggflow.processing import (
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

# Pasta de dados: --data-dir, BRAGGFLOW_DATA_DIR ou ./data (braggflow.paths).
# A API e os projetos salvos se referem aos arquivos como "data/<subpasta>/...":
# esse "data" é um prefixo virtual que aponta para a pasta escolhida, qualquer
# que seja o nome ou o lugar dela, para que projetos antigos continuem abrindo.
DATA_PREFIX = "data"


def set_data_dir(data_dir=None, *, create: bool = True) -> Path:
    """Escolhe a pasta de dados do app (e cria as subpastas, por padrão)."""
    global DATA_DIR, RAW_DIR, UPLOAD_DIR, PROCESSED_DIR, SETUPS_DIR, STYLES_DIR, PROJECTS_DIR
    DATA_DIR = resolve_data_dir(data_dir, create=create)
    RAW_DIR = DATA_DIR / "raw"
    UPLOAD_DIR = DATA_DIR / "uploads"
    PROCESSED_DIR = DATA_DIR / "processed"
    SETUPS_DIR = DATA_DIR / "setups"
    STYLES_DIR = DATA_DIR / "styles"
    PROJECTS_DIR = DATA_DIR / "projects"
    return DATA_DIR


# Só importar o módulo não cria pastas; o comando braggflow-web as cria
set_data_dir(create=False)


def _rel(path: Path) -> str:
    """Caminho de um arquivo como a API o mostra: ``data/<subpasta>/...``."""
    return f"{DATA_PREFIX}/{Path(path).relative_to(DATA_DIR).as_posix()}"

# Qualquer exportação de texto do interrogador ou do analisador de espectro
RAW_EXTENSIONS = {".asc", ".txt", ".csv", ".dat", ".tsv", ".prn", ".spec"}

# rcParams do matplotlib são globais; o servidor Flask atende em threads
_figure_lock = threading.Lock()

FIGURE_MIMETYPES = {"pdf": "application/pdf", "png": "image/png", "svg": "image/svg+xml",
                    "eps": "application/postscript", "tiff": "image/tiff"}

# Arquivos do interrogador já lidos (reprocessar não relê o disco)
FILE_CACHE_SIZE = 2
_file_cache: OrderedDict = OrderedDict()
_spectrum_cache: OrderedDict = OrderedDict()
_processed_cache: OrderedDict = OrderedDict()
_kind_cache: dict = {}
_cache_lock = threading.Lock()

# Sugestão inicial de mapeamento (mesma de main.py). A interface permite
# editar por arquivo, já que o mapeamento nem sempre é o mesmo.
DEFAULT_RENAME = {
    "CH_1 Sensor_1 [nm]": "EFBG1",
    "CH_2 Sensor_1 [nm]": "EFBG2",
    "CH_3 Sensor_1 [nm]": "FBG",
}

# Máximo de pontos por canal enviados ao gráfico (o processamento usa tudo)
MAX_PLOT_POINTS = 8000

# Mude junto com o literal API_BUILD em templates/index.html sempre que as
# rotas mudarem: é assim que a página percebe um servidor ainda sem reiniciar.
API_BUILD = "2026-10-14"

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200 MB
app.config["TEMPLATES_AUTO_RELOAD"] = True


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _list_raw_files() -> list[dict]:
    """
    Arquivos brutos disponíveis, com o tipo de conteúdo de cada um:
    ``timeseries`` (pico por canal no tempo) ou ``spectrum`` (intensidade por
    comprimento de onda).
    """
    files = []
    for folder in (RAW_DIR, UPLOAD_DIR):
        if not folder.is_dir():
            continue
        for f in sorted(folder.iterdir()):
            if not (f.is_file() and f.suffix.lower() in RAW_EXTENSIONS):
                continue
            stat = f.stat()
            files.append({
                "path": _rel(f),
                "kind": _cached_kind(f),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="minutes"),
            })
    return files


def _cached_kind(path: Path) -> str:
    """Tipo do arquivo, lido só do começo dele e guardado por data/tamanho."""
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    with _cache_lock:
        if key in _kind_cache:
            return _kind_cache[key]
    try:
        kind = classify_file(path)
    except (ValueError, IOError, OSError):
        kind = "unknown"
    with _cache_lock:
        _kind_cache[key] = kind
    return kind


def _resolve_data_file(rel_path: str) -> Path:
    """Resolve um caminho ``data/...`` garantindo que fique dentro da pasta de dados."""
    caminho = Path(rel_path)
    if caminho.is_absolute():
        full = caminho.resolve()
    elif caminho.parts[:1] == (DATA_PREFIX,):
        full = DATA_DIR.joinpath(*caminho.parts[1:]).resolve()
    else:
        full = None
    data_dir = DATA_DIR.resolve()
    if full is None or not full.is_file() or data_dir not in full.parents:
        raise ValueError(f"Arquivo inválido ou fora de data/: {rel_path}")
    return full


def _num(value, default=None):
    """Converte para float aceitando None/'' como ausente."""
    if value is None or value == "":
        return default
    return float(value)


def _safe_name(name: str) -> str:
    """Mantém apenas caracteres inofensivos em nomes de arquivo."""
    return "".join(c for c in name if c.isalnum() or c in "._- ").strip(". ")


def _load_cached(path: Path):
    """
    Lê o arquivo do interrogador uma única vez e reaproveita a leitura
    enquanto ele não mudar (mesmo caminho, data de modificação e tamanho).
    Retorna (InterrogatorData, fingerprint da origem).
    """
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    with _cache_lock:
        if key in _file_cache:
            _file_cache.move_to_end(key)
            return _file_cache[key]

    entry = (load_interrogator_file(path), file_fingerprint(path))
    with _cache_lock:
        for old in [k for k in _file_cache if k[0] == key[0]]:
            del _file_cache[old]  # versões antigas do mesmo arquivo
        _file_cache[key] = entry
        while len(_file_cache) > FILE_CACHE_SIZE:
            _file_cache.popitem(last=False)
    return entry


def _load_processed_cached(path: Path):
    """Lê um CSV processado uma vez e reaproveita enquanto ele não mudar."""
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    with _cache_lock:
        if key in _processed_cache:
            _processed_cache.move_to_end(key)
            return _processed_cache[key]

    df, units, metadata = read_processed_csv(path)
    entry = (df, units, channel_quantities(metadata))
    with _cache_lock:
        for old in [k for k in _processed_cache if k[0] == key[0]]:
            del _processed_cache[old]
        _processed_cache[key] = entry
        while len(_processed_cache) > FILE_CACHE_SIZE * 3:
            _processed_cache.popitem(last=False)
    return entry


def _load_spectra_cached(path: Path):
    """Lê o arquivo de espectro uma vez e reaproveita enquanto ele não mudar."""
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    with _cache_lock:
        if key in _spectrum_cache:
            _spectrum_cache.move_to_end(key)
            return _spectrum_cache[key]

    spectra = load_spectra(path)
    with _cache_lock:
        for old in [k for k in _spectrum_cache if k[0] == key[0]]:
            del _spectrum_cache[old]
        _spectrum_cache[key] = spectra
        while len(_spectrum_cache) > FILE_CACHE_SIZE * 3:
            _spectrum_cache.popitem(last=False)
    return spectra


def _curve_key(path: Path, spectra, trace_name: str) -> str:
    """Identificador da curva: o nome do arquivo basta quando há um traço só."""
    stem = path.stem
    return stem if len(spectra.spectra) == 1 else f"{stem} · {trace_name}"


def _spectrum_items(options: dict) -> list[dict]:
    """
    Curvas de espectro pedidas pela interface. Cada entrada traz o seu próprio
    preparo (recorte, suavização, normalização e deslocamento), aplicado só a
    ela.
    """
    items = []
    for entry in options.get("spectra") or []:
        path = _resolve_data_file(entry["file"])
        spectra = _load_spectra_cached(path)
        name = entry.get("trace") or (spectra.names[0] if spectra.names else "")
        spectrum = spectra.get(name)
        if spectrum is None:
            raise ValueError(f"Traço '{name}' não encontrado em {path.name}.")

        key = _curve_key(path, spectra, name)
        settings = resolve_spectrum_settings(entry.get("settings"), prefix=f"[{key}] ")
        wavelength, intensity = prepare_spectrum(spectrum.wavelength, spectrum.intensity, settings)
        items.append({"key": key, "label": entry.get("label") or key,
                      "x": wavelength, "y": intensity})
    if not items:
        raise ValueError("Selecione pelo menos um espectro.")
    return items


def _series_entries(options: dict) -> list[dict]:
    """Entradas ``{file, channel}``; aceita o formato antigo (um arquivo só)."""
    entries = options.get("series")
    if entries:
        return [e for e in entries if e.get("file") and e.get("channel")]

    file = options.get("file")
    if not file:
        return []
    channels = options.get("channels")
    if not channels:
        df, _, _ = _load_processed_cached(_resolve_data_file(file))
        channels = [c for c in df.columns if c != "Time"]
    return [{"file": file, "channel": channel} for channel in channels]


def _series_items(options: dict, style: dict, markers: list):
    """
    Curvas de série no tempo, possivelmente de vários CSVs processados.
    Retorna ``(items, xlabel, ylabel, divisor, markers)``.
    """
    entries = _series_entries(options)
    if not entries:
        raise ValueError("Selecione pelo menos uma curva.")

    offset = marker_offset(markers, style["data"])
    markers = shift_markers(markers, offset)
    several = len({entry["file"] for entry in entries}) > 1

    items, unit, is_shift, divisor = [], "nm", False, 1.0
    for entry in entries:
        path = _resolve_data_file(entry["file"])
        df, units, quantities = _load_processed_cached(path)
        channel = entry["channel"]
        if channel not in df.columns:
            raise ValueError(f"Canal '{channel}' não existe em {path.name}.")

        x, divisor = time_axis(df, style["data"], offset)
        y, unit, is_shift = channel_values(df, units, quantities, channel, style["data"])
        stem = path.stem.removesuffix("_processado")
        key = f"{stem} · {channel}" if several else channel
        items.append({"key": key, "label": key, "x": x, "y": y})

    xlabel, ylabel = series_labels(unit, is_shift, style["data"]["time_unit"],
                                   style["axes"]["language"])
    return items, xlabel, ylabel, divisor, markers


def _setup_from_options(options: dict) -> SensorSetup:
    """
    Setup de sensores enviado pela interface. Sem ele, usa o mapeamento
    ``rename`` (formato antigo) ou o padrão de main.py.
    """
    raw = options.get("sensors")
    if not raw:
        return SensorSetup.from_rename_map(options.get("rename") or DEFAULT_RENAME)

    sensors = []
    for s in raw:
        low, high = _num(s.get("band_min")), _num(s.get("band_max"))
        name = (s.get("name") or "").strip() or None
        if (low is None) != (high is None):
            raise ValueError(
                f"Banda incompleta no sensor '{name or s['channel']}': "
                "informe mínimo e máximo, ou deixe os dois vazios."
            )
        sensors.append(Sensor(
            channel=s["channel"],
            name=name,
            nominal_wavelength=_num(s.get("nominal_wavelength")),
            band=(low, high) if low is not None else None,
        ))
    return SensorSetup(name=str(options.get("setup_name") or ""), sensors=sensors)


def _br(valor: float, fmt: str = ".4g") -> str:
    """Número para as mensagens da interface, no padrão brasileiro (2,5)."""
    return format(valor, fmt).replace(".", ",")


def _br_int(n: int) -> str:
    """Contagem com ponto de milhar (12.996)."""
    return f"{int(n):,}".replace(",", ".")


def _invalid_report(entry: dict) -> str:
    """Resumo por canal das leituras marcadas como inválidas numa etapa."""
    n = max(entry["samples_after"], 1)
    parts = []
    for ch, nan_after in entry["nan_after"].items():
        added = nan_after - entry["nan_before"][ch]
        if added > 0:
            parts.append(f"{ch} {_br_int(added)} ({_br(100 * added / n, '.2g')}%)")
    return "Limpeza: " + (", ".join(parts) if parts else "nenhuma leitura inválida")


def _run_pipeline(options: dict):
    """
    Executa o OpticalPipeline com as etapas habilitadas em ``options``.

    Retorna (pipeline, (raw_time, raw_signals), messages). O bruto é
    capturado após o recorte temporal e a limpeza do interrogador — leituras
    descartadas aparecem como lacunas no overlay. ``messages`` tem as listas
    ``report`` (informativo) e ``warnings`` (atenção do usuário).
    """
    messages = {"report": [], "warnings": []}
    caminhos = _requested_files(options)

    partes = [_load_cached(caminho) for caminho in caminhos]
    if len(partes) == 1:
        data, source = partes[0]
        juncoes = []
    else:
        data, juncoes = concatenate([parte[0] for parte in partes])
        source = [parte[1] for parte in partes]
        nomes = ", ".join(caminho.name for caminho in caminhos)
        messages["report"].append(
            f"{len(partes)} arquivos juntos ({nomes}); emendas em "
            + ", ".join(f"{_br(t)} s" for t in juncoes))

    pipeline = OpticalPipeline.from_data(data, str(caminhos[0]), source)
    pipeline.joins = juncoes
    pipeline.apply_setup(_setup_from_options(options))

    # Recorte temporal
    window = options.get("window") or {}
    start = _num(window.get("start"))
    end = _num(window.get("end"))
    if start is not None or end is not None:
        pipeline.delimit_time_window(start_time=start, end_time=end)

    cleaning = options.get("cleaning") or {}
    if cleaning.get("enabled"):
        pipeline.preprocess(
            mark_invalid_peaks,
            zero_as_missing=bool(cleaning.get("zeros", True)),
            bands=pipeline.sensor_bands() if cleaning.get("bands", True) else None,
            jump_threshold=_num(cleaning.get("jump_threshold")),
            max_jump_duration=_num(cleaning.get("jump_duration")),
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
            messages["report"].append(
                f"Eixo de tempo: {_br_int(merged)} amostra(s) com tempo repetido ou inválido unidas/descartadas"
            )
        if timebase.get("resample"):
            fs = _sampling_rate(timebase.get("fs"), pipeline, messages)
            pipeline.preprocess(resample_uniform, fs=fs,
                                max_gap=_num(timebase.get("max_gap")))
            messages["report"].append(
                f"Reamostrado a {_br(fs)} Hz ({_br_int(len(pipeline.time_array))} amostras)"
            )

    nulls = options.get("nulls") or {}
    if nulls.get("enabled"):
        pipeline.preprocess(
            remove_null_values,
            strategy=nulls.get("strategy", "linear"),
            fill_value=_num(nulls.get("fill_value")),
        )

    outliers = options.get("outliers") or {}
    if outliers.get("enabled"):
        pipeline.preprocess(
            remove_outliers,
            method=outliers.get("method", "rolling"),
            threshold=_num(outliers.get("threshold"), 3.5),
            window_size=int(_num(outliers.get("window_size"), 51)),
            strategy=outliers.get("strategy", "linear"),
            fill_value=_num(outliers.get("fill_value")),
        )

    # Etapas que supõem amostragem uniforme e dados completos: avisa sobre
    # lacunas no eixo de tempo e leituras inválidas remanescentes.
    uniform_steps = [name for name, key in (
        ("Savitzky-Golay", "savgol"), ("média móvel", "moving_average"),
        ("passa-baixa", "lowpass"), ("passa-alta", "highpass"),
    ) if (options.get(key) or {}).get("enabled")]
    if uniform_steps and len(pipeline.time_array) > 2:
        dt = np.diff(pipeline.time_array)
        n_gaps = int((dt > 1.5 * np.median(dt)).sum())
        if n_gaps:
            messages["warnings"].append(
                f"{_br_int(n_gaps)} lacuna(s) no eixo de tempo; {', '.join(uniform_steps)} "
                "supõe(m) amostragem uniforme. Ative a reamostragem no cartão "
                "'Eixo de tempo' ou use estratégias que preservam as linhas."
            )
        n_nan = int(np.isnan(pipeline.signals_array).sum())
        if n_nan:
            messages["warnings"].append(
                f"{_br_int(n_nan)} leitura(s) inválida(s) chegam aos filtros e serão "
                "propagadas; ative 'Remoção de nulos'."
            )

    savgol = options.get("savgol") or {}
    if savgol.get("enabled"):
        pipeline.apply_filter(
            apply_savgol_filter,
            window_length=int(_num(savgol.get("window_length"), 11)),
            polyorder=int(_num(savgol.get("polyorder"), 2)),
        )

    movavg = options.get("moving_average") or {}
    if movavg.get("enabled"):
        pipeline.apply_filter(
            apply_moving_average_filter,
            window_size=int(_num(movavg.get("window_size"), 30)),
        )

    lowpass = options.get("lowpass") or {}
    if lowpass.get("enabled"):
        pipeline.apply_filter(
            apply_lowpass_filter,
            fs=_sampling_rate(lowpass.get("fs"), pipeline, messages),
            cutoff=_num(lowpass.get("cutoff"), 20.0),
            order=int(_num(lowpass.get("order"), 4)),
        )

    highpass = options.get("highpass") or {}
    if highpass.get("enabled"):
        pipeline.apply_filter(
            apply_highpass_filter,
            fs=_sampling_rate(highpass.get("fs"), pipeline, messages),
            cutoff=_num(highpass.get("cutoff"), 5.0),
            order=int(_num(highpass.get("order"), 4)),
        )

    delta = options.get("delta_lambda") or {}
    linha_de_base = None
    if delta.get("enabled"):
        n_base = int(_num(delta.get("baseline_samples"), 20))
        # A mesma linha de base que o Δλ subtrai, para o bruto ir junto
        with np.errstate(all="ignore"):
            linha_de_base = np.nanmean(pipeline.signals_array[:max(n_base, 1)], axis=0)
        pipeline.apply_filter(to_delta_lambda, baseline_samples=n_base)

    tempcomp = options.get("temp_comp") or {}
    if tempcomp.get("enabled"):
        pipeline.apply_filter(
            temperature_compensation,
            temp_channel_idx=tempcomp.get("channel", "FBG"),
            k_coeff=_num(tempcomp.get("k_coeff"), 1.0),
        )

    raw_signals = _align_raw(raw_signals, pipeline.signals_array, linha_de_base,
                             highpass.get("enabled") or tempcomp.get("enabled"), messages)
    return pipeline, (raw_time, raw_signals), messages


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
        messages["report"].append(
            "Sinal bruto deslocado pela mediana para a escala do processado "
            "(passa-alta ou compensação de temperatura tiram o nível DC)")
    elif linha_de_base is not None:
        deslocamento = linha_de_base
    else:
        return raw
    return raw - np.where(np.isfinite(deslocamento), deslocamento, 0.0)


def _sampling_rate(value, pipeline: OpticalPipeline, messages: dict) -> float:
    """fs informado pelo usuário ou, se vazio, estimado do vetor de tempo."""
    fs = _num(value)
    if fs is None:
        fs = estimate_sampling_rate(pipeline.time_array)
        msg = f"fs estimado a partir do vetor de tempo: {_br(fs)} Hz"
        if msg not in messages["report"]:
            messages["report"].append(msg)
    return fs


def _requested_files(options: dict) -> list[Path]:
    """Arquivos do processamento: um só, ou vários a juntar em sequência."""
    pedidos = options.get("files") or ([options["file"]] if options.get("file") else [])
    if not pedidos:
        raise ValueError("Nenhum arquivo selecionado.")
    return [_resolve_data_file(caminho) for caminho in pedidos]


def _processed_name(options: dict) -> str:
    """``<primeiro>_processado.csv``; com vários arquivos, ``_juntos``."""
    arquivos = options.get("files") or [options.get("file", "")]
    stem = Path(arquivos[0]).stem
    return f"{stem}_juntos" if len(arquivos) > 1 else stem


def _processed_dir(options: dict) -> Path:
    """
    Pasta dos CSVs processados: ``data/processed/<projeto>/``. Cada projeto
    tem a sua, para que o mesmo arquivo bruto processado com opções
    diferentes em outro projeto não sobrescreva este. Sem nome de projeto,
    usa ``data/processed/`` como antes.
    """
    projeto = _safe_name(str(options.get("project") or ""))
    return PROCESSED_DIR / projeto if projeto else PROCESSED_DIR


def _existing_processed(stem: str, folder: Path) -> str | None:
    """CSV já salvo para ``stem`` na pasta do projeto, se houver."""
    caminho = folder / f"{stem}_processado.csv"
    if caminho.is_file():
        return _rel(caminho)
    return None


def _adopt_legacy_processed(project: Project) -> None:
    """
    Projetos de antes das pastas por projeto: copia para a pasta do projeto
    os CSVs dos seus arquivos que estavam soltos em ``data/processed/``
    (com o JSON de rastreabilidade), sem apagar nem alterar os originais.
    Só copia o que ainda não existe na pasta do projeto.
    """
    pasta = _processed_dir({"project": project.name})
    if pasta == PROCESSED_DIR:
        return
    for entry in project.series:
        stem = Path(entry["file"]).stem
        for nome in (f"{stem}_processado.csv", f"{stem}_juntos_processado.csv"):
            origem, destino = PROCESSED_DIR / nome, pasta / nome
            if not origem.is_file() or destino.exists():
                continue
            pasta.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origem, destino)
            if metadata_path_for(origem).is_file():
                shutil.copy2(metadata_path_for(origem), metadata_path_for(destino))


def _save_processed(pipeline: OpticalPipeline, source_rel: str,
                    folder: Path | None = None) -> str:
    """
    Grava o resultado completo em <pasta>/<nome>_processado.csv (mesmo nome
    de main.py), junto com o JSON de rastreabilidade, para que apareça na aba
    Visualização. Escreve em arquivos temporários e substitui no fim, para
    que a figura nunca leia um CSV pela metade durante um reprocessamento.
    """
    folder = folder or PROCESSED_DIR
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"{source_rel}_processado.csv"
    token = uuid.uuid4().hex
    tmp_csv = dest.with_name(f".{dest.stem}.{token}.csv.tmp")
    tmp_json = dest.with_name(f".{dest.stem}.{token}.json.tmp")
    try:
        pipeline.save_processed_data(tmp_csv, metadata_path=tmp_json)
        tmp_csv.replace(dest)
        tmp_json.replace(metadata_path_for(dest))
    finally:
        tmp_csv.unlink(missing_ok=True)
        tmp_json.unlink(missing_ok=True)
    return _rel(dest)


def _downsample(*arrays: np.ndarray, max_points: int = MAX_PLOT_POINTS):
    """Aplica o mesmo stride a todos os arrays (linhas) para o payload do plot."""
    n = len(arrays[0])
    stride = max(1, int(np.ceil(n / max_points)))
    return [a[::stride] for a in arrays], stride


def _to_jsonable(arr: np.ndarray) -> list:
    """Converte array 1D em lista JSON-válida (NaN/Inf → null)."""
    arr = np.asarray(arr, dtype=float)
    out = arr.astype(object)
    out[~np.isfinite(arr)] = None
    return out.tolist()


# ─────────────────────────────────────────────────────────────────────────────
# Figuras de publicação (aba Visualização)
# ─────────────────────────────────────────────────────────────────────────────

def _is_spectrum_request(options: dict) -> bool:
    return str(options.get("source", "")) == "spectra"


def _render_requested_figure(options: dict, fmt=None, preview: bool = False):
    """
    Desenha a figura pedida, de série no tempo ou de espectros.
    Retorna ``(bytes, info, style)``.
    """
    style = resolve_style(options.get("style"))
    dpi = style["export"]["preview_dpi"] if preview else None
    markers = parse_markers(options.get("markers"))

    if _is_spectrum_request(options):
        items = _spectrum_items(options)
        xlabel, ylabel = spectrum_labels(style)
        divisor = 1.0
    else:
        items, xlabel, ylabel, divisor, markers = _series_items(options, style, markers)

    image, info = render_curve_figure(items, markers, style, xlabel, ylabel, divisor,
                                      fmt=fmt, dpi=dpi)
    return image, info, style


def _style_path(name: str) -> Path:
    safe = _safe_name(name)
    if not safe:
        raise ValueError("Informe um nome para o estilo.")
    return STYLES_DIR / f"{safe}.json"


def _project_path(name: str) -> Path:
    safe = _safe_name(name)
    if not safe:
        raise ValueError("Informe um nome para o projeto.")
    return PROJECTS_DIR / f"{safe}.json"


# ─────────────────────────────────────────────────────────────────────────────
# Rotas
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/version")
def api_version():
    """Versão do servidor, para a página avisar quando ele está desatualizado."""
    from braggflow import __version__
    return jsonify({"api_build": API_BUILD, "version": __version__})


@app.route("/api/files")
def api_files():
    return jsonify({"files": _list_raw_files()})


@app.route("/api/channels")
def api_channels():
    """
    Canais do arquivo do interrogador, com sugestão de nome, unidade e
    comprimento de onda nominal (mediana das leituras válidas) — base para
    montar o setup de sensores e sugerir bandas.
    """
    rel = request.args.get("file", "")
    try:
        path = _resolve_data_file(rel)
        data, _ = _load_cached(path)
        nominal = {}
        for i, ch in enumerate(data.channels):
            col = data.signals[:, i]
            valid = col[np.isfinite(col) & (col > 0)]
            nominal[ch] = round(float(np.median(valid)), 4) if len(valid) else None
        try:
            fs = estimate_sampling_rate(data.time)
        except ValueError:
            fs = None
        return jsonify({
            "channels": data.channels,
            "defaults": {c: DEFAULT_RENAME.get(c, c) for c in data.channels},
            "units": dict(zip(data.channels, data.units)),
            "nominal": nominal,
            "n_samples": int(len(data.time)),
            "duration_s": float(data.time[-1] - data.time[0]) if len(data.time) else 0.0,
            "fs": fs,
            "time_origin": data.time_origin,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/setups")
def api_setups():
    """Setups de sensores salvos em data/setups."""
    names = []
    if SETUPS_DIR.is_dir():
        names = sorted(f.stem for f in SETUPS_DIR.glob("*.json") if f.is_file())
    return jsonify({"setups": names})


@app.route("/api/setups/<name>")
def api_setup_get(name):
    path = SETUPS_DIR / f"{_safe_name(name)}.json"
    if not _safe_name(name) or not path.is_file():
        return jsonify({"error": f"Setup não encontrado: {name}"}), 404
    try:
        return jsonify(SensorSetup.load(path).to_dict())
    except (ValueError, KeyError) as e:
        return jsonify({"error": f"Setup inválido: {e}"}), 400


@app.route("/api/setups", methods=["POST"])
def api_setup_save():
    """Salva (ou substitui) um setup a partir dos sensores da interface."""
    options = request.get_json(silent=True) or {}
    name = _safe_name(str(options.get("setup_name", "")))
    if not name:
        return jsonify({"error": "Informe um nome para o setup."}), 400
    try:
        setup = _setup_from_options({**options, "setup_name": name})
        if not options.get("sensors"):
            raise ValueError("Nenhum sensor para salvar.")
        setup.save(SETUPS_DIR / f"{name}.json")
    except (ValueError, TypeError, KeyError, OSError) as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"name": name})


@app.route("/api/spectra/traces")
def api_spectrum_traces():
    """Traços de um arquivo de espectro, com faixa e número de pontos."""
    rel = request.args.get("file", "")
    try:
        path = _resolve_data_file(rel)
        spectra = _load_spectra_cached(path)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({
        "file": rel,
        "traces": [
            {
                "name": spectrum.name,
                "key": _curve_key(path, spectra, spectrum.name),
                "n_points": spectrum.n_points,
                "range": [round(float(spectrum.wavelength[0]), 3),
                          round(float(spectrum.wavelength[-1]), 3)],
            }
            for spectrum in spectra.spectra
        ],
    })


@app.route("/api/spectra/preview", methods=["POST"])
def api_spectrum_preview():
    """
    Espectro já preparado (recorte, suavização, normalização e deslocamento),
    decimado para o gráfico interativo da aba Espectros.
    """
    options = request.get_json(silent=True) or {}
    try:
        path = _resolve_data_file(options.get("file", ""))
        spectra = _load_spectra_cached(path)
        settings = resolve_spectrum_settings(options.get("settings"))
        traces = []
        for spectrum in spectra.spectra:
            wavelength, intensity = prepare_spectrum(spectrum.wavelength, spectrum.intensity, settings)
            (x, y), stride = _downsample(wavelength, intensity)
            traces.append({
                "name": spectrum.name,
                "key": _curve_key(path, spectra, spectrum.name),
                "wavelength": _to_jsonable(x),
                "intensity": _to_jsonable(y),
                "n_points": int(len(wavelength)),
                "plot_stride": stride,
                # medido no espectro inteiro, não no decimado do gráfico
                **analyse_spectrum(wavelength, intensity, settings),
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"file": options.get("file"), "traces": traces})


@app.route("/api/concat/preview", methods=["POST"])
def api_concat_preview():
    """
    Prévia da concatenação: onde cada arquivo entra na linha do tempo, na
    ordem recebida, para o cartão de concatenação mostrar início, fim e
    pausas antes de processar.
    """
    options = request.get_json(silent=True) or {}
    try:
        caminhos = _requested_files(options)
        if len(caminhos) < 2:
            raise ValueError("Escolha dois ou mais arquivos para juntar.")
        plano = concat_plan([_load_cached(caminho)[0] for caminho in caminhos])
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    partes = [
        {**parte,
         "file": _rel(caminho),
         "name": caminho.name}
        for parte, caminho in zip(plano, caminhos)
    ]
    taxas = sorted({round(1 / parte["step"], 3) for parte in plano if parte["step"] > 0})
    avisos = []
    if len(taxas) > 1:
        avisos.append(
            "Os arquivos têm taxas de amostragem diferentes ("
            + ", ".join(f"{taxa:g} Hz" for taxa in taxas)
            + "); os filtros supõem amostragem uniforme. "
            "Reamostre na etapa 'Eixo de tempo'.")

    return jsonify({
        "parts": partes,
        "joins": [parte["start"] for parte in plano[1:]],
        "n_samples": sum(parte["n_samples"] for parte in plano),
        "total_duration": plano[-1]["end"] - plano[0]["start"],
        "warnings": avisos,
    })


@app.route("/api/file-info")
def api_file_info():
    """Formato detectado e conteúdo de um arquivo bruto (diagnóstico)."""
    try:
        return jsonify(describe_file(_resolve_data_file(request.args.get("file", ""))))
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/processed")
def api_processed():
    """
    CSVs processados disponíveis para a aba de visualização: os da pasta do
    projeto (``?project=``; sem projeto, ``data/processed/``) e os enviados.
    """
    pasta = _processed_dir({"project": request.args.get("project", "")})
    files = []
    for folder in (pasta, UPLOAD_DIR):
        if folder.is_dir():
            for f in sorted(folder.iterdir()):
                if f.is_file() and f.suffix.lower() == ".csv":
                    files.append(_rel(f))
    return jsonify({"files": files,
                    "folder": _rel(pasta)})


@app.route("/api/processed-channels")
def api_processed_channels():
    """
    Canais de um CSV processado (só o cabeçalho), com unidade e grandeza de
    cada um quando o JSON de rastreabilidade existe.
    """
    rel = request.args.get("file", "")
    try:
        path = _resolve_data_file(rel)
        channels, units = read_processed_header(path)
        quantities = channel_quantities(read_metadata(path))
        return jsonify({
            "channels": channels,
            "units": units,
            "quantities": {ch: quantities.get(ch) for ch in channels},
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/figure", methods=["POST"])
def api_figure():
    """
    Pré-visualização em PNG (base64) na resolução ``export.preview_dpi``, com
    o tamanho final que o arquivo exportado terá.
    """
    options = request.get_json(silent=True) or {}
    if not (options.get("file") or options.get("spectra") or options.get("series")):
        return jsonify({"error": "Requisição sem dados selecionados."}), 400

    with _figure_lock:
        try:
            image, info, _ = _render_requested_figure(options, fmt="png", preview=True)
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    return jsonify({"image": base64.b64encode(image).decode("ascii"), "info": info})


@app.route("/api/figure/download", methods=["POST"])
def api_figure_download():
    """Figura final no formato e na resolução definidos em ``style.export``."""
    options = request.get_json(silent=True) or {}
    if not (options.get("file") or options.get("spectra") or options.get("series")):
        return jsonify({"error": "Requisição sem dados selecionados."}), 400

    with _figure_lock:
        try:
            data, _, style = _render_requested_figure(options)
            fmt = style["export"]["format"]
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    first = (options.get("spectra") or options.get("series") or [{}])[0]
    source = options.get("file") or first.get("file") or "figura"
    stem = Path(source).stem.removesuffix("_processado")
    return send_file(
        io.BytesIO(data),
        mimetype=FIGURE_MIMETYPES[fmt],
        as_attachment=True,
        download_name=f"{stem}_figura.{fmt}",
    )


def _analysis_curves(options: dict, style: dict):
    """
    Curvas para a análise: tempo em segundos do arquivo (sem a unidade da
    figura nem o deslocamento das marcações) e valores como aparecem no
    gráfico. Retorna ``(curvas, unidade)``.
    """
    if _is_spectrum_request(options):
        raise ValueError("A análise estatística é das séries no tempo, não dos espectros.")

    entries = _series_entries(options)
    if not entries:
        raise ValueError("Marque pelo menos uma curva.")
    several = len({entry["file"] for entry in entries}) > 1

    curvas, unidade = [], "nm"
    for entry in entries:
        path = _resolve_data_file(entry["file"])
        df, units, quantities = _load_processed_cached(path)
        channel = entry["channel"]
        if channel not in df.columns:
            raise ValueError(f"Canal '{channel}' não existe em {path.name}.")
        values, unidade, _ = channel_values(df, units, quantities, channel, style["data"])
        stem = path.stem.removesuffix("_processado")
        curvas.append({
            "key": f"{stem} · {channel}" if several else channel,
            "time": df["Time"].to_numpy(dtype=float),
            "values": values,
        })
    return curvas, unidade


@app.route("/api/analysis", methods=["POST"])
def api_analysis():
    """
    Estatísticas por intervalo entre marcações e o degrau em cada marcação,
    para as mesmas curvas que estão na figura.
    """
    options = request.get_json(silent=True) or {}
    try:
        style = resolve_style(options.get("style"))
        markers = parse_markers(options.get("markers"))
        settings = options.get("analysis") or {}
        curvas, unidade = _analysis_curves(options, style)
        resultado = [
            {"key": curva["key"],
             **analyse_curve(
                 curva["time"], curva["values"], markers,
                 settle_window=_num(settings.get("settle_window")),
                 reference=str(settings.get("reference") or "previous"),
                 step_window=_num(settings.get("step_window"), 10.0),
             )}
            for curva in curvas
        ]
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({"unit": unidade, "curves": resultado,
                    "n_markers": len(markers)})


@app.route("/api/figure/options")
def api_figure_options():
    """Estilo padrão e as opções disponíveis para montar a interface."""
    return jsonify({
        "style": default_style(),
        "palettes": PALETTES,
        "fonts": list(available_fonts()),
        "linestyles": list(CHANNEL_LINESTYLES),
        "markers": list(MARKERS),
        "legend_positions": list(LEGEND_POSITIONS),
        "formats": list(EXPORT_FORMATS),
        "spectrum_settings": default_spectrum_settings(),
        "normalizations": list(NORMALIZATIONS),
    })


@app.route("/api/styles")
def api_styles():
    """Estilos de figura salvos em data/styles."""
    names = []
    if STYLES_DIR.is_dir():
        names = sorted(f.stem for f in STYLES_DIR.glob("*.json") if f.is_file())
    return jsonify({"styles": names})


@app.route("/api/styles/<name>")
def api_style_get(name):
    try:
        path = _style_path(name)
        if not path.is_file():
            raise FileNotFoundError
        style = resolve_style(json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, FileNotFoundError):
        return jsonify({"error": f"Estilo não encontrado ou inválido: {name}"}), 404
    return jsonify({"name": path.stem, "style": style})


@app.route("/api/styles", methods=["POST"])
def api_style_save():
    """Valida e salva (ou substitui) um estilo de figura."""
    options = request.get_json(silent=True) or {}
    try:
        path = _style_path(str(options.get("name", "")))
        style = resolve_style(options.get("style"))
        STYLES_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(style, indent=2, ensure_ascii=False), encoding="utf-8")
    except (ValueError, TypeError, KeyError, OSError) as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"name": path.stem})


@app.route("/api/projects")
def api_projects():
    """Projetos salvos, do mais recente para o mais antigo."""
    projects = []
    if PROJECTS_DIR.is_dir():
        for path in PROJECTS_DIR.glob("*.json"):
            try:
                projects.append(Project.load(path).summary())
            except (ValueError, OSError, KeyError):
                continue  # arquivo estragado: não derruba a lista
    projects.sort(key=lambda p: p["updated"], reverse=True)
    return jsonify({"projects": projects})


@app.route("/api/projects/<name>")
def api_project_get(name):
    try:
        path = _project_path(name)
        if not path.is_file():
            raise FileNotFoundError
        project = Project.load(path)
    except (ValueError, FileNotFoundError):
        return jsonify({"error": f"Projeto não encontrado ou inválido: {name}"}), 404
    try:
        _adopt_legacy_processed(project)
    except OSError:
        pass    # sem a cópia, a aba Visualização só não lista os CSVs antigos
    return jsonify(project.to_dict())


@app.route("/api/projects", methods=["POST"])
def api_project_save():
    """Salva (ou substitui) um projeto com tudo o que está na tela."""
    data = request.get_json(silent=True) or {}
    try:
        path = _project_path(str(data.get("name", "")))
        # Preserva a data de criação quando o projeto já existe
        if path.is_file():
            data = {**data, "created": Project.load(path).created}
        project = Project.from_dict(data)
        project.name = path.stem
        project.save(path)
    except (ValueError, TypeError, KeyError, OSError) as e:
        return jsonify({"error": f"Projeto inválido: {e}"}), 400
    return jsonify(project.summary())


@app.route("/api/projects/<name>", methods=["DELETE"])
def api_project_delete(name):
    try:
        path = _project_path(name)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if not path.is_file():
        return jsonify({"error": f"Projeto não encontrado: {name}"}), 404
    path.unlink()
    return jsonify({"deleted": path.stem})


@app.route("/api/upload", methods=["POST"])
def api_upload():
    file = request.files.get("file")
    if file is None or not file.filename:
        return jsonify({"error": "Nenhum arquivo enviado."}), 400
    suffix = Path(file.filename).suffix.lower()
    if suffix in DESCRIPTOR_EXTENSIONS:
        # O catman grava um descritor do ensaio sem os dados dentro
        info = read_descriptor(file.read().decode("utf-8", errors="replace"))
        alvo = info.get("data_file") or "o arquivo .ASC ou .txt do ensaio"
        return jsonify({"error":
            f"{Path(file.filename).name} descreve o ensaio, mas não contém os dados. "
            f"Envie {alvo}, que é o arquivo indicado dentro dele."}), 400
    if suffix not in RAW_EXTENSIONS:
        return jsonify({"error":
            f"Extensão não suportada: {suffix}. Aceito: "
            f"{', '.join(sorted(RAW_EXTENSIONS))}."}), 400

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_name(Path(file.filename).name) or f"upload{suffix}"
    dest = UPLOAD_DIR / safe_name
    file.save(dest)
    return jsonify({"file": _rel(dest)})


@app.route("/api/process", methods=["POST"])
def api_process():
    options = request.get_json(silent=True) or {}
    if not (options.get("file") or options.get("files")):
        return jsonify({"error": "Requisição sem arquivo selecionado."}), 400

    try:
        pipeline, (raw_time, raw_signals), messages = _run_pipeline(options)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    t, sig, channels = pipeline.get_data()
    n_samples = len(t)

    # ``save: false`` = só pré-visualização (abrir um projeto, escolher um
    # arquivo): mostra o resultado sem regravar o CSV que já existe.
    pasta, nome = _processed_dir(options), _processed_name(options)
    processed_file = None
    if options.get("save", True):
        try:
            processed_file = _save_processed(pipeline, nome, pasta)
        except OSError as e:
            messages["warnings"].append(f"CSV processado não foi salvo: {e}")

    (t_ds, *sig_cols), stride = _downsample(
        t, *[sig[:, i] for i in range(sig.shape[1])]
    )
    payload = {
        "channels": channels,
        "time": _to_jsonable(t_ds),
        "signals": {ch: _to_jsonable(col) for ch, col in zip(channels, sig_cols)},
        "n_samples": n_samples,
        "plot_stride": stride,
        "units": dict(zip(channels, pipeline.units)),
        "quantity": pipeline.quantities[0] if pipeline.quantities else None,
        "report": messages["report"],
        "warnings": messages["warnings"],
        "processed_file": processed_file,
        "existing_file": processed_file or _existing_processed(nome, pasta),
        "joins": getattr(pipeline, "joins", []),
    }

    if options.get("include_raw"):
        (rt_ds, *raw_cols), _ = _downsample(
            raw_time, *[raw_signals[:, i] for i in range(raw_signals.shape[1])]
        )
        payload["raw"] = {
            "time": _to_jsonable(rt_ds),
            "signals": {ch: _to_jsonable(col) for ch, col in zip(channels, raw_cols)},
        }

    return jsonify(payload)


@app.route("/api/download", methods=["POST"])
def api_download():
    """Reprocessa com as mesmas opções e devolve o CSV completo (sem downsample)."""
    options = request.get_json(silent=True) or {}
    if not (options.get("file") or options.get("files")):
        return jsonify({"error": "Requisição sem arquivo selecionado."}), 400

    try:
        pipeline, _, _ = _run_pipeline(options)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    t, sig, _ = pipeline.get_data()
    buf = io.StringIO()
    np.savetxt(buf, np.hstack((t.reshape(-1, 1), sig)), delimiter=",",
               header=pipeline.csv_header(), comments="")
    buf.seek(0)

    stem = _processed_name(options)
    return send_file(
        io.BytesIO(buf.getvalue().encode("utf-8")),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"{stem}_processado.csv",
    )


def main(argv=None) -> None:
    """Ponto de entrada do comando ``braggflow-web``."""
    import argparse

    parser = argparse.ArgumentParser(prog="braggflow-web", description="BraggFlow — interface web")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--data-dir", default=None,
                        help="Pasta de dados (padrão: $BRAGGFLOW_DATA_DIR ou ./data)")
    args = parser.parse_args(argv)
    pasta = set_data_dir(args.data_dir)
    print(f"BraggFlow web — http://127.0.0.1:{args.port}  (dados em {pasta})")
    app.run(host="127.0.0.1", port=args.port, debug=False)


if __name__ == "__main__":
    main()
