import json
import math
from pathlib import Path

import numpy as np
import pytest

from pythrust.propeller import BladeSection
from pythrust.propeller.bem import solve_stations

RHO, MU, SPEED_OF_SOUND = 1.225, 1.78e-5, 340.0
REFERENCE = json.loads((Path(__file__).parent / "data" / "qprop_stations.json").read_text())


def _stations(prop, count=25):
    """QPROP's analysis stations: midpoints of equal intervals from root to tip.

    The reference blades have linear chord and blade angle, so the stations'
    geometry is known exactly whatever spline QPROP fits through it.
    """
    edges = np.linspace(prop["root_m"], prop["tip_m"], count + 1)
    r = 0.5 * (edges[:-1] + edges[1:])
    t = (r - prop["root_m"]) / (prop["tip_m"] - prop["root_m"])
    chord = prop["chord_m"][0] + t * (prop["chord_m"][1] - prop["chord_m"][0])
    beta = np.radians(prop["blade_angle_deg"][0] + t * (prop["blade_angle_deg"][1] - prop["blade_angle_deg"][0]))
    return r, chord, beta


def _solve(prop, r, chord, beta, airspeed_mps, rpm, section=None):
    section = section or BladeSection(*prop["section"])
    return solve_stations(
        prop["blade_count"], prop["radius_m"], r, chord, beta, [section] * len(r),
        airspeed_mps, rpm * math.pi / 30.0, RHO, MU, SPEED_OF_SOUND,
    )


@pytest.mark.parametrize(
    "case", REFERENCE["cases"], ids=lambda c: f"{c['propeller']}-V{c['airspeed_mps']}-rpm{c['rpm']}"
)
def test_matches_qprop_station_output(case):
    """QPROP 1.22 prints CL to 4 decimals, CD to 5, Re to units, Mach to 3, Wa to 4 digits."""
    prop = REFERENCE["props"][case["propeller"]]
    expected = np.array(case["stations"])
    r, chord, beta = _stations(prop)
    assert r == pytest.approx(expected[:, 0], abs=6e-5)

    solution = _solve(prop, r, chord, beta, case["airspeed_mps"], case["rpm"])

    assert solution.converged.all()
    assert solution.cl == pytest.approx(expected[:, 1], abs=6e-5)
    assert solution.cd == pytest.approx(expected[:, 2], rel=5e-4, abs=6e-6)
    assert solution.reynolds == pytest.approx(expected[:, 3], rel=1e-4, abs=0.6)
    assert solution.mach == pytest.approx(expected[:, 4], abs=6e-4)
    assert solution.axial_velocity == pytest.approx(expected[:, 5], rel=6e-4, abs=6e-4)


def test_solution_satisfies_the_circulation_and_perpendicularity_relations():
    prop = REFERENCE["props"]["A"]
    r, chord, beta = _stations(prop)

    s = _solve(prop, r, chord, beta, 10.0, 7000.0)
    w = np.hypot(s.axial_velocity, s.tangential_velocity)

    assert s.circulation == pytest.approx(0.5 * w * chord * s.cl, rel=1e-9, abs=1e-12)
    # The induced velocity is perpendicular to the total velocity: va Wa = vt Wt.
    assert s.axial_induced * s.axial_velocity == pytest.approx(
        s.tangential_induced * s.tangential_velocity, rel=1e-9, abs=1e-12
    )


def test_light_loading_has_no_induced_velocity():
    prop = REFERENCE["props"]["A"]
    r, chord, beta = _stations(prop)
    omega = 6000.0 * math.pi / 30.0

    s = _solve(prop, r, chord * 1e-6, beta, 15.0, 6000.0)

    assert s.axial_velocity == pytest.approx(np.full_like(r, 15.0), rel=1e-5)
    assert s.tangential_velocity == pytest.approx(omega * r, rel=1e-5)
    assert s.alpha == pytest.approx(beta - np.arctan2(15.0, omega * r), abs=1e-6)


def test_stations_with_different_sections():
    prop = REFERENCE["props"]["A"]
    r, chord, beta = _stations(prop, count=4)
    base = BladeSection(*prop["section"])
    other = BladeSection(*REFERENCE["props"]["B"]["section"])

    mixed = solve_stations(
        prop["blade_count"], prop["radius_m"], r, chord, beta, [base, other, base, other],
        10.0, 6000.0 * math.pi / 30.0, RHO, MU, SPEED_OF_SOUND,
    )
    only_other = _solve(prop, r, chord, beta, 10.0, 6000.0, section=other)

    assert mixed.cl[1] == pytest.approx(only_other.cl[1], rel=1e-12)
    assert mixed.cl[3] == pytest.approx(only_other.cl[3], rel=1e-12)
