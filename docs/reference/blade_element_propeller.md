# Blade-Element Propeller

`BladeElementPropeller` follows the blade-element/vortex formulation of
Drela's QPROP [1], with the section model of the QPROP user guide [2]. Each
blade station is solved on its own; the stations' loads then sum to the
thrust and torque.

## Symbols

| Symbol | Description | SI Unit |
|---|---|---|
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

## QPROP Propeller Files

A QPROP propeller file describes the blade itself: chord and blade angle at
radial stations, and the airfoil's lift and drag parameters. The format is
defined in the [QPROP user guide](https://web.mit.edu/drela/Public/web/qprop/qprop_doc.txt).
`pythrust.io.read_qprop_propeller` reads one into a `BladeGeometry` in SI units:

```python
from pythrust.io import read_qprop_propeller

blade = read_qprop_propeller("prop.txt")
print(blade.blade_count, blade.radius_m)
print(blade.r_m, blade.chord_m, blade.blade_angle_rad)
print(blade.sections[0].cl_alpha_per_rad)
```

The file holds, in order:

| Line | Content |
|---|---|
| 1 | Name |
| 2 | `Nblades [R]`; without `R`, the last station's radius is the tip radius |
| 3 | `CL0 CL_a` |
| 4 | `CLmin CLmax` |
| 5 | `CD0 CD2u CD2l CLCD0` |
| 6 | `REref REexp` |
| 7 | `Rfac Cfac Bfac` |
| 8 | `Radd Cadd Badd` |
| 9 on | `r chord beta`, one station per line from root to tip |

Radii and chords become `value * fac + add` in metres, and the blade angle
`beta * Bfac + Badd` in degrees, converted to radians. A station line may
append its own `CL0 CL_a CLmin CLmax CD0 CD2u CD2l CLCD0 REref REexp`; values it
leaves out take those of lines 3 to 6. Lines starting with `#` and blank lines
are skipped, and text after `!` is ignored.

`CL_a` is read per radian. The QPROP guide does not state its unit; its example
value of 5.8 is a lift slope per radian.

The tip radius `R` on line 2 is scaled like the station radii, as the QPROP
guide states. QPROP 1.22 itself applies `Rfac` and `Radd` only to the stations
and uses `R` as written, so a file that gives `R` with `Rfac` other than 1 or
`Radd` other than 0 gives different tip losses in QPROP and in PyThrust.
Without `R`, or with the radii in metres, the two agree. `R` must not be less
than the last station's radius.

## API

### Blade Geometry

`pythrust.io.read_qprop_propeller(path)` reads a QPROP propeller file into a
`BladeGeometry`, the input of a blade-element propeller model:

| Field | Unit | Description |
|---|---:|---|
| `blade_count` | - | Number of blades |
| `radius_m` | m | Tip radius |
| `r_m` | m | Station radii, root to tip |
| `chord_m` | m | Chord at each station |
| `blade_angle_rad` | rad | Blade angle from the plane of rotation at each station |
| `sections` | - | `BladeSection` at each station |

`BladeSection` holds QPROP's airfoil parameters, listed with their symbols in
[Section lift and drag](#section-lift-and-drag).
`section_coefficients(section, alpha_rad, reynolds, mach)` evaluates the section
model on scalars or NumPy arrays and returns `(CL, CD)`.

### Blade-Element Propeller

`BladeElementPropeller(geometry, mu=1.78e-5, speed_of_sound=340.0, stations=25)`
is a `PropellerModel` computed from a `BladeGeometry` with QPROP's
blade-element/vortex formulation:

```python
from pythrust.io import read_qprop_propeller
from pythrust.propeller import BladeElementPropeller

propeller = BladeElementPropeller(read_qprop_propeller("prop.txt"))
thrust_n, torque_nm = propeller.thrust_torque(rho=1.225, airspeed_mps=10.0, rpm=8000.0)
```

| Member | Description |
|---|---|
| `geometry` | The `BladeGeometry` |
| `mu`, `speed_of_sound` | Air viscosity in kg/(m s) and speed of sound in m/s; the defaults are QPROP's |
| `diameter_m` | Twice the tip radius |
| `max_advance_ratio` | Advance ratio at which the section at 75% radius has zero lift, an estimate of zero thrust |
| `thrust_torque(rho, airspeed_mps, rpm)` | Thrust in N and torque in N m; zero for both at zero RPM or where a station has no solution |

## Theory

### Analysis stations

The blade is described at stations $r_1 < \dots < r_K$ with chord, blade
angle and section parameters. It is analysed at the midpoints of $N$ equal
intervals from $r_1$ to $r_K$ ($N = 25$ by default), each of width
$\Delta r = (r_K - r_1)/N$. Chord, blade angle and section parameters there
come from a cubic spline through the stations whose second derivative is
constant in the first and last intervals (zero third derivative). The tip
radius $R_{\text{tip}}$ is given, or else $r_K$.

### Velocities

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

### Circulation from the wake

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

### Section lift and drag

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

### Station equation

The section's lift gives the circulation $\Gamma_l = \tfrac{1}{2} W c\, c_l$.
A station is solved where the two circulations agree:

$$
\mathcal{R}(\psi) = \Gamma_w(\psi) - \tfrac{1}{2} W(\psi)\, c\, c_l(\psi) = 0
$$

$\psi$ is searched between the angles where $W_a$ and where $W_t$ fall to zero,
$-\arcsin(U_a/U) < \psi < \arccos(-U_t/U)$. PyThrust samples $\mathcal{R}$ on that
range, takes the sign change nearest $\psi_0$, the flow without induced
velocity, and refines the root with the Illinois method.

### Thrust and torque

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

### Start of the RPM search

The solver starts its RPM search at the advance ratio the propeller model
gives as `max_advance_ratio`. For the blade-element model this is the advance
ratio at which the section at 75% radius has zero lift, ignoring the induced
velocity, which is small near zero thrust:

$$
J_{\max} = \pi \, \frac{r_{75}}{R_{\text{tip}}} \tan\left(\beta_{75} + \frac{c_{l0}}{c_{l\alpha}}\right)
$$

### Differences from QPROP

- **Tip radius scaling.** A QPROP propeller file may give the tip radius on its
  second line. The QPROP guide scales it with `Rfac` and `Radd` like the
  station radii; QPROP 1.22 uses it unscaled. PyThrust follows the guide.
- **Multiple roots.** At a stalled station of a windmilling blade
  $\mathcal{R}(\psi)$ can have more than one root, and QPROP can pick another one
  than PyThrust.
- **Externally induced velocity.** QPROP accepts a velocity induced by another
  rotor ahead of the propeller; PyThrust does not.

### Verification against QPROP

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

## References

1. **QPROP Formulation**  
   Mark Drela, MIT Aero & Astro, June 2006  
   [PDF Link](https://web.mit.edu/drela/Public/web/qprop/qprop_theory.pdf)

2. **QPROP User Guide**, version 1.21  
   Mark Drela, MIT Aero & Astro, July 2007  
   [Text Link](https://web.mit.edu/drela/Public/web/qprop/qprop_doc.txt)
