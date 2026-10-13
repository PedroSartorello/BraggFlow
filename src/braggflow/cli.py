"""
Command-line entry points.

``braggflow process <file> [--setup SETUP.json] [--out OUT.csv]``
    Processes one interrogator file with the standard recipe (the one of
    ``examples/01_process_file.py``) and saves the processed CSV plus its
    JSON provenance file.

``braggflow-web [--port 5000] [--data-dir DIR]``
    Starts the web app.
"""

import argparse
from pathlib import Path
from typing import List, Optional

from .paths import resolve_data_dir


def default_setup():
    """Three-channel setup used when no ``--setup`` is given."""
    from .sensors import Sensor, SensorSetup

    return SensorSetup(name="padrão", sensors=[
        Sensor("CH_1 Sensor_1 [nm]", "EFBG1"),
        Sensor("CH_2 Sensor_1 [nm]", "EFBG2"),
        Sensor("CH_3 Sensor_1 [nm]", "FBG"),
    ])


def process_file(path: Path, setup_path: Optional[Path] = None, out: Optional[Path] = None,
                 data_dir: Optional[Path] = None, plot: bool = True) -> Path:
    """
    Standard processing of one interrogator file; returns the CSV written.

    Without ``out`` the result goes to ``<data dir>/processed/<name>_processado.csv``.
    """
    from . import OpticalPipeline
    from .processing import (
        apply_moving_average_filter,
        apply_savgol_filter,
        mark_invalid_peaks,
        remove_null_values,
        remove_outliers,
        sort_and_deduplicate,
    )
    from .sensors import SensorSetup

    path = Path(path)
    setup = SensorSetup.load(setup_path) if setup_path else default_setup()
    if out is None:
        out = resolve_data_dir(data_dir) / "processed" / f"{path.stem}_processado.csv"

    pipeline = OpticalPipeline(path)
    pipeline.load_data().apply_setup(setup)
    (pipeline
     .delimit_time_window(start_time=None, end_time=None)
     .preprocess(mark_invalid_peaks, zero_as_missing=True, bands=pipeline.sensor_bands())
     .preprocess(sort_and_deduplicate, duplicates="mean")
     .preprocess(remove_null_values, strategy="linear")
     .preprocess(remove_outliers, method="rolling", threshold=3.5, window_size=51, strategy="linear")
     .apply_filter(apply_savgol_filter, window_length=11, polyorder=2)
     .apply_filter(apply_moving_average_filter, window_size=30)
     .save_processed_data(out))

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

    p = sub.add_parser("process", help="process one interrogator file")
    p.add_argument("file", type=Path, help="interrogator export (.asc, .txt, .csv, .dat, ...)")
    p.add_argument("--setup", type=Path, help="sensor setup JSON (saved by the web app)")
    p.add_argument("--out", type=Path, help="output CSV (default: <data dir>/processed/<name>_processado.csv)")
    p.add_argument("--data-dir", type=Path, help="data folder (default: $BRAGGFLOW_DATA_DIR or ./data)")
    p.add_argument("--no-plot", action="store_true", help="do not open the signal plots")

    args = parser.parse_args(argv)
    if args.command == "process":
        process_file(args.file, args.setup, args.out, args.data_dir, plot=not args.no_plot)


def web(argv: Optional[List[str]] = None) -> None:
    """``braggflow-web`` command."""
    from .webapp.app import main as run_app

    run_app(argv)
