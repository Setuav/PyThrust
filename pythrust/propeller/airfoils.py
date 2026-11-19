"""The airfoils APC names in its propeller geometry files."""

from __future__ import annotations

from functools import lru_cache
from typing import Dict

from .polar import AirfoilPolar

# Kulfan (CST) parameters, 8 weights per side, fitted with setuav_neuralfoil.geometry to the
# coordinates in the UIUC Airfoil Coordinates Database (e63.dat, clarky.dat); NeuralFoil fits the
# same parameters to those coordinates itself.
_KULFAN = {
    "E63": {
        "upper_weights": (0.136310, 0.228128, 0.080441, 0.327311, 0.034266, 0.401917, 0.102548, 0.496576),
        "lower_weights": (-0.019579, 0.111248, -0.023875, 0.215112, -0.013155, 0.266035, 0.082548, 0.362868),
        "leading_edge_weight": -0.077701,
        "TE_thickness": 0.0,
    },
    "CLARK-Y": {
        "upper_weights": (0.111461, 0.111148, 0.354036, 0.115449, 0.360527, 0.169056, 0.275045, 0.231965),
        "lower_weights": (-0.210673, -0.242267, 0.085753, -0.183673, 0.050975, -0.102317, -0.014223, -0.044881),
        "leading_edge_weight": 0.561800,
        "TE_thickness": 0.001188,
    },
}


@lru_cache(maxsize=None)
def _apc_airfoil_polars(n_crit: float) -> Dict[str, AirfoilPolar]:
    from setuav_neuralfoil import geometry

    shapes = {name: geometry.get_kulfan_coordinates(**parameters) for name, parameters in _KULFAN.items()}
    shapes["APC12"] = geometry.naca("4412")  # APC's note in its files: "APC12 airfoil is equivalent to NACA 4412".
    return {
        name: AirfoilPolar.from_neuralfoil(shape, n_crit=n_crit, name=name)
        for name, shape in shapes.items()
    }


def apc_airfoil_polars(n_crit: float = 7.0) -> Dict[str, AirfoilPolar]:
    """Polars of the airfoils in APC geometry files: E63, APC12 (NACA 4412) and CLARK-Y.

    The result goes straight to ``read_apc_geometry(path, apc_airfoil_polars())``. The polars are
    computed with NeuralFoil once per ``n_crit`` and cached.
    """
    return dict(_apc_airfoil_polars(float(n_crit)))
