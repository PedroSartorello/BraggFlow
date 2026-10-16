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
(`data/projects/<name>.json`). Processed CSVs go to `data/processed/<project>/`, so two
projects never overwrite each other's results. Opening a project only shows the
saved state; "Processar ▶" (or automatic reprocessing) writes the CSV.

*Saving and undoing.* With "Salvar sozinho" on (the default, remembered in
this browser), the project saves itself about 2 s after each change; the
header says "alterações…", "salvando…" or "salvo às 14:03" (a failed save
shows "erro ao salvar", click to retry). Switching projects or closing the
page saves what is pending first, without asking. The project name is saved
when you leave the field or press Enter, not at each letter, since saving
under another name makes a copy. A project deleted while open is not saved
again by itself. With "Salvar sozinho" off, "Salvar" (Ctrl+S) saves and the app
asks before leaving a project with unsaved changes.

↶ / ↷ (Ctrl+Z, Ctrl+Shift+Z or Ctrl+Y outside text fields) undo and redo
changes to the project — files, steps, sensors, markers, figure style — up to
50 steps back to how it was when it was opened; changes less than half a
second apart (typing a value) count as one step, and the project name is not
part of it. Inside a text field, Ctrl+Z is the field's own undo.

## Tabs

**Séries temporais** — interrogator files. The sidebar follows the order of
the work: *1 · Arquivos*, *2 · Sensores* (names, allowed bands and K_T,
reusable as setups) and *3 · Etapas* (cleaning and sampling, filters and
conversion, each with its parameters). The plot shows the processed signal
over the raw one. Several files of one run can be joined in the "Concatenação"
card, which appears once the project has two or more files. Shortcuts:
Ctrl+Enter processes, Ctrl+S saves the project.

*Markers* (instants that split the run, used by the figure and the interval
statistics) are made on the plot with the *Marcar* tool: a click adds one, and
dragging a marker line changes its instant. With the other tools a click adds
nothing, so zooming never leaves stray markers. They are listed, with label
and colour, in the "Marcações" panel under the plot, where they can also be
typed in.

The toolbar above the plot chooses how to look at it (display only, the
processing does not change; the choice is remembered in this browser):

* *Canais separados* (default) — one panel per channel, each with its own y
  scale and the same time axis; *Mesmo gráfico* — all channels on one axis.
* *Relativo ao início* — each channel minus its first value.
* *Sinal bruto* — the signal before processing, underneath. The y scale follows
  the processed signal, so raw spikes do not flatten the curve.
* *Zoom* / *Medir trecho* / *Marcar* — what the mouse does. With *Medir trecho*, the
  dragged stretch gets, for every channel: mean, σ, min, max, peak to peak,
  drift (slope of a fitted line, per second), the value at the start and at
  the end (interpolated) and their difference. Computed on the whole
  processed signal, not on the decimated plot; "Copiar" puts the table on the
  clipboard for a spreadsheet; Esc clears it.

Plot shortcuts (outside text fields): 1 / 2 separate or same plot, D relative
to the start, B raw signal, M measure, A mark, Z zoom, Esc clear the
measurement.

**Temperature compensation** (last step of the Séries temporais pipeline) —
reference-grating method: each sensing FBG loses the thermal part measured by
the reference, `Δλ_comp = Δλ_s − (K_T,s/K_T,r)·Δλ_r`. Enter the thermal
sensitivity K_T (pm/°C) of every grating, the reference included, in the
Sensores card (it is saved with the setup and the project); a sensor without
K_T uses the "k padrão" of the step. It works on wavelength shifts, so turning
it on turns Δλ on too. The status details list the k used for each channel,
and the JSON records the K_T values.

**Espectros** — optical spectra (OSA, or spectrometers such as OceanView
exports with or without header). Each file has its own preparation, applied in
this order:

1. *Transmission (raw data)*, optional (the card stays closed, and says "não
   usada", until a source or a dark is chosen): choose the source spectrum R and/or
   the background (dark) D among the spectra of the project; the sample S
   becomes `T = (S − D)/(R − D)` (%, 0–1, dB or absorbance), `S/R` without
   dark, or `S − D` without source. Left empty, the spectrum is analysed as
   it is — raw counts, or transmission already computed by the spectrometer.
2. Wavelength window, smoothing (Savitzky-Golay or moving average).
3. *Remove trend*: subtracts a polynomial (degree 0–4) fitted to the window,
   so shallow valleys on a sloping baseline (LMR, SPR, fringes) stand out.
4. Normalisation and vertical offset.

Detection of maxima and minima with position (sub-sample), prominence, FWHM or
3-dB band, Q factor, centroid and spacing; results table with CSV export.

*Evolução entre arquivos* follows the valleys (or peaks) across the spectra of
the project, in acquisition order (header `Date:` or time in the file name),
each with its own preparation; source and dark files are left out. Two modes:
the most prominent valley of each file, or one track per valley of the first
file (each keeps the nearest valley of the next file, up to a maximum jump).
Plot λ, Δλ to the first file, intensity, depth or width against elapsed time or
file order; table and CSV with every value.

**Interval statistics** (Séries temporais, under the markers) — for every
channel of the processed signal on the plot: mean, deviation, extremes, drift,
noise and steady-state mean of each interval between markers, the difference
to the previous (or first) interval, and the step at each marker. Recomputed
when the markers, the processing or the "relative to the start" view change;
CSV export.

**Figura** — publication figures from processed CSVs or spectra. The sidebar
starts with what changes the figure the most, *Estilo e tamanho* (saved
style, size preset — IEEE, Elsevier, A4, slide —, font and base size), then
*Dados*, *Curvas*, *Figura* and *Marcações e eixos*. Each card shows a
summary in its title, so closed cards can be read without opening them; a
blue dot marks every option that differs from the loaded style (or the
default), the card title counts them, and "Restaurar este cartão" brings that
card back. The search box at the top filters the options by name or section
("fonte", "legenda", "tick"; Enter jumps to the first, Esc clears). "Ajustar à
tela" shows the whole figure; "Copiar figura" puts it on the clipboard as a PNG
(export resolution, up to 300 dpi) for slides and documents; "Baixar figura"
exports PDF/PNG/SVG/EPS/TIFF.

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
| `viz.js` | Figura tab: data sources, styles (changed options, card summaries, search), markers, figure, copy |
| `analysis.js` | interval statistics under the Séries temporais plot |
| `projects.js` | project screen, adding/removing files, save, open, delete, autosave, undo/redo history, unsaved-changes dialog |
| `tabs.js` | switching tabs |
| `main.js` | events that cross tabs (sidebar, keyboard shortcuts) and startup |

A variable that another module must **reassign** goes in `shared` (an
imported `let` is read-only for the importer). Keep `core.js` free of
imports: the other modules use `$` while loading. `API_BUILD` in `core.js`
must match the one in `app.py`.
