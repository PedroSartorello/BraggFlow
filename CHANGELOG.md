# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.0] — unreleased

First packaged version, organised so that other researchers can install it,
run an example in minutes and find where each part lives. The processing
itself did not change: the same input gives the same output as before.

### Breaking

- **The import package is now `braggflow` instead of `src`.** Every import
  of the old `src` package must name `braggflow` instead; see
  [`docs/migration.md`](docs/migration.md).
- The web app moved to `src/braggflow/webapp/` and starts with
  `braggflow-web` instead of `python webapp/app.py`.
- The data folder is `--data-dir`, `$BRAGGFLOW_DATA_DIR` or `./data` in the
  working directory (it used to be fixed at `<repository>/data`).

### Added

- `pyproject.toml`: installable with `pip install -e .`, Python ≥ 3.10,
  runtime dependencies with minimum versions, `dev` extra with pytest.
- Commands `braggflow process <file>` and `braggflow-web`.
- `braggflow.paths.resolve_data_dir` and the configurable data folder.
- Synthetic example data (`examples/make_synthetic_data.py`) and the examples
  `01_process_file.py` and `02_publication_figure.py`.
- `docs/data-formats.md`, `docs/webapp.md`, `docs/migration.md`,
  `CITATION.cff`, `CONTRIBUTING.md`, `data/README.md`.
- `braggflow` re-exports `Sensor` and `SensorSetup`.
- GitHub Actions (`.github/workflows/tests.yml`): pytest on Linux and Windows,
  Python 3.10–3.14, plus a run with the minimum dependency versions and the
  browser tests.
- Browser tests (`tests/e2e/`, Playwright): adding a file, processing, saving
  and reopening a project, switching projects, unsaved-changes dialog,
  spectrum peaks and the figure. Extra `e2e` in `pyproject.toml`.
- Thermal sensitivity K_T (pm/°C) of each FBG in the sensor setup
  (`Sensor.temp_sensitivity`, a column in the Sensores card). The temperature
  compensation uses `k = K_T,s / K_T,r` per sensor
  (`thermal_sensitivities=`), falling back to one `k_coeff`; the status
  details list the k of each channel. Old setups and projects load unchanged.
- Spectrometer spectra (OceanView/SpectraSuite, UV-VIS-NIR, with or without
  header): wavelengths from 150 to 2500 nm, header lines kept as metadata, and
  the acquisition time from the `Date:` header and/or the file name
  (`..._09-30-15-250`).
- Espectros tab: optional transmission from raw data (`T = (S − D)/(R − D)`,
  `to_transmission` / `apply_transmission`; or the raw spectrum as it is),
  trend removal (`remove_trend`), and the evolution of valleys or peaks across
  files (`spectra_evolution`, `/api/spectra/evolution`) with plot, table and
  CSV.
- Valley tracking for series of many spectra: a reference wavelength
  ("Marcar no gráfico" and a click on the valley, or typed) with a search
  window and "seguir a deriva" (`spectra_evolution(mode="reference")`); the
  valley position from a least-squares parabola fitted to the bottom
  (`analyse_spectrum` → `fit`, the default `locate` of the evolution), several
  times less noisy than the 3-point vertex on broad valleys; one preparation
  for every spectrum of the project (`Project.spectra_common`,
  `spectra_settings`); clicking a point of the evolution opens its spectrum,
  ◀ ▶ walk through them, and outliers can be left out of the evolution
  (`spectra_files[].exclude`). Evolution options are validated by
  `EVOLUTION_SPEC` and saved with the project (`Project.evolution`).
- Many spectra at once: "Importar pasta" and dropping a folder keep it as
  `data/uploads/<folder>/`; subfolders of `data/raw` and `data/uploads` are
  listed and offered as "adicionar todos"; `/api/upload` takes several files
  per request; adding files draws the list once and previews one file; the
  prepared spectra and their valleys are cached (`AppState.analyses`), and a
  file that cannot be read is skipped with a warning.
- Figura: the evolution of a valley between spectra as a third source
  (`source: "evolution"`, `evolution_labels`), with the y quantity and time
  unit.
- Events of the evolution (medium changes, injections): "Marcar evento" and a
  click on the evolution plot, drag to move, label/colour/time in a list
  under the plot and in the Figura *Dados* card. Stored by acquisition
  instant (`Project.evolution_events`, `parse_evolution_events`), returned
  with `elapsed_s` by `/api/spectra/evolution` (which now also gives `start`),
  drawn as the vertical lines of the evolution figure, and added to the
  table and CSV as an "Evento" column.
- Séries temporais plot: one panel per channel (default) or all on the same
  plot, values relative to the start, and the y scale follows the processed
  signal instead of the raw spikes. "Medir trecho": dragging a stretch gives
  mean, σ, extremes, drift, start/end values and their difference for every
  channel, on the full-resolution processed signal (`selection_statistics`,
  `/api/series/stats`, reusing the processing just shown). Keyboard shortcuts
  for the plot.
- Sidebar in the order of the work, numbered (1 · Arquivos, 2 · Sensores,
  3 · Etapas; in Espectros, 1 · Arquivos, 2 · Preparo, 3 · Picos e vales).
  "Concatenação" appears only with two or more files, and the raw-data
  transmission card stays closed while unused, showing what it uses.
- Markers moved from the sidebar to the plot: the *Marcar* tool (shortcut A)
  adds one per click and drags existing ones; the list is a panel under the
  plot. A click with the zoom or measure tool no longer adds a marker.
- Figura tab (formerly Visualização): "Estilo e tamanho" first (saved style,
  size preset, font), a summary in each card title, a dot on every option that
  differs from the loaded style or the default with a per-card "Restaurar",
  a search box for the options, "Ajustar à tela" that fits the whole figure
  (it fitted only the width), and "Copiar figura" (PNG to the clipboard).
- Interval statistics moved from the figure tab to Séries temporais, under the
  markers, computed on the processed signal shown on the plot
  (`/api/series/intervals`); they follow the markers and the processing.
- Projects save themselves ("Salvar sozinho", on by default) about 2 s after
  each change, with the state in the header; switching projects or closing
  the page saves what is pending instead of asking. Undo and redo (↶ ↷,
  Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y) walk through up to 50 states of the project
  since it was opened.
- Hide columns: "ocultar" in the Sensores card leaves an interrogator column
  out of everything, as if absent (`Sensor.hidden`, `OpticalPipeline.drop_channels`,
  applied first by `run_recipe`; recorded in the provenance). Saved with the
  setup and the project.
- `braggflow.recipe`: the processing recipe as a dict of options
  (`run_recipe`, `STANDARD_RECIPE`), shared by `braggflow process` and the web
  app.
- `braggflow.webapp.app.create_app(data_dir)`: each app has its own data folder
  and read caches (`braggflow.webapp.state`).

### Changed

- `main.py` became `examples/01_process_file.py`; without arguments it
  processes the synthetic example.
- `requirements.txt` is a shortcut for `-e .[dev]`.
- `braggflow process` runs `STANDARD_RECIPE` through `run_recipe` instead of
  its own copy of the steps. The CSV is byte for byte the same; the JSON no
  longer lists the empty time-window step and records `None` for the optional
  parameters, as the web app does.
- The page script and styles left `index.html`: ES modules in
  `webapp/static/js/` (no build step) and `webapp/static/css/app.css`. The
  code of each function is unchanged.
- `temperature_compensation` refuses absolute wavelengths (it declares
  `input_quantity = "wavelength_shift"`): apply `to_delta_lambda` first. Before,
  it accepted them and returned `λ_s − k·λ_r`, which carries the constant
  `λ_s0 − k·λ_r0`. In the web app, turning the compensation on turns Δλ on.
- The web app no longer keeps the data folder and caches in module globals;
  there is no module-level `app` (use `create_app`).
- `.gitignore` versions the synthetic example data and test fixtures, and keeps
  everything else under `data/` ignored.

### Removed

- Standalone scripts superseded by the web app: `mainPlot.py`,
  `mainPlotFluke.py`, `mainPlotVazao.py`, `scripts/plotarCSV.py`,
  `scripts/plotarCSV2.py`, `scripts/calcular_medias.py`,
  `scripts/media_ciclos.py`, `scripts/calcular_media_ciclos.py`, and the empty
  `notebooks/01_exploracao.ipynb`.
- The Gas Marker page (`gasMarker.html`), no longer used. The gas event table
  format it exported is still read by `load_gas_table`.

### Fixed

- Switching projects left the "Evolução entre arquivos" (and the peaks and
  valleys table) of the previous project on screen. They are cleared, and the
  evolution is recomputed for the open project, also when its files or their
  preparation change while the card is open.
- A spectrum preview still on its way when the project changed created a
  file named `null` in the new project, and the evolution then failed with
  "Arquivo inválido ou fora de data/: null" (the intermittent CI failure of
  `test_evolution_belongs_to_the_open_project`).
- Text files with blank lines in the equipment header were read from the wrong
  line (the header count skipped them, the reader did not).
- A one-field line just before the data (such as
  `>>>>>Begin Spectral Data<<<<<`) is no longer taken as the column names.

- The "Projetos…" screen no longer erases a project name typed while the
  project list is still loading.
