# Propulsion System Mathematical Model

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

---

## 2) Propeller Aerodynamics

Propeller coefficients $C_t(J, \text{RPM})$ and $C_p(J, \text{RPM})$ are loaded from an empirical database and evaluated using bilinear interpolation.

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

The relationship between torque, back-EMF, and speed is defined below:

$$
K_t = \frac{30}{\pi K_v}
$$

$$
I = \frac{Q}{K_t} + I_0
$$

$$
V_{\text{back}} = \frac{\text{RPM}}{K_v} (1 + \tau \omega)
$$

$$
V_m = V_{\text{back}} + I R
$$

where $\tau$ is the magnetic lag time constant (set to $0$ for first-order models), and $\omega = n \cdot 2\pi$.

---

## 4) System Electrical Resistance & Power Chain

The voltage drops across ESC MOSFETs, battery internal resistance, cables, and connectors are modeled as a lumped transmission system resistance ($R_{\text{system}}$):

$$
V_m = \text{throttle} \times V_{\text{pack}} - I R_{\text{system}}
$$

The overall electrical power drawn from the battery pack is:

$$
P_{\text{battery}} = \frac{V_m I + I^2 R_{\text{system}}}{\eta_{\text{discharge}}}
$$

---

## 5) Coupled Equilibrium Condition

For a given throttle setting and airspeed, the equilibrium shaft speed (RPM) is the solution of the coupled electrical and aerodynamic torque equilibrium equation:

$$
F(\text{RPM}) = \text{throttle} \times V_{\text{pack}} - \Big( V_{\text{back}}(\text{RPM}) + I(\text{RPM}) (R + R_{\text{system}}) \Big) = 0
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
