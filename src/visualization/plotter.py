import matplotlib.pyplot as plt
import numpy as np
from typing import List, Optional 
import plotly.graph_objects as go

def plot_signals(time_array: np.ndarray, 
                 signals_array: np.ndarray, 
                 channels: List[str], 
                 title: Optional[str] = None,
                 save_path: Optional[str] = None,
                 selected_channels: Optional[List[int]] = None) -> None:
    """
    Plots the signal data against time for each channel.
    
    Parameters:
    - time_array: 1D numpy array containing the time data.
    - signals_array: 2D numpy array containing the signal data corresponding to the time data.
    - channels: List of channel names corresponding to the columns in signals_array.
    - title: Optional string for the plot title.
    - save_path: Optional string for the file path to save the plot. If None, the plot will be displayed instead of saved.
    - selected_channels: Optional list of specific channel names to plot (e.g., ["CH_1", "CH_3"]). If None, all channels will be plotted.
    """
    plt.figure(figsize=(8, 5))
    plt.grid(True, linestyle='--', alpha=0.6)

    num_channels = signals_array.shape[1]
    for i in range(num_channels):
        if selected_channels is not None and channels[i] not in selected_channels:
            continue
        
        plt.plot(time_array,    
                 signals_array[:, i], 
                 label=channels[i],
                 linewidth=1.5,
                 alpha=0.8
                 )

    plt.xlabel("Time", fontsize=12)
    plt.ylabel("Signal", fontsize=12)
    plt.title(title, fontsize=14, fontweight='bold') if title else None
    plt.legend(loc='upper right', bbox_to_anchor=(1.15, 1))
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"Plot saved to: {save_path}")
    else:
        plt.show()

def interactive_plot(time_array: np.ndarray, 
                    signals_array: np.ndarray, 
                    channels: List[str], 
                    title: Optional[str] = None,
                    selected_channels: Optional[List[int]] = None) -> None:
    """
    Creates an interactive plot of the signal data against time for each channel.
    
    Parameters:
    - time_array: 1D numpy array containing the time data.
    - signals_array: 2D numpy array containing the signal data corresponding to the time data.
    - channels: List of channel names corresponding to the columns in signals_array.
    - title: Optional string for the plot title.
    - selected_channels: Optional list of specific channel names to plot (e.g., ["CH_1", "CH_3"]). If None, all channels will be plotted.
    """
    fig = go.Figure()
    num_channels = signals_array.shape[1]
    for i in range(num_channels):
        if selected_channels is not None and channels[i] not in selected_channels:
            continue
        fig.add_trace(go.Scatter(x=time_array, 
                                 y=signals_array[:, i], 
                                 mode='lines', 
                                 name=channels[i],
                                 line=dict(width=1.5)
                                 ))
    if title:
        fig.update_layout(title=title,
                          hovermode='x unified',
                          xaxis_title='Time')
    fig.show()