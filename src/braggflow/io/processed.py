"""
Processed-data file format.

A processed CSV has a ``Time [s]`` column followed by one column per channel,
each header carrying its unit (``EFBG1 [nm]``). An optional JSON sidecar with
the same stem (``file.json``) records how the data was produced.
"""

import json
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

_UNIT_RE = re.compile(r"^(.*?)\s*\[([^\]]*)\]\s*$")


def split_unit(column: str) -> Tuple[str, Optional[str]]:
    """``'EFBG1 [nm]'`` -> ``('EFBG1', 'nm')``; no brackets -> ``(name, None)``."""
    column = str(column).strip()
    match = _UNIT_RE.match(column)
    if not match:
        return column, None
    return match.group(1).strip(), match.group(2).strip() or None


def format_column(name: str, unit: Optional[str]) -> str:
    """Inverse of :func:`split_unit`."""
    return f"{name} [{unit}]" if unit else name


def metadata_path_for(csv_path) -> Path:
    """Path of the JSON sidecar that describes a processed CSV."""
    return Path(csv_path).with_suffix(".json")


def read_processed_header(path) -> Tuple[list, Dict[str, Optional[str]]]:
    """Channel names (without units) and their units, reading only the header."""
    header = pd.read_csv(path, nrows=0)
    names, units = [], {}
    for col in header.columns:
        name, unit = split_unit(col)
        names.append(name)
        units[name] = unit
    if "Time" not in names:
        raise ValueError(f"Column 'Time' not found in {Path(path).name}.")
    return [n for n in names if n != "Time"], {n: u for n, u in units.items() if n != "Time"}


def read_metadata(csv_path) -> Optional[dict]:
    """JSON sidecar of a processed CSV, or None when absent or unreadable."""
    path = metadata_path_for(csv_path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def read_processed_csv(path) -> Tuple[pd.DataFrame, Dict[str, Optional[str]], Optional[dict]]:
    """
    Loads a processed CSV (with or without units in the header).

    Returns
    -------
    df : DataFrame whose columns are the bare names (``Time``, ``EFBG1``...).
    units : dict mapping each channel name to its unit (None if unknown).
    metadata : the JSON sidecar content, or None.
    """
    df = pd.read_csv(path)
    names = [split_unit(c) for c in df.columns]
    df.columns = [name for name, _ in names]
    if "Time" not in df.columns:
        raise ValueError(f"Column 'Time' not found in {Path(path).name}.")
    units = {name: unit for name, unit in names if name != "Time"}
    return df, units, read_metadata(path)


def channel_quantities(metadata: Optional[dict]) -> Dict[str, str]:
    """Channel name -> physical quantity recorded in the sidecar (if any)."""
    if not metadata:
        return {}
    return {
        ch["name"]: ch.get("quantity")
        for ch in metadata.get("channels", [])
        if "name" in ch
    }
