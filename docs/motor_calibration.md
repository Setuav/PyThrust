# Motor Model & System Resistance Calibration

## Overview

PyThrust models the electric propulsion system using motor parameters ($K_v$, $R_m$, $I_0$) taken directly from the manufacturer datasheet, which are treated as known and fixed. In practice, the system's power delivery is affected by electrical transmission losses outside the motor core: namely the internal resistance of the battery, cable resistance, connectors/solder joints, and the ESC MOSFET conduction resistance.

The `PropulsionCalibrator` identifies a single lumped parameter, `system.resistance_ohm` ($R_{\text{system}}$), from measured test-stand data (RPM, Thrust, and Current) using a physically-motivated power balance model.

---

## Physical Loss Model

### Voltage Balance

At a given `throttle` and battery voltage $V_{\text{bat}}$, the ideal average voltage applied by PWM switching is $V_{\text{applied}} = \text{throttle} \times V_{\text{bat}}$.

The voltage actually reaching the motor terminals is reduced by transmission voltage drops:
$$V_{\text{motor}} = V_{\text{applied}} - I_{\text{motor}} R_{\text{system}}$$

Equating this to the motor's internal back-EMF voltage balance ($V_{\text{motor}} = V_{\text{back}} + I_{\text{motor}} R_m$):
$$\text{throttle} \times V_{\text{bat}} = V_{\text{back}} + I_{\text{motor}} (R_m + R_{\text{system}})$$

where
$$V_{\text{back}} = \frac{\text{RPM}}{K_v}, \qquad I_{\text{motor}} = \frac{\tau}{K_t} + I_0, \qquad K_t = \frac{60}{2\pi K_v}$$

$\tau$ is the propeller shaft torque determined from the aerodynamic database at the measured RPM.

### Power Balance & Battery Current

The electrical power drawn from the battery is the sum of motor power and transmission conduction losses ($I_{\text{motor}}^2 R_{\text{system}}$):
$$P_{\text{battery}} = V_{\text{motor}} I_{\text{motor}} + I_{\text{motor}}^2 R_{\text{system}} = V_{\text{back}} I_{\text{motor}} + I_{\text{motor}}^2 (R_m + R_{\text{system}})$$

Thus, the predicted battery DC current is:
$$I_{\text{bat\_pred}}(R_{\text{system}}) = \frac{V_m I_{\text{motor}} + I_{\text{motor}}^2 R_{\text{system}}}{V_{\text{bat}}}$$

where $V_m = V_{\text{back}} + I_{\text{motor}} R_m$ is the motor terminal voltage.

---

## Identification Procedure

Given **N** test points $\{(RPM_i, T_i, I_i)\}$ from a thrust stand, the calibrator solves the least-squares problem:

$$\hat{R}_{\text{system}} = \arg\min_{R \in [0.0,\, 1.0]} \sum_{i=1}^N \left[ \frac{I^{\text{pred}}_i(R) - I^{\text{meas}}_i}{I_{\max}} \right]^2$$

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
