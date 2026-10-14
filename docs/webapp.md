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

## For developers

`braggflow.webapp.app.create_app(data_dir=None)` builds an app with its own
data folder and read caches (`braggflow.webapp.state`), so tests or two
instances never share them; `braggflow-web` calls it. The processing options
sent by the page are run by `braggflow.recipe.run_recipe`, the same function
behind `braggflow process`.

```python
from braggflow.webapp.app import create_app

app = create_app("/path/to/data")
client = app.test_client()
client.get("/api/files").get_json()
```

The page is `templates/index.html` (markup only), `static/css/app.css` and
the ES modules in `static/js/`, loaded straight by the browser — no Node, no
build step. `main.js` is the entry point; the modules are:

| Module | What |
|---|---|
| `core.js` | `$`, error bar, number formatting, the `fetch` wrapper and the server version check; imports nothing |
| `state.js` | files of the project and what each one keeps; `shared`, the variables read and changed by more than one module |
| `series.js` | Séries temporais tab: processing options, sensors, setups, file list, plot, processing (one, batch, joined), concatenation |
| `spectra.js` | Espectros tab: preparation, plot, peaks and valleys |
| `viz.js` | Visualização tab: data sources, styles, markers, figure |
| `analysis.js` | interval statistics |
| `projects.js` | project screen, adding/removing files, save, open, delete, unsaved-changes dialog |
| `tabs.js` | switching tabs |
| `main.js` | events that cross tabs (sidebar, keyboard shortcuts) and startup |

A variable that another module must **reassign** goes in `shared` (an
imported `let` is read-only for the importer). Keep `core.js` free of
imports: the other modules use `$` while loading. `API_BUILD` in `core.js`
must match the one in `app.py`.
