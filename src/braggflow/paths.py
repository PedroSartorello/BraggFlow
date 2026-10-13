"""
Where BraggFlow keeps its data: raw interrogator files, uploads, processed
results and the settings saved by the web app.

The data folder is resolved in this order:

1. the ``data_dir`` argument (the ``--data-dir`` option of the commands);
2. the ``BRAGGFLOW_DATA_DIR`` environment variable;
3. ``./data`` in the current working directory.
"""

import os
from pathlib import Path
from typing import Optional, Union

ENV_VAR = "BRAGGFLOW_DATA_DIR"

#: Standard subfolders, created on demand.
SUBDIRS = ("raw", "uploads", "processed", "projects", "setups", "styles", "figures")


def resolve_data_dir(data_dir: Optional[Union[str, os.PathLike]] = None,
                     *, create: bool = True) -> Path:
    """
    Absolute path of the data folder (see the module docstring for the order).

    With ``create=True`` the folder and its standard subfolders are created
    when missing.
    """
    if data_dir:
        base = Path(data_dir)
    elif os.environ.get(ENV_VAR):
        base = Path(os.environ[ENV_VAR])
    else:
        base = Path.cwd() / "data"
    base = base.expanduser().resolve()
    if create:
        for sub in SUBDIRS:
            (base / sub).mkdir(parents=True, exist_ok=True)
    return base
