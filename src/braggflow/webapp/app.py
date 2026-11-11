"""
app.py – Front-end web do pipeline óptico (BraggFlow)
=====================================================
Servidor Flask que expõe o ``OpticalPipeline`` para processamento interativo
no navegador: o usuário escolhe o arquivo .ASC, liga/desliga etapas, ajusta
parâmetros e vê o resultado em um gráfico Plotly em tempo real.

``create_app(data_dir)`` monta um app com a sua própria pasta de dados e os
seus caches (``webapp.state``); a receita de processamento é
``braggflow.recipe.run_recipe``, a mesma do comando ``braggflow process``.

As mensagens de erro e os avisos saem no idioma da interface: a página envia
o cabeçalho ``Accept-Language`` em todo pedido, e cada pedido usa esse idioma
(``braggflow.i18n``); sem o cabeçalho, português.

Uso:
    braggflow-web [--port 5000] [--data-dir DIR]
    # abra http://127.0.0.1:5000
"""

import base64
import io
import json
import mimetypes
import re
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
from flask import Blueprint, Flask, current_app, g, jsonify, render_template, request, send_file

import matplotlib
matplotlib.use("Agg")  # backend sem janela — obrigatório em servidor

from braggflow.analysis import analyse_curve, selection_statistics
from braggflow.i18n import DEFAULT_LANGUAGE, LANGUAGES, num, reset_language, set_language, tr, use_language
from braggflow.io.processed import (
    channel_quantities,
    metadata_path_for,
    read_metadata,
    read_processed_header,
    write_processed_csv,
)
from braggflow.paths import write_text_atomic
from braggflow.io.reader import (
    DESCRIPTOR_EXTENSIONS,
    concat_plan,
    describe_file,
    read_descriptor,
)
from braggflow.pipeline import OpticalPipeline
from braggflow.processing import estimate_sampling_rate
from braggflow.processing.filters import choose_savgol, savgol_cutoff
from braggflow.projects import Project
from braggflow.recipe import DEFAULT_RENAME, as_float, run_recipe, setup_from_options
from braggflow.sensors import SensorSetup
from braggflow.processing.spectra import (
    NORMALIZATIONS,
    TRANSMISSION_OUTPUTS,
    analyse_spectrum,
    apply_transmission,
    default_spectrum_settings,
    parse_evolution_events,
    prepare_spectrum,
    resolve_evolution_options,
    resolve_spectrum_settings,
    spectra_evolution,
    transmission_unit,
)
from braggflow.visualization.figure import (
    CHANNEL_LINESTYLES,
    TIME_DIVISORS,
    channel_values,
    evolution_labels,
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
    resolve_style,
)

from .state import AppState, DataFolder

# No Windows, o mimetypes lê os tipos do registro, onde .js às vezes está como
# text/plain; o navegador então recusa os módulos da página (static/js/).
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")

# Qualquer exportação de texto do interrogador ou do analisador de espectro
RAW_EXTENSIONS = {".asc", ".txt", ".csv", ".dat", ".tsv", ".prn", ".spec", ".bin"}   # .bin: binário do catman

# rcParams do matplotlib são globais do processo (não do app); o servidor
# Flask atende em threads
_figure_lock = threading.Lock()

FIGURE_MIMETYPES = {"pdf": "application/pdf", "png": "image/png", "svg": "image/svg+xml",
                    "eps": "application/postscript", "tiff": "image/tiff"}

# Máximo de pontos por canal enviados ao gráfico (o processamento usa tudo)
MAX_PLOT_POINTS = 8000

# Na evolução, todos os extremos de cada espectro entram na busca (o "máximo
# por tipo" do preparo é para a tabela)
EVOLUTION_MAX_PEAKS = 500

# Subpastas guardadas quando uma pasta inteira é enviada (pasta/sub/arquivo)
MAX_UPLOAD_DEPTH = 3

# Mude junto com o literal API_BUILD em static/js/core.js sempre que as
# rotas mudarem: é assim que a página percebe um servidor ainda sem reiniciar.
API_BUILD = "2026-11-10"

bp = Blueprint("braggflow", __name__)


def create_app(data_dir=None, *, create: bool = True) -> Flask:
    """
    App com a sua própria pasta de dados (``--data-dir``,
    ``BRAGGFLOW_DATA_DIR`` ou ``./data``) e os seus caches. ``create=False``
    não cria as subpastas.
    """
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200 MB
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.extensions["braggflow"] = AppState(DataFolder(data_dir, create=create))
    app.register_blueprint(bp)
    return app


# Idioma das mensagens: o que a página pede (Accept-Language), por pedido
def _request_language() -> str:
    for valor, _ in request.accept_languages:
        idioma = valor.split("-")[0].lower()
        if idioma in LANGUAGES:
            return idioma
    return DEFAULT_LANGUAGE


@bp.before_request
def _use_request_language():
    g.braggflow_language = set_language(_request_language())


@bp.teardown_request
def _restore_language(_erro=None):
    token = g.pop("braggflow_language", None)
    if token is not None:
        reset_language(token)


# O app só atende a própria página: um site aberto no navegador não pode
# enviar arquivos nem apagar projetos (Origin de outro site), nem ler os dados
# por um domínio que aponta para 127.0.0.1 (DNS rebinding: o Host não é local)
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


@bp.before_request
def _only_this_page():
    if urlsplit(f"//{request.host}").hostname not in LOCAL_HOSTS:
        return jsonify({"error": tr("app.foreignRequest")}), 403
    origem = request.headers.get("Origin")
    if request.method not in ("GET", "HEAD", "OPTIONS") and origem and urlsplit(origem).netloc != request.host:
        return jsonify({"error": tr("app.foreignRequest")}), 403
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _state() -> AppState:
    """Pasta de dados e caches do app que atende a requisição."""
    return current_app.extensions["braggflow"]


def _data() -> DataFolder:
    return _state().data


def _rel(path: Path) -> str:
    return _data().rel(path)


def _memo(nome: str) -> dict:
    """
    Anotações que valem só enquanto o pedido é atendido (caminhos resolvidos,
    data e tamanho dos arquivos): uma evolução pede a mesma fonte e o mesmo
    fundo milhares de vezes, e cada consulta ao disco custa.
    """
    if "_memo" not in g:
        g._memo = {}
    return g._memo.setdefault(nome, {})


def _resolve_data_file(rel_path: str) -> Path:
    vistos = _memo("paths")
    if rel_path not in vistos:
        vistos[rel_path] = _data().resolve(rel_path, _memo("folders"))
    return vistos[rel_path]


def _signature(path: Path) -> tuple:
    """Caminho, data de modificação e tamanho: muda quando o arquivo muda."""
    vistos = _memo("signatures")
    if path not in vistos:
        stat = path.stat()
        vistos[path] = (str(path), stat.st_mtime_ns, stat.st_size)
    return vistos[path]


def _list_raw_files() -> list[dict]:
    """
    Arquivos brutos disponíveis, com o tipo de conteúdo de cada um:
    ``timeseries`` (pico por canal no tempo) ou ``spectrum`` (intensidade por
    comprimento de onda). Inclui as subpastas (uma pasta por ensaio, ou uma
    pasta enviada inteira), menos as ocultas.
    """
    files = []
    for folder in (_data().raw, _data().uploads):
        if not folder.is_dir():
            continue
        for f in sorted(folder.rglob("*")):
            if not (f.is_file() and f.suffix.lower() in RAW_EXTENSIONS):
                continue
            if any(parte.startswith(".") for parte in f.relative_to(folder).parts):
                continue
            stat = f.stat()
            files.append({
                "path": _rel(f),
                "kind": _state().kinds.get(f),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="minutes"),
            })
    return files


def _safe_name(name: str) -> str:
    """Mantém apenas caracteres inofensivos em nomes de arquivo."""
    return "".join(c for c in name if c.isalnum() or c in "._- ").strip(". ")


def _curve_key(path: Path, spectra, trace_name: str) -> str:
    """Identificador da curva: o nome do arquivo basta quando há um traço só."""
    stem = path.stem
    return stem if len(spectra.spectra) == 1 else f"{stem} · {trace_name}"


# Nomes que o leitor dá aos traços sem rótulo ("Traço", "Traço 2"): ficam como
# chave (o projeto os guarda), mas a interface e a figura os mostram no idioma delas
_DEFAULT_TRACE = re.compile(r"Traço(?: (\d+))?")


def _trace_label(nome: str) -> str:
    achado = _DEFAULT_TRACE.fullmatch(nome)
    if not achado:
        return nome
    return tr("app.traceNumber", n=achado.group(1)) if achado.group(1) else tr("app.trace")


def _first_trace(rel_path: str):
    """``(λ, intensidade)`` do primeiro traço de um arquivo de espectro (fonte, fundo)."""
    path = _resolve_data_file(rel_path)
    spectrum = _state().spectra.get(path).spectra[0]
    return spectrum.wavelength, spectrum.intensity


def _prepared(spectrum, settings: dict):
    """Fonte e fundo (se escolhidos), depois o preparo: ``(λ, intensidade)``."""
    intensity = apply_transmission(spectrum.wavelength, spectrum.intensity, settings, _first_trace)
    return prepare_spectrum(spectrum.wavelength, intensity, settings)


def _acquisition(spectra) -> dict:
    """Instante da aquisição para a interface (ISO; sem data quando veio só do nome)."""
    quando = spectra.acquired
    if quando is None:
        return {"acquired": None, "acquired_from": ""}
    texto = (quando.time().isoformat(timespec="milliseconds") if spectra.acquired_from == "filename"
             else quando.isoformat(timespec="milliseconds"))
    return {"acquired": texto, "acquired_from": spectra.acquired_from}


def _settings_key(settings: dict) -> str:
    """O preparo como texto, para as chaves do cache: montado uma vez por preparo e por pedido."""
    vistos = _memo("settings")
    achado = vistos.get(id(settings))
    if achado is None or achado[0] is not settings:
        achado = vistos[id(settings)] = (settings, json.dumps(settings, sort_keys=True, default=str))
    return achado[1]


def _spectrum_extrema(path: Path, trace: str, settings: dict) -> dict:
    """
    Extremos de um espectro já preparado, com a unidade e o instante da
    aquisição. Ficam guardados pelo arquivo, pela fonte e pelo fundo (caminho,
    data e tamanho), pelo traço e pelo preparo: recalcular a evolução com
    outro λ de referência ou outro modo não relê nem reanalisa nada.
    """
    deps = [path] + [_resolve_data_file(settings[k])
                     for k in ("reference_file", "dark_file") if settings.get(k)]
    cache = _state().analyses
    chave = (trace, _settings_key(settings), *(_signature(p) for p in deps))
    pronto = cache.get(chave)
    if pronto is None:
        spectra = _state().spectra.get(path)
        nome = trace or (spectra.names[0] if spectra.names else "")
        spectrum = spectra.get(nome)
        if spectrum is None:
            raise ValueError(tr("app.traceNotFound", trace=nome, file=path.name))
        wavelength, intensity = _prepared(spectrum, settings)
        pronto = {
            "extrema": analyse_spectrum(wavelength, intensity, settings)["extrema"],
            "unit": transmission_unit(settings, spectra.intensity_unit),
            "acquired": spectra.acquired,
            "acquired_from": spectra.acquired_from,
            "multi_trace": len(spectra.spectra) > 1,
            "trace": nome,
        }
        cache.put(chave, pronto)
    return pronto


def _compute_evolution(options: dict) -> dict:
    """
    Evolução dos vales (ou picos) dos espectros pedidos, para a aba Espectros
    e para a figura. ``options``: ``items`` (``[{file, trace?, settings?}]``),
    ``settings`` (o preparo comum, para os itens sem preparo próprio), as
    opções de :data:`EVOLUTION_SPEC` e ``events`` (``[{at, label, color}]``),
    que voltam com ``elapsed_s``: segundos desde o 1º espectro, ou ``None``
    quando os arquivos não têm o instante da aquisição.

    Um arquivo que não dá para ler ou preparar não derruba o cálculo: fica de
    fora e aparece em ``skipped`` e nos avisos.
    """
    opts = resolve_evolution_options(options)
    eventos = parse_evolution_events(options.get("events"))
    comum = options.get("settings") or {}
    kind = opts["kind"]
    entradas, unidades, ignorados, vistos = [], set(), [], set()
    preparos = {}       # o preparo comum é validado uma vez, não uma por arquivo
    for item in options.get("items") or []:
        arquivo = str(item.get("file") or "")
        trace = str(item.get("trace") or "")
        if (arquivo, trace) in vistos:
            continue
        vistos.add((arquivo, trace))
        try:
            path = _resolve_data_file(arquivo)
            bruto = item.get("settings") or comum
            settings = preparos.get(id(bruto))
            if settings is None:
                settings = preparos[id(bruto)] = resolve_spectrum_settings(
                    {**bruto, "find_min": kind == "min", "find_max": kind == "max",
                     "max_peaks": EVOLUTION_MAX_PEAKS}, prefix=f"[{path.name}] ")
            pronto = _spectrum_extrema(path, trace, settings)
        except Exception as e:
            ignorados.append({"file": arquivo, "error": str(e)})
            continue
        rel = _rel(path)
        unidades.add(pronto["unit"])
        entradas.append({**pronto, "file": rel,
                         "key": f"{rel} · {pronto['trace']}" if pronto["multi_trace"] else rel})

    if len(entradas) < 2:
        motivo = ""
        if ignorados:
            motivo = tr("app.couldNotRead", files="; ".join(
                f"{Path(i['file']).name or tr('app.noName')} ({i['error']})" for i in ignorados[:3]))
        raise ValueError(tr("app.evolutionNeedsTwo") + motivo)

    resultado = spectra_evolution(entradas, kind=kind, mode=opts["mode"],
                                  tolerance=opts["tolerance"], reference=opts["reference"],
                                  window=opts["window"], follow=opts["follow"],
                                  locate=opts["locate"])

    origem = {e["key"]: e for e in entradas}
    for arquivo in resultado["files"]:
        e = origem[arquivo["key"]]
        arquivo["file"] = e["file"]
        arquivo["acquired_from"] = e["acquired_from"]
        if e["acquired_from"] == "filename" and arquivo["acquired"]:
            arquivo["acquired"] = arquivo["acquired"].split("T")[1]     # só a hora

    nome = tr("spectra.valley" if kind == "min" else "spectra.peak")
    avisos = []
    if ignorados:
        nomes = ", ".join(Path(i["file"]).name or tr("app.noName") for i in ignorados[:3])
        mais = tr("app.andMore", n=len(ignorados) - 3) if len(ignorados) > 3 else ""
        avisos.append(tr("app.skippedFiles", n=len(ignorados), names=nomes, more=mais))
    if resultado["x"] == "order":
        avisos.append(tr("app.byFileOrder"))
    elif len({e["acquired_from"] == "filename" for e in entradas}) > 1:
        avisos.append(tr("app.mixedTimes"))
    if len(unidades) > 1:
        avisos.append(tr("app.mixedUnits", units=", ".join(sorted(unidades))))
    if opts["mode"] != "follow":
        vazios = sum(p is None for p in resultado["tracks"][0]["points"])
        if vazios:
            onde = tr("app.inWindow") if opts["mode"] == "reference" and opts["window"] else ""
            avisos.append(tr("app.noneFound", kind=nome, where=onde, n=vazios))
    if opts["locate"] != "vertex":
        sem = sum(1 for t in resultado["tracks"] for p in t["points"]
                  if p is not None and p["located"] != opts["locate"])
        if sem:
            metodo = tr({"fit": "app.methodFit", "centroid": "app.methodCentroid",
                         "gaussian": "app.methodGaussian", "lorentzian": "app.methodLorentzian",
                         "midpoint": "app.methodMidpoint"}[opts["locate"]])
            avisos.append(tr("app.locateFallback", method=metodo, n=sem))
    inicio = datetime.fromisoformat(resultado["start"]) if resultado["start"] else None
    for evento in eventos:
        evento["elapsed_s"] = ((datetime.fromisoformat(evento["at"]) - inicio).total_seconds()
                               if inicio else None)
    resultado.update({"unit": unidades.pop() if len(unidades) == 1 else "", "warnings": avisos,
                      "skipped": ignorados, "events": eventos})
    return resultado


def _track_label(trilha: dict, resultado: dict, index: int, language: str) -> str:
    """
    Legenda automática de uma trilha no idioma da figura: o nome que a aba
    Espectros mostra segue o idioma da interface, mas a figura vai para o artigo.
    """
    pt = language == "pt"
    nome = ("vale" if pt else "valley") if resultado["kind"] == "min" else ("pico" if pt else "peak")
    if resultado["mode"] == "reference":
        lam = f"{resultado['reference']:.1f}"
        return f"{nome} perto de {lam.replace('.', ',')} nm" if pt else f"{nome} near {lam} nm"
    if resultado["mode"] == "prominent":
        return f"{nome} mais proeminente" if pt else f"most prominent {nome}"
    return f"{nome} {index + 1}"


def _evolution_items(options: dict, style: dict, markers: list):
    """
    Curvas da evolução para a figura: uma por trilha marcada, com a grandeza
    escolhida (``y`` das opções) contra o tempo desde o primeiro espectro, na
    unidade da figura, ou contra o número do espectro. As marcações são os
    eventos da evolução (``evolution.events``), não as das séries; no eixo de
    números, cada evento fica entre os espectros de antes e de depois dele.
    Retorna ``(items, xlabel, ylabel, divisor, markers)``.
    """
    pedido = options.get("evolution") or {}
    opts = resolve_evolution_options(pedido)
    resultado = _compute_evolution(pedido)
    data_s = style["data"]
    tempos = np.array([f["elapsed_s"] if f["elapsed_s"] is not None else np.nan
                       for f in resultado["files"]], dtype=float)
    markers = [{"time": e["elapsed_s"], "label": e["label"], "color": e["color"]}
               for e in resultado["events"] if e["elapsed_s"] is not None]
    por_tempo = resultado["x"] == "time" and opts["x"] == "time"
    if por_tempo:
        offset = marker_offset(markers, data_s)
        markers = shift_markers(markers, offset)
        divisor = TIME_DIVISORS[data_s["time_unit"]]
        x = (tempos - offset) / divisor
    else:
        divisor = 1.0
        x = np.array([f["index"] for f in resultado["files"]], dtype=float)
        if resultado["x"] == "time":
            markers = [{**m, "time": float(np.interp(m["time"], tempos, x))} for m in markers]
        else:
            markers = []                    # sem o instante dos arquivos, os eventos não têm onde ficar

    marcadas = options.get("tracks")
    items = []
    for indice, trilha in enumerate(resultado["tracks"]):
        if marcadas is not None and trilha["key"] not in marcadas:
            continue
        y = np.array([np.nan if p is None or p.get(opts["y"]) is None else p[opts["y"]]
                      for p in trilha["points"]], dtype=float)
        items.append({"key": trilha["key"], "x": x, "y": y,
                      "label": _track_label(trilha, resultado, indice, style["axes"]["language"])})
    if not items:
        raise ValueError(tr("app.checkTrack"))
    xlabel, ylabel = evolution_labels(opts["y"], resultado["unit"], resultado["kind"],
                                      data_s["time_unit"] if por_tempo else None,
                                      style["axes"]["language"])
    return items, xlabel, ylabel, divisor, markers


def _spectrum_items(options: dict, language: str) -> list[dict]:
    """
    Curvas de espectro pedidas pela interface. Cada entrada traz o seu próprio
    preparo (recorte, suavização, normalização e deslocamento), aplicado só a
    ela. A legenda automática fica no idioma da figura (``language``).
    """
    items = []
    for entry in options.get("spectra") or []:
        path = _resolve_data_file(entry["file"])
        spectra = _state().spectra.get(path)
        name = entry.get("trace") or (spectra.names[0] if spectra.names else "")
        spectrum = spectra.get(name)
        if spectrum is None:
            raise ValueError(tr("app.traceNotFound", trace=name, file=path.name))

        key = _curve_key(path, spectra, name)
        settings = resolve_spectrum_settings(entry.get("settings"), prefix=f"[{key}] ")
        wavelength, intensity = _prepared(spectrum, settings)
        with use_language(language):
            legenda = entry.get("label") or _curve_key(path, spectra, _trace_label(name))
        items.append({"key": key, "label": legenda, "x": wavelength, "y": intensity})
    if not items:
        raise ValueError(tr("app.selectSpectrum"))
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
        df, _, _ = _state().processed.get(_resolve_data_file(file))
        channels = [c for c in df.columns if c != "Time"]
    return [{"file": file, "channel": channel} for channel in channels]


def _series_curves(options: dict, data_s: dict) -> list[dict]:
    """
    As curvas pedidas dos CSVs processados, para a figura e para a análise:
    ``key`` (o canal, ou ``arquivo · canal`` com vários CSVs), a tabela
    (``df``), os valores como aparecem no gráfico (``y``), ``unit`` e
    ``is_shift``.
    """
    entries = _series_entries(options)
    several = len({entry["file"] for entry in entries}) > 1
    curvas = []
    for entry in entries:
        path = _resolve_data_file(entry["file"])
        df, units, quantities = _state().processed.get(path)
        channel = entry["channel"]
        if channel not in df.columns:
            raise ValueError(tr("app.channelMissing", channel=channel, file=path.name))
        y, unit, is_shift = channel_values(df, units, quantities, channel, data_s)
        stem = path.stem.removesuffix("_processado")
        curvas.append({"key": f"{stem} · {channel}" if several else channel,
                       "df": df, "y": y, "unit": unit, "is_shift": is_shift})
    return curvas


def _series_items(options: dict, style: dict, markers: list):
    """
    Curvas de série no tempo, possivelmente de vários CSVs processados.
    Retorna ``(items, xlabel, ylabel, divisor, markers)``.
    """
    curvas = _series_curves(options, style["data"])
    if not curvas:
        raise ValueError(tr("app.selectCurve"))

    offset = marker_offset(markers, style["data"])
    markers = shift_markers(markers, offset)
    items, divisor = [], 1.0
    for curva in curvas:
        x, divisor = time_axis(curva["df"], style["data"], offset)
        items.append({"key": curva["key"], "label": curva["key"], "x": x, "y": curva["y"]})

    xlabel, ylabel = series_labels(curvas[-1]["unit"], curvas[-1]["is_shift"],
                                   style["data"]["time_unit"], style["axes"]["language"])
    return items, xlabel, ylabel, divisor, markers


def _run_pipeline(options: dict):
    """
    ``run_recipe`` com os arquivos pedidos (dentro da pasta de dados) e o
    cache de leitura do app. Retorna (pipeline, (raw_time, raw_signals), messages).
    """
    return run_recipe(_requested_files(options), options, load=_state().interrogator.get)


def _remember_result(options: dict, pipeline) -> None:
    """Guarda o sinal processado para medir trechos sem reprocessar."""
    t, sig, channels = pipeline.get_data()
    _state().results.put(_state().results.key(options, _requested_files(options)),
                         (t.copy(), sig.copy(), list(channels), list(pipeline.units)))


def _processed_result(options: dict):
    """``(tempo, sinais, canais, unidades)`` da receita; do cache quando já foi processada."""
    chave = _state().results.key(options, _requested_files(options))
    resultado = _state().results.get(chave)
    if resultado is None:
        pipeline, _, _ = _run_pipeline(options)
        _remember_result(options, pipeline)
        resultado = _state().results.get(chave)
    return resultado


def _requested_files(options: dict) -> list[Path]:
    """Arquivos do processamento: um só, ou vários a juntar em sequência."""
    pedidos = options.get("files") or ([options["file"]] if options.get("file") else [])
    if not pedidos:
        raise ValueError(tr("recipe.noFile"))
    return [_resolve_data_file(caminho) for caminho in pedidos]


def _processed_name(options: dict) -> str:
    """
    ``<primeiro>_processado.csv``; com vários arquivos, ``_juntos``. Um
    arquivo numa subpasta leva a pasta no nome (``dia1__ensaio``): dois
    ``ensaio.ASC`` de pastas diferentes não gravam o mesmo CSV. Em data/raw,
    leva também ``raw__``, para não cruzar com a mesma pasta enviada pela
    página (data/uploads). ``loadVizSources`` (viz.js) monta o mesmo nome.
    """
    arquivos = options.get("files") or [options.get("file", "")]
    partes = Path(arquivos[0]).parts
    raiz, pastas = (partes[1], partes[2:-1]) if partes[:1] == (DataFolder.PREFIX,) else ("", ())
    if pastas and raiz == "raw":
        pastas = ("raw", *pastas)
    stem = "__".join([*pastas, Path(arquivos[0]).stem])
    return f"{stem}_juntos" if len(arquivos) > 1 else stem


def _processed_dir(options: dict) -> Path:
    """
    Pasta dos CSVs processados: ``data/processed/<projeto>/``. Cada projeto
    tem a sua, para que o mesmo arquivo bruto processado com opções
    diferentes em outro projeto não sobrescreva este. Sem nome de projeto,
    usa ``data/processed/`` como antes.
    """
    projeto = _safe_name(str(options.get("project") or ""))
    return _data().processed / projeto if projeto else _data().processed


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
    processed = _data().processed
    pasta = _processed_dir({"project": project.name})
    if pasta == processed:
        return
    for entry in project.series:
        stem = Path(entry["file"]).stem
        for nome in (f"{stem}_processado.csv", f"{stem}_juntos_processado.csv"):
            origem, destino = processed / nome, pasta / nome
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
    Figura. Escreve em arquivos temporários e substitui no fim, para
    que a figura nunca leia um CSV pela metade durante um reprocessamento.
    """
    folder = folder or _data().processed
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
# Figuras de publicação (aba Figura)
# ─────────────────────────────────────────────────────────────────────────────

def _is_spectrum_request(options: dict) -> bool:
    return str(options.get("source", "")) == "spectra"


def _is_evolution_request(options: dict) -> bool:
    return str(options.get("source", "")) == "evolution"


def _has_figure_data(options: dict) -> bool:
    return bool(options.get("file") or options.get("spectra") or options.get("series")
                or (_is_evolution_request(options) and options.get("evolution")))


def _render_requested_figure(options: dict, fmt=None, preview: bool = False):
    """
    Desenha a figura pedida: série no tempo, espectros ou a evolução dos
    vales entre espectros. Retorna ``(bytes, info, style)``.
    """
    style = resolve_style(options.get("style"))
    dpi = style["export"]["preview_dpi"] if preview else None
    markers = parse_markers(options.get("markers"))

    if _is_spectrum_request(options):
        items = _spectrum_items(options, style["axes"]["language"])
        xlabel, ylabel = spectrum_labels(style)
        divisor = 1.0
    elif _is_evolution_request(options):
        items, xlabel, ylabel, divisor, markers = _evolution_items(options, style, markers)
    else:
        items, xlabel, ylabel, divisor, markers = _series_items(options, style, markers)

    image, info = render_curve_figure(items, markers, style, xlabel, ylabel, divisor,
                                      fmt=fmt, dpi=dpi)
    return image, info, style


def _style_path(name: str) -> Path:
    safe = _safe_name(name)
    if not safe:
        raise ValueError(tr("app.styleNameRequired"))
    return _data().styles / f"{safe}.json"


def _project_path(name: str) -> Path:
    safe = _safe_name(name)
    if not safe:
        raise ValueError(tr("project.nameRequired"))
    return _data().projects / f"{safe}.json"


# ─────────────────────────────────────────────────────────────────────────────
# Rotas
# ─────────────────────────────────────────────────────────────────────────────

@bp.route("/")
def index():
    return render_template("index.html")


@bp.route("/api/version")
def api_version():
    """Versão do servidor, para a página avisar quando ele está desatualizado."""
    from braggflow import __version__
    return jsonify({"api_build": API_BUILD, "version": __version__})


@bp.route("/api/files")
def api_files():
    return jsonify({"files": _list_raw_files()})


@bp.route("/api/channels")
def api_channels():
    """
    Canais do arquivo do interrogador, com sugestão de nome, unidade e
    comprimento de onda nominal (mediana das leituras válidas) — base para
    montar o setup de sensores e sugerir bandas.
    """
    rel = request.args.get("file", "")
    try:
        path = _resolve_data_file(rel)
        data, _ = _state().interrogator.get(path)
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


@bp.route("/api/setups")
def api_setups():
    """Setups de sensores salvos em data/setups."""
    names, setups = [], _data().setups
    if setups.is_dir():
        names = sorted(f.stem for f in setups.glob("*.json") if f.is_file())
    return jsonify({"setups": names})


@bp.route("/api/setups/<name>")
def api_setup_get(name):
    path = _data().setups / f"{_safe_name(name)}.json"
    if not _safe_name(name) or not path.is_file():
        return jsonify({"error": tr("app.setupNotFound", name=name)}), 404
    try:
        return jsonify(SensorSetup.load(path).to_dict())
    except (ValueError, KeyError) as e:
        return jsonify({"error": tr("app.setupInvalid", error=e)}), 400


@bp.route("/api/setups", methods=["POST"])
def api_setup_save():
    """Salva (ou substitui) um setup a partir dos sensores da interface."""
    options = request.get_json(silent=True) or {}
    name = _safe_name(str(options.get("setup_name", "")))
    if not name:
        return jsonify({"error": tr("app.setupNameRequired")}), 400
    try:
        setup = setup_from_options({**options, "setup_name": name})
        if not options.get("sensors"):
            raise ValueError(tr("app.noSensors"))
        setup.save(_data().setups / f"{name}.json")
    except (ValueError, TypeError, KeyError, OSError) as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"name": name})


@bp.route("/api/spectra/traces")
def api_spectrum_traces():
    """Traços de um arquivo de espectro, com faixa e número de pontos."""
    rel = request.args.get("file", "")
    try:
        path = _resolve_data_file(rel)
        spectra = _state().spectra.get(path)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({
        "file": rel,
        "unit": spectra.intensity_unit,
        **_acquisition(spectra),
        "traces": [
            {
                "name": spectrum.name,
                "key": _curve_key(path, spectra, spectrum.name),
                "label": _curve_key(path, spectra, _trace_label(spectrum.name)),
                "n_points": spectrum.n_points,
                "range": [round(float(spectrum.wavelength[0]), 3),
                          round(float(spectrum.wavelength[-1]), 3)],
            }
            for spectrum in spectra.spectra
        ],
    })


@bp.route("/api/spectra/preview", methods=["POST"])
def api_spectrum_preview():
    """
    Espectro já preparado (recorte, suavização, normalização e deslocamento),
    decimado para o gráfico interativo da aba Espectros.
    """
    options = request.get_json(silent=True) or {}
    try:
        path = _resolve_data_file(options.get("file", ""))
        spectra = _state().spectra.get(path)
        settings = resolve_spectrum_settings(options.get("settings"))
        traces = []
        for spectrum in spectra.spectra:
            wavelength, intensity = _prepared(spectrum, settings)
            (x, y), stride = _downsample(wavelength, intensity)
            traces.append({
                "name": spectrum.name,
                "label": _trace_label(spectrum.name),
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
    return jsonify({"file": options.get("file"), "traces": traces,
                    "unit": transmission_unit(settings, spectra.intensity_unit),
                    **_acquisition(spectra)})


@bp.route("/api/spectra/smoothing-auto", methods=["POST"])
def api_spectrum_smoothing_auto():
    """
    Janela da suavização do espectro (e a ordem, no Savitzky-Golay) escolhida
    pelos dados, por validação cruzada (``choose_savgol``), no espectro como
    chega à suavização: recortado e convertido em transmissão, se for o caso.
    Corpo: ``{file, settings}``, como em ``/api/spectra/preview``.
    """
    options = request.get_json(silent=True) or {}
    try:
        path = _resolve_data_file(options.get("file", ""))
        spectra = _state().spectra.get(path)
        settings = resolve_spectrum_settings({**(options.get("settings") or {}), "smooth_window": None,
                                              "detrend": None, "normalize": "none", "offset": 0})
        preparados = [_prepared(spectrum, settings) for spectrum in spectra.spectra]
        savgol = settings["smooth_method"] == "savgol"
        escolha = choose_savgol([y for _, y in preparados], orders=(2, 4) if savgol else (0,))
        passo = float(np.median(np.diff(preparados[0][0])))
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({**escolha, "method": settings["smooth_method"], "window_nm": escolha["window"] * passo})


@bp.route("/api/spectra/evolution", methods=["POST"])
def api_spectrum_evolution():
    """
    Vales (ou picos) de vários espectros, um por arquivo, acompanhados de
    arquivo para arquivo na ordem da aquisição (ver ``_compute_evolution``).
    Os extremos são medidos no espectro inteiro já preparado e guardados: só
    o primeiro cálculo de cada preparo lê os arquivos.
    """
    try:
        resultado = _compute_evolution(request.get_json(silent=True) or {})
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(resultado)


@bp.route("/api/concat/preview", methods=["POST"])
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
            raise ValueError(tr("app.joinNeedsTwo"))
        plano = concat_plan([_state().interrogator.get(caminho)[0] for caminho in caminhos])
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
        avisos.append(tr("app.mixedRates", rates=", ".join(f"{num(taxa, 'g')} Hz" for taxa in taxas)))

    return jsonify({
        "parts": partes,
        "joins": [parte["start"] for parte in plano[1:]],
        "n_samples": sum(parte["n_samples"] for parte in plano),
        "total_duration": plano[-1]["end"] - plano[0]["start"],
        "warnings": avisos,
    })


@bp.route("/api/file-info")
def api_file_info():
    """Formato detectado e conteúdo de um arquivo bruto (diagnóstico)."""
    try:
        return jsonify(describe_file(_resolve_data_file(request.args.get("file", ""))))
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/api/processed")
def api_processed():
    """
    CSVs processados disponíveis para a aba de visualização: os da pasta do
    projeto (``?project=``; sem projeto, ``data/processed/``) e os enviados.
    """
    pasta = _processed_dir({"project": request.args.get("project", "")})
    files = []
    for folder in (pasta, _data().uploads):
        if folder.is_dir():
            for f in sorted(folder.iterdir()):
                if f.is_file() and f.suffix.lower() == ".csv":
                    files.append(_rel(f))
    return jsonify({"files": files,
                    "folder": _rel(pasta)})


@bp.route("/api/processed-channels")
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


@bp.route("/api/figure", methods=["POST"])
def api_figure():
    """
    Pré-visualização em PNG (base64) na resolução ``export.preview_dpi``, com
    o tamanho final que o arquivo exportado terá.
    """
    options = request.get_json(silent=True) or {}
    if not _has_figure_data(options):
        return jsonify({"error": tr("app.noFigureData")}), 400

    with _figure_lock:
        try:
            image, info, _ = _render_requested_figure(options, fmt="png", preview=True)
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    return jsonify({"image": base64.b64encode(image).decode("ascii"), "info": info})


@bp.route("/api/figure/download", methods=["POST"])
def api_figure_download():
    """Figura final no formato e na resolução definidos em ``style.export``."""
    options = request.get_json(silent=True) or {}
    if not _has_figure_data(options):
        return jsonify({"error": tr("app.noFigureData")}), 400

    with _figure_lock:
        try:
            data, _, style = _render_requested_figure(options)
            fmt = style["export"]["format"]
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    first = (options.get("spectra") or options.get("series") or [{}])[0]
    source = options.get("file") or first.get("file") or "figura"
    stem = "evolucao" if _is_evolution_request(options) else Path(source).stem.removesuffix("_processado")
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
    if _is_spectrum_request(options) or _is_evolution_request(options):
        raise ValueError(tr("app.analysisSeriesOnly"))

    curvas = _series_curves(options, style["data"])
    if not curvas:
        raise ValueError(tr("app.checkCurve"))
    return ([{"key": c["key"], "time": c["df"]["Time"].to_numpy(dtype=float), "values": c["y"]}
             for c in curvas], curvas[-1]["unit"])


@bp.route("/api/analysis", methods=["POST"])
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
                 settle_window=as_float(settings.get("settle_window")),
                 reference=str(settings.get("reference") or "previous"),
                 step_window=as_float(settings.get("step_window"), 10.0),
             )}
            for curva in curvas
        ]
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({"unit": unidade, "curves": resultado,
                    "n_markers": len(markers)})


@bp.route("/api/figure/options")
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
        "evolution": resolve_evolution_options({}),
        "normalizations": list(NORMALIZATIONS),
        "transmission_outputs": list(TRANSMISSION_OUTPUTS),
    })


@bp.route("/api/styles")
def api_styles():
    """Estilos de figura salvos em data/styles."""
    names, styles = [], _data().styles
    if styles.is_dir():
        names = sorted(f.stem for f in styles.glob("*.json") if f.is_file())
    return jsonify({"styles": names})


@bp.route("/api/styles/<name>")
def api_style_get(name):
    try:
        path = _style_path(name)
        if not path.is_file():
            raise FileNotFoundError
        style = resolve_style(json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, FileNotFoundError):
        return jsonify({"error": tr("app.styleNotFound", name=name)}), 404
    return jsonify({"name": path.stem, "style": style})


@bp.route("/api/styles", methods=["POST"])
def api_style_save():
    """Valida e salva (ou substitui) um estilo de figura."""
    options = request.get_json(silent=True) or {}
    try:
        path = _style_path(str(options.get("name", "")))
        style = resolve_style(options.get("style"))
        write_text_atomic(path, json.dumps(style, indent=2, ensure_ascii=False))
    except (ValueError, TypeError, KeyError, OSError) as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"name": path.stem})


@bp.route("/api/projects")
def api_projects():
    """Projetos salvos, do mais recente para o mais antigo."""
    projects, folder = [], _data().projects
    if folder.is_dir():
        for path in folder.glob("*.json"):
            try:
                projects.append(Project.load(path).summary())
            except (ValueError, OSError, KeyError):
                continue  # arquivo estragado: não derruba a lista
    projects.sort(key=lambda p: p["updated"], reverse=True)
    return jsonify({"projects": projects})


@bp.route("/api/projects/<name>")
def api_project_get(name):
    try:
        path = _project_path(name)
        if not path.is_file():
            raise FileNotFoundError
        project = Project.load(path)
    except (ValueError, FileNotFoundError):
        return jsonify({"error": tr("app.projectNotFound", name=name)}), 404
    try:
        _adopt_legacy_processed(project)
    except OSError:
        pass    # sem a cópia, a aba Figura só não lista os CSVs antigos
    return jsonify(project.to_dict())


@bp.route("/api/projects", methods=["POST"])
def api_project_save():
    """Salva (ou substitui) um projeto com tudo o que está na tela."""
    data = request.get_json(silent=True) or {}
    try:
        path = _project_path(str(data.get("name", "")))
        if path.is_file():
            # Só substitui o projeto que a página abriu (a mesma data de
            # criação): um projeto novo, ou renomeado, com o nome de outro não o apaga
            criado = json.loads(path.read_text(encoding="utf-8")).get("created")
            if criado and str(data.get("created") or "") != criado:
                return jsonify({"error": tr("app.projectExists", name=path.stem)}), 409
            data = {**data, "created": criado or ""}
        else:
            data = {**data, "created": ""}      # projeto novo ou cópia (renomear): data própria
        project = Project.from_dict(data)
        project.name = path.stem
        project.save(path)
    except (ValueError, TypeError, KeyError, OSError) as e:
        return jsonify({"error": tr("app.projectInvalid", error=e)}), 400
    return jsonify(project.summary())


@bp.route("/api/projects/<name>", methods=["DELETE"])
def api_project_delete(name):
    try:
        path = _project_path(name)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if not path.is_file():
        return jsonify({"error": tr("app.projectMissing", name=name)}), 404
    path.unlink()
    return jsonify({"deleted": path.stem})


def _upload_destination(filename: str) -> Path:
    """
    Onde guardar um arquivo enviado: ``data/uploads/<nome>`` ou, quando uma
    pasta inteira é enviada (nome ``pasta/sub/arquivo.txt``), nas mesmas
    subpastas, até ``MAX_UPLOAD_DEPTH``. Cada parte passa por ``_safe_name``
    (sem ``..`` nem caminhos absolutos).
    """
    partes = [_safe_name(parte) for parte in re.split(r"[\\/]", filename or "")]
    partes = [parte for parte in partes if parte]
    suffix = Path(filename or "").suffix.lower()
    nome = partes[-1] if partes else f"upload{suffix}"
    pastas = partes[:-1][-MAX_UPLOAD_DEPTH:]
    return _data().uploads.joinpath(*pastas, nome)


def _save_upload(file) -> str:
    """Valida e grava um arquivo enviado; devolve o caminho ``data/...``."""
    nome = Path(file.filename.replace("\\", "/")).name
    suffix = Path(nome).suffix.lower()
    if suffix in DESCRIPTOR_EXTENSIONS:
        # O catman grava um descritor do ensaio sem os dados dentro
        info = read_descriptor(file.read().decode("utf-8", errors="replace"))
        alvo = info.get("data_file") or tr("app.descriptorTarget")
        raise ValueError(tr("app.descriptorOnly", name=nome, target=alvo))
    if suffix not in RAW_EXTENSIONS:
        raise ValueError(tr("app.badExtension", name=nome, suffix=suffix or tr("app.noExtension"),
                            accepted=", ".join(sorted(RAW_EXTENSIONS))))
    # Um arquivo com o mesmo nome e outro conteúdo não substitui o que já
    # está lá (um projeto pode usá-lo): vai como "nome (2).ext"
    dest, dados = _upload_destination(file.filename), file.read()
    original, n = dest, 1
    while dest.is_file() and dest.read_bytes() != dados:
        n += 1
        dest = original.with_name(f"{original.stem} ({n}){original.suffix}")
    if not dest.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(dados)
    return _rel(dest)


@bp.route("/api/upload", methods=["POST"])
def api_upload():
    """
    Grava um ou vários arquivos (campo ``file`` repetido) em data/uploads.
    O nome pode trazer a pasta de origem (``pasta/arquivo.txt``), que é
    mantida. Um arquivo recusado não impede os outros: volta em ``errors``.
    """
    files = [f for f in request.files.getlist("file") if f and f.filename]
    if not files:
        return jsonify({"error": tr("app.noUpload")}), 400
    salvos, erros = [], []
    for file in files:
        try:
            salvos.append(_save_upload(file))
        except (ValueError, OSError) as e:
            erros.append(str(e))
    if not salvos:
        return jsonify({"error": " · ".join(erros), "errors": erros}), 400
    return jsonify({"file": salvos[0], "files": salvos, "errors": erros})


@bp.route("/api/process", methods=["POST"])
def api_process():
    options = request.get_json(silent=True) or {}
    if not (options.get("file") or options.get("files")):
        return jsonify({"error": tr("app.noFileInRequest")}), 400

    try:
        pipeline, (raw_time, raw_signals), messages = _run_pipeline(options)
        _remember_result(options, pipeline)
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
            messages["warnings"].append(tr("app.csvNotSaved", error=e))

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


@bp.route("/api/savgol/auto", methods=["POST"])
def api_savgol_auto():
    """
    Janela e ordem do Savitzky-Golay escolhidas pelos dados, por validação
    cruzada (``choose_savgol``), no sinal como chega ao filtro: depois do
    recorte, da limpeza, dos nulos, dos outliers e da reamostragem, sem os
    filtros nem o Δλ. Corpo: as mesmas opções de ``/api/process``. Devolve
    também o corte de −3 dB em Hz.
    """
    options = request.get_json(silent=True) or {}
    try:
        antes_do_filtro = {**options, **{etapa: {"enabled": False} for etapa in (
            "savgol", "moving_average", "lowpass", "highpass", "delta_lambda", "temp_comp")}}
        pipeline, _, _ = _run_pipeline(antes_do_filtro)
        t, sig, _ = pipeline.get_data()
        escolha = choose_savgol([sig[:, i] for i in range(sig.shape[1])])
        fs = estimate_sampling_rate(t)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    avisos = []
    if (options.get("timebase") or {}).get("resample"):
        avisos.append(tr("app.autoResampled"))
    return jsonify({**escolha, "fs": fs, "warnings": avisos,
                    "cutoff_hz": savgol_cutoff(escolha["window"], escolha["order"]) * fs})


@bp.route("/api/series/stats", methods=["POST"])
def api_series_stats():
    """
    Estatísticas de um trecho escolhido no gráfico, para cada canal, medidas
    no sinal processado inteiro (não no decimado da tela).
    Corpo: ``{options, start, end, relative}``; ``options`` é a mesma receita
    de ``/api/process``.
    """
    corpo = request.get_json(silent=True) or {}
    options = corpo.get("options") or {}
    try:
        inicio, fim = as_float(corpo.get("start")), as_float(corpo.get("end"))
        if inicio is None or fim is None or not fim > inicio:
            raise ValueError(tr("app.emptyStretch"))
        if not (options.get("file") or options.get("files")):
            raise ValueError(tr("app.noFileInRequest"))
        t, sig, channels, units = _processed_result(options)
        relativo = bool(corpo.get("relative"))
        linhas = [{"channel": ch, "unit": unit,
                   **selection_statistics(t, sig[:, i], inicio, fim, relative=relativo)}
                  for i, (ch, unit) in enumerate(zip(channels, units))]
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"start": inicio, "end": fim, "duration": fim - inicio, "channels": linhas})


@bp.route("/api/series/intervals", methods=["POST"])
def api_series_intervals():
    """
    Estatísticas por intervalo entre as marcações e o degrau em cada uma,
    para cada canal do sinal processado mostrado na aba Séries temporais.
    Corpo: ``{options, markers, analysis, relative}``; mesma resposta de
    ``/api/analysis`` (``unit``, ``curves``, ``n_markers``).
    """
    corpo = request.get_json(silent=True) or {}
    options = corpo.get("options") or {}
    try:
        if not (options.get("file") or options.get("files")):
            raise ValueError(tr("app.processFirst"))
        markers = parse_markers(corpo.get("markers"))
        settings = corpo.get("analysis") or {}
        t, sig, channels, units = _processed_result(options)
        relativo = bool(corpo.get("relative"))
        curvas = []
        for i, ch in enumerate(channels):
            valores = sig[:, i]
            if relativo:                       # como no gráfico "relativo ao início"
                validos = valores[np.isfinite(valores)]
                valores = valores - (validos[0] if len(validos) else 0.0)
            curvas.append({"key": ch, **analyse_curve(
                t, valores, markers,
                settle_window=as_float(settings.get("settle_window")),
                reference=str(settings.get("reference") or "previous"),
                step_window=as_float(settings.get("step_window"), 10.0),
            )})
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"unit": units[0] if units else "", "curves": curvas,
                    "n_markers": len(markers), "relative": relativo})


@bp.route("/api/download", methods=["POST"])
def api_download():
    """O CSV completo (sem downsample) da receita; reaproveita o último processamento."""
    options = request.get_json(silent=True) or {}
    if not (options.get("file") or options.get("files")):
        return jsonify({"error": tr("app.noFileInRequest")}), 400

    try:
        t, sig, channels, units = _processed_result(options)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    buf = io.StringIO()
    write_processed_csv(buf, t, sig, channels, units)

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
    app = create_app(args.data_dir)
    pasta = app.extensions["braggflow"].data.root
    print(f"BraggFlow web — http://127.0.0.1:{args.port}  (dados em {pasta})")
    app.run(host="127.0.0.1", port=args.port, debug=False)


if __name__ == "__main__":
    main()
