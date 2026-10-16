# Migration notes (from the "src" layout to 0.1.0)

Version 0.1.0 turns the repository into an installable package. The processing
itself did not change — the same input gives the same numbers — but imports,
commands and a few paths did.

## Install once

```bash
pip install -e .            # from the repository root; add ".[dev]" for pytest
```

`requirements.txt` now only points at the package (`-e .[dev]`), so
`pip install -r requirements.txt` still works.

## Imports

The package is now `braggflow`. Module names inside it did not change.

| Before | Now |
|---|---|
| `from src import OpticalPipeline` | `from braggflow import OpticalPipeline` |
| `from src.pipeline import OpticalPipeline` | `from braggflow.pipeline import OpticalPipeline` |
| `from src.sensors import Sensor, SensorSetup` | `from braggflow import Sensor, SensorSetup` (or `braggflow.sensors`) |
| `from src.processing import …` | `from braggflow.processing import …` |
| `from src.io.reader import …`, `src.io.processed` | `braggflow.io.reader`, `braggflow.io.processed` |
| `from src.visualization… import …` | `from braggflow.visualization… import …` |
| `from src.analysis`, `src.projects`, `src.options` | `braggflow.analysis`, `braggflow.projects`, `braggflow.options` |

A quick way to update your own scripts:

```bash
sed -i -E 's/\bfrom src\./from braggflow./; s/\bfrom src import/from braggflow import/' your_script.py
```

## Commands

| Before | Now |
|---|---|
| `python main.py data/raw/x.ASC [--setup s.json]` | `braggflow process data/raw/x.ASC [--setup s.json] [--out x.csv]` — or `python examples/01_process_file.py data/raw/x.ASC` |
| `python webapp/app.py [--port 5001]` | `braggflow-web [--port 5001] [--data-dir DIR]` |

## Paths

| Before | Now |
|---|---|
| `src/…` | `src/braggflow/…` |
| `webapp/app.py`, `webapp/templates/` | `src/braggflow/webapp/app.py`, `src/braggflow/webapp/templates/` |
| `main.py` | `examples/01_process_file.py` |
| data folder: always `<repository>/data` | `--data-dir`, else `$BRAGGFLOW_DATA_DIR`, else **`./data` in the directory where you run the command** |

**Watch the last line.** The web app used to find `data/` next to its own code;
now it uses the folder you run it from. Start `braggflow-web` from the
repository root (where your `data/` already is), or set
`BRAGGFLOW_DATA_DIR=/path/to/BraggFlow/data`, and your files, projects, setups
and styles show up as before. Paths saved inside projects
(`data/uploads/x.ASC`) keep working: `data/` is resolved against whatever
folder the app uses.

## Removed

These standalone scripts were removed (the author uses the web app, which
covers them).

| File | What it did |
|---|---|
| `mainPlot.py`, `mainPlotFluke.py`, `mainPlotVazao.py` | publication figures with gas-event bands; flow and Fluke temperature variants |
| `scripts/plotarCSV.py`, `scripts/plotarCSV2.py` | figure of one or more concatenated CSVs with gas events (the second added an uncompensated EFBG2 overlay) |
| `scripts/calcular_medias.py`, `scripts/media_ciclos.py`, `scripts/calcular_media_ciclos.py` | mean of the last N seconds of each gas cycle (now: interval statistics under the Séries temporais plot, `braggflow.analysis`) |
| `notebooks/01_exploracao.ipynb` | empty file |
| `gasMarker.html` | standalone page to click the gas changes on a processed CSV and export the event table; no longer used (the table format is still read, see [`data-formats.md`](data-formats.md#3-gas-event-table)) |
