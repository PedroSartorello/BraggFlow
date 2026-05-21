import argparse
from pathlib import Path
from src import OpticalPipeline
from src.processing import apply_savgol_filter, to_delta_lambda, temperature_compensation
from src.visualization import plot_signals

parser = argparse.ArgumentParser(description="Processamento de dados ópticos")
parser.add_argument('file', type=Path)
args = parser.parse_args()

pipeline = OpticalPipeline(args.file)

# Processamento fluído e declarativo
(pipeline.load_data()
         .delimit_time_window(start_time=10.0, end_time=None)
         .apply_filter(apply_savgol_filter, window_length=11, polyorder=2)
         .apply_filter(to_delta_lambda, baseline_samples=100)
         .apply_filter(temperature_compensation, temp_channel_idx='CH_3 Sensor_1 [nm]', k_coeff=1)
         .save_processed_data("data/processed/13_05_26_cloro_teste1a7_processed.csv")
         )

# Extração
t, sig, ch = pipeline.get_data()

print("Time array shape:", t.shape)
print("Signals array shape:", sig.shape)
print("Channels:", ch)

plot_signals(t, sig, ch, 
             selected_channels=['CH_1 Sensor_1 [nm]', 'CH_2 Sensor_1 [nm]'], 
             title="Sinal do Canal 1 e Canal 2")