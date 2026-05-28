import argparse
from pathlib import Path
from src import OpticalPipeline
from src.processing import apply_savgol_filter, to_delta_lambda, temperature_compensation, apply_moving_average_filter
from src.visualization import plot_signals
from src.visualization import interactive_plot
from src.processing import remove_null_values, remove_outliers

# No cmd -> python main.py data/raw/arquivo.ASC
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
         .delimit_time_window(start_time=0.0, end_time=6800)
         .preprocess(remove_null_values, strategy='remove')   # ← retira linhas com NaN/Inf
         .preprocess(remove_outliers, method='mad', threshold=3.5, strategy='linear')
         .apply_filter(apply_moving_average_filter, window_size=300)
         .apply_filter(to_delta_lambda, baseline_samples=100)
         .apply_filter(temperature_compensation, temp_channel_idx='FBG', k_coeff=1)
         .save_processed_data("data/processed/co2_processed.csv")
         )

# Extração
t, sig, ch = pipeline.get_data()

print("Time array shape:", t.shape)
print("Signals array shape:", sig.shape)
print("Channels:", ch)

# Visualização estática
plot_signals(t, sig, ch, 
             selected_channels=['EFBG1', 'EFBG2', 'FBG'], 
             title="Sinal do Canal 1, 2 e 3")

# Abre uma janela interativa para explorar os dados
# interactive_plot(t, sig, ch, 
#              selected_channels=['EFBG1', 'EFBG2', 'FBG'], 
#              title="Sinal do Canal 1, 2 e 3")