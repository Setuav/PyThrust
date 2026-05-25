"""Unit tests for OpenMDAO PropulsionComponent wrapper."""

from __future__ import annotations

from pathlib import Path
import pytest
import openmdao.api as om

from pythrust.propellers import PropellerDatabase
from pythrust.propulsion import (
    BatterySpec,
    MotorSpec,
    PropellerSpec,
    PropulsionSolver,
    SystemSpec,
)
from pythrust.openmdao import PropulsionComponent

_DATASET_DIR = Path(__file__).parent.parent / "datasets" / "propellers" / "apc_202602"
_PROP_ID = "APC_13x6.5E"


@pytest.fixture(scope="module")
def prop_entry():
    db = PropellerDatabase()
    if not db.load(_DATASET_DIR, strict=False):
        pytest.skip(f"Propeller dataset not found at {_DATASET_DIR}")
    entry = db.get(_PROP_ID)
    if entry is None:
        pytest.skip(f"{_PROP_ID} not found in dataset")
    return entry


def test_propulsion_component_runs(prop_entry):
    # 1. Run the raw solver as ground truth
    motor = MotorSpec(
        kv_rpm_per_v=860.0,
        resistance_ohm=0.0258,
        no_load_current_a=1.3,
        current_max_a=65.0,
    )
    battery = BatterySpec(voltage_v=14.8)
    system = SystemSpec(resistance_ohm=0.095)
    propeller = PropellerSpec(diameter_m=0.3302)
    
    solver = PropulsionSolver()
    op_ref = solver.solve_operating_point(
        motor=motor,
        battery=battery,
        system=system,
        propeller=propeller,
        prop_entry=prop_entry,
        rho=1.225,
        airspeed_mps=0.0,
        throttle=0.7,
    )
    assert op_ref.is_feasible

    # 2. Setup OpenMDAO problem
    prob = om.Problem()
    model = prob.model

    comp = PropulsionComponent(prop_entry=prop_entry)
    model.add_subsystem('prop', comp, promotes=['*'])

    prob.setup()

    # Set inputs
    prob.set_val('kv_rpm_per_v', 860.0)
    prob.set_val('resistance_ohm', 0.0258)
    prob.set_val('no_load_current_a', 1.3)
    prob.set_val('current_max_a', 65.0)
    prob.set_val('voltage_v', 14.8)
    prob.set_val('resistance_system_ohm', 0.095)
    prob.set_val('diameter_m', 0.3302)
    prob.set_val('throttle', 0.7)
    prob.set_val('rho', 1.225)
    prob.set_val('airspeed_mps', 0.0)

    # Solve / run
    prob.run_model()

    # Get outputs
    rpm_val = prob.get_val('rpm')[0]
    thrust_val = prob.get_val('thrust_n')[0]
    is_feasible_val = prob.get_val('is_feasible')[0]

    # Verify matching values
    assert rpm_val == pytest.approx(op_ref.rpm, abs=1e-2)
    assert thrust_val == pytest.approx(op_ref.thrust_n, rel=1e-3)
    assert is_feasible_val == 1.0

    # 3. Check partial derivatives using finite difference
    partials = prob.check_partials(method='fd', out_stream=None)
    
    # Assert derivatives are successfully calculated and non-empty
    assert len(partials) > 0
