"""
Projetos: uma análise inteira guardada com nome.

Um projeto reúne tudo o que foi definido para um ensaio — arquivo do
interrogador, sensores (nome e banda), etapas de processamento com os seus
parâmetros, marcações de tempo, canais escolhidos e o estilo da figura — num
único JSON em ``data/projects``. Abrir o projeto recoloca o app no mesmo
estado; os dados em si continuam nos arquivos originais.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .processing.spectra import (
    parse_evolution_events,
    resolve_evolution_options,
    resolve_spectrum_settings,
)
from .sensors import Sensor
from .visualization.figure import default_style, parse_markers, resolve_style

# Seções de opções de processamento aceitas (as mesmas da interface)
PROCESSING_SECTIONS = (
    "window", "cleaning", "timebase", "nulls", "outliers", "savgol",
    "moving_average", "lowpass", "highpass", "delta_lambda", "temp_comp",
)


def _clean_processing(processing: Optional[dict]) -> Dict[str, dict]:
    """Mantém só as seções conhecidas, com valores simples (str/número/bool)."""
    processing = processing or {}
    if not isinstance(processing, dict):
        raise ValueError("Opções de processamento inválidas.")

    clean: Dict[str, dict] = {}
    for section in PROCESSING_SECTIONS:
        values = processing.get(section)
        if values is None:
            continue
        if not isinstance(values, dict):
            raise ValueError(f"Opções inválidas na etapa '{section}'.")
        clean[section] = {
            str(key): value for key, value in values.items()
            if value is None or isinstance(value, (str, int, float, bool))
        }
    if "include_raw" in processing:
        clean["include_raw"] = bool(processing["include_raw"])
    return clean


@dataclass
class Project:
    name: str
    file: str = ""                                   # arquivo do interrogador
    description: str = ""
    sensors: List[Sensor] = field(default_factory=list)
    processing: Dict[str, dict] = field(default_factory=dict)
    markers: List[dict] = field(default_factory=list)   # {time, label, color}
    series: List[dict] = field(default_factory=list)    # um estado por arquivo
    join_series: bool = False                           # arquivos de um mesmo ensaio
    spectra_files: List[dict] = field(default_factory=list)  # [{file, settings, exclude}]
    # Mesmo preparo para todos os espectros (então ``settings`` de cada um é
    # None); None = projeto de antes da opção, decidido ao abrir
    spectra_common: Optional[bool] = None
    spectra_settings: Optional[dict] = None
    evolution: dict = field(default_factory=dict)       # como acompanhar os vales
    evolution_events: List[dict] = field(default_factory=list)   # {at, label, color}
    source: str = "series"                              # "spectra" ou "evolution"
    viz_sources: Dict[str, List[str]] = field(default_factory=dict)
    channels: List[str] = field(default_factory=list)   # curvas marcadas
    spectra: List[dict] = field(default_factory=list)   # [{file, trace}]
    style: dict = field(default_factory=default_style)
    created: str = ""
    updated: str = ""

    def __post_init__(self):
        self.name = str(self.name).strip()
        if not self.name:
            raise ValueError("Informe um nome para o projeto.")
        self.file = str(self.file or "")
        self.processing = _clean_processing(self.processing)
        self.markers = parse_markers(self.markers)
        self.channels = [str(c) for c in self.channels]
        if self.source == "timeseries":
            self.source = "series"          # nome antigo da fonte
        if self.source not in ("series", "spectra", "evolution"):
            raise ValueError(f"Fonte da figura inválida: {self.source}.")

        self.series = [self._clean_series_entry(entry) for entry in (self.series or [])
                       if isinstance(entry, dict) and entry.get("file")]
        if not self.series and self.file:
            # Formato antigo: o projeto guardava um arquivo só
            self.series = [self._clean_series_entry(
                {"file": self.file, "sensors": [s.to_dict() for s in self.sensors],
                 "processing": self.processing})]

        self.spectra_files = [
            {"file": str(entry["file"]),
             "settings": (resolve_spectrum_settings(entry["settings"],
                                                    prefix=f"[{Path(str(entry['file'])).name}] ")
                          if isinstance(entry.get("settings"), dict) else None),
             "exclude": bool(entry.get("exclude", False))}
            for entry in (self.spectra_files or [])
            if isinstance(entry, dict) and entry.get("file")
        ]
        if self.spectra_common is not None:
            self.spectra_common = bool(self.spectra_common)
        if self.spectra_settings is not None:
            self.spectra_settings = resolve_spectrum_settings(self.spectra_settings,
                                                              prefix="[preparo comum] ")
        self.evolution = resolve_evolution_options(self.evolution or {})
        self.evolution_events = parse_evolution_events(self.evolution_events)
        self.viz_sources = {
            key: [str(path) for path in (self.viz_sources or {}).get(key, [])]
            for key in ("series", "spectra")
        }
        self.spectra = [
            {"file": str(item["file"]), "trace": str(item.get("trace", ""))}
            for item in (self.spectra or []) if isinstance(item, dict) and item.get("file")
        ]
        self.style = resolve_style(self.style)
        now = datetime.now().isoformat(timespec="seconds")
        self.created = self.created or now
        self.updated = now

    @staticmethod
    def _clean_series_entry(entry: dict) -> dict:
        """Estado de um arquivo: sensores e etapas, validados."""
        sensors = [Sensor.from_dict(s) if isinstance(s, dict) else s
                   for s in (entry.get("sensors") or [])]
        return {
            "file": str(entry["file"]),
            "include": bool(entry.get("include", True)),
            "sensors": [s.to_dict() for s in sensors],
            "processing": _clean_processing(entry.get("processing")),
        }

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "file": self.file,
            "description": self.description,
            "created": self.created,
            "updated": self.updated,
            "sensors": [s.to_dict() for s in self.sensors],
            "processing": self.processing,
            "markers": self.markers,
            "series": self.series,
            "join_series": self.join_series,
            "spectra_files": self.spectra_files,
            "spectra_common": self.spectra_common,
            "spectra_settings": self.spectra_settings,
            "evolution": self.evolution,
            "evolution_events": self.evolution_events,
            "source": self.source,
            "viz_sources": self.viz_sources,
            "channels": self.channels,
            "spectra": self.spectra,
            "style": self.style,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        if not isinstance(data, dict):
            raise ValueError("Projeto inválido.")
        return cls(
            name=data.get("name", ""),
            file=data.get("file", ""),
            description=str(data.get("description", "")),
            sensors=[Sensor.from_dict(s) for s in data.get("sensors", [])],
            processing=data.get("processing"),
            markers=data.get("markers") or [],
            series=data.get("series") or [],
            join_series=bool(data.get("join_series")),
            spectra_files=data.get("spectra_files") or [],
            spectra_common=data.get("spectra_common"),
            spectra_settings=data.get("spectra_settings"),
            evolution=data.get("evolution") or {},
            evolution_events=data.get("evolution_events") or [],
            source=str(data.get("source") or "series"),
            viz_sources=data.get("viz_sources") or {},
            channels=data.get("channels") or [],
            spectra=data.get("spectra") or [],
            style=data.get("style"),
            created=str(data.get("created", "")),
        )

    def summary(self) -> dict:
        """Dados curtos para listar os projetos sem carregar tudo."""
        return {
            "name": self.name,
            "file": self.file,
            "description": self.description,
            "updated": self.updated,
            "n_sensors": len(self.sensors),
            "n_markers": len(self.markers),
            "n_series": len(self.series),
            "n_spectra": len(self.spectra_files),
        }

    def save(self, path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
                        encoding="utf-8")

    @classmethod
    def load(cls, path) -> "Project":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        project = cls.from_dict(data)
        project.updated = str(data.get("updated", "")) or project.updated
        return project
