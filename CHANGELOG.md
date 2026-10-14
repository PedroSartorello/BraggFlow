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
  Python 3.10–3.14, plus a run with the minimum dependency versions.
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
