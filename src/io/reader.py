import pandas as pd 
import numpy as np
from typing import Tuple, List

def read_asc(ascfile):
    """
    Reads a .asc file and extracts the time and signal data.
    Parameters:
    - ascfile: str, path to the .asc file to be read.
    Returns:
    - time_array: numpy array containing the time data.
    - signals_array: numpy array containing the signal data from the CH columns.
    - ch_cols: list of column names corresponding to the CH columns.
    """
    # Read the .asc file using pandas
    try:
        df = pd.read_csv(ascfile,
                         sep=r'\t', 
                         decimal=',',
                         engine='python',
                         )
    except Exception as e:
        raise IOError(f"Error reading the .asc file: {e}")

    df.dropna(axis=1, how='all', inplace=True)  # Drop columns that are completely empty
    df.columns = df.columns.str.strip()         # Strip whitespace from column names

    ch_cols = [col for col in df.columns if col.startswith('CH')]
    if not ch_cols:
        raise ValueError("No columns starting with 'CH' found in the .asc file.")
    time_col = [col for col in df.columns if col.startswith('Time')]
    if not time_col:
        raise ValueError("No time column found in the .asc file.")
    
    time_col = time_col[0]                      # Assuming there's only one time column

    df.dropna(subset=[time_col], inplace=True)  # Drop rows where time column is NaN
    df = df[(df[ch_cols] != 0).any(axis=1)]     # Drop rows where all CH columns are zero

    time_array = df[time_col].to_numpy()
    signals_array = df[ch_cols].to_numpy()

    return time_array, signals_array, ch_cols
