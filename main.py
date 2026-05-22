import argparse
from pathlib import Path
from src import OpticalPipeline
from src.processing import apply_savgol_filter, to_delta_lambda, temperature_compensation
from src.visualization import plot_signals
from src.visualization import interactive_plot

# No cmd -> python main data/raw/arquivo.ASC
parser = argparse.ArgumentParser()
parser.add_argument('file', type=Path)
args = parser.parse_args()

pipeline = OpticalPipeline(args.file)

# Mapeamento para renomeação para canais
rename_map = {
    'CH_1 Sensor_1 [nm]': 'EFBG1',
    'CH_2 Sensor_1 [nm]': 'EFBG2',
    'CH_3 Sensor_1 [nm]': 'FBG',
}

# Processamento fluído e declarativo
(pipeline.load_data()
         .rename_channel(rename_map)
         .delimit_time_window(start_time=10.0, end_time=None)
         .apply_filter(apply_savgol_filter, window_length=11, polyorder=2)
         .apply_filter(to_delta_lambda, baseline_samples=100)
         .apply_filter(temperature_compensation, temp_channel_idx='FBG', k_coeff=1)
         .save_processed_data("data/processed/13_05_26_cloro_teste1a7_processed.csv")
         )

# Extração
t, sig, ch = pipeline.get_data()

print("Time array shape:", t.shape)
print("Signals array shape:", sig.shape)
print("Channels:", ch)

# Visualização estática
plot_signals(t, sig, ch, 
             selected_channels=['EFBG1', 'EFBG2'], 
             title="Sinal do Canal 1 e Canal 2")

# Abre uma janela interativa para explorar os dados
interactive_plot(t, sig, ch, 
             selected_channels=['EFBG1', 'EFBG2'], 
             title="Sinal do Canal 1 e Canal 2")