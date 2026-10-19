"""
Sensor setup: what is connected to each interrogator channel.

A setup maps the channel columns of an interrogator export to named FBG
sensors, with their nominal Bragg wavelength, the spectral band each
grating is allowed to occupy and, optionally, its thermal sensitivity (used
by the temperature compensation). It is saved as JSON and reused across
acquisitions of the same experimental assembly.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass
class Sensor:
    channel: str                                 # column name in the interrogator file
    name: Optional[str] = None                   # display name (defaults to channel)
    nominal_wavelength: Optional[float] = None   # λ0 [nm]
    band: Optional[Tuple[float, float]] = None   # allowed peak range [nm]
    temp_sensitivity: Optional[float] = None     # K_T [pm/°C], from a temperature calibration
    hidden: bool = False                         # column left out of everything, as if absent

    def __post_init__(self):
        if self.nominal_wavelength in ("", None):
            self.nominal_wavelength = None
        else:
            self.nominal_wavelength = float(self.nominal_wavelength)

        if self.temp_sensitivity in ("", None):
            self.temp_sensitivity = None
        else:
            self.temp_sensitivity = float(self.temp_sensitivity)
            if not self.temp_sensitivity > 0:
                raise ValueError(
                    f"Sensor '{self.label}': thermal sensitivity K_T must be > 0 "
                    f"(got {self.temp_sensitivity})."
                )

        # Banda pela metade (um limite vazio) é o mesmo que não ter banda
        if self.band is not None and any(v in ("", None) for v in self.band):
            self.band = None
        if self.band is not None:
            low, high = (float(v) for v in self.band)
            if not low < high:
                raise ValueError(
                    f"Sensor '{self.label}': band minimum must be below maximum "
                    f"(got {low}, {high})."
                )
            self.band = (low, high)

    @property
    def label(self) -> str:
        return (self.name or "").strip() or self.channel

    def to_dict(self) -> dict:
        return {
            "channel": self.channel,
            "name": self.name,
            "nominal_wavelength": self.nominal_wavelength,
            "band": list(self.band) if self.band else None,
            "temp_sensitivity": self.temp_sensitivity,
            "hidden": self.hidden,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Sensor":
        band = data.get("band")
        if not isinstance(band, (list, tuple)) or len(band) != 2:
            band = None
        return cls(
            channel=data["channel"],
            name=data.get("name"),
            nominal_wavelength=data.get("nominal_wavelength"),
            band=tuple(band) if band else None,
            temp_sensitivity=data.get("temp_sensitivity"),
            hidden=bool(data.get("hidden", False)),
        )


@dataclass
class SensorSetup:
    name: str = ""
    sensors: List[Sensor] = field(default_factory=list)
    description: str = ""

    def get(self, channel: str) -> Optional[Sensor]:
        """Sensor attached to a file channel, or None."""
        return next((s for s in self.sensors if s.channel == channel), None)

    def names(self, channels: Sequence[str]) -> List[str]:
        """Display name for each file channel (the channel itself when unmapped)."""
        return [self.get(ch).label if self.get(ch) else ch for ch in channels]

    def bands(self, channels: Sequence[str]) -> List[Optional[Tuple[float, float]]]:
        """Allowed band for each file channel (None when not configured)."""
        return [self.get(ch).band if self.get(ch) else None for ch in channels]

    def hidden_channels(self, channels: Sequence[str]) -> List[str]:
        """File channels marked as hidden (left out of the processing)."""
        return [ch for ch in channels if self.get(ch) and self.get(ch).hidden]

    def temp_sensitivities(self, channels: Sequence[str]) -> List[Optional[float]]:
        """Thermal sensitivity K_T of each file channel (None when not configured)."""
        return [self.get(ch).temp_sensitivity if self.get(ch) else None for ch in channels]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "sensors": [s.to_dict() for s in self.sensors],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SensorSetup":
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            sensors=[Sensor.from_dict(s) for s in data.get("sensors", [])],
        )

    @classmethod
    def from_rename_map(cls, rename_map: Dict[str, str], name: str = "") -> "SensorSetup":
        """Setup with names only, from a ``{channel: name}`` mapping."""
        return cls(name=name, sensors=[Sensor(ch, new) for ch, new in rename_map.items()])

    def save(self, path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
                        encoding="utf-8")

    @classmethod
    def load(cls, path) -> "SensorSetup":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
