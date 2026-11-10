"""
Estado de uma instância do web app: a pasta de dados e os caches de leitura.

Cada app criado por ``create_app`` tem o seu ``AppState`` (em
``app.extensions["braggflow"]``), então duas instâncias — ou dois testes —
nunca compartilham pasta nem cache.
"""

import hashlib
import json
import os
import stat
import threading
import weakref
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from braggflow.i18n import tr
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
        self._resolved_root = self.root.resolve()
        self._root_prefix = str(self.root) + os.sep
        self.raw = self.root / "raw"
        self.uploads = self.root / "uploads"
        self.processed = self.root / "processed"
        self.setups = self.root / "setups"
        self.styles = self.root / "styles"
        self.projects = self.root / "projects"

    def rel(self, path: Path) -> str:
        """Caminho de um arquivo como a API o mostra: ``data/<subpasta>/...``."""
        texto = str(path)
        if texto.startswith(self._root_prefix):
            return f"{self.PREFIX}/{texto[len(self._root_prefix):].replace(os.sep, '/')}"
        return f"{self.PREFIX}/{Path(path).relative_to(self.root).as_posix()}"

    def resolve(self, rel_path: str, folders: Optional[dict] = None) -> Path:
        """
        Resolve um caminho ``data/...`` garantindo que fique dentro da pasta de dados.

        ``folders`` é um dicionário de quem chama, com as pastas já resolvidas
        (o app usa um por pedido): com ele, os arquivos seguintes de uma mesma
        pasta custam uma consulta ao disco em vez de um ``resolve()`` inteiro,
        que numa pasta sincronizada pesa — e uma evolução resolve milhares.
        """
        caminho = Path(rel_path)
        if caminho.is_absolute():
            full = caminho.resolve()
        elif caminho.parts[:1] == (self.PREFIX,):
            if folders is not None:
                direto = self._plain_file(caminho.parts[1:], folders)
                if direto is not None:
                    return direto
            full = self.root.joinpath(*caminho.parts[1:]).resolve()
        else:
            full = None
        if full is None or not full.is_file() or self._resolved_root not in full.parents:
            raise ValueError(tr("data.invalidPath", path=rel_path))
        return full

    def _plain_file(self, parts: tuple, folders: dict) -> Optional[Path]:
        """
        O arquivo ``parts`` quando a pasta dele, já resolvida, fica dentro da
        pasta de dados e ele é um arquivo comum: aí o caminho resolvido é a
        pasta mais o nome. Atalhos (que podem apontar para fora), ``..`` e o
        que não existe devolvem ``None`` e seguem pelo ``resolve()`` inteiro.
        """
        if not parts or any(p in ("", ".", "..") for p in parts):
            return None
        if parts[:-1] not in folders:
            pasta = self.root.joinpath(*parts[:-1]).resolve()
            dentro = pasta == self._resolved_root or self._resolved_root in pasta.parents
            folders[parts[:-1]] = pasta if dentro else None
        pasta = folders[parts[:-1]]
        if pasta is None:
            return None
        full = pasta / parts[-1]
        try:
            comum = stat.S_ISREG(os.lstat(full).st_mode)
        except OSError:
            return None
        return full if comum else None


class FileCache:
    """
    Resultado de ``loader(path)`` guardado enquanto o arquivo não mudar
    (mesmo caminho, data de modificação e tamanho). Uma versão nova de um
    arquivo substitui a antiga; acima de ``size``, sai a usada há mais tempo
    (``None`` = sem limite). ``size`` conta entradas ou, com ``weigh``, a
    soma de ``weigh(resultado)`` (pontos de espectro, por exemplo); a mais
    recente fica mesmo que sozinha passe do limite.
    """

    def __init__(self, loader: Callable, size: Optional[int], weigh: Optional[Callable] = None):
        self._loader = loader
        self._size = size
        self._weigh = weigh or (lambda entry: 1)
        self._entries: OrderedDict = OrderedDict()     # chave → (resultado, peso)
        self._current: dict = {}                       # caminho → chave da versão guardada
        self._total = 0
        self._lock = threading.Lock()

    def get(self, path: Path):
        stat = path.stat()
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        with self._lock:
            if key in self._entries:
                self._entries.move_to_end(key)
                return self._entries[key][0]

        entry = self._loader(path)
        peso = self._weigh(entry)
        with self._lock:
            antiga = self._current.get(key[0])
            if antiga in self._entries:
                self._total -= self._entries.pop(antiga)[1]     # a versão anterior do mesmo arquivo
            self._entries[key] = (entry, peso)
            self._current[key[0]] = key
            self._total += peso
            while self._size is not None and self._total > self._size and len(self._entries) > 1:
                saiu, (_, peso_saiu) = self._entries.popitem(last=False)
                self._total -= peso_saiu
                self._current.pop(saiu[0], None)
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
# Espectros lidos e extremos já medidos: uma evolução com milhares de
# arquivos é recalculada (outro λ de referência, outro modo, outro preparo)
# sem reler nada. O limite é em bytes, não em arquivos: os espectros de um
# mesmo equipamento dividem um eixo de λ só (ver SharedAxes), então cada um
# pesa 8 bytes por ponto. 256 MB guardam ~16 mil espectros de 2048 pontos
# (espectrômetro) ou ~1000 do catman (.BIN, 32.768 pontos).
SPECTRA_CACHE_BYTES = 256 * 1024 * 1024
ANALYSIS_CACHE_SIZE = 32768


class SharedAxes:
    """
    Lê espectros dando a todos os que têm o mesmo eixo de λ (os arquivos de
    um mesmo equipamento, numa série) uma cópia só desse eixo, que não pode
    mais ser alterada. O eixo sai da memória junto com o último espectro que
    o usa.
    """

    def __init__(self, loader: Callable = load_spectra):
        self._loader = loader
        self._axes = weakref.WeakValueDictionary()
        self._lock = threading.Lock()

    def __call__(self, path: Path):
        spectra = self._loader(path)
        for s in spectra.spectra:
            chave = (s.wavelength.size, hashlib.blake2b(s.wavelength.tobytes(), digest_size=16).digest())
            with self._lock:
                eixo = self._axes.get(chave)
                if eixo is None:
                    eixo = self._axes[chave] = s.wavelength
                    eixo.flags.writeable = False
            s.wavelength = eixo
        return spectra


def _spectrum_bytes(spectra) -> int:
    """Memória de um arquivo de espectro: as intensidades e os eixos de λ distintos."""
    eixos = {id(s.wavelength): s.wavelength.nbytes for s in spectra.spectra}
    return sum(s.intensity.nbytes for s in spectra.spectra) + sum(eixos.values())


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
    spectra: FileCache = field(default_factory=lambda: FileCache(SharedAxes(), SPECTRA_CACHE_BYTES,
                                                                 weigh=_spectrum_bytes))
    kinds: FileCache = field(default_factory=lambda: FileCache(_classify, None))
    results: ResultCache = field(default_factory=ResultCache)
    analyses: ResultCache = field(default_factory=lambda: ResultCache(ANALYSIS_CACHE_SIZE))
