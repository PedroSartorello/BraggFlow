# BraggFlow

A declarative Python pipeline for processing Fiber Bragg Grating (FBG) optical sensor data. Designed to be readable, chainable, and easy to extend.

## What it does

BraggFlow loads raw spectrometer data (`.ASC` files) and applies a configurable sequence of signal processing steps — filtering, normalization, delta-lambda conversion, and temperature compensation — through a fluent method-chaining interface.

## Installation

```bash
git clone https://github.com/PedroSartorello/BraggFlow.git
cd BraggFlow
pip install -r requirements.txt
```

Dependencies: `numpy`, `pandas`, `scipy`.

## Usage

```python
from src.pipeline import OpticalPipeline
from src.processing import apply_savgol_filter, to_delta_lambda, temperature_compensation
from src.visualization import plot_signals

pipeline = OpticalPipeline("data/raw/your_file.ASC")

(pipeline.load_data()
    .delimit_time_window(start_time=10.0, end_time=None)
    .apply_filter(apply_savgol_filter, window_length=11, polyorder=2)
    .apply_filter(to_delta_lambda, baseline_samples=100)
    .apply_filter(temperature_compensation, temp_channel_idx='CH_3 Sensor_1 [nm]', k_coeff=1)
    .save_processed_data("data/processed/output.csv")
)

t, sig, ch = pipeline.get_data()
plot_signals(t, sig, ch, title="Channel Signal")
```

## Project structure

```
BraggFlow/
  src/          # Pipeline, processing, and visualization modules
  notebooks/    # Exploratory notebooks
  tests/        # Unit tests
  main.py       # Example entry point
```

## Running tests

```bash
pytest tests/
```

## License

MIT