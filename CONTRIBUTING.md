# Contributing

Thanks for helping. BraggFlow is research software: correctness and
reproducibility come first, so every change to the processing comes with a
test.

## Set up the environment

Python 3.10 or newer.

```bash
git clone https://github.com/PedroSartorello/BraggFlow.git
cd BraggFlow
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
python examples/make_synthetic_data.py      # example data for a quick check
```

The editable install (`-e`) means your edits in `src/braggflow/` take effect
without reinstalling.

## Run the tests

```bash
pytest
```

`pytest` finds the tests in `tests/` (configured in `pyproject.toml`). Tests
that need data build it themselves or use small **synthetic** files; put any
new fixture under `tests/fixtures/` (versioned) and generate it with code.
**Never commit real measurements** — the repository is public and test data
may be confidential. Everything under `data/` is ignored by git for that
reason.

## Where things live

| Path | What |
|---|---|
| `src/braggflow/pipeline.py` | `OpticalPipeline`: loading, the fluent steps, provenance |
| `src/braggflow/processing/` | the processing functions (one module per family) |
| `src/braggflow/io/` | format detection, interrogator and spectrum readers, processed CSV |
| `src/braggflow/visualization/` | publication figures and quick plots |
| `src/braggflow/recipe.py` | the processing recipe as a dict of options, shared by `braggflow process` and the web app |
| `src/braggflow/webapp/` | the Flask app (`app.py`: `create_app` and routes; `state.py`: data folder and caches; `templates/`, `static/`) |
| `src/braggflow/cli.py`, `paths.py` | the commands and the data-folder resolution |
| `examples/` | runnable examples and the synthetic data generator |
| `docs/` | data formats, web app, migration notes |

## Add a processing step

A step is a plain function. Pick the kind by what it does to the samples.

**Signal only** (smoothing, conversion, compensation) — used with
`pipeline.apply_filter(func, **kwargs)`:

```python
def func(signals: np.ndarray, **kwargs) -> np.ndarray:
    """signals has shape (n_samples, n_channels); return the same shape."""
```

- Keyword arguments whose **name contains `channel`** may be passed as a
  channel name (`temp_channel_idx="FBG"`); the pipeline turns it into the
  column index before calling you.
- If the step changes the physical quantity, declare it:
  `func.output_quantity = "wavelength_shift"` (see `to_delta_lambda`). It is
  recorded for every channel in the JSON.

**Can add, remove or move samples** (cleaning, outliers, resampling) — used
with `pipeline.preprocess(func, **kwargs)`:

```python
def func(time: np.ndarray, signals: np.ndarray, **kwargs) -> tuple[np.ndarray, np.ndarray]:
    """Return the new time array and the matching signals array."""
```

Mark invalid readings as `NaN` rather than dropping them when you can; the
pipeline counts NaN per channel before and after each step.

Then:

1. Put the function in the right module of `src/braggflow/processing/` and
   export it from `src/braggflow/processing/__init__.py`.
2. Keep keyword arguments JSON-friendly (numbers, strings, lists): they are
   written as the step's `params` in the provenance JSON automatically.
3. Add tests in `tests/` with synthetic signals whose expected result you know
   (a sine below and above a cutoff, a step of known height, …).
4. Optionally expose it in the web app: add its option section to
   `run_recipe` in `src/braggflow/recipe.py` (used by the web app and by
   `braggflow process`) and its controls to
   `src/braggflow/webapp/templates/index.html`.
5. Add a line to the "Processing steps" table of the README and to
   `CHANGELOG.md`.

## Pull requests

- One topic per pull request, with a short description of the why.
- `pytest` must pass. Say in the description which data you used to check the
  change (synthetic, or real data you did **not** commit).
- Do not change the numbers produced by an existing step without saying so
  explicitly: published results may depend on them.
