"""
Leitura de arquivos de interrogador e analisador de espectro.

O formato é detectado sozinho: codificação (UTF-8, UTF-8 com BOM, UTF-16 LE/BE,
Latin-1), separador (tabulação, ponto e vírgula, vírgula ou espaços), marca
decimal (ponto ou vírgula), linhas de cabeçalho do equipamento e presença ou
não de nomes de coluna. Qualquer extensão de texto serve (.ASC, .txt, .csv,
.dat, .tsv, .prn…).

Dois tipos de conteúdo são reconhecidos:

* ``timeseries`` – comprimento de onda de pico de cada canal ao longo do tempo,
  que é o que o ``OpticalPipeline`` processa (:func:`load_interrogator_file`).
* ``spectrum`` – espectro óptico, intensidade por comprimento de onda, um ou
  mais traços por arquivo (:func:`load_spectra`): analisadores de espectro
  (OSA) e espectrômetros UV-VIS-NIR (OceanView/SpectraSuite, com ou sem o
  cabeçalho ``>>>>>Begin Spectral Data<<<<<``). O instante da aquisição vem
  do cabeçalho (``Date: ...``) ou do nome do arquivo (``..._09-30-15-250``).
"""

import codecs
import hashlib
import re
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .processed import split_unit

# Prefixos de nome de coluna reconhecidos como eixo de tempo
TIME_PREFIXES = ("time", "tempo", "timestamp", "datetime", "date")

# Faixa óptica (nm) usada para reconhecer uma coluna de comprimento de onda:
# do UV dos espectrômetros (~200 nm) ao infravermelho dos OSA (até 2500 nm)
WAVELENGTH_RANGE = (150.0, 2500.0)
# Picos de FBG ficam nesta faixa e variam pouco: num arquivo sem cabeçalho,
# várias colunas assim indicam série temporal, mesmo que a 1ª coluna (tempo)
# cresça em passos regulares como um eixo de comprimento de onda
FBG_PEAK_RANGE = (1000.0, 2000.0)

_WHITESPACE_SEP = r"\s+"
_SEPARATORS = ("\t", ";", ",", _WHITESPACE_SEP)
_HEAD_BYTES = 1 << 16
_NUMBER_RE = re.compile(r"^[+-]?(\d+[.,]?\d*|[.,]\d+)([eE][+-]?\d+)?$")


# ─────────────────────────────────────────────────────────────────────────────
# Dados
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TextFormat:
    """Como o arquivo de texto está escrito."""

    encoding: str = "utf-8"
    sep: str = "\t"
    decimal: str = "."
    has_header: bool = True
    skiprows: int = 0      # linhas de preâmbulo antes da tabela

    @property
    def is_regex_sep(self) -> bool:
        return self.sep == r"\s+"

    def describe(self) -> str:
        names = {"\t": "tabulação", ";": "ponto e vírgula", ",": "vírgula",
                 r"\s+": "espaços"}
        return (f"{self.encoding}, separado por {names.get(self.sep, self.sep)}, "
                f"decimal '{self.decimal}'"
                f"{', com cabeçalho' if self.has_header else ', sem cabeçalho'}")


@dataclass
class InterrogatorData:
    """Série temporal: comprimento de onda de pico de cada canal."""

    time: np.ndarray                   # segundos (relativos a time_origin)
    signals: np.ndarray                # (n_amostras, n_canais)
    channels: List[str]                # nomes das colunas do arquivo
    units: List[Optional[str]]         # unidade lida do cabeçalho, ex.: 'nm'
    time_origin: Optional[str] = None  # instante da primeira amostra, se houver


def concat_plan(datasets: List[InterrogatorData]) -> List[dict]:
    """
    Onde cada arquivo entra na linha do tempo da concatenação, na ordem
    recebida: ``{index, n_samples, duration, start, end, step, gap, source}``.

    Quando os arquivos trazem data e hora, o intervalo entre eles é o tempo
    real que passou entre as aquisições (``source='relógio'``); sem isso, ou
    se as horas não forem coerentes, cada arquivo começa logo onde o anterior
    parou, mantendo o passo de amostragem (``source='sequência'``).
    """
    _check_same_channels(datasets)

    plano, fim_anterior, inicio_absoluto = [], 0.0, _to_datetime(datasets[0].time_origin)
    for i, dados in enumerate(datasets):
        passo = float(np.median(np.diff(dados.time))) if len(dados.time) > 1 else 0.0
        duracao = float(dados.time[-1] - dados.time[0])

        if i == 0:
            inicio, origem = 0.0, "início"
        else:
            inicio, origem = fim_anterior + max(plano[-1]["step"], 0.0), "sequência"
            instante = _to_datetime(dados.time_origin)
            if inicio_absoluto is not None and instante is not None:
                pelo_relogio = (instante - inicio_absoluto).total_seconds()
                if pelo_relogio >= inicio:      # respeita a pausa real entre ensaios
                    inicio, origem = pelo_relogio, "relógio"

        plano.append({
            "index": i,
            "n_samples": int(len(dados.time)),
            "duration": duracao,
            "start": inicio,
            "end": inicio + duracao,
            "step": passo,
            "gap": None if i == 0 else inicio - fim_anterior,
            "source": origem,
        })
        fim_anterior = inicio + duracao
    return plano


def _check_same_channels(datasets: List[InterrogatorData]) -> None:
    datasets = [d for d in datasets if len(d.time)]
    if not datasets:
        raise ValueError("Nenhum arquivo com amostras para juntar.")
    base = datasets[0]
    for outro in datasets[1:]:
        if outro.channels != base.channels:
            faltando = set(base.channels) ^ set(outro.channels)
            raise ValueError(
                "Só dá para juntar arquivos com os mesmos canais; "
                f"diferem em: {sorted(faltando) or 'ordem das colunas'}."
            )


def concatenate(datasets: List[InterrogatorData]) -> Tuple[InterrogatorData, List[float]]:
    """
    Junta arquivos de um mesmo ensaio num sinal contínuo, na ordem recebida,
    seguindo :func:`concat_plan`.

    Retorna ``(dados, junções)``, com os instantes em que um arquivo termina
    e o seguinte começa — úteis para marcar as emendas no gráfico.
    """
    datasets = [d for d in datasets if len(d.time)]
    if not datasets:
        raise ValueError("Nenhum arquivo com amostras para juntar.")
    if len(datasets) == 1:
        return datasets[0], []

    plano = concat_plan(datasets)
    tempos = [dados.time - float(dados.time[0]) + parte["start"]
              for dados, parte in zip(datasets, plano)]

    juntos = InterrogatorData(
        time=np.concatenate(tempos),
        signals=np.vstack([d.signals for d in datasets]),
        channels=list(datasets[0].channels),
        units=list(datasets[0].units),
        time_origin=datasets[0].time_origin,
    )
    return juntos, [parte["start"] for parte in plano[1:]]


def _to_datetime(valor: Optional[str]):
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor)
    except ValueError:
        return None


@dataclass
class Spectrum:
    """Um traço espectral: intensidade por comprimento de onda."""

    name: str
    wavelength: np.ndarray   # nm, crescente
    intensity: np.ndarray

    @property
    def n_points(self) -> int:
        return len(self.wavelength)


@dataclass
class SpectrumSet:
    """Todos os traços de um arquivo de espectro."""

    spectra: List[Spectrum] = field(default_factory=list)
    source: str = ""
    intensity_unit: str = "a.u."
    acquired: Optional[datetime] = None   # instante da aquisição, se conhecido
    acquired_from: str = ""               # "header", "header+filename" ou "filename"
    metadata: Dict[str, str] = field(default_factory=dict)   # "chave: valor" do cabeçalho

    @property
    def names(self) -> List[str]:
        return [s.name for s in self.spectra]

    def get(self, name: str) -> Optional[Spectrum]:
        return next((s for s in self.spectra if s.name == name), None)


# ─────────────────────────────────────────────────────────────────────────────
# Detecção de formato
# ─────────────────────────────────────────────────────────────────────────────

def _detect_encoding(raw: bytes) -> str:
    if raw.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if raw.startswith(codecs.BOM_UTF16_LE) or raw.startswith(codecs.BOM_UTF16_BE):
        return "utf-16"
    # UTF-16 sem BOM: metade dos bytes é nula
    if raw[:4096].count(0) > len(raw[:4096]) * 0.2:
        even_zeros = raw[:4096:2].count(0)
        odd_zeros = raw[1:4096:2].count(0)
        return "utf-16-be" if even_zeros > odd_zeros else "utf-16-le"
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "latin-1"


def _split(line: str, sep: str) -> List[str]:
    return re.split(sep, line.strip()) if sep == r"\s+" else line.rstrip("\r\n").split(sep)


def _is_number(text: str) -> bool:
    return bool(_NUMBER_RE.match(text.strip()))


def _looks_like_data(fields: List[str]) -> bool:
    """Linha de dados: pelo menos metade dos campos preenchidos são números."""
    filled = [f for f in fields if f.strip()]
    if len(filled) < 2:
        return False
    numeric = sum(_is_number(f) for f in filled)
    return numeric >= max(1, len(filled) // 2)


def detect_text_format(path, max_lines: int = 60) -> TextFormat:
    """Descobre codificação, separador, decimal e cabeçalho de um arquivo."""
    with open(path, "rb") as f:
        raw = f.read(_HEAD_BYTES)
    if not raw.strip():
        raise ValueError("Arquivo vazio.")

    encoding = _detect_encoding(raw)
    text = raw.decode(encoding, errors="replace")
    # Linhas em branco ficam fora da análise, mas o skiprows do pandas conta
    # todas as linhas do arquivo: ``numbers`` guarda a posição real de cada uma.
    numbered = [(i, line) for i, line in enumerate(text.splitlines()[:max_lines]) if line.strip()]
    if not numbered:
        raise ValueError("Arquivo sem linhas de dados.")
    # a última linha pode estar cortada pelo limite de leitura
    if len(numbered) > 2:
        numbered = numbered[:-1]
    numbers = [i for i, _ in numbered]
    lines = [line for _, line in numbered]

    # Delimitadores explícitos têm prioridade sobre espaços: um rótulo como
    # "CH 1" não pode acabar partido em duas colunas.
    # Vale a ordem de prioridade, não o número de colunas: a vírgula decimal
    # parte a linha em mais pedaços que a tabulação e venceria no critério
    # errado. Espaços ficam por último, para não quebrar rótulos como "CH 1".
    candidates = []
    for candidate in _SEPARATORS:
        # Linhas de comentário ou título do equipamento não têm o separador;
        # elas ficam de fora da conta para não derrubar a consistência.
        counts = [n for n in (len(_split(line, candidate)) for line in lines) if n >= 2]
        if len(counts) < max(2, len(lines) // 3):
            continue
        median = int(np.median(counts))
        if median < 2:
            continue
        # ±1 campo: o cabeçalho costuma ter um a menos que as linhas de dados,
        # que terminam com um separador sobrando.
        consistency = sum(abs(c - median) <= 1 for c in counts) / len(counts)
        if consistency >= 0.7:
            candidates.append((candidate, consistency, median))

    if not candidates:
        raise ValueError("Não foi possível identificar o separador de colunas.")
    sep = next((c for c, consistency, _ in candidates if consistency >= 0.9),
               max(candidates, key=lambda item: item[1:])[0])

    rows = [_split(line, sep) for line in lines]
    first_data = next((i for i, fields in enumerate(rows) if _looks_like_data(fields)), None)
    if first_data is None:
        raise ValueError("Não foi encontrada nenhuma linha de dados numéricos.")

    # Linhas de dados costumam terminar com um separador sobrando, então o
    # cabeçalho pode ter um campo a menos que elas.
    # Um campo só não é cabeçalho: é título ou marcador do equipamento, como
    # ">>>>>Begin Spectral Data<<<<<" do OceanView antes de duas colunas.
    previous = rows[first_data - 1] if first_data > 0 else []
    has_header = (len([f for f in previous if f.strip()]) >= 2
                  and not _looks_like_data(previous)
                  and abs(len(previous) - len(rows[first_data])) <= 1)
    skiprows = numbers[first_data - 1] if has_header else numbers[first_data]

    decimal = "."
    data_text = " ".join(" ".join(r) for r in rows[first_data:])
    if sep != "," and re.search(r"\d,\d", data_text):
        decimal = ","
    return TextFormat(encoding=encoding, sep=sep, decimal=decimal,
                      has_header=has_header, skiprows=skiprows)


def sniff_format(path, n_lines: int = 60) -> Tuple[str, str]:
    """Separador e marca decimal (compatibilidade com o uso antigo)."""
    fmt = detect_text_format(path, max_lines=n_lines)
    return fmt.sep, fmt.decimal


def read_table(path, fmt: Optional[TextFormat] = None,
               nrows: Optional[int] = None) -> Tuple[pd.DataFrame, TextFormat]:
    """
    Lê o arquivo como tabela, detectando o formato quando não informado.
    ``nrows`` limita a leitura, para espiar um arquivo grande.
    """
    fmt = fmt or detect_text_format(path)
    try:
        df = pd.read_csv(
            path,
            sep=fmt.sep,
            decimal=fmt.decimal,
            engine="python" if fmt.is_regex_sep else "c",
            header=0 if fmt.has_header else None,
            skiprows=fmt.skiprows,
            index_col=False,  # linhas que terminam com separador não viram índice
            encoding=fmt.encoding,
            encoding_errors="replace",
            nrows=nrows,
        )
    except Exception as e:
        raise IOError(f"Erro ao ler o arquivo: {e}") from e

    df = df.dropna(axis=1, how="all")
    if fmt.has_header:
        df.columns = [str(c).strip() for c in df.columns]
    else:
        df.columns = [f"col_{i + 1}" for i in range(df.shape[1])]
    if df.empty:
        raise ValueError("Arquivo sem dados.")
    return df, fmt


# ─────────────────────────────────────────────────────────────────────────────
# Classificação do conteúdo
# ─────────────────────────────────────────────────────────────────────────────

def _to_float(column: pd.Series, decimal: str) -> np.ndarray:
    """Coluna como float; textos (ex.: 'N/A') viram NaN."""
    if pd.api.types.is_numeric_dtype(column):
        return column.to_numpy(dtype=float)
    text = column.astype(str).str.strip()
    if decimal == ",":
        text = text.str.replace(",", ".", regex=False)
    return pd.to_numeric(text, errors="coerce").to_numpy(dtype=float)


def _numeric_columns(df: pd.DataFrame, decimal: str) -> Dict[str, np.ndarray]:
    """
    Colunas numéricas, já convertidas. O que conta é a fração de células
    *preenchidas* que são números: em exportações de OSA metade das linhas
    pertence a um traço vazio, e a coluna continua sendo numérica.
    """
    numeric = {}
    for name in df.columns:
        values = _to_float(df[name], decimal)
        if pd.api.types.is_numeric_dtype(df[name]):
            filled = df[name].notna().to_numpy()
        else:
            filled = (df[name].astype(str).str.strip() != "").to_numpy()
        if filled.sum() < 2:
            continue
        if np.isfinite(values[filled]).mean() > 0.8:
            numeric[name] = values
    return numeric


def _label_column(df: pd.DataFrame, numeric: Dict[str, np.ndarray]) -> Optional[str]:
    """Coluna de texto com poucos valores distintos (nome do traço)."""
    for name in df.columns:
        if name in numeric:
            continue
        values = df[name].astype(str).str.strip()
        if 0 < values.nunique() <= 50:
            return name
    return None


def _is_wavelength(values: np.ndarray) -> bool:
    """Valores dentro da faixa óptica e sempre crescentes (ou decrescentes)."""
    finite = values[np.isfinite(values)]
    if len(finite) < 10:
        return False
    low, high = WAVELENGTH_RANGE
    if not (low <= finite.min() and finite.max() <= high):
        return False              # inclui o tempo, que começa em 0
    if abs(finite[-1] - finite[0]) < 1.0:
        return False              # um canal de FBG varia bem menos de 1 nm
    diffs = np.diff(finite)
    if not (np.all(diffs > 0) or np.all(diffs < 0)):
        return False
    # Grade regular, tolerando o arredondamento do arquivo (passos de 2 e 3 pm
    # num espectro gravado com três casas decimais, por exemplo).
    step = np.median(diffs)
    if step == 0:
        return False
    ratio = diffs / step
    return bool(np.mean((ratio > 0.2) & (ratio < 5.0)) > 0.95)


def classify_table(df: pd.DataFrame, fmt: TextFormat) -> str:
    """``'timeseries'`` ou ``'spectrum'`` conforme o conteúdo da tabela."""
    if any(str(c).lower().startswith(TIME_PREFIXES) for c in df.columns):
        return "timeseries"

    numeric = _numeric_columns(df, fmt.decimal)
    if len(numeric) < 2:
        return "timeseries"

    label = _label_column(df, numeric)
    if label is not None:
        first = df[label].astype(str).str.strip().iloc[0]
        mask = (df[label].astype(str).str.strip() == first).to_numpy()
        if any(_is_wavelength(values[mask]) for values in numeric.values()):
            return "spectrum"
        return "timeseries"

    # Duas ou mais colunas, todas com cara de pico de FBG: interrogador sem
    # cabeçalho. Uma coluna só pode ser a intensidade de um dark ou de uma
    # fonte, que também fica quase parada na casa dos milhares de contagens.
    outras = list(numeric.values())[1:]
    if len(outras) >= 2 and all(_looks_like_fbg_peaks(v) for v in outras):
        return "timeseries"
    return "spectrum" if any(_is_wavelength(v) for v in numeric.values()) else "timeseries"


def _looks_like_fbg_peaks(values: np.ndarray) -> bool:
    """Coluna de pico de FBG: na faixa de 1000–2000 nm e quase parada (< 20 nm)."""
    finite = values[np.isfinite(values) & (values > 0)]   # 0 = pico perdido
    if len(finite) < 10:
        return False
    low, high = FBG_PEAK_RANGE
    return bool(low <= np.median(finite) <= high and np.ptp(finite) < 20.0)


def classify_file(path, nrows: int = 2000) -> str:
    """Tipo do conteúdo lendo só o começo do arquivo (listagens rápidas)."""
    df, fmt = read_table(path, nrows=nrows)
    return classify_table(df, fmt)


def describe_file(path) -> dict:
    """Resumo do arquivo para a interface: tipo, formato e colunas."""
    df, fmt = read_table(path)
    kind = classify_table(df, fmt)
    info = {
        "kind": kind,
        "format": fmt.describe(),
        "encoding": fmt.encoding,
        "columns": [str(c) for c in df.columns],
        "n_rows": int(len(df)),
    }
    if kind == "spectrum":
        spectra = _spectra_from_table(df, fmt, Path(path).name)
        info["traces"] = spectra.names
        if spectra.spectra:
            first = spectra.spectra[0]
            info["wavelength_range"] = [round(float(first.wavelength[0]), 3),
                                        round(float(first.wavelength[-1]), 3)]
            info["n_points"] = first.n_points
    else:
        info["channels"] = [c for c in df.columns
                            if str(c).upper().startswith("CH")] or info["columns"][1:]
    return info


# ─────────────────────────────────────────────────────────────────────────────
# Série temporal (pico por canal)
# ─────────────────────────────────────────────────────────────────────────────

def parse_time_column(values: pd.Series) -> Tuple[np.ndarray, Optional[str]]:
    """
    Converte a coluna de tempo em segundos.

    Colunas numéricas passam direto. Colunas de texto são lidas como data e
    hora (ISO ou dia/mês/ano, ou só hora) e convertidas em segundos desde a
    primeira amostra; o instante inicial é devolvido. Horas que passam da
    meia-noite são desdobradas. Valores ilegíveis viram NaN.
    """
    if pd.api.types.is_numeric_dtype(values):
        return values.to_numpy(dtype=float), None

    text = values.astype(str).str.strip().str.replace(",", ".", regex=False)
    numeric = pd.to_numeric(text, errors="coerce")
    if numeric.notna().mean() >= 0.9:
        return numeric.to_numpy(dtype=float), None

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        stamps = pd.to_datetime(text, dayfirst=True, errors="coerce")

    valid = stamps.notna().to_numpy()
    if not valid.any():
        raise ValueError("A coluna de tempo não é numérica nem uma data reconhecível.")

    first = stamps[valid].iloc[0]
    seconds = np.full(len(stamps), np.nan)
    seconds[valid] = (stamps[valid] - first).dt.total_seconds().to_numpy()

    time_only = re.match(r"^\d{1,2}:\d{2}", text[valid].iloc[0]) is not None
    if time_only:
        finite = np.flatnonzero(valid)
        wraps = np.concatenate([[0], np.cumsum(np.diff(seconds[finite]) < -43200)])
        seconds[finite] += 86400.0 * wraps
        return seconds, None
    return seconds, first.isoformat()


def load_interrogator_file(path) -> InterrogatorData:
    """
    Lê a série temporal de picos de um interrogador.

    * A coluna de tempo é a primeira cujo nome começa com Time/Tempo/
      Timestamp/Date; sem cabeçalho, a primeira coluna numérica.
    * Os canais são as colunas que começam com ``CH``; não havendo nenhuma,
      todas as outras colunas numéricas.
    * Os valores saem como foram exportados: picos perdidos (0) são tratados
      por :func:`braggflow.processing.cleaning.mark_invalid_peaks`.
    """
    df, fmt = read_table(path)
    if classify_table(df, fmt) == "spectrum":
        raise ValueError(
            f"{Path(path).name} é um espectro (intensidade por comprimento de onda), "
            "não uma série de picos no tempo. Use a aba Visualização, em "
            "'Espectros', para abri-lo."
        )

    time_col = next(
        (c for prefix in TIME_PREFIXES for c in df.columns if str(c).lower().startswith(prefix)),
        None,
    )
    numeric = _numeric_columns(df, fmt.decimal)
    if time_col is None:
        time_col = next(iter(numeric), None)
        if time_col is None:
            raise ValueError("Nenhuma coluna de tempo encontrada (Time, Tempo, Timestamp ou Date).")

    ch_cols = [c for c in df.columns if str(c).upper().startswith("CH")]
    if not ch_cols:
        ch_cols = [c for c in numeric if c != time_col]
    if not ch_cols:
        raise ValueError("Nenhuma coluna de canal encontrada no arquivo.")

    time_array, origin = parse_time_column(df[time_col])
    keep = np.isfinite(time_array)
    signals = np.column_stack([_to_float(df[c], fmt.decimal) for c in ch_cols])
    units = [split_unit(str(c))[1] or "nm" for c in ch_cols]

    return InterrogatorData(
        time=time_array[keep],
        signals=signals[keep],
        channels=[str(c) for c in ch_cols],
        units=units,
        time_origin=origin,
    )


def read_asc(ascfile):
    """Lê um arquivo de interrogador e devolve ``(tempo, sinais, canais)``."""
    data = load_interrogator_file(ascfile)
    return data.time, data.signals, data.channels


# ─────────────────────────────────────────────────────────────────────────────
# Espectros
# ─────────────────────────────────────────────────────────────────────────────

def _make_spectrum(name: str, wavelength: np.ndarray, intensity: np.ndarray) -> Optional[Spectrum]:
    valid = np.isfinite(wavelength) & np.isfinite(intensity)
    if valid.sum() < 2:
        return None  # traço vazio (ex.: 'Subset 2' em exportações de OSA)
    wavelength, intensity = wavelength[valid], intensity[valid]
    if wavelength[0] > wavelength[-1]:
        wavelength, intensity = wavelength[::-1], intensity[::-1]
    return Spectrum(name=name.strip() or "Traço", wavelength=wavelength, intensity=intensity)


def _spectra_from_table(df: pd.DataFrame, fmt: TextFormat, source: str) -> SpectrumSet:
    numeric = _numeric_columns(df, fmt.decimal)
    if len(numeric) < 2:
        raise ValueError("O arquivo não tem duas colunas numéricas (comprimento de onda e intensidade).")

    label = _label_column(df, numeric)
    spectra: List[Spectrum] = []

    if label is not None:
        labels = df[label].astype(str).str.strip().to_numpy()
        for name in dict.fromkeys(labels):           # mantém a ordem do arquivo
            mask = labels == name
            columns = list(numeric)
            lam_col = next((c for c in columns if _is_wavelength(numeric[c][mask])), None)
            if lam_col is None:
                continue
            after = columns[columns.index(lam_col) + 1:]
            int_col = after[0] if after else next((c for c in columns if c != lam_col), None)
            if int_col is None:
                continue
            spectrum = _make_spectrum(name, numeric[lam_col][mask], numeric[int_col][mask])
            if spectrum:
                spectra.append(spectrum)
    else:
        columns = list(numeric)
        lam_col = next((c for c in columns if _is_wavelength(numeric[c])), columns[0])
        for i, name in enumerate([c for c in columns if c != lam_col], start=1):
            label_name = str(name) if fmt.has_header else f"Traço {i}"
            spectrum = _make_spectrum(label_name, numeric[lam_col], numeric[name])
            if spectrum:
                spectra.append(spectrum)

    if not spectra:
        raise ValueError("Nenhum traço espectral válido encontrado no arquivo.")
    return SpectrumSet(spectra=spectra, source=source)


_MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), start=1)}
# "Mon Mar 02 09:30:15 BRT 2026" (OceanView/SpectraSuite); o fuso é ignorado
_HEADER_DATE = re.compile(
    r"^(?:\w{3}\s+)?(\w{3})\s+(\d{1,2})\s+(\d{1,2}):(\d{2}):(\d{2})(?:\s+[A-Za-z][\w+:-]*)?\s+(\d{4})$")
# "..._09-30-15-250" no fim do nome: hora, minuto, segundo e milissegundo
_FILENAME_TIME = re.compile(r"(?:^|[_\s-])(\d{2})-(\d{2})-(\d{2})(?:-(\d{1,3}))?$")


def read_preamble(path, fmt: Optional[TextFormat] = None) -> Dict[str, str]:
    """Linhas ``chave: valor`` antes da tabela (cabeçalho do equipamento)."""
    fmt = fmt or detect_text_format(path)
    if not fmt.skiprows:
        return {}
    with open(path, "r", encoding=fmt.encoding, errors="replace") as f:
        lines = [next(f, "") for _ in range(fmt.skiprows)]
    meta = {}
    for line in lines:
        key, sep, value = line.strip().partition(":")
        if sep and key.strip() and len(key) <= 60:
            meta[key.strip()] = value.strip()
    return meta


def _parse_header_date(text: str) -> Optional[datetime]:
    text = text.strip()
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    m = _HEADER_DATE.match(text)
    if not m or m.group(1).lower() not in _MONTHS:
        return None
    mon, day, hh, mm, ss, year = m.groups()
    try:
        return datetime(int(year), _MONTHS[mon.lower()], int(day), int(hh), int(mm), int(ss))
    except ValueError:
        return None


def acquisition_time(path, metadata: Optional[Dict[str, str]] = None):
    """
    Instante em que o espectro foi gravado: ``(datetime, origem)``.

    O cabeçalho (``Date: ...``) dá data e hora até o segundo. O nome do
    arquivo (``..._09-30-15-250``) dá a hora com milissegundos, mas não a
    data: quando os dois existem e batem no segundo, os milissegundos do nome
    completam o cabeçalho; sem cabeçalho, a data fica 1900-01-01 e só a hora
    vale (serve para ordenar e medir intervalos no mesmo dia).
    Devolve ``(None, "")`` quando nenhum dos dois existe.
    """
    header = None
    for key, value in (metadata or {}).items():
        if key.lower() in ("date", "data", "timestamp", "acquisition time"):
            header = _parse_header_date(value)
            if header:
                break

    m = _FILENAME_TIME.search(Path(path).stem)
    from_name = None
    if m:
        hh, mm, ss, ms = m.groups()
        try:
            from_name = datetime(1900, 1, 1, int(hh), int(mm), int(ss),
                                 int((ms or "0").ljust(3, "0")) * 1000)
        except ValueError:
            from_name = None

    if header and from_name and header.time().replace(microsecond=0) == from_name.time().replace(microsecond=0):
        return header.replace(microsecond=from_name.microsecond), "header+filename"
    if header:
        return header, "header"
    if from_name:
        return from_name, "filename"
    return None, ""


def load_spectra(path) -> SpectrumSet:
    """
    Lê um arquivo de espectro óptico (intensidade por comprimento de onda).

    Aceita o formato largo (uma coluna de comprimento de onda e uma coluna de
    intensidade por traço) e o formato longo de analisadores de espectro, em
    que os traços vêm empilhados com uma coluna de rótulo (``CH 1``,
    ``Subset 2``…); traços sem dados são descartados.
    """
    df, fmt = read_table(path)
    spectra = _spectra_from_table(df, fmt, Path(path).name)
    spectra.metadata = read_preamble(path, fmt)
    spectra.acquired, spectra.acquired_from = acquisition_time(path, spectra.metadata)
    if "transmission" in Path(path).stem.lower():
        spectra.intensity_unit = "%"
    return spectra


# ─────────────────────────────────────────────────────────────────────────────

# Arquivos que descrevem o ensaio, sem conter os dados (catman)
DESCRIPTOR_EXTENSIONS = {".tsx", ".tsm"}


def read_descriptor(text: str) -> dict:
    """
    Lê um descritor do catman (linhas ``CHAVE=valor``) e devolve o que
    interessa: o arquivo de dados que ele acompanha, a taxa de amostragem,
    o número de amostras e o instante de início.
    """
    info = {}
    for line in text.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            info[key.strip()] = value.strip()
    return {
        "data_file": info.get("Data file") or info.get("DATAFILE", "").split("\\")[-1],
        "sample_rate": info.get("Default sample rate"),
        "n_samples": info.get("Number of samples default sample rate"),
        "start_time": info.get("Start time"),
        "stop_time": info.get("Stop time"),
    }


def file_fingerprint(path) -> dict:
    """Nome, tamanho, data de modificação e SHA-256 do arquivo de origem."""
    path = Path(path)
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    stat = path.stat()
    return {
        "file": path.name,
        "size_bytes": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "sha256": digest.hexdigest(),
    }
