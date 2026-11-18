# Propulsion and Battery Model Theory

This document defines the core mathematical model for the electric propulsion system (propeller + brushless motor + battery/ESC).

## 1) Symbols and Units

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
| $K_v$ | Motor speed constant | $\text{RPM/V}$ |
| $K_t$ | Motor torque constant | $\text{N}\cdot\text{m/A}$ |
| $I$ | Motor winding current | $\text{A}$ |
| $I_0$ | Motor no-load current | $\text{A}$ |
| $R$ | Motor internal winding resistance | $\Omega$ |
| $R_{\text{system}}$ | Lumped transmission system resistance | $\Omega$ |
| $V_m$ | Motor terminal voltage | $\text{V}$ |
| $V_{\text{back}}$ | Back-EMF voltage | $\text{V}$ |
| $V_{\text{pack}}$ | Battery terminal pack voltage | $\text{V}$ |
| $x$ | Battery depth of discharge | Dimensionless |
| $N_s, N_p$ | Pack cells in series and parallel | Dimensionless |

---

## 2) Propeller Aerodynamics

Propeller coefficients $C_t(J, \text{RPM})$ and $C_p(J, \text{RPM})$ are tabulated, for example read from an APC performance file, and evaluated using bilinear interpolation.

### Aerodynamic Equations

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

---

## 3) Brushless DC Motor Model

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

---

## 4) Battery Model

The fixed-voltage battery model uses a constant terminal pack voltage:

$$
V_{\text{pack}} = V_{\text{nominal}}
$$

The rate-map battery model uses a cell open-circuit voltage curve and a cell
resistance curve indexed by depth of discharge:

$$
V_{\text{cell}}(x, I_{\text{cell}}) =
OCV(x) - R(x)I_{\text{cell}}
$$

For a pack topology:

$$
V_{\text{pack}} = N_s V_{\text{cell}}
$$

$$
I_{\text{cell}} = \frac{I_{\text{pack}}}{N_p}
$$

During mission stepping, state advances by charge conservation:

$$
x_{\text{next}} = x + \frac{I_{\text{cell}}}{Q_{\text{cell}}}\Delta t
$$

## 5) System Electrical Resistance & Power Chain

The voltage drops across ESC MOSFETs, battery internal resistance, cables, and connectors are modeled as a lumped transmission system resistance ($R_{\text{system}}$):

$$
V_m = \text{throttle} \times V_{\text{pack}} - I R_{\text{system}}
$$

The overall electrical power drawn from the battery pack is:

$$
P_{\text{battery}} = \frac{V_m I + I^2 R_{\text{system}}}{\eta_{\text{discharge}}}
$$

For `RateMapBattery`, the equivalent-circuit terminal voltage already captures
the cell-level voltage sag from the battery curves. `R_system` should still be
used for wiring, ESC, connector, or other losses outside the battery model.

---

## 6) Coupled Equilibrium Condition

For a given throttle setting and airspeed, the equilibrium shaft speed (RPM) is the solution of the coupled electrical and aerodynamic torque equilibrium equation:

$$
F(\text{RPM}) =
V_{\text{back}}(\text{RPM})
+ I(\text{RPM})R
+ I(\text{RPM})R_{\text{system}}
- \text{throttle} \times V_{\text{pack}}(x, I(\text{RPM}))
= 0
$$

A root-finding method (e.g., Brent's method) solves $F(\text{RPM}) = 0$ for RPM. Once the equilibrium RPM is determined, $T, Q, P_{\text{shaft}}, I$, and efficiency parameters are calculated.

---

## References

1. **First-Order DC Electric Motor Model**  
   Mark Drela, MIT Aero & Astro, February 2007  
   [PDF Link](https://web.mit.edu/drela/Public/web/qprop/motor1_theory.pdf)

2. **Second-Order DC Electric Motor Model**  
   Mark Drela, MIT Aero & Astro, March 2006  
   [PDF Link](https://web.mit.edu/drela/Public/web/qprop/motor2_theory.pdf)

3. **Battery Knockdown Factors for Conceptual Design**  
   Robert A. McDonald, AIAA Aviation Forum, 2024  
   DOI: `10.2514/6.2024-3903`
