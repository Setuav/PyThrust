# OpenMDAO

`pythrust.openmdao.PropulsionComponent` wraps `PropulsionSolver` as an `ExplicitComponent` for optimization models.

Its `propeller` option is a `TablePropeller`, for example `PropulsionComponent(propeller=read_apc("PER3_13x65E.dat"))`.

Inputs include motor parameters, fixed battery voltage, system resistance, propeller diameter, throttle, density, and airspeed. Outputs include RPM, thrust, torque, battery current, battery power, motor current, motor voltage, and feasibility.

!!! warning "Inputs are not real parts"
    The motor inputs are independent: changing `kv_rpm_per_v` leaves
    `resistance_ohm` and `no_load_current_a` unchanged, although a real motor
    with a lower Kv has a higher resistance. `diameter_m` scales the
    `propeller` option's table with unchanged coefficients, which describes a
    geometrically similar propeller that may not exist. An optimizer that
    varies Kv or diameter therefore drifts toward low Kv and large diameter.
    Use datasheet values as fixed inputs, or check any optimum against real
    motors and propellers.
