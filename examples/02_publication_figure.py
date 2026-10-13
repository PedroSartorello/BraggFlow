"""
Publication figure from the CSV written by ``01_process_file.py``, with the
gas events of the synthetic table marked on it. Uses the same style engine
as the Visualização tab of the web app.

    python examples/01_process_file.py
    python examples/02_publication_figure.py [processed.csv] [--gas events.csv] [--out figure.pdf]

Without arguments it uses the synthetic example and writes
``<data dir>/figures/synthetic_interrogator.pdf``.
"""

import argparse
from pathlib import Path

from braggflow.io.processed import channel_quantities, read_processed_csv
from braggflow.paths import resolve_data_dir
from braggflow.visualization.figure import parse_markers, render_figure, resolve_style
from braggflow.visualization.publication import load_gas_table

EXAMPLES = Path(__file__).resolve().parent
DATA_DIR = resolve_data_dir()

parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
parser.add_argument("csv", type=Path, nargs="?",
                    default=DATA_DIR / "processed" / "synthetic_interrogator_processado.csv",
                    help="processed CSV (default: the output of 01_process_file.py)")
parser.add_argument("--gas", type=Path, default=EXAMPLES / "data" / "synthetic_gas_events.csv",
                    help="gas event table (GAS, SM_INDEX, SEGUNDOS, ...); see docs/data-formats.md")
parser.add_argument("--out", type=Path, default=DATA_DIR / "figures" / "synthetic_interrogator.pdf")
args = parser.parse_args()

df, units, metadata = read_processed_csv(args.csv)
channels = [c for c in df.columns if c != "Time"]

# One marker per gas event, at the start time of the event
gas = load_gas_table(args.gas, df)
markers = parse_markers([{"time": row.SEGUNDOS, "label": row.GAS} for row in gas.itertuples()])

style = resolve_style({
    "figure": {"width": 8.89, "height": 9, "font_size": 8},      # IEEE single column
    "data": {"time_unit": "min"},
    "ticks": {"decimal_separator": "."},
    "export": {"format": args.out.suffix.lstrip(".") or "pdf"},
})
image, info = render_figure(df, units, channel_quantities(metadata), channels, markers, style)

args.out.parent.mkdir(parents=True, exist_ok=True)
args.out.write_bytes(image)
print(f"Saved {args.out} ({info['width_cm']} x {info['height_cm']} cm)")
