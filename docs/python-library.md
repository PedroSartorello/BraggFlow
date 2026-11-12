# The Python library

BraggFlow loads optical interrogator exports — the Bragg peak wavelength of each channel over time (`.ASC`, `.txt` or `.csv`) — and applies a configurable sequence of signal processing steps — interrogator artefact cleaning, time-axis repair, null/outlier removal, filtering, delta-lambda conversion, and temperature compensation — through a fluent method-chaining interface. Every processed CSV carries units in its header and a JSON record of how it was produced. It also ships publication-ready plotting and a Flask web app for exploring the pipeline in the browser.

The web app is described in [`webapp.md`](webapp.md).

## Requirements

- Python ≥ 3.10
- numpy ≥ 1.24, pandas ≥ 2.0, scipy ≥ 1.10, matplotlib ≥ 3.7, plotly ≥ 5.0,
  flask ≥ 2.3 — installed automatically by `pip`
- pytest ≥ 7 for the tests (`pip install -e ".[dev]"`)
- A browser for the web app; its page loads Plotly from a CDN

## Installation

Follow the [quick start](../README.md#quick-start): it clones the
repository, creates a virtual environment in `.venv` and installs into it
with `.venv\Scripts\python -m pip install -e .` (Windows) or
`.venv/bin/python -m pip install -e .` (Linux, macOS); `-e ".[dev]"` adds
pytest. If a step fails, see
[Installation problems](webapp.md#installation-problems).

This installs the `braggflow` package and the `braggflow` and
`braggflow-web` commands. Run your scripts with the same Python
(`.venv\Scripts\python my_script.py`), or activate the environment first.
Installing from `requirements.txt` (`-r requirements.txt` in place of `-e .`)
gives the same plus the dev extra. Coming from an older checkout (imports of the old `src` package,
`python main.py`, `python webapp/app.py`)? See
[`docs/migration.md`](migration.md).

### Data folder

Inputs, uploads, results and the settings saved by the web app live in a data
folder: the `--data-dir` option, else the `BRAGGFLOW_DATA_DIR` environment
variable, else `./data` in the directory where you run the command. Its
subfolders (`raw/`, `uploads/`, `processed/`, `projects/`, `setups/`, `styles/`,
`figures/`) are created automatically and are **ignored by git** — see
[`data/README.md`](../data/README.md).

## Usage

```python
from braggflow import OpticalPipeline, Sensor, SensorSetup
from braggflow.processing import (
    mark_invalid_peaks,
    sort_and_deduplicate,
    resample_uniform,
    remove_null_values,
    remove_outliers,
    apply_savgol_filter,
    apply_moving_average_filter,
    to_delta_lambda,
    temperature_compensation,
)
from braggflow.visualization import plot_signals

# What is connected to each interrogator channel: name and allowed band (nm)
setup = SensorSetup(name="bench", sensors=[
    Sensor("CH_1 Sensor_1 [nm]", "EFBG1", band=(1548.0, 1552.0)),
    Sensor("CH_2 Sensor_1 [nm]", "EFBG2", band=(1543.0, 1547.0)),
    Sensor("CH_3 Sensor_1 [nm]", "FBG", band=(1538.0, 1542.0)),
])

pipeline = OpticalPipeline("data/raw/your_file.ASC")
pipeline.load_data().apply_setup(setup)

(pipeline
    .delimit_time_window(start_time=None, end_time=None)
    .preprocess(mark_invalid_peaks, bands=pipeline.sensor_bands(), jump_threshold=0.1)
    .preprocess(sort_and_deduplicate)
    .preprocess(resample_uniform, fs=None)
    .preprocess(remove_null_values, strategy="linear")
    .preprocess(remove_outliers, method="rolling", threshold=3.5, strategy="linear")
    .apply_filter(apply_savgol_filter, window_length=11, polyorder=2)
    .apply_filter(apply_moving_average_filter, window_size=30)
    .apply_filter(to_delta_lambda, baseline_samples=20)
    # K_T of each grating (pm/°C), in channel order; k = K_T,s / K_T,r
    .apply_filter(temperature_compensation, temp_channel_idx="FBG",
                  thermal_sensitivities=[12.4, 11.8, 10.1])
    .save_processed_data("data/processed/output.csv")   # + output.json
)

t, sig, ch = pipeline.get_data()
plot_signals(t, sig, ch, selected_channels=["EFBG1"], title="Channel Signal")
```

Two kinds of steps:

- `preprocess(func, ...)` — for steps that can add or remove rows (null/outlier
  removal); signature `func(time, signals, **kwargs) -> (time, signals)`.
- `apply_filter(func, ...)` — for steps that transform the signal only;
  signature `func(signals, **kwargs) -> signals`. Keyword arguments whose name
  contains `channel` may be passed as a channel name string and are resolved to
  the column index automatically.

### Command line

```bash
braggflow process data/raw/your_file.ASC [--setup data/setups/bench.json] [--out result.csv]
```

Saves one file as `<data dir>/processed/<name>_processado.csv` with its
JSON (time in seconds, one column per sensor, units in the header) and opens
one plot per channel (`--no-plot` to skip). `--time-unit ms|s|min|h` reads
the numbers of the time column in that unit when the header does not say it
(or says it wrong). No processing step is on, as in a
new project of the web app. Without `--setup`, each sensor is named after its
column without the unit (`CH_1 Sensor_1 [nm]` → `CH_1 Sensor_1`). A full chain
of steps (interrogator cleaning, time order, null and outlier removal,
Savitzky-Golay and moving average), written with the fluent API, is in
[`examples/01_process_file.py`](../examples/01_process_file.py).

### Input files

The full description of every format (interrogator exports, spectra, gas
event tables, processed CSV + JSON, sensor setups) is in
[`docs/data-formats.md`](data-formats.md). In short: format detection is
automatic, whatever the extension (`.ASC`, `.txt`, `.csv`,
`.dat`, `.tsv`, `.prn`…), and spectra recorded by catman in its binary format
(`.BIN`) are read too. For text files that means the encoding (UTF-8, UTF-8 with BOM, UTF-16 LE/BE,
Latin-1), separator (tab, `;`, `,` or whitespace), decimal mark, instrument
preamble lines and whether there is a header row at all.

Two kinds of content are recognised (`classify_file`):

* **Time series** — peak wavelength per channel over time, what the pipeline
  processes. The time column is the first named `Time…`, `Tempo…`,
  `Timestamp…` or `Date…` (seconds or absolute timestamps, converted to
  seconds since the first sample); channels are the columns starting with
  `CH`, otherwise every other numeric column. Values are kept as exported —
  lost peaks (`0`) are handled by `mark_invalid_peaks`.
* **Optical spectra** — intensity against wavelength. Both the wide layout
  (one wavelength column plus one column per trace) and the long layout of
  spectrum analysers (traces stacked with a label column such as `CH 1`,
  `Subset 2`) are read; empty traces are dropped and descending sweeps are
  reordered.

```python
from braggflow.io.reader import classify_file, describe_file, load_spectra

classify_file("data/raw/AR.dat")          # 'spectrum'
describe_file("data/raw/AR.dat")["format"]  # 'utf-16, separado por tabulação, decimal ...'
spectra = load_spectra("data/raw/AR.dat")
spectra.names                             # ['CH 1']
```

### Joining split measurements

A run recorded as several files (catman splits long acquisitions) can be
processed as one continuous signal: mark the files in the Séries temporais tab
and use the "Concatenação" card, which shows the order and where each file
starts and ends, and lets you reorder them. Each file continues where the
previous stopped, keeping the sampling step; when the exports carry absolute
timestamps, the real gap between acquisitions is preserved instead. The join
instants are reported in the status bar and stored in the JSON sidecar, and
the result is saved as `<primeiro>_juntos_processado.csv`.

```python
from braggflow.io.reader import concatenate, load_interrogator_file

joined, joins = concatenate([load_interrogator_file(p) for p in partes])
joins            # instantes em que um arquivo termina e o seguinte começa
```

### Interval statistics

Below the figure, the visualization tab computes statistics for the selected
curves using the time markers as interval boundaries:

* **per interval** — samples, duration, mean, standard deviation, median,
  minimum, maximum, peak-to-peak, linear drift (per second) with its error,
  noise (scatter around the fitted line), the steady-state mean over the last
  N seconds, and the amplitude difference against the previous or the first
  interval;
* **per marker** — the step at the transition: the mean over N seconds after
  minus the mean over the same N seconds before.

Everything follows the figure's own transformation (pm, Δ relative to the
start), so table and plot agree, and exports as CSV. The same functions are
available from Python:

```python
from braggflow.analysis import analyse_curve

result = analyse_curve(time, values, markers, settle_window=120, reference="previous")
result["intervals"][1]["delta"]      # degrau em relação ao patamar anterior
result["steps"][0]["step"]           # degrau na primeira marcação
```

### Projects

A project bundles one analysis under a name: the interrogator file, the
sensors and their bands, every processing step with its parameters, the time
markers, the channels in the figure and the figure style. Projects live in
`data/projects/*.json`; they save themselves a moment after each change (or
with "Salvar", if "Salvar sozinho" is off), changes can be undone and redone
(Ctrl+Z / Ctrl+Shift+Z), and the "Projetos…" screen opens, creates and deletes
them (the last one opened comes first). Each project keeps its processed CSVs
in `data/processed/<project>/`.

```python
from braggflow.projects import Project

project = Project.load("data/projects/Ensaio CO2.json")
print(project.file, project.markers, project.processing["outliers"])
```

### Sensor setups

A `SensorSetup` maps interrogator channels to named sensors with their nominal
wavelength and allowed band. Save it with `setup.save(path)` and reuse it with
`SensorSetup.load(path)`; the web app stores setups in `data/setups/`.

### Output format

`save_processed_data("x.csv")` writes a CSV whose header carries units
(`Time [s],EFBG1 [nm],...`) and a sidecar `x.json` with the source file
(name, size, SHA-256), absolute start time, sensor setup, sampling statistics,
the unit and quantity (`wavelength` or `wavelength_shift`) of each channel,
and every step applied with its parameters and invalid-sample counts.
`braggflow.io.processed.read_processed_csv` loads both back.

## Processing steps

| Function | Kind | Purpose |
| --- | --- | --- |
| `mark_invalid_peaks` | preprocess | Mark lost peaks (≤ 0), out-of-band readings and peak jumps as NaN |
| `sort_and_deduplicate` | preprocess | Put samples in time order and merge repeated timestamps |
| `resample_uniform` | preprocess | Interpolate onto a uniform time grid (optional maximum gap) |
| `remove_null_values` | preprocess | Drop or fill null samples |
| `remove_outliers` | preprocess | Local (rolling) MAD outlier detection and correction |
| `apply_savgol_filter` | filter | Savitzky–Golay smoothing |
| `apply_moving_average_filter` | filter | Centred (zero-lag) moving-average smoothing |
| `apply_lowpass_filter` / `apply_highpass_filter` | filter | Butterworth frequency filtering |
| `to_delta_lambda` | filter | Convert to wavelength shift relative to a baseline |
| `temperature_compensation` | filter | Reference-grating compensation, `Δλ_comp = Δλ_s − (K_T,s/K_T,r)·Δλ_r`, with the thermal sensitivity K_T of each FBG (or one ratio k); needs `to_delta_lambda` first |

## Publication figures

In the web app, the Figure tab draws **time series** (processed CSVs), **optical spectra**
(prepared in the Espectros tab) or the **evolution of a valley** between
spectra; pick one in "Source". Both
use the same style engine, which exposes every option of
`src/braggflow/visualization/figure.py`:
figure size (cm or in, with IEEE/Elsevier/A4/slide presets), font family and
sizes, layout (stacked panels or one axis), per-curve legend text, colour, line
style and marker, axis limits, labels, spines and grid, tick direction, length,
step, count, decimals and decimal comma, legend position (inside or outside),
columns and frame, time markers with shaded bands, and export format
(PDF, PNG, SVG, EPS, TIFF), resolution, transparency and margin cropping.
Without cropping the exported file has exactly the requested size. Styles are
saved as JSON in `data/styles/` and the preview updates as you edit.

The same styling works from Python:

```python
from braggflow.io.processed import read_processed_csv
from braggflow.visualization.figure import resolve_style, render_figure

df, units, meta = read_processed_csv("data/processed/output.csv")
style = resolve_style({"figure": {"width": 8.89, "height": 6.5, "font_size": 8},
                       "ticks": {"decimal_separator": ","},
                       "export": {"format": "pdf"}})
data, info = render_figure(df, units, {}, ["EFBG1", "FBG"], [], style)
open("figure.pdf", "wb").write(data)
```

## Examples

```bash
python examples/make_synthetic_data.py     # synthetic interrogator file, gas table, spectrum
python examples/01_process_file.py         # fluent API → data/processed/…_processado.csv + .json
python examples/02_publication_figure.py   # publication figure with the gas events marked
```

The synthetic interrogator file has two EFBGs and a reference FBG near
1550/1545/1540 nm with a common thermal drift, noise, lost peaks (`0`),
outliers and Δλ steps while CO2 flows.

## Project structure

```
BraggFlow/
  pyproject.toml           # Package metadata, dependencies, commands, pytest settings
  src/braggflow/
    __init__.py            # OpticalPipeline, Sensor, SensorSetup, __version__
    pipeline.py            # Fluent pipeline and provenance (JSON sidecar)
    recipe.py              # Processing recipe as options (shared by the CLI and the web app)
    cli.py                 # braggflow process / braggflow-web
    paths.py               # Data-folder resolution
    io/                    # Format detection, interrogator and spectrum readers, processed CSV
    processing/            # Cleaning, time base, filters, normalization, compensation, spectra
    visualization/         # Quick plots and styleable publication figures
    analysis.py            # Interval statistics driven by the markers
    sensors.py             # Sensor setups
    projects.py            # Saved projects (files + steps + markers + style)
    options.py             # Validation of options coming from the UI
    webapp/                # Flask app: app.py (create_app + routes), state.py,
                           #   templates/index.html, static/js/ (ES modules), static/css/
  examples/                # Runnable examples and synthetic data (examples/data/)
  docs/                    # python-library.md, webapp.md, data-formats.md, migration.md
  data/                    # Your data (ignored by git): raw/ uploads/ processed/ projects/ setups/ styles/ figures/
  tests/                   # Unit tests
```

## Running tests

```bash
python -m pip install -e ".[dev]"     # with the Python of .venv
python -m pytest
```

The browser tests in `tests/e2e/` (the web app driven in Chromium) run too
when Playwright is installed: `python -m pip install -e ".[e2e]"` and
`python -m playwright install chromium`.
