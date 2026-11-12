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
- Bilingual interface: Brazilian Portuguese (the default) and English, with a
  PT · EN switch at the end of the header and in the project dialog. The
  choice is kept in the browser (`localStorage`), `<html lang>` follows it,
  and switching redraws status lines, tables and plots without reloading or
  touching the project.
  - Every text of the page is in `static/js/strings.js`; the HTML marks its
    texts with `data-i18n*` attributes and the modules call `t()`
    (`static/js/i18n.js`).
  - Numbers follow the interface language (`1.550,25` or `1,550.25`),
    including the CSVs the page builds (statistics, peaks and valleys,
    evolution): `;` and decimal comma in Portuguese, `,` and decimal point in
    English.
  - Server messages (errors, warnings, the processing report, the names of
    evolution tracks) come back in the interface language: the page sends
    `Accept-Language` with every request, and `braggflow.i18n` keeps the
    messages in both languages (`tr`, `use_language`). Without the header,
    and in `braggflow process`, they stay in Portuguese.
  - Figures keep their own language setting (automatic labels and legends).
  - Tests: `tests/test_i18n.py` checks the dictionary and the server messages;
    browser tests switch to English and back, check that the choice survives
    a reload, and look for untranslated text on every tab.
- Spectra in the catman binary format (`.BIN`, HBM), as recorded from the
  FS22, open in the Espectros tab like the text exports:
  - the "Wavelength CH…" channel is the axis, and "Spectrum CH…" are the traces;
  - the acquisition time comes from the file.

  `braggflow.io.reader.read_catman_binary` reads the channels. Tests use
  synthetic `.BIN` files (`tests/catman_synthetic.py`).
- Savitzky-Golay window and order chosen from the data: a button under the
  filter fields in Séries temporais, and under the smoothing in Espectros,
  fills them by leave-one-out cross-validation
  (`braggflow.processing.filters.choose_savgol`; the filter is linear, so
  the error of leaving each sample out comes from one filtering per
  candidate). In Séries the note gives the −3 dB cut-off in Hz
  (`savgol_cutoff`). On synthetic signals the choice lands within 10% of the
  smallest error possible with the clean signal known.
- Three more techniques for the position of a peak or valley, in the peaks
  table and as "Posição" of the evolution: *ajuste gaussiano* and *ajuste
  lorentziano* (centre of the curve fitted to the region above the width
  level, as a weighted parabola through the logarithm or the inverse of the
  height, without iteration) and *centro da largura* (midpoint between the
  two crossings of the width level). `analyse_spectrum` returns `gaussian`,
  `lorentzian` and `midpoint` for each extremum, and `LOCATE_METHODS` lists
  the six choices of `spectra_evolution(locate=...)`.
- "?" in the title of the "Evolução entre arquivos" card: every field
  explained, with each position technique and when to use it.

### Changed

- Séries temporais: a new project starts with every step off. Cleaning, time
  axis, nulls, outliers, Savitzky-Golay and moving average used to come on,
  so the first plot was already filtered. The page has no predefined sensor
  names either. `CH_1`, `CH_2` and `CH_3` were called EFBG1, EFBG2 and FBG;
  now each sensor starts with its column name without the unit
  (`braggflow.sensors.channel_labels`), which is also the name of an unnamed
  channel in the processed CSV (`CH_1 Sensor_1 [nm]` instead of
  `CH_1 Sensor_1 [nm] [nm]`). A new project no longer inherits the steps of
  the project open before it. `braggflow process` keeps its standard recipe
  and names.
- "Evolução entre arquivos" is faster. On a series of thousands of spectra the
  first calculation takes about a third of the time, a recalculation (another
  mode, reference, window or position) is more than ten times faster, and
  changing the preparation no longer reads the files again. The results are
  the same, to rounding.
  - Each spectrum file is opened once instead of four times
    (`load_spectra`), and the spectra read stay in memory by size (256 MB,
    `SPECTRA_CACHE_BYTES`); spectra with the same wavelength axis share one
    copy of it.
  - Savitzky-Golay smoothing of a spectrum is one convolution with cached
    coefficients (`savgol_smooth`, equal to `scipy.signal.savgol_filter` to
    rounding), and the parabola fits are solved in closed form.
  - "todos os do 1º arquivo" matches the valleys of consecutive files with
    arrays instead of sorting every pair.
  - In the page, stepping through the spectra moves the ring on the plot
    instead of redrawing it, the table is only built when open, and the file
    lists are rebuilt only when the files change.
- Interface review (Impeccable critique, 25/40): the visual system stays
  ("A Bancada Organizada", recorded in `DESIGN.md`) and its weak points are
  fixed:
  - Text keeps its case: table headers and labels no longer turn λ, nm and σ
    into Λ, NM and Σ.
  - Functional text is at least 11.5px, and hints and labels are 12px. Faded
    text reaches 5:1 contrast, field borders reach 3:1, and figures are
    tabular.
  - A value the processing would refuse is marked at its field, with the
    reason under it, before any request. Examples are an even Savitzky-Golay
    window or a search window ≤ 0. The status names the field, and the plot
    keeps its last result with a "Desatualizado" badge instead of being
    blanked. The server explains a bad Savitzky-Golay window in Portuguese,
    naming the step.
  - The error notice sits fixed under the header, can be closed, and is
    announced to screen readers. A failed autosave says why.
  - The project screen is a real dialog that keeps focus, and the tabs follow
    the ARIA tab pattern with arrow keys. Step switches and the fields in
    sensor, marker and curve rows have accessible names, and keyboard focus is
    visible everywhere.
  - Shortcuts are shown where they act, as key caps. In Espectros, ← and →
    step through the spectra.
  - Evolution card:
    - the plot follows its container's width;
    - the selects are no longer cut;
    - controls are grouped into "Acompanhar" and "Mostrar", with one primary
      action.
  - "Gravar o CSV a cada mudança" names what the toggle does. Séries imports
    files with a button instead of the browser's native file control.
  - Automatic legends of the evolution figure follow the figure's language.
  - Narrow windows and 200% zoom stack the sidebar above the work area, and
    reduced motion is respected.
- Visual pass on the same system:
  - The sidebar is one surface divided by hairlines instead of a stack of
    boxed cards, and its section labels are larger (15px).
  - The header reads "BraggFlow / project name · Projetos", with the tabs in
    the centre and undo, redo and save as icon buttons.
  - Text glyphs (▶ ↶ ⭳ ×) gave way to a drawn icon set, one stroke weight.
  - The status bar reads like an instrument: values with their unit, and the
    CSV's state ("CSV salvo", "CSV ainda não gravado") in a pill.
  - Long hints fold into "Como funciona" disclosures, and the Plotly toolbar
    is hidden, since the plot tools already sit above each plot.
- The README is a short product page:
  - logo, advantages, screenshots, the library in brief, contributing,
    security and licence;
  - the screenshots show the English interface and use synthetic data
    (`docs/images/`).
  The full library guide moved to `docs/python-library.md`, and
  `SECURITY.md` says how to report a vulnerability.

- `main.py` became `examples/01_process_file.py`; without arguments it
  processes the synthetic example.
- `requirements.txt` is a shortcut for `-e .[dev]`.
- `braggflow process` runs `STANDARD_RECIPE` through `run_recipe` instead of
  its own copy of the steps. The CSV is byte for byte the same; the JSON no
  longer lists the empty time-window step and records `None` for the optional
  parameters, as the web app does.
- `API_BUILD` is `2026-11-03`: the page sends its language and expects the
  messages in it, so an older server asks to be restarted.
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

- The quick start in the README failed on other computers. It is now one
  block for Windows and one for Linux and macOS, run line by line, that
  creates `.venv` and calls its Python directly, so it no longer depends on:
  - `&&`, which Windows PowerShell 5.1 does not accept;
  - `python` on Windows, often only the Microsoft Store shortcut (`py` instead),
    or on Linux and macOS, where it is `python3`;
  - activating the environment, which PowerShell blocks by default;
  - `pip` outside a virtual environment, refused by recent Linux and Homebrew
    (`externally-managed-environment`);
  - `braggflow-web.exe`, which Smart App Control blocks on Windows 11
    (`python -m braggflow.webapp.app` instead).
  `docs/webapp.md` gained "Installation problems", with each usual message
  and what to do; CONTRIBUTING and the library guide follow the same steps.
- The web app opens the browser when it starts (`--no-browser` to skip) and,
  without `--port`, takes the next free port when 5000 is taken, as by the
  AirPlay receiver on macOS (`choose_port`).

- Markers could only be added in the Séries temporais tab. The marker list now
  also appears in the "Marcações e eixos" card of the Figura tab, for series
  and spectra figures: add, change or remove a marker there and the figure,
  the Séries plot, the statistics and the project follow. It is the same list,
  moved to the open tab.

- Joined files only worked as one signal for the "Processar juntos" click:
  any later change (a filter, a sensor) reprocessed the first file alone and
  was saved only in it. While the "Concatenação" card is open, the checked
  files are now one signal for every processing (steps, "Processar", CSV
  download, measurements, statistics, automatic Savitzky-Golay); the
  settings on screen are saved in all of them, and opening or closing the
  card switches between the join and the single file.

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
- Fixes from the code review (`/ponytail-audit`):
  - A new project, or a renamed one, with the name of an existing project
    replaced it at the first autosave. The page now sends the creation date of
    the open project, and the server only replaces the file with that date
    (409 otherwise). The project screen refuses the name before that. A copy
    made by renaming gets its own date, and the date is kept to the
    microsecond, so it identifies the project. Undo and redo leave the date
    alone.
  - Uploading a file with the name of one already in `data/uploads/` replaced
    it. A file with other content now goes in as `nome (2).ext`; the same
    file again is reused.
  - With null removal off, one lost reading made the moving average blank
    the rest of the channel (915 of 1000 samples in the test). Missing
    samples now stay where they are and leave their neighbours' windows.
  - The server answers only its own page: requests with another `Host` (DNS
    rebinding) or, for uploads and changes, another `Origin` are refused (403).
  - Two files with the same name in different folders wrote the same
    processed CSV. A file in a subfolder now gets the folder in the name
    (`dia1__ensaio_processado.csv`, or `raw__dia1__…` for a subfolder of
    `data/raw`, so it does not meet the same folder sent through the page);
    files at the root keep their name. A result already processed from a
    subfolder under the old name shows again after processing it once more.
  - Processing requests in the Séries tab run one at a time, in order. Before,
    clicking a long file and then another could draw the first one's answer
    last, with the second file selected, and the CSV on disk could end up
    with the older options.
  - Projects, sensor setups and figure styles are written to a temporary file
    and then put in place, so an interrupted save no longer leaves half a JSON.
  - The last interval of the statistics left out the last sample.
  - The evolution figure called raw spectra in dB (catman, OSA) "Transmissão
    (dB)"; it now says "Intensidade (dB)".
  - The spectra cache is limited by points (8 million, about 128 MB) instead
    of by files, so hundreds of catman `.BIN` files (32,768 points each) do
    not take half a gigabyte.
  - "Baixar CSV" reuses the last processing instead of running it again, and
    shares the CSV writer with `save_processed_data`
    (`braggflow.io.processed.write_processed_csv`).
  - The unused `processing.filters.detrend_signal` was removed.
