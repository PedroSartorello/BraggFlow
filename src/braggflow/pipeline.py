import json
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import numpy as np

from .io.processed import format_column, metadata_path_for
from .io.reader import InterrogatorData, file_fingerprint, load_interrogator_file
from .processing.delimiting import slice_time_window
from .sensors import SensorSetup


class OpticalPipeline:
    def __init__(self, file_path: str):
        self.file_path = file_path

        # Initialize attributes to hold time and signal data
        self.time_array = None
        self.signals_array = None
        self.channels: Optional[List[str]] = None
        self._is_loaded: bool = False

        # Provenance: original column names, units and physical quantity per
        # channel, the sensor setup and every step applied (see metadata()).
        self.source_channels: List[str] = []
        self.units: List[str] = []
        self.quantities: List[str] = []
        self.setup: Optional[SensorSetup] = None
        self.source = None            # dict, ou lista deles quando há junção
        self.joins: List[float] = []  # instantes das emendas entre arquivos
        self.time_origin: Optional[str] = None
        self.history: List[dict] = []

    def _check_loaded(self):
        if not self._is_loaded:
            raise RuntimeError("Data must be loaded before performing this operation.")

    def load_data(self) -> 'OpticalPipeline':
        """
        Loads the data from the specified file path and initializes the time and signal arrays.

        Returns:
        - self: The instance of the OpticalPipeline with loaded data.
        """
        data = load_interrogator_file(self.file_path)
        return self._set_data(data, file_fingerprint(self.file_path))

    @classmethod
    def from_data(cls, data: InterrogatorData, file_path: str = "",
                  source: Optional[dict] = None) -> 'OpticalPipeline':
        """
        Builds a loaded pipeline from data already in memory (e.g. a cached
        file). Arrays are copied, so the cached data is never modified.
        """
        pipeline = cls(file_path)
        return pipeline._set_data(data, source)

    def _set_data(self, data: InterrogatorData, source: Optional[dict]) -> 'OpticalPipeline':
        self.time_array = np.array(data.time, dtype=float)
        self.signals_array = np.array(data.signals, dtype=float)
        self.channels = list(data.channels)
        self.source_channels = list(data.channels)
        self.units = [u or "nm" for u in data.units]
        self.quantities = ["wavelength"] * len(self.channels)
        self.time_origin = data.time_origin
        self.source = source
        self.history = []
        self._is_loaded = True
        return self

    def apply_setup(self, setup: SensorSetup) -> 'OpticalPipeline':
        """
        Attaches a sensor setup: channels take the sensor names, and the
        sensor bands become available through ``sensor_bands()``.
        """
        self._check_loaded()
        names = setup.names(self.source_channels)
        duplicates = sorted({n for n in names if names.count(n) > 1})
        if duplicates:
            raise ValueError(f"Duplicate channel names in setup: {duplicates}.")
        self.setup = setup
        self.channels = names
        self._record("apply_setup", "setup", {"setup": setup.name}, None)
        return self

    def sensor_bands(self) -> List[Optional[Tuple[float, float]]]:
        """Allowed band of each channel from the attached setup (None if absent)."""
        self._check_loaded()
        if self.setup is None:
            return [None] * len(self.channels)
        return self.setup.bands(self.source_channels)

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
        self._record("rename_channel", "setup", {"rename_map": rename_map}, None)
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
        before = self._snapshot()
        self.time_array, self.signals_array = slice_time_window(self.time_array, self.signals_array, start_time, end_time)
        self._record("delimit_time_window", "window",
                     {"start_time": start_time, "end_time": end_time}, before)
        return self

    def preprocess(self, preprocess_func: Callable, **kwargs) -> 'OpticalPipeline':
        """
        Applies a preprocessing function that may modify both time and signal data.

        Use this for functions with the signature::

            func(time_array, signals_array, **kwargs) -> (time_array, signals_array)

        This is the correct method for ``remove_null_values`` and any other step
        that can add or remove rows (e.g. outlier removal, resampling).

        Parameters:
        - preprocess_func: Callable with signature (time, signals, **kwargs) -> (time, signals).

        Returns:
        - self: The instance of the OpticalPipeline with preprocessed data.
        """
        self._check_loaded()
        before = self._snapshot()
        self.time_array, self.signals_array = preprocess_func(
            self.time_array, self.signals_array, **kwargs
        )
        self._record(preprocess_func.__name__, "preprocess", kwargs, before)
        return self

    def apply_filter(self, filter_func: Callable, **kwargs) -> 'OpticalPipeline':
        """
        Applies the specified filter function to the signal data only.

        Use this for functions with the signature::

            func(signals_array, **kwargs) -> signals_array

        Keyword arguments whose name contains ``channel`` (e.g.
        ``temp_channel_idx``) may be given as a channel name string; it is
        resolved to the corresponding column index automatically. Other
        string kwargs are passed through unchanged, so option values like
        ``strategy='linear'`` can never collide with a channel name.

        A function may declare ``output_quantity`` (e.g. ``to_delta_lambda``
        produces a wavelength shift); it is recorded for every channel.

        Parameters:
        - filter_func: A callable that takes a 2D numpy array and returns a filtered 2D numpy array.

        Returns:
        - self: The instance of the OpticalPipeline with filtered data.
        """
        self._check_loaded()
        before = self._snapshot()
        recorded = dict(kwargs)

        for key, value in kwargs.items():
            if "channel" in key and isinstance(value, str):
                if value not in self.channels:
                    raise ValueError(
                        f"Channel '{value}' (kwarg '{key}') not found in "
                        f"channels list: {self.channels}"
                    )
                kwargs[key] = self.channels.index(value)

        self.signals_array = filter_func(self.signals_array, **kwargs)

        quantity = getattr(filter_func, "output_quantity", None)
        if quantity:
            self.quantities = [quantity] * len(self.channels)
        self._record(filter_func.__name__, "filter", recorded, before)
        return self

    def get_data(self) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """
        Returns the time array, signals array, and channel names.
        """
        self._check_loaded()
        return self.time_array, self.signals_array, self.channels

    # ── provenance ───────────────────────────────────────────────────────────

    def _snapshot(self) -> dict:
        return {
            "n_samples": int(len(self.time_array)),
            "nan": np.isnan(self.signals_array).sum(axis=0),
        }

    def _record(self, step: str, kind: str, params: dict,
                before: Optional[dict]) -> None:
        entry = {"step": step, "kind": kind, "params": _jsonable(params)}
        if before is not None:
            nan_after = np.isnan(self.signals_array).sum(axis=0)
            entry.update({
                "samples_before": before["n_samples"],
                "samples_after": int(len(self.time_array)),
                "nan_before": dict(zip(self.channels, before["nan"].tolist())),
                "nan_after": dict(zip(self.channels, nan_after.tolist())),
            })
        self.history.append(entry)

    def csv_header(self) -> str:
        """CSV header with units: ``Time [s],EFBG1 [nm],...``."""
        self._check_loaded()
        columns = [format_column("Time", "s")]
        columns += [format_column(ch, unit) for ch, unit in zip(self.channels, self.units)]
        return ",".join(columns)

    def metadata(self) -> dict:
        """Everything needed to trace how the current data was produced."""
        from . import __version__

        self._check_loaded()
        dt = np.diff(self.time_array)
        sampling = {"n_samples": int(len(self.time_array))}
        if len(dt) and np.all(np.isfinite(dt)):
            median = float(np.median(dt))
            sampling.update({
                "interval_median_s": median,
                "interval_max_s": float(dt.max()),
                "fs_estimated_hz": 1.0 / median if median > 0 else None,
                "uniform": bool(np.allclose(dt, median, rtol=1e-3, atol=1e-9)),
            })

        return {
            "software": {"name": "BraggFlow", "version": __version__},
            "created": datetime.now().isoformat(timespec="seconds"),
            "source": self.source or {"file": Path(str(self.file_path)).name},
            "joins": [float(t) for t in self.joins],
            "time_origin": self.time_origin,
            "setup": self.setup.to_dict() if self.setup else None,
            "sampling": sampling,
            "channels": [
                {"name": ch, "source_channel": src, "unit": unit, "quantity": qty}
                for ch, src, unit, qty in zip(
                    self.channels, self.source_channels, self.units, self.quantities)
            ],
            "steps": self.history,
        }

    def save_processed_data(self, output_path: str,
                            metadata_path: Optional[str] = "auto") -> 'OpticalPipeline':
        """
        Saves the processed data to the specified output path.

        Parameters:
        - output_path: str, the file path where the processed data will be saved.
        - metadata_path: where to write the JSON provenance record. ``'auto'``
          (default) uses the CSV path with a ``.json`` suffix; None skips it.
        """
        self._check_loaded()

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Add time array as the first column to the signals array
        data_matrix = np.hstack((self.time_array.reshape(-1, 1), self.signals_array))
        # Save the data matrix to a CSV file with channel names and units as headers
        np.savetxt(output_path, data_matrix, delimiter=",", header=self.csv_header(), comments='')

        if metadata_path == "auto":
            metadata_path = metadata_path_for(output_path)
        if metadata_path:
            Path(metadata_path).write_text(
                json.dumps(self.metadata(), indent=2, ensure_ascii=False), encoding="utf-8"
            )
        return self


def _jsonable(value):
    """Converts step parameters into JSON-serialisable values."""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist() if value.size <= 100 else f"<array {value.shape}>"
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return getattr(value, "__name__", repr(value))
