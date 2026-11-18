# Motor

## Symbols

| Symbol | Description | SI Unit |
|---|---|---|
| $K_v$ | Motor speed constant | $\text{RPM/V}$ |
| $K_t$ | Motor torque constant | $\text{N}\cdot\text{m/A}$ |
| $I$ | Motor winding current | $\text{A}$ |
| $I_0$ | Motor no-load current | $\text{A}$ |
| $R$ | Motor internal winding resistance | $\Omega$ |
| $V_m$ | Motor terminal voltage | $\text{V}$ |
| $V_{\text{back}}$ | Back-EMF voltage | $\text{V}$ |

## Model

PyThrust uses Mark Drela's DC motor model [1, 2]. The torque constant, the
no-load current and the winding resistance are

$$
K_t = \frac{30}{\pi K_v} \cdot \frac{K_V}{K_Q}
$$

$$
I = \frac{Q}{K_t} + I_0(\omega), \qquad
I_0(\omega) = I_{00} + I_{01}\,\omega + I_{02}\,\omega^2
$$

$$
R(I) = R_0 + R_2 I^2
$$

and the back-EMF and terminal voltage are

$$
V_{\text{back}} = \frac{\text{RPM}}{K_v} (1 + \tau \omega)
$$

$$
V_m = V_{\text{back}} + I R(I)
$$

where $\omega = n \cdot 2\pi$ in rad/s and $\tau$ is the magnetic lag time
constant.

With the second-order terms at their defaults ($K_Q = K_V$, $I_{01} = I_{02} = 0$,
$R_2 = 0$, $\tau = 0$) this is the first-order model [1]: constant resistance and
constant no-load current. A motor from a datasheet uses the first-order model,
because the datasheet gives only $K_v$, $R_0$ and $I_{00}$, the last measured at a
stated voltage.

| Symbol | `MotorSpec` field |
|---|---|
| $K_v$ | `kv_rpm_per_v` |
| $K_Q / K_V$ | `torque_constant_kv_ratio` |
| $R_0$, $R_2$ | `resistance_ohm`, `resistance_quadratic` |
| $I_{00}$, $I_{01}$, $I_{02}$ | `no_load_current_a`, `no_load_current_linear`, `no_load_current_quadratic` |
| $\tau$ | `magnetic_lag_tau` |

## API

`pythrust.motor.MotorSpec` defines brushless motor electrical parameters:

| Field | Unit | Description |
|---|---:|---|
| `kv_rpm_per_v` | RPM/V | Motor speed constant |
| `resistance_ohm` | ohm | Winding resistance |
| `no_load_current_a` | A | Datasheet no-load current |
| `current_max_a` | A | Maximum continuous or configured current limit |
| `torque_constant_kv_ratio` | - | Optional second-order ratio of torque to speed constant |
| `magnetic_lag_tau` | s | Optional magnetic lag time constant |
| `no_load_current_linear` | A·s | Optional linear speed term of the no-load current |
| `no_load_current_quadratic` | A·s² | Optional quadratic speed term of the no-load current |
| `resistance_quadratic` | ohm/A² | Optional current-dependent winding resistance |

Use `get_no_load_current(rpm)` and `get_winding_resistance(current_a)` when evaluating speed-dependent or current-dependent motor behavior.

`pythrust.io.read_qprop_motor(path, current_max_a=math.inf)` reads a QPROP motor file into a `MotorSpec`; see [Data Files](propellers.md).

## QPROP Motor Files

A QPROP motor file gives a name, the motor type, then one parameter per line.
`pythrust.io.read_qprop_motor` reads one into a `MotorSpec`:

```python
from pythrust.io import read_qprop_motor

motor = read_qprop_motor("motor.txt", current_max_a=40.0)
```

| Type | Parameters, one per line | `MotorSpec` fields |
|---|---|---|
| 1 | `R Io Kv` | first-order model |
| 2 | `R0 Io0 Kv Kq tau Io1 Io2 R2`; at least the first three | second-order model |

Kv and Kq are in rpm/V. `torque_constant_kv_ratio` is `Kq / Kv`, and a zero
`Kq` means `Kq = Kv`. `Io1` (A s) and `Io2` (A s^2) multiply the shaft speed in
rad/s and its square, and `R2` (ohm/A^2) the current squared. Type 2
parameters left out are zero.

QPROP files carry no current limit; `current_max_a` sets it and defaults to
infinity. QPROP reads only the first number on each line, so a line with
more than one number raises `ValueError` rather than shifting the
parameters. Motor types other than 1 and 2 are rejected.

With the same propeller and motor files, `PropulsionSolver` and a
`BladeElementPropeller` give the RPM, thrust, torque and current that QPROP
1.22 gives at a set voltage, to the digits QPROP prints.

## Datasheet Values

Write the motor constants into a `MotorSpec`:

```python
from pythrust.motor import MotorSpec

motor = MotorSpec(
    kv_rpm_per_v=860.0,       # Kv
    resistance_ohm=0.0258,    # winding resistance Rm
    no_load_current_a=1.3,    # no-load current Io
    current_max_a=65.0,       # maximum continuous current
)
```

Datasheets give the no-load current at a stated voltage, usually 10 V. The
first-order model treats it as constant. For a motor without a published
current limit, pass `current_max_a=math.inf`; the solver then never reports
`current_limit`.

## References

1. **First-Order DC Electric Motor Model**  
   Mark Drela, MIT Aero & Astro, February 2007  
   [PDF Link](https://web.mit.edu/drela/Public/web/qprop/motor1_theory.pdf)

2. **Second-Order DC Electric Motor Model**  
   Mark Drela, MIT Aero & Astro, March 2006  
   [PDF Link](https://web.mit.edu/drela/Public/web/qprop/motor2_theory.pdf)
