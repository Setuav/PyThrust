# Motor Model & System Resistance Calibration

## Overview

PyThrust models the electric propulsion system using motor parameters ($K_v$, $R_m$, $I_0$) taken directly from the manufacturer datasheet, which are treated as known and fixed. In practice, the system's power delivery is affected by electrical transmission losses outside the motor core: namely the internal resistance of the battery, cable resistance, connectors/solder joints, and the ESC MOSFET conduction resistance.

The `PropulsionCalibrator` identifies a single lumped parameter, `system.resistance_ohm` ($R_{\text{system}}$), from measured test-stand data (RPM, Thrust, and Current) using a physically-motivated power balance model.

---

## Physical Loss Model

### Symbols

| Symbol | Meaning |
|---|---|
| $K_v$ | Motor speed constant from the datasheet |
| $R_m$ | Motor winding resistance from the datasheet |
| $I_0$ | Motor no-load current from the datasheet |
| $R_{\text{system}}$ | Lumped resistance being calibrated |
| $V_{\text{bat}}$ | Battery voltage during the test |
| $V_{\text{applied}}$ | Average voltage commanded by throttle |
| $V_{\text{back}}$ | Motor back-EMF voltage |
| $V_m$ | Motor terminal voltage |
| $I_{\text{motor}}$ | Motor winding current predicted from propeller torque |
| $I_{\text{bat,pred}}$ | Predicted battery current |
| $\tau$ | Propeller shaft torque from the aerodynamic database |

### Step 1: Applied Voltage

At a given throttle and battery voltage, the ideal average voltage applied by PWM switching is:

$$
V_{\text{applied}} =
\text{throttle} \cdot V_{\text{bat}}
$$

Some of this voltage is lost before it reaches the motor because the battery, ESC, wires, and connectors all have finite resistance.

### Step 2: Motor State at the Measured RPM

For each measured RPM, PyThrust first evaluates the propeller torque from the propeller database. That torque determines the motor current needed to spin the propeller:

$$
K_t = \frac{60}{2 \pi K_v}
$$

$$
I_{\text{motor}} =
\frac{\tau}{K_t} + I_0
$$

The motor back-EMF voltage is:

$$
V_{\text{back}} =
\frac{\text{RPM}}{K_v}
$$

The motor terminal voltage is then:

$$
V_m =
V_{\text{back}} + I_{\text{motor}} R_m
$$

### Step 3: Add System Losses

The calibrated resistance is added outside the motor winding resistance:

$$
V_{\text{applied}} =
V_{\text{back}}
+ I_{\text{motor}} R_m
+ I_{\text{motor}} R_{\text{system}}
$$

Equivalently:

$$
V_{\text{applied}} =
V_{\text{back}}
+ I_{\text{motor}} (R_m + R_{\text{system}})
$$

This is the voltage-balance view of the same physical loss model.

### Step 4: Predict Battery Current

The battery must supply both motor electrical power and the extra conduction loss in the system resistance:

$$
P_{\text{battery}} =
V_m I_{\text{motor}}
+ I_{\text{motor}}^2 R_{\text{system}}
$$

The predicted battery current for a candidate resistance value is:

$$
I_{\text{bat,pred}}(R_{\text{system}}) =
\frac{
  V_m I_{\text{motor}}
  + I_{\text{motor}}^2 R_{\text{system}}
}{
  V_{\text{bat}}
}
$$

Here, $R_{\text{system}}$ is the only unknown parameter being fitted.

---

## Identification Procedure

Given **N** test points from a thrust stand, each point contains:

$$
(\text{RPM}_i,\ T_i,\ I_{\text{bat,meas},i})
$$

The calibrator chooses the system resistance that minimizes the normalized current error:

$$
\hat{R}_{\text{system}} =
\arg\min_{R \in [0.0,\, 1.0]}
\sum_{i=1}^{N}
\left(
  \frac{
    I_{\text{bat,pred},i}(R)
    - I_{\text{bat,meas},i}
  }{
    I_{\max}
  }
\right)^2
$$

This is a linear optimization problem in $R_{\text{system}}$ and is solved using `scipy.optimize.least_squares` with bound constraints to prevent non-physical negative resistance.

---

## Input Format

### CSV

The CSV file must contain columns for RPM, Thrust (in grams), and Battery Current (in Amps):

```csv
rpm,thrust_g,current_a
3897,500,3.9
4804,750,6.7
5421,1000,10.2
6071,1250,13.9
```

- **`rpm`** — shaft speed in RPM
- **`thrust_g`** — static thrust in grams
- **`current_a`** — battery current in Amps

### Python Dict List

```python
points = [
    ManufacturerTestPoint(rpm=3897.0, thrust_g=500.0, current_a=3.9),
    ...
]
```

---

## Quality Metrics

The calibration outcome returns residuals and $R^2$ values to evaluate propeller and model compatibility:

- **Thrust $R^2$**: Coefficient of determination for thrust. A value $\ge 0.95$ shows good propeller aerodynamic match.
- **Thrust RMSE**: RMS error in thrust predictions compared to measured data.
- **Current RMSE**: RMS error in battery current predictions compared to measured data.

---

## Usage

```python
from pythrust.propulsion.autotune import ManufacturerTestPoint, PropulsionCalibrator
from pythrust.propulsion import MotorSpec, BatterySpec, SystemSpec, PropellerSpec

motor = MotorSpec(kv_rpm_per_v=860, resistance_ohm=0.0258, no_load_current_a=1.3, current_max_a=65)
battery = BatterySpec(voltage_v=14.8)
system = SystemSpec(resistance_ohm=0.05) # starting guess
propeller = PropellerSpec(diameter_m=0.3302)

cal = PropulsionCalibrator()
points = cal.load_csv("table.csv")
result = cal.calibrate(points, motor, battery, system, propeller, prop_entry)

print(result.system_resistance_ohm)   # e.g. 0.095 ohm
system_calibrated = result.to_system_spec()
```
