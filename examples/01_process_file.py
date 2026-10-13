import argparse
from pathlib import Path
from braggflow import OpticalPipeline
from braggflow.processing import apply_savgol_filter, to_delta_lambda, temperature_compensation, apply_moving_average_filter
from braggflow.processing import mark_invalid_peaks, sort_and_deduplicate, resample_uniform
from braggflow.processing import remove_null_values, remove_outliers
from braggflow.sensors import Sensor, SensorSetup
from braggflow.visualization import plot_signals
from braggflow.visualization import interactive_plot
from braggflow.paths import resolve_data_dir

# Arquivo sintético gerado por examples/make_synthetic_data.py
EXAMPLE_FILE = Path(__file__).resolve().parent / "data" / "synthetic_interrogator.asc"

# No cmd -> python examples/01_process_file.py [data/raw/arquivo.ASC] [--setup data/setups/montagem.json]
# Sem arquivo, processa o exemplo sintético. O resultado vai para a pasta de
# dados (--data-dir do braggflow, $BRAGGFLOW_DATA_DIR ou ./data).
parser = argparse.ArgumentParser()
parser.add_argument('file', type=Path, nargs='?', default=EXAMPLE_FILE)
parser.add_argument('--setup', type=Path, help='Setup de sensores (JSON salvo pelo web app)')
args = parser.parse_args()

# Setup de sensores: nome e banda permitida (nm) de cada canal do interrogador
if args.setup:
    setup = SensorSetup.load(args.setup)
else:
    setup = SensorSetup(name='padrão', sensors=[
        Sensor('CH_1 Sensor_1 [nm]', 'EFBG1'),
        Sensor('CH_2 Sensor_1 [nm]', 'EFBG2'),
        Sensor('CH_3 Sensor_1 [nm]', 'FBG'),
    ])

pipeline = OpticalPipeline(args.file)
pipeline.load_data().apply_setup(setup)

# Processamento fluído e declarativo
(pipeline
         .delimit_time_window(start_time=None, end_time=None)
         .preprocess(mark_invalid_peaks, zero_as_missing=True, bands=pipeline.sensor_bands())
         .preprocess(sort_and_deduplicate, duplicates='mean')
         #.preprocess(resample_uniform, fs=None)
         .preprocess(remove_null_values, strategy='linear')
         .preprocess(remove_outliers, method='rolling', threshold=3.5, window_size=51, strategy='linear')
         .apply_filter(apply_savgol_filter, window_length=11, polyorder=2)
         .apply_filter(apply_moving_average_filter, window_size=30)
         #.apply_filter(to_delta_lambda, baseline_samples=20)
         #.apply_filter(temperature_compensation, temp_channel_idx='FBG', k_coeff=1)
         .save_processed_data(resolve_data_dir() / "processed" / f"{args.file.stem}_processado.csv")
         )

# Extração
t, sig, ch = pipeline.get_data()

print("Time array shape:", t.shape)
print("Signals array shape:", sig.shape)
print("Channels:", ch)

# Visualização estática
plot_signals(t, sig, ch,
             selected_channels=['EFBG1'],
             title="Sinal do Canal 1")

plot_signals(t, sig, ch,
             selected_channels=['EFBG2'])
plot_signals(t, sig, ch,
             selected_channels=['FBG'])

#Abre uma janela interativa para explorar os dados
# interactive_plot(t, sig, ch,
#              selected_channels=['EFBG1', 'EFBG2', 'FBG'],
#              title="Sinal do Canal 1, 2 e 3")
