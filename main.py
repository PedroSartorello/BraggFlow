from src.pipeline import OpticalPipeline
from src.processing.filters import apply_savgol_filter
from src.visualization.plotter import plot_signals
from src.processing.normalization import to_delta_lambda
from src.processing.compensation import temperature_compensation

pipeline = OpticalPipeline("C:\\Users\\pedro\\Desktop\\Mestrado\\opticalPipeline\\data\\raw\\13_05_26_cloro_teste1a7.ASC")

# Processamento fluído e declarativo
(pipeline.load_data()
         .delimit_time_window(start_time=10.0, end_time=None)
         .apply_filter(apply_savgol_filter, window_length=11, polyorder=2)
         .apply_filter(to_delta_lambda, baseline_samples=100)
         .apply_filter(temperature_compensation, temp_channel_idx='CH_3 Sensor_1 [nm]', k_coeff=1)
         .save_processed_data("data/processed/13_05_26_cloro_teste1a7_processed.csv"))

# Extração
t, sig, ch = pipeline.get_data()

print("Time array shape:", t.shape)
print("Signals array shape:", sig.shape)
print("Channels:", ch)

plot_signals(t, sig, ch, title="Sinal do Canal 1")

