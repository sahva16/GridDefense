"""GridDefense — physics-aware detection, classification and localisation of false data
injection attacks on the IEEE 14-bus system.

The package re-implements the main pipeline of the final notebook
(notebook/GridDefense_Final.ipynb, Sections 1–10). The notebook remains the
reference: every number in the report comes from it.
"""
from . import config
from .data import generate_dataset, split_indices
from .features import add_physics_features, add_topo_features, AE_FEATURES, RF_FEATURES
from .pipeline import GridDefense

__all__ = ["config", "generate_dataset", "split_indices", "add_physics_features", "add_topo_features",
           "AE_FEATURES", "RF_FEATURES", "GridDefense"]
__version__ = "1.0.0"
