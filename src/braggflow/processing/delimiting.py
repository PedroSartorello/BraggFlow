import numpy as np
from typing import Tuple

from ..i18n import tr

def slice_time_window(time_array: np.ndarray, signals_array: np.ndarray, start_time: float = None, end_time: float = None) -> Tuple[np.ndarray, np.ndarray]:
    """
    Slices the time and signal arrays based on the specified start and end times.
    
    Parameters:
    - time_array: 1D numpy array containing the time data.
    - signals_array: 2D numpy array containing the signal data corresponding to the time data.
    - start_time: float, the starting time for slicing.
    - end_time: float, the ending time for slicing.
    
    Returns:
    - sliced_time_array: 1D numpy array containing the sliced time data.
    - sliced_signals_array: 2D numpy array containing the sliced signal data corresponding to the sliced time data.
    """
    # If start_time or end_time is not provided, use the min and max of the time_array
    if start_time is None:
        start_time = np.nanmin(time_array)
    if end_time is None:
        end_time = np.nanmax(time_array)
        
    if start_time >= end_time:
        raise ValueError(tr("lib.windowOrder"))
        
    # Create a boolean mask for the specified time window
    mask = (time_array >= start_time) & (time_array <= end_time)
    
    # Apply the mask to slice the time and signal arrays
    sliced_time_array = time_array[mask]
    sliced_signals_array = signals_array[mask]

    if len(sliced_time_array) == 0:
        raise ValueError(tr("lib.windowEmpty", start=f"{start_time:g}", end=f"{end_time:g}",
                            low=f"{np.nanmin(time_array):g}", high=f"{np.nanmax(time_array):g}"))
    
    return sliced_time_array, sliced_signals_array
