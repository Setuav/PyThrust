from pathlib import Path

import pytest

from pythrust.io import read_apc

APC_FILE = Path(__file__).parent / "data" / "PER3_13x65E.dat"


def test_read_apc_file():
    propeller = read_apc(APC_FILE)

    assert propeller.diameter_m == pytest.approx(13.0 * 0.0254)
    assert propeller.rpm_levels == [1000.0 * k for k in range(1, 19)]
    first = propeller.data_by_rpm[1000.0][0]
    assert (first.j, first.ct, first.cp) == (0.0, 0.0889, 0.0376)


def test_read_apc_keeps_only_positive_coefficients_sorted_by_advance_ratio():
    propeller = read_apc(APC_FILE)

    for points in propeller.data_by_rpm.values():
        advance_ratios = [point.j for point in points]
        assert advance_ratios == sorted(set(advance_ratios))
        assert all(point.ct >= 0.0 and point.cp >= 0.0 for point in points)


def _apc_text(model_line, rows):
    lines = [f"   {model_line}", "", "   PROP RPM =   5000", "", "   V  J  Pe  Ct  Cp ..."]
    lines += ["   " + "  ".join(str(value) for value in row) for row in rows]
    return "\r\n".join(lines) + "\r\n"


def _row(j, ct, cp):
    return [0.0, j, 0.0, ct, cp] + [0.0] * 10


def test_read_apc_drops_windmilling_rows(tmp_path):
    path = tmp_path / "PER3_10x5.dat"
    path.write_text(_apc_text("10x5   (10x5.dat)", [_row(0.0, 0.1, 0.05), _row(0.5, 0.02, 0.01), _row(0.7, -0.01, -0.002)]))

    propeller = read_apc(path)

    assert propeller.diameter_m == pytest.approx(0.254)
    assert [point.j for point in propeller.data_by_rpm[5000.0]] == [0.0, 0.5]


def test_read_apc_rejects_a_file_without_a_size(tmp_path):
    path = tmp_path / "bad.dat"
    path.write_text(_apc_text("not a propeller", [_row(0.0, 0.1, 0.05)]))

    with pytest.raises(ValueError, match="no propeller size"):
        read_apc(path)


def test_read_apc_rejects_a_file_without_data(tmp_path):
    path = tmp_path / "empty.dat"
    path.write_text(_apc_text("10x5   (10x5.dat)", []))

    with pytest.raises(ValueError, match="no performance data"):
        read_apc(path)
