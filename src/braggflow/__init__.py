"""BraggFlow: processing and publication figures for FBG interrogator data."""

from .pipeline import OpticalPipeline
from .sensors import Sensor, SensorSetup

__version__ = "0.1.0"
__author__ = "Pedro Henrique Sartorello"

__all__ = ["OpticalPipeline", "Sensor", "SensorSetup", "__version__"]
