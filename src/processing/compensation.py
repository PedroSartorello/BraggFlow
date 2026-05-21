import numpy as np
def temperature_compensation(signals: np.ndarray, temp_channel_idx: int, k_coeff: float = 1) -> np.ndarray:
    """
    Applies temperature compensation to the signal based on the provided temperature data and compensation factor.
    
    Parameters:
    - signals: 2D numpy array of shape (n_samples, n_channels) containing the signal data.
    - temp_channel_idx: The index of the channel containing the temperature data.
    - k_coeff: The compensation coefficient determining the impact of temperature on the signal.
    
    Returns:
    - A new array containing the temperature-compensated signal.
    """
    # Create a copy of the signals to avoid modifying the original data
    compensated_signals = np.copy(signals)
    
    # Extract the temperature signal from the specified channel
    temp_signal = signals[:, temp_channel_idx]
    
    # Apply the compensation to all channels except the temperature channel
    for target_channel_idx in range(signals.shape[1]):
        if target_channel_idx != temp_channel_idx:
            compensated_signals[:, target_channel_idx] -= (temp_signal * k_coeff)
    
    return compensated_signals