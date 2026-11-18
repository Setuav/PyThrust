import math

import pytest

from pythrust.io import read_qprop_propeller
from pythrust.propeller import BladeGeometry, BladeSection

INCH = 0.0254

PROPELLER = """\
Test 8x4 propeller       ! name

 2   4.0                 ! Nblades  R

 0.45   5.9              ! CL0     CL_a
-0.35   1.15             ! CLmin   CLmax

 0.025  0.045  0.018  0.45   ! CD0  CD2u  CD2l  CLCD0
 80000  -0.6                 ! REref  REexp

 0.0254  0.0254  1.0     ! Rfac  Cfac  Bfac
 0.0     0.0     0.0     ! Radd  Cadd  Badd

#  r     chord   beta
  0.8    0.70    30.0
  2.0    0.80    16.0
  3.0    0.65    11.0
  3.9    0.30     8.5
"""

DEFAULT_SECTION = BladeSection(
    cl0=0.45,
    cl_alpha_per_rad=5.9,
    cl_min=-0.35,
    cl_max=1.15,
    cd0=0.025,
    cd2_upper=0.045,
    cd2_lower=0.018,
    cl_at_cd0=0.45,
    reynolds_ref=80000.0,
    reynolds_exp=-0.6,
)


def _write(tmp_path, text):
    path = tmp_path / "prop.txt"
    path.write_text(text)
    return path


def test_reads_geometry_in_si_units(tmp_path):
    blade = read_qprop_propeller(_write(tmp_path, PROPELLER))

    assert isinstance(blade, BladeGeometry)
    assert blade.blade_count == 2
    assert blade.radius_m == pytest.approx(4.0 * INCH)
    assert blade.r_m == pytest.approx([0.8 * INCH, 2.0 * INCH, 3.0 * INCH, 3.9 * INCH])
    assert blade.chord_m == pytest.approx([0.70 * INCH, 0.80 * INCH, 0.65 * INCH, 0.30 * INCH])
    assert blade.blade_angle_rad == pytest.approx([math.radians(b) for b in (30.0, 16.0, 11.0, 8.5)])
    assert blade.sections == (DEFAULT_SECTION,) * 4


def test_tip_radius_defaults_to_the_last_station(tmp_path):
    blade = read_qprop_propeller(_write(tmp_path, PROPELLER.replace(" 2   4.0 ", " 2 ")))

    assert blade.radius_m == pytest.approx(3.9 * INCH)


def test_applies_scale_factors_before_added_constants(tmp_path):
    text = PROPELLER.replace(" 0.0254  0.0254  1.0 ", " 0.02  0.03  2.0 ").replace(
        " 0.0     0.0     0.0 ", " 0.001  0.002  -5.0 "
    )

    blade = read_qprop_propeller(_write(tmp_path, text))

    assert blade.radius_m == pytest.approx(4.0 * 0.02 + 0.001)
    assert blade.r_m[0] == pytest.approx(0.8 * 0.02 + 0.001)
    assert blade.chord_m[0] == pytest.approx(0.70 * 0.03 + 0.002)
    assert blade.blade_angle_rad[0] == pytest.approx(math.radians(30.0 * 2.0 - 5.0))


def test_station_lines_override_section_parameters_in_order(tmp_path):
    text = PROPELLER.replace("  2.0    0.80    16.0\n", "  2.0    0.80    16.0   0.30  6.1\n").replace(
        "  3.0    0.65    11.0\n",
        "  3.0    0.65    11.0   0.40  5.5  -0.2  1.0  0.03  0.05  0.02  0.4  60000  -0.5\n",
    )

    blade = read_qprop_propeller(_write(tmp_path, text))

    assert blade.sections[0] == DEFAULT_SECTION
    assert blade.sections[1].cl0 == 0.30
    assert blade.sections[1].cl_alpha_per_rad == 6.1
    assert blade.sections[1].cl_max == DEFAULT_SECTION.cl_max
    assert blade.sections[2] == BladeSection(0.40, 5.5, -0.2, 1.0, 0.03, 0.05, 0.02, 0.4, 60000.0, -0.5)


def test_skips_comments_blank_lines_and_trailing_text(tmp_path):
    text = "# a header comment\n\n" + PROPELLER.replace("  0.8    0.70    30.0\n", "  0.8    0.70    30.0  ! root\n# inner note\n")

    blade = read_qprop_propeller(_write(tmp_path, text))

    assert len(blade.r_m) == 4
    assert blade.chord_m[0] == pytest.approx(0.70 * INCH)


@pytest.mark.parametrize(
    "old, new, message",
    [
        (" 2   4.0 ", " 2.5   4.0 ", "blade count"),
        ("-0.35   1.15 ", "-0.35 ", "expected 2 numbers"),
        ("  2.0    0.80    16.0\n", "  2.0    0.80    abc\n", "'abc' is not a number"),
        ("  2.0    0.80    16.0\n", "  2.0    0.80\n", "expected 'r chord beta'"),
        ("  2.0    0.80    16.0\n", "  0.5    0.80    16.0\n", "station radii must increase"),
    ],
)
def test_rejects_malformed_files_naming_the_problem(tmp_path, old, new, message):
    with pytest.raises(ValueError, match=message):
        read_qprop_propeller(_write(tmp_path, PROPELLER.replace(old, new)))


def test_rejects_a_file_with_one_station(tmp_path):
    text = PROPELLER.split("#  r")[0]  + "  3.9  0.30  8.5\n"

    with pytest.raises(ValueError):
        read_qprop_propeller(_write(tmp_path, text))


def test_blade_geometry_requires_matching_station_lists():
    with pytest.raises(ValueError, match="same length"):
        BladeGeometry(2, 0.1, (0.02, 0.1), (0.01,), (0.3, 0.1), (DEFAULT_SECTION,) * 2)
