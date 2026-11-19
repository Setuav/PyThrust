# Propeller Models

The propulsion solver needs the thrust $T$ and torque $Q$ of the propeller at
an air density, airspeed and RPM. PyThrust ships no propeller data: you bring
a manufacturer's file and pick the model that reads it.

| Model | Input | Page |
|---|---|---|
| `TablePropeller` | Tabulated thrust and power coefficients, such as an APC performance file | [Tabulated Propeller](table_propeller.md) |
| `BladeElementPropeller` | Blade geometry and airfoil data, from a QPROP propeller file or an APC or UIUC geometry file, with QPROP section parameters or NeuralFoil polars | [Blade-Element Propeller](blade_element_propeller.md) |

## Model Interface

The solver takes any object that satisfies `pythrust.propeller.PropellerModel`:

| Member | Description |
|---|---|
| `diameter_m` | Propeller diameter in metres |
| `max_advance_ratio` | Advance ratio up to which the model is expected to give thrust; the RPM search starts there |
| `thrust_torque(rho, airspeed_mps, rpm)` | Thrust in N and shaft torque in N m; NaN where the model has no result |

Negative thrust or torque, as for a windmilling propeller, is a result: the
solver keeps it in its RPM search and marks an operating point that lands
there infeasible (`invalid_coefficients`). NaN tells the solver that the model
has no answer at that RPM, as past the end of a table.

## Coefficients

| Symbol | Description | SI Unit |
|---|---|---|
| $V$ | Flight airspeed | $\text{m/s}$ |
| $D$ | Propeller diameter | $\text{m}$ |
| $n$ | Propeller shaft speed | $\text{1/s}$ (with $n = \text{RPM}/60$) |
| $\rho$ | Air density | $\text{kg/m}^3$ |
| $J$ | Advance ratio | Dimensionless |
| $C_t, C_p$ | Thrust and power coefficients | Dimensionless |
| $T$ | Thrust force | $\text{N}$ |
| $Q$ | Propeller torque | $\text{N}\cdot\text{m}$ |
| $P_{\text{shaft}}$ | Shaft mechanical power | $\text{W}$ |

Both models relate thrust and torque to the coefficients by

$$
J = \frac{V}{n D}, \quad n = \frac{\text{RPM}}{60}
$$

$$
T = C_t \rho n^2 D^4
$$

$$
Q = \frac{C_p \rho n^2 D^5}{2\pi}
$$

$$
P_{\text{shaft}} = 2\pi n Q = C_p \rho n^3 D^5
$$
