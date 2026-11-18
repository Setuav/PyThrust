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
| $\Omega$ | Propeller angular speed, $2\pi n$ | $\text{rad/s}$ |
| $B$ | Number of blades | Dimensionless |
| $R_{\text{tip}}$ | Propeller tip radius | $\text{m}$ |
| $r$ | Radius of a blade station | $\text{m}$ |
| $c$ | Blade chord | $\text{m}$ |
| $\beta$ | Blade angle from the plane of rotation | $\text{rad}$ |
| $W_a, W_t$ | Axial and tangential velocity seen by the blade | $\text{m/s}$ |
| $\phi, \alpha$ | Inflow angle and angle of attack | $\text{rad}$ |
| $\Gamma$ | Circulation of one blade | $\text{m}^2\text{/s}$ |
| $c_l, c_d$ | Section lift and drag coefficients | Dimensionless |
| $Re, M$ | Section Reynolds and Mach numbers | Dimensionless |
| $\mu, a$ | Air viscosity and speed of sound | $\text{kg/(m s)}$, $\text{m/s}$ |

---

## 2) Propeller Aerodynamics

The solver needs the thrust $T$ and torque $Q$ of the propeller at an air
density, airspeed and RPM. PyThrust has two propeller models that give them:
a table of measured or computed coefficients, and a blade-element model that
computes them from the blade's geometry. Both use

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

### 2.1) Tabulated Coefficients

`TablePropeller` holds $C_t(J, \text{RPM})$ and $C_p(J, \text{RPM})$, for example
read from an APC performance file. It interpolates linearly in $J$ within each
RPM band, then linearly between the two bands around the RPM.

### 2.2) Blade-Element Model

`BladeElementPropeller` follows the blade-element/vortex formulation of
Drela's QPROP [4], with the section model of the QPROP user guide [5]. Each
blade station is solved on its own; the stations' loads then sum to the
thrust and torque.

#### Analysis stations

The blade is described at stations $r_1 < \dots < r_K$ with chord, blade
angle and section parameters. It is analysed at the midpoints of $N$ equal
intervals from $r_1$ to $r_K$ ($N = 25$ by default), each of width
$\Delta r = (r_K - r_1)/N$. Chord, blade angle and section parameters there
come from a cubic spline through the stations whose second derivative is
constant in the first and last intervals (zero third derivative). The tip
radius $R_{\text{tip}}$ is given, or else $r_K$.

#### Velocities

Without induced velocity, a station at radius $r$ sees the axial velocity
$U_a = V$ and the tangential velocity $U_t = \Omega r$, of magnitude
$U = \sqrt{U_a^2 + U_t^2}$. The velocities with the blade's own induced
velocity are written with one angle $\psi$:

$$
W_a = \tfrac{1}{2}\left(U_a + U \sin\psi\right)
$$

$$
W_t = \tfrac{1}{2}\left(U_t + U \cos\psi\right)
$$

so that the induced velocities $v_a = W_a - U_a$ and $v_t = U_t - W_t$ are
perpendicular to the total velocity $W = \sqrt{W_a^2 + W_t^2}$ for every $\psi$.
At $\psi_0 = \arctan(U_a / U_t)$ there is no induced velocity. Then

$$
\phi = \arctan\frac{W_a}{W_t}, \qquad \alpha = \beta - \phi
$$

$$
Re = \frac{\rho W c}{\mu}, \qquad M = \frac{W}{a}
$$

#### Circulation from the wake

With the local wake advance ratio $\lambda_w$ and Prandtl's tip-loss factor
$F_{\text{tip}}$ evaluated on it,

$$
\lambda_w = \frac{r}{R_{\text{tip}}} \frac{W_a}{W_t}
$$

$$
F_{\text{tip}} = \frac{2}{\pi} \arccos\left(
  \exp\left[-\frac{B}{2} \left(1 - \frac{r}{R_{\text{tip}}}\right) \frac{1}{\lambda_w}\right]
\right)
$$

the circulation of one blade follows from the tangential induced velocity:

$$
\Gamma_w = v_t \, \frac{4 \pi r}{B} \, F_{\text{tip}}
\sqrt{1 + \left(\frac{4 \lambda_w R_{\text{tip}}}{\pi B r}\right)^2}
$$

The square root grows near the hub and keeps the relation consistent with a
heavily loaded actuator disk.

#### Section lift and drag

The section's lift is linear in the angle of attack, with the Prandtl-Glauert
factor:

$$
c_{l,\text{lin}} = \frac{c_{l0} + c_{l\alpha}\,\alpha}{\sqrt{1 - M^2}}
$$

Where $c_{l,\text{lin}}$ passes $c_{l,\max}$ or $c_{l,\min}$, the section is
stalled and its lift falls off with the angle of attack:

$$
c_l =
\begin{cases}
c_{l,\max} \cos\left(\alpha - c_{l0}/c_{l\alpha}\right) & c_{l,\text{lin}} > c_{l,\max} \\
c_{l,\min} \cos\left(\alpha - c_{l0}/c_{l\alpha}\right) & c_{l,\text{lin}} < c_{l,\min} \\
c_{l,\text{lin}} & \text{otherwise}
\end{cases}
$$

The drag is quadratic in the lift and scales with the Reynolds number; a
stalled section adds a term that does not:

$$
c_d = \left[c_{d0} + c_{d2} \left(c_l - c_{l,cd0}\right)^2\right]
\left(\frac{Re}{Re_{\text{ref}}}\right)^{e}
+ \begin{cases} 2 \sin^2\left(\alpha - \alpha_{cd0}\right) & \text{stalled} \\ 0 & \text{otherwise} \end{cases}
$$

with $c_{d2} = c_{d2,u}$ for $c_l > c_{l,cd0}$, $c_{d2} = c_{d2,l}$ otherwise, and
$\alpha_{cd0} = (c_{l,cd0} - c_{l0})/c_{l\alpha}$. The QPROP guide gives the
linear lift, the clipping limits, the drag polar and the stall drag term; the
stalled lift and the unscaled stall drag were measured from QPROP 1.22's
output.

| Symbol | `BladeSection` field |
|---|---|
| $c_{l0}$, $c_{l\alpha}$ | `cl0`, `cl_alpha_per_rad` |
| $c_{l,\min}$, $c_{l,\max}$ | `cl_min`, `cl_max` |
| $c_{d0}$, $c_{d2,u}$, $c_{d2,l}$, $c_{l,cd0}$ | `cd0`, `cd2_upper`, `cd2_lower`, `cl_at_cd0` |
| $Re_{\text{ref}}$, $e$ | `reynolds_ref`, `reynolds_exp` |

#### Station equation

The section's lift gives the circulation $\Gamma_l = \tfrac{1}{2} W c\, c_l$.
A station is solved where the two circulations agree:

$$
\mathcal{R}(\psi) = \Gamma_w(\psi) - \tfrac{1}{2} W(\psi)\, c\, c_l(\psi) = 0
$$

$\psi$ is searched between the angles where $W_a$ and where $W_t$ fall to zero,
$-\arcsin(U_a/U) < \psi < \arccos(-U_t/U)$. PyThrust samples $\mathcal{R}$ on that
range, takes the sign change nearest $\psi_0$, the flow without induced
velocity, and refines the root with the Illinois method.

#### Thrust and torque

The lift and drag of a station resolve into thrust and torque along $\phi$.
With $\Gamma = \tfrac{1}{2} W c\, c_l$ and $W\cos\phi = W_t$, $W\sin\phi = W_a$,
the midpoint sums over the stations are

$$
T = \rho B \sum \left(\Gamma W_t - \tfrac{1}{2} W c\, c_d\, W_a\right) \Delta r
$$

$$
Q = \rho B \sum \left(\Gamma W_a + \tfrac{1}{2} W c\, c_d\, W_t\right) r\, \Delta r
$$

At zero RPM, or where a station has no root, the model gives zero thrust and
torque.

#### Start of the RPM search

The solver starts its RPM search at the advance ratio the propeller model
gives as `max_advance_ratio`. For the blade-element model this is the advance
ratio at which the section at 75% radius has zero lift, ignoring the induced
velocity, which is small near zero thrust:

$$
J_{\max} = \pi \, \frac{r_{75}}{R_{\text{tip}}} \tan\left(\beta_{75} + \frac{c_{l0}}{c_{l\alpha}}\right)
$$

#### Differences from QPROP

- **Tip radius scaling.** A QPROP propeller file may give the tip radius on its
  second line. The QPROP guide scales it with `Rfac` and `Radd` like the
  station radii; QPROP 1.22 uses it unscaled. PyThrust follows the guide.
- **Multiple roots.** At a stalled station of a windmilling blade
  $\mathcal{R}(\psi)$ can have more than one root, and QPROP can pick another one
  than PyThrust.
- **Externally induced velocity.** QPROP accepts a velocity induced by another
  rotor ahead of the propeller; PyThrust does not.

#### Verification against QPROP

The tests compare PyThrust with QPROP 1.22 run on the same input files:

- **Section model:** 22 points from $-68°$ to $+68°$ angle of attack and Mach
  0.13 to 0.55, including both stall limits; $c_l$ and $c_d$ agree to the
  digits QPROP prints.
- **Stations:** 7 operating points on two blades, static to negative thrust;
  $c_l$, $c_d$, $Re$, $M$ and $W_a$ at all 25 stations agree to the digits
  QPROP prints.
- **Thrust and torque:** 13 operating points on three blades agree within
  0.04%, inside QPROP's four printed digits.
- **Propeller and motor:** with a QPROP motor file and a set voltage, RPM,
  thrust, torque and current agree to the digits QPROP prints.

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

4. **QPROP Formulation**  
   Mark Drela, MIT Aero & Astro, June 2006  
   [PDF Link](https://web.mit.edu/drela/Public/web/qprop/qprop_theory.pdf)

5. **QPROP User Guide**, version 1.21  
   Mark Drela, MIT Aero & Astro, July 2007  
   [Text Link](https://web.mit.edu/drela/Public/web/qprop/qprop_doc.txt)
