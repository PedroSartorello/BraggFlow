# Web app

A browser front-end for the whole pipeline: import interrogator files and
spectra, process them, mark events, compute interval statistics and export
publication figures. It runs locally; nothing leaves your computer.

## Start it

```bash
braggflow-web                         # http://127.0.0.1:5000
braggflow-web --port 5001
braggflow-web --data-dir /path/to/my/data
```

The data folder is `--data-dir`, else `$BRAGGFLOW_DATA_DIR`, else `./data` in
the directory you start it from; the subfolders are created on start (see
[`data/README.md`](../data/README.md)). The server listens on `127.0.0.1` only
and has no login, so it is meant for your own machine. The page loads Plotly
from a CDN, so the first load needs internet access.

Quick try with the example data:

```bash
python examples/make_synthetic_data.py
braggflow-web
```

then, in the start screen, create a project and add
`examples/data/synthetic_interrogator.asc` with "Escolher no computador" (or
drop it on the page).

## Projects

A project keeps a whole analysis under a name: the files with their own sensors
and processing steps, the concatenation order, the time markers, the spectra
settings, the selected curves and the figure style
(`data/projects/<name>.json`). The app asks before leaving a project with
unsaved changes. Processed CSVs go to `data/processed/<project>/`, so two
projects never overwrite each other's results. Opening a project only shows the
saved state; "Processar ▶" (or automatic reprocessing) writes the CSV.

## Tabs

**Séries temporais** — interrogator files. For each file: sensor names and
allowed bands (reusable as setups), and the pipeline steps grouped as cleaning
and sampling, filters and conversion, each with its parameters. The plot shows
the processed signal over the raw one; click it to add a time marker. Several
files of one run can be joined in the "Concatenação" card, in the order shown
there. Shortcuts: Ctrl+Enter processes, Ctrl+S saves the project.

**Espectros** — optical spectra. Wavelength window, smoothing (Savitzky-Golay
or moving average), normalisation, vertical offset, and detection of maxima and
minima with position (sub-sample), prominence, FWHM or 3-dB band, Q factor,
centroid and spacing; results table with CSV export.

**Visualização** — publication figures from processed CSVs or spectra: size
presets (IEEE, Elsevier, A4, slide), fonts, stacked or overlaid curves, legend,
axes and ticks, marker bands, export to PDF/PNG/SVG/EPS/TIFF. Below the figure,
statistics per interval between markers (mean, deviation, drift, noise,
steady-state mean, steps).

## Gas Marker

`http://127.0.0.1:5000/static/gas_marker.html` is a standalone page: open a
processed CSV, click the instants where the gas changes and export the event
table (`GAS, SM_INDEX, SEGUNDOS, OBSERVACOES`). The format is described in
[`data-formats.md`](data-formats.md#3-gas-event-table). The page works offline
as a plain file too, but loads Plotly and PapaParse from a CDN.
