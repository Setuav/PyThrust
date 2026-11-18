import math

import numpy as np
import pytest

from pythrust.propeller import BladeSection
from pythrust.propeller import section_coefficients

SECTION = BladeSection(
    cl0=0.40,
    cl_alpha_per_rad=5.70,
    cl_min=-0.50,
    cl_max=1.10,
    cd0=0.020,
    cd2_upper=0.060,
    cd2_lower=0.030,
    cl_at_cd0=0.40,
    reynolds_ref=70000.0,
    reynolds_exp=0.0,
)

# QPROP 1.22 output for SECTION: (alpha_rad, Mach, CL, CD). Each row is one
# station of a blade with a 1e-6 m chord in forward flight, so the induced
# velocity is negligible and alpha is the blade angle less the inflow angle.
# QPROP prints CL to 4 decimals and CD to 5.
QPROP_ROWS = [
    (-1.186822, 0.142, -0.1543, 1.74856),
    (-0.502658, 0.130, -0.4202, 0.50435),
    (-0.376989, 0.264, -0.4508, 0.31275),
    (-0.335099, 0.154, -0.4595, 0.25847),
    (-0.209439, 0.318, -0.4806, 0.12972),
    (-0.167558, 0.179, -0.4859, 0.09917),
    (-0.134744, 0.225, -0.3777, 0.03815),
    (-0.085872, 0.291, -0.0935, 0.02731),
    (-0.041890, 0.374, 0.1738, 0.02153),
    (-0.037002, 0.360, 0.2027, 0.02117),
    (0.000003, 0.205, 0.4087, 0.02000),
    (0.011861, 0.430, 0.5181, 0.02084),
    (0.060743, 0.502, 0.8627, 0.03284),
    # Below cl_max uncorrected, above it with the Prandtl-Glauert factor: the
    # first row is not stalled, the second is, so stall is judged on the
    # corrected lift.
    (0.103849, 0.416, 1.0908, 0.04864),
    (0.109082, 0.459, 1.0992, 0.07303),
    (0.125656, 0.430, 1.0983, 0.08067),
    (0.167544, 0.232, 1.0948, 0.10458),
    (0.293215, 0.487, 1.0728, 0.21423),
    (0.335106, 0.259, 1.0616, 0.26256),
    (0.460772, 0.545, 1.0172, 0.43825),
    (0.502650, 0.287, 0.9987, 0.50567),
    (1.186828, 0.273, 0.4826, 1.73975),
]


@pytest.mark.parametrize("alpha, mach, cl_qprop, cd_qprop", QPROP_ROWS)
def test_matches_qprop(alpha, mach, cl_qprop, cd_qprop):
    cl, cd = section_coefficients(SECTION, alpha, 1.0e5, mach)

    assert cl == pytest.approx(cl_qprop, abs=3e-4)
    assert cd == pytest.approx(cd_qprop, rel=2e-3, abs=2e-5)


def test_linear_lift_with_prandtl_glauert_factor():
    cl, _ = section_coefficients(SECTION, 0.05, 1.0e5, 0.6)

    assert cl == pytest.approx((0.40 + 5.70 * 0.05) / 0.8)


def test_stalled_lift_falls_off_past_the_limits():
    alpha_high, alpha_low = 0.4, -0.4
    cl, _ = section_coefficients(SECTION, [alpha_high, alpha_low], 1.0e5, 0.0)
    offset = 0.40 / 5.70

    assert cl[0] == pytest.approx(1.10 * math.cos(alpha_high - offset))
    assert cl[1] == pytest.approx(-0.50 * math.cos(alpha_low - offset))


def test_drag_picks_the_quadratic_term_by_side_of_cl_at_cd0():
    alpha_above, alpha_below = 0.10, -0.10
    cl, cd = section_coefficients(SECTION, [alpha_above, alpha_below], 1.0e5, 0.0)

    assert cd[0] == pytest.approx(0.020 + 0.060 * (cl[0] - 0.40) ** 2)
    assert cd[1] == pytest.approx(0.020 + 0.030 * (cl[1] - 0.40) ** 2)


def test_stalled_drag_adds_an_unscaled_stall_term():
    section = BladeSection(0.40, 5.70, -0.50, 1.10, 0.020, 0.060, 0.030, 0.40, 70000.0, -0.5)
    alpha, reynolds = 0.4, 35000.0

    cl, cd = section_coefficients(section, alpha, reynolds, 0.0)

    profile = (0.020 + 0.060 * (cl - 0.40) ** 2) * (reynolds / 70000.0) ** -0.5
    assert cd == pytest.approx(profile + 2.0 * math.sin(alpha - 0.0) ** 2)


def test_reynolds_scaling():
    section = BladeSection(0.40, 5.70, -0.50, 1.10, 0.020, 0.060, 0.030, 0.40, 70000.0, -0.5)

    _, cd_ref = section_coefficients(section, 0.0, 70000.0, 0.0)
    _, cd_low = section_coefficients(section, 0.0, 17500.0, 0.0)

    assert cd_low == pytest.approx(2.0 * cd_ref)


def test_broadcasts_over_arrays():
    alpha = np.linspace(-0.3, 0.3, 7)

    cl, cd = section_coefficients(SECTION, alpha, np.full(7, 1.0e5), 0.1)

    assert cl.shape == cd.shape == (7,)
    assert np.all(cd > 0.0)
