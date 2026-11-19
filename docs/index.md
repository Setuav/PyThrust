# PyThrust

![PyThrust Banner](images/PyThrust_banner.png)

Welcome to the official documentation for **PyThrust** - an open-source Python framework for electric propulsion system analysis, co-design, and parameter optimization in UAV applications.

PyThrust combines tabulated and blade-element propeller models, brushless motor models, battery/system loss modeling, and OpenMDAO integration so UAV designers can move from theoretical propulsion sizing to real component choices with traceable calculations.

---

## Core Capabilities

Electric UAV propulsion design usually crosses several domains: aerodynamics, motor electrical behavior, battery loading, and mission constraints. PyThrust keeps those pieces in one workflow:

<div class="grid cards" markdown>

-   **Operating-point solver**

    Solve equilibrium RPM, thrust, torque, current, voltage, power, and efficiency for a coupled motor-propeller-battery system.

-   **Manufacturer data**

    Read APC performance files, QPROP propeller and motor files or APC and UIUC geometry files for a blade-element model, and enter motor datasheet constants, instead of sizing only against abstract component assumptions.

-   **Battery-aware analysis**

    Use fixed-voltage batteries for quick studies or rate-map batteries when voltage sag and state of charge matter.

-   **Optimization**

    Use the solver inside OpenMDAO co-design workflows.

</div>

---

## Feature Visuals

| APC Propeller Coefficients | Rate-Map Battery Mission |
| :---: | :---: |
| ![APC propeller coefficients](images/propeller_coefficients.png) | ![Rate-map battery mission](images/rate_map_battery_mission.png) |

## Explore the Docs

<div class="grid cards" markdown>

-   **Getting Started**

    Install PyThrust, add optional extras, and run the first operating-point solve.

    [Open guide](getting_started.md)

-   **Solving an Operating Point**

    Wire a motor, propeller and battery into the solver and read the result.

    [Open guide](usage.md)

-   **Propellers**

    Tabulated coefficients from APC files, or a blade-element model from QPROP, APC or UIUC geometry files with NeuralFoil airfoil polars.

    [Open reference](reference/propellers.md)

-   **Examples**

    Run battery and mission workflows from the repository.

    [Open examples](examples.md)

-   **Motor and Battery**

    Drela's motor model with QPROP motor files, and fixed-voltage or rate-map batteries.

    [Motor](reference/motor.md) · [Battery](reference/battery.md)

-   **Propulsion Solver**

    The equilibrium equations, RPM search, result fields, feasibility rules and bus solver.

    [Open reference](reference/propulsion_solver.md)

</div>
