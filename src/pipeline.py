import numpy as np
from typing import Callable, Tuple, List, Optional
from .io.reader import read_asc
from .processing.filters import apply_savgol_filter
from .processing.delimiting import slice_time_window
from .processing.preprocessing import remove_null_values

class OpticalPipeline:
    def __init__(self, file_path: str):
        self.file_path = file_path

        # Initialize attributes to hold time and signal data
        self.time_array = None
        self.signals_array = None
        self.channels: Optional[List[str]] = None
        self.__is_loaded: bool = False

    def _check_loaded(self):
        if not self.__is_loaded:
            raise RuntimeError("Data must be loaded before performing this operation.")
        
    def load_data(self) -> 'OpticalPipeline':
        """
        Loads the data from the specified file path and initializes the time and signal arrays.
        
        Returns:
        - self: The instance of the OpticalPipeline with loaded data.
        """
        self.time_array, self.signals_array, self.channels = read_asc(self.file_path)
        self.__is_loaded = True
        return self
    
    def rename_channel(self, rename_map: dict) -> 'OpticalPipeline':
        """
        Renames a channel in the channels list.
        
        Parameters:
        - rename_map: dict, a dictionary mapping old channel names to new channel names.
        
        Returns:
        - self: The instance of the OpticalPipeline with the renamed channels.
        """
        self._check_loaded()
        for old_name, new_name in rename_map.items():
            if old_name in self.channels:
                idx = self.channels.index(old_name)
                self.channels[idx] = new_name
            else:
                raise ValueError(f"Channel '{old_name}' not found in channels list.")
        return self
    
    def delimit_time_window(self, start_time: float, end_time: float) -> 'OpticalPipeline':
        """
        Delimits the time and signal data based on the specified start and end times.
        
        Parameters:
        - start_time: float, the starting time for delimiting.
        - end_time: float, the ending time for delimiting.
        
        Returns:
        - self: The instance of the OpticalPipeline with delimited data.
        """
        self._check_loaded()
        self.time_array, self.signals_array = slice_time_window(self.time_array, self.signals_array, start_time, end_time)
        return self
    
    def preprocess(self, preprocess_func: Callable, **kwargs) -> 'OpticalPipeline':
        """
        Applies a preprocessing function that may modify both time and signal data.

        Use this for functions with the signature::

            func(time_array, signals_array, **kwargs) -> (time_array, signals_array)

        This is the correct method for ``remove_null_values`` and any other step
        that can add or remove rows (e.g. outlier removal).

        Parameters:
        - preprocess_func: Callable with signature (time, signals, **kwargs) -> (time, signals).

        Returns:
        - self: The instance of the OpticalPipeline with preprocessed data.
        """
        self._check_loaded()
        self.time_array, self.signals_array = preprocess_func(
            self.time_array, self.signals_array, **kwargs
        )
        return self

    def apply_filter(self, filter_func: Callable, **kwargs) -> 'OpticalPipeline':
        """
        Applies the specified filter function to the signal data only.

        Use this for functions with the signature::

            func(signals_array, **kwargs) -> signals_array

        Parameters:
        - filter_func: A callable that takes a 2D numpy array and returns a filtered 2D numpy array.

        Returns:
        - self: The instance of the OpticalPipeline with filtered data.
        """
        self._check_loaded()

        for key, value in kwargs.items():
            if isinstance(value, str) and value in self.channels:
                kwargs[key] = self.channels.index(value)

        self.signals_array = filter_func(self.signals_array, **kwargs)
        return self
    
    def get_data(self) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """
        Returns the time array, signals array, and channel names.
        """
        self._check_loaded()
        return self.time_array, self.signals_array, self.channels
    
    def save_processed_data(self, output_path: str) -> 'OpticalPipeline':
        """
        Saves the processed data to the specified output path.
        
        Parameters:
        - output_path: str, the file path where the processed data will be saved.
        """
        self._check_loaded()

        # Add time array as the first column to the signals array
        data_matrix = np.hstack((self.time_array.reshape(-1, 1), self.signals_array))
        # Save the data matrix to a CSV file with channel names as headers
        header = "Time," + ",".join(self.channels)
        np.savetxt(output_path, data_matrix, delimiter=",", header=header, comments='')
        
        return self
        
        