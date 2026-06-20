![PyThrust Banner](docs/images/PyThrust_banner.png)

[![CI/CD Pipeline](https://github.com/Setuav/PyThrust/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/Setuav/PyThrust/actions/workflows/ci-cd.yml)
[![Docs](https://github.com/Setuav/PyThrust/actions/workflows/docs.yml/badge.svg)](https://github.com/Setuav/PyThrust/actions/workflows/docs.yml)
[![Documentation](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://setuav.github.io/PyThrust/)
[![PyPI](https://img.shields.io/pypi/v/setuav-pythrust)](https://pypi.org/project/setuav-pythrust/)
[![Python versions](https://img.shields.io/pypi/pyversions/setuav-pythrust)](https://pypi.org/project/setuav-pythrust/)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)

## About

PyThrust is an open-source framework for electric propulsion system analysis, co-design, and parameter optimization in UAV applications. It can be used for multidisciplinary design optimization (MDO) within OpenMDAO. It includes steady-state performance solvers, auto-tuning calibration tools to fit manufacturer test data, and database search tools to map theoretical designs onto real-world brushless motor and propeller catalogs.

## Feature Visuals

| System Resistance Calibration | OpenMDAO Hover Co-Design |
| :---: | :---: |
| ![System Resistance Calibration](docs/images/calibration_results.png) | ![OpenMDAO Hover Co-Design](docs/images/optimize_and_plot_results.png) |
| **Empirical Propeller Database** | **Hover Efficiency Map** |
| ![Empirical Propeller Database](docs/images/propeller_coefficients.png) | ![Hover Efficiency Map](docs/images/efficiency_heatmap.png) |

## Documentation

The full documentation is available at:

**https://setuav.github.io/PyThrust/**

Key sections:

- [Getting Started](https://setuav.github.io/PyThrust/getting_started/)
- [Propulsion Solver](https://setuav.github.io/PyThrust/usage/)
- [Motor Calibration](https://setuav.github.io/PyThrust/motor_calibration/)
- [Examples](https://setuav.github.io/PyThrust/examples/)
- [Propulsion and Battery Theory](https://setuav.github.io/PyThrust/theory/)
- [Component Databases](https://setuav.github.io/PyThrust/databases/)

## License

PyThrust is licensed under the Apache License, Version 2.0 (the "License"). See [LICENSE](https://github.com/Setuav/PyThrust/blob/main/LICENSE) for the full license.

## Copyright

Copyright (c) 2026 Setuav. All rights reserved.
