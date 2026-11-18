"""Readers for QPROP propeller and motor files.

The format is described in Mark Drela's QPROP user guide,
https://web.mit.edu/drela/Public/web/qprop/qprop_doc.txt.
"""

from __future__ import annotations

import math
from dataclasses import fields, replace
from pathlib import Path
from typing import List, Tuple, Union

from pythrust.motor import MotorSpec
from pythrust.propeller.blade import BladeGeometry, BladeSection

_HEADER_TOKENS = (2, 2, 4, 2, 3, 3)
"""Token counts of the lines after the blade line: CL0 CL_a, CLmin CLmax,
CD0 CD2u CD2l CLCD0, REref REexp, Rfac Cfac Bfac, Radd Cadd Badd."""
_SECTION_FIELDS = tuple(field.name for field in fields(BladeSection))
_MOTOR_PARAMETERS = {1: 3, 2: 8}
"""Number of parameters of each QPROP motor type."""


def read_qprop_propeller(path: Union[str, Path]) -> BladeGeometry:
    """Read a QPROP propeller file into a blade geometry in SI units.

    The file gives, in order: a name; the blade count and, optionally, the
    tip radius; the section parameters ``CL0 CL_a``, ``CLmin CLmax``,
    ``CD0 CD2u CD2l CLCD0`` and ``REref REexp``; the scale factors
    ``Rfac Cfac Bfac`` and the added constants ``Radd Cadd Badd``; then one
    ``r chord beta`` line per station from root to tip. A station line may
    append its own section parameters in the same order as the defaults; those
    it leaves out take the default values.

    Radii and chords become ``value * fac + add`` in metres, and the blade
    angle ``(beta * Bfac + Badd)`` degrees in radians. Without a tip radius on
    the blade line, the last station's radius is the tip radius. ``CL_a`` is
    taken per radian.

    Lines starting with ``#`` and blank lines are skipped, and text after
    ``!`` is ignored. Raises ``ValueError`` naming the line of a malformed file.
    """
    path = Path(path)
    lines = _content_lines(path)
    if len(lines) < 1 + 1 + len(_HEADER_TOKENS) + 2:
        raise ValueError(f"{path.name}: too few lines for a QPROP propeller file")

    blade_line, blade_tokens = lines[1]
    if len(blade_tokens) not in (1, 2):
        raise ValueError(f"{path.name}:{blade_line}: expected 'Nblades [R]'")
    blade_count = _integer(path, blade_line, blade_tokens[0])
    tip_radius = _number(path, blade_line, blade_tokens[1]) if len(blade_tokens) == 2 else None

    header: List[float] = []
    for (number, tokens), expected in zip(lines[2:8], _HEADER_TOKENS):
        if len(tokens) != expected:
            raise ValueError(f"{path.name}:{number}: expected {expected} numbers, got {len(tokens)}")
        header.extend(_number(path, number, token) for token in tokens)
    default_section = BladeSection(*header[:10])
    r_fac, c_fac, b_fac, r_add, c_add, b_add = header[10:]

    r_m, chord_m, blade_angle_rad, sections = [], [], [], []
    for number, tokens in lines[8:]:
        if not 3 <= len(tokens) <= 3 + len(_SECTION_FIELDS):
            raise ValueError(
                f"{path.name}:{number}: expected 'r chord beta' and up to "
                f"{len(_SECTION_FIELDS)} section values, got {len(tokens)} numbers"
            )
        r, chord, beta, *overrides = (_number(path, number, token) for token in tokens)
        r_m.append(r * r_fac + r_add)
        chord_m.append(chord * c_fac + c_add)
        blade_angle_rad.append(math.radians(beta * b_fac + b_add))
        sections.append(replace(default_section, **dict(zip(_SECTION_FIELDS, overrides))))

    if tip_radius is None:
        radius_m = r_m[-1]
    else:
        radius_m = tip_radius * r_fac + r_add
    try:
        return BladeGeometry(
            blade_count=blade_count,
            radius_m=radius_m,
            r_m=tuple(r_m),
            chord_m=tuple(chord_m),
            blade_angle_rad=tuple(blade_angle_rad),
            sections=tuple(sections),
        )
    except ValueError as error:
        raise ValueError(f"{path.name}: {error}") from error


def read_qprop_motor(path: Union[str, Path], current_max_a: float = math.inf) -> MotorSpec:
    """Read a QPROP motor file into a MotorSpec.

    The file gives a name, the motor type, then one parameter per line.
    Type 1 gives ``R Io Kv``; type 2 gives ``R0 Io0 Kv Kq tau Io1 Io2 R2``, of
    which at least the first three, the rest defaulting to zero. A zero ``Kq``
    means ``Kq = Kv``. Kv and Kq are in rpm/V, ``Io1`` in A s and ``Io2`` in
    A s^2, against the shaft speed in rad/s.

    QPROP files carry no current limit; ``current_max_a`` sets it.

    Raises ``ValueError`` naming the line of a malformed file, for a motor
    type other than 1 or 2, or for a line with more than one number: QPROP
    reads only the first number of each line.
    """
    path = Path(path)
    lines = _content_lines(path)
    if len(lines) < 2:
        raise ValueError(f"{path.name}: too few lines for a QPROP motor file")

    type_line, type_tokens = lines[1]
    if len(type_tokens) != 1:
        raise ValueError(f"{path.name}:{type_line}: expected the motor type alone on its line")
    motor_type = _integer(path, type_line, type_tokens[0], "motor type")
    if motor_type not in _MOTOR_PARAMETERS:
        raise ValueError(f"{path.name}:{type_line}: motor type {motor_type} is not 1 or 2")

    values = []
    for number, tokens in lines[2:]:
        if len(tokens) != 1:
            raise ValueError(f"{path.name}:{number}: expected one parameter per line, got {len(tokens)} values")
        values.append(_number(path, number, tokens[0]))
    expected = _MOTOR_PARAMETERS[motor_type]
    if not 3 <= len(values) <= expected:
        raise ValueError(f"{path.name}: motor type {motor_type} takes 3 to {expected} parameters, got {len(values)}")

    resistance, no_load, kv, kq, tau, io1, io2, r2 = values + [0.0] * (8 - len(values))
    return MotorSpec(
        kv_rpm_per_v=kv,
        resistance_ohm=resistance,
        no_load_current_a=no_load,
        current_max_a=current_max_a,
        torque_constant_kv_ratio=1.0 if kq == 0.0 else kq / kv,
        magnetic_lag_tau=tau,
        no_load_current_linear=io1,
        no_load_current_quadratic=io2,
        resistance_quadratic=r2,
    )


def _content_lines(path: Path) -> List[Tuple[int, List[str]]]:
    """Return the line number and tokens of each line that is not blank or a comment."""
    content = []
    for number, raw in enumerate(path.read_text(errors="ignore").splitlines(), start=1):
        text = raw.split("!", 1)[0].strip()
        if not text or text.startswith("#"):
            continue
        content.append((number, text.split()))
    return content


def _number(path: Path, line: int, token: str) -> float:
    try:
        value = float(token)
    except ValueError:
        raise ValueError(f"{path.name}:{line}: {token!r} is not a number") from None
    if not math.isfinite(value):
        raise ValueError(f"{path.name}:{line}: {token!r} is not finite")
    return value


def _integer(path: Path, line: int, token: str, what: str = "blade count") -> int:
    value = _number(path, line, token)
    if value != int(value) or value < 1:
        raise ValueError(f"{path.name}:{line}: {what} {token!r} is not a positive integer")
    return int(value)
