"""
Command-line entry points.

``braggflow process <file> [--setup SETUP.json] [--out OUT.csv]``
    Reads one interrogator file and saves it as a processed CSV (time in
    seconds, one column per sensor, units in the header) plus its JSON
    provenance file. No processing step is on, as in a new project of the
    web app; ``examples/01_process_file.py`` shows a full chain of steps
    written with the fluent API.

``braggflow-web [--port 5000] [--data-dir DIR]``
    Starts the web app.
"""

import argparse
from pathlib import Path
from typing import List, Optional

from .paths import resolve_data_dir


def process_file(path: Path, setup_path: Optional[Path] = None, out: Optional[Path] = None,
                 data_dir: Optional[Path] = None, plot: bool = True,
                 time_unit: Optional[str] = None) -> Path:
    """
    One interrogator file to a processed CSV; returns the CSV written.

    No step is on, as in a new project of the web app, and it goes through
    the same ``run_recipe``. Without ``setup_path`` each sensor is named after
    its column without the unit (``braggflow.sensors.channel_labels``).
    ``time_unit`` (``'ms'``, ``'s'``, ``'min'`` or ``'h'``) says how to read
    the numbers of the time column when the header does not say it right.
    Without ``out`` the result goes to
    ``<data dir>/processed/<name>_processado.csv``.
    """
    from .recipe import run_recipe
    from .sensors import SensorSetup

    path = Path(path)
    setup = SensorSetup.load(setup_path) if setup_path else SensorSetup()
    if out is None:
        out = resolve_data_dir(data_dir) / "processed" / f"{path.stem}_processado.csv"

    pipeline, _, messages = run_recipe([path], {"time_unit": time_unit}, setup=setup)
    for linha in messages["report"] + messages["warnings"]:
        print(linha)
    pipeline.save_processed_data(out)

    t, sig, ch = pipeline.get_data()
    print("Time array shape:", t.shape)
    print("Signals array shape:", sig.shape)
    print("Channels:", ch)
    print("Saved:", out)

    if plot:
        from .visualization import plot_signals

        for channel in ch:
            plot_signals(t, sig, ch, selected_channels=[channel], title=channel)
    return Path(out)


def main(argv: Optional[List[str]] = None) -> None:
    """``braggflow`` command."""
    from . import __version__

    parser = argparse.ArgumentParser(prog="braggflow", description="BraggFlow — FBG interrogator data")
    parser.add_argument("--version", action="version", version=f"braggflow {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("process", help="save one interrogator file as a processed CSV (no step on)")
    p.add_argument("file", type=Path, help="interrogator export (.asc, .txt, .csv, .dat, ...)")
    p.add_argument("--setup", type=Path, help="sensor setup JSON (saved by the web app)")
    p.add_argument("--out", type=Path, help="output CSV (default: <data dir>/processed/<name>_processado.csv)")
    p.add_argument("--data-dir", type=Path, help="data folder (default: $BRAGGFLOW_DATA_DIR or ./data)")
    p.add_argument("--no-plot", action="store_true", help="do not open the signal plots")
    p.add_argument("--time-unit", choices=["ms", "s", "min", "h"],
                   help="unit of the numbers in the time column (default: from the header, else s)")

    args = parser.parse_args(argv)
    if args.command == "process":
        process_file(args.file, args.setup, args.out, args.data_dir, plot=not args.no_plot,
                     time_unit=args.time_unit)


def web(argv: Optional[List[str]] = None) -> None:
    """``braggflow-web`` command."""
    from .webapp.app import main as run_app

    run_app(argv)
