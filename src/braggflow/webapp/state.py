"""
Estado de uma instância do web app: a pasta de dados e os caches de leitura.

Cada app criado por ``create_app`` tem o seu ``AppState`` (em
``app.extensions["braggflow"]``), então duas instâncias — ou dois testes —
nunca compartilham pasta nem cache.
"""

import json
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from braggflow.io.processed import channel_quantities, read_processed_csv
from braggflow.io.reader import classify_file, load_spectra
from braggflow.paths import resolve_data_dir
from braggflow.recipe import load_file


class DataFolder:
    """
    Pasta de dados (``--data-dir``, ``BRAGGFLOW_DATA_DIR`` ou ``./data``).

    A API e os projetos salvos se referem aos arquivos como
    ``data/<subpasta>/...``: esse ``data`` é um prefixo virtual que aponta
    para esta pasta, qualquer que seja o nome ou o lugar dela, para que
    projetos antigos continuem abrindo.
    """

    PREFIX = "data"

    def __init__(self, data_dir=None, *, create: bool = True):
        self.root = resolve_data_dir(data_dir, create=create)
        self.raw = self.root / "raw"
        self.uploads = self.root / "uploads"
        self.processed = self.root / "processed"
        self.setups = self.root / "setups"
        self.styles = self.root / "styles"
        self.projects = self.root / "projects"

    def rel(self, path: Path) -> str:
        """Caminho de um arquivo como a API o mostra: ``data/<subpasta>/...``."""
        return f"{self.PREFIX}/{Path(path).relative_to(self.root).as_posix()}"

    def resolve(self, rel_path: str) -> Path:
        """Resolve um caminho ``data/...`` garantindo que fique dentro da pasta de dados."""
        caminho = Path(rel_path)
        if caminho.is_absolute():
            full = caminho.resolve()
        elif caminho.parts[:1] == (self.PREFIX,):
            full = self.root.joinpath(*caminho.parts[1:]).resolve()
        else:
            full = None
        root = self.root.resolve()
        if full is None or not full.is_file() or root not in full.parents:
            raise ValueError(f"Arquivo inválido ou fora de data/: {rel_path}")
        return full


class FileCache:
    """
    Resultado de ``loader(path)`` guardado enquanto o arquivo não mudar
    (mesmo caminho, data de modificação e tamanho). Uma versão nova de um
    arquivo substitui a antiga; acima de ``size`` entradas, sai a usada há
    mais tempo (``None`` = sem limite).
    """

    def __init__(self, loader: Callable, size: Optional[int]):
        self._loader = loader
        self._size = size
        self._entries: OrderedDict = OrderedDict()
        self._lock = threading.Lock()

    def get(self, path: Path):
        stat = path.stat()
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        with self._lock:
            if key in self._entries:
                self._entries.move_to_end(key)
                return self._entries[key]

        entry = self._loader(path)
        with self._lock:
            for old in [k for k in self._entries if k[0] == key[0]]:
                del self._entries[old]  # versões antigas do mesmo arquivo
            self._entries[key] = entry
            while self._size is not None and len(self._entries) > self._size:
                self._entries.popitem(last=False)
        return entry


class ResultCache:
    """
    Últimos resultados do processamento, pela receita e pelos arquivos de
    origem (caminho, data e tamanho): medir um trecho do gráfico não refaz o
    processamento que acabou de ser mostrado.
    """

    # Opções que não mudam o sinal processado (só onde e se ele é gravado)
    IGNORED = ("save", "include_raw", "project")

    def __init__(self, size: int = 4):
        self._size = size
        self._entries: OrderedDict = OrderedDict()
        self._lock = threading.Lock()

    def key(self, options: dict, files) -> str:
        receita = {k: v for k, v in options.items() if k not in self.IGNORED}
        origem = []
        for path in files:
            stat = Path(path).stat()
            origem.append([str(path), stat.st_mtime_ns, stat.st_size])
        return json.dumps([receita, origem], sort_keys=True, default=str)

    def get(self, key: str):
        with self._lock:
            if key in self._entries:
                self._entries.move_to_end(key)
                return self._entries[key]
        return None

    def put(self, key: str, value) -> None:
        with self._lock:
            self._entries[key] = value
            self._entries.move_to_end(key)
            while len(self._entries) > self._size:
                self._entries.popitem(last=False)


# Arquivos do interrogador já lidos (reprocessar não relê o disco)
FILE_CACHE_SIZE = 2
# Espectros lidos e extremos já medidos: uma evolução com centenas de
# arquivos é recalculada (outro λ de referência, outro modo) sem reler nada.
# Um espectro de 1000–4000 pontos ocupa de 20 a 70 kB.
SPECTRA_CACHE_SIZE = 1024
ANALYSIS_CACHE_SIZE = 8192


def _load_processed(path: Path):
    df, units, metadata = read_processed_csv(path)
    return df, units, channel_quantities(metadata)


def _classify(path: Path) -> str:
    """Tipo do arquivo, lido só do começo dele."""
    try:
        return classify_file(path)
    except (ValueError, IOError, OSError):
        return "unknown"


@dataclass
class AppState:
    data: DataFolder
    interrogator: FileCache = field(default_factory=lambda: FileCache(load_file, FILE_CACHE_SIZE))
    processed: FileCache = field(default_factory=lambda: FileCache(_load_processed, FILE_CACHE_SIZE * 3))
    spectra: FileCache = field(default_factory=lambda: FileCache(load_spectra, SPECTRA_CACHE_SIZE))
    kinds: FileCache = field(default_factory=lambda: FileCache(_classify, None))
    results: ResultCache = field(default_factory=ResultCache)
    analyses: ResultCache = field(default_factory=lambda: ResultCache(ANALYSIS_CACHE_SIZE))
