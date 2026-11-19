# Validation

Accuracy of PyThrust's propeller models against wind-tunnel data. The data is downloaded, not
kept in the repository.

## APC propellers against UIUC measurements

```bash
PYTHONPATH=. python validation/apc_uiuc.py   # downloads to validation/.cache, writes validation/results
PYTHONPATH=. python validation/report.py     # prints tables, writes docs/images/validation
```

`apc_uiuc.py` takes every APC propeller of the
[UIUC Propeller Database](https://m-selig.ae.illinois.edu/props/propDB.html) with static and
forward-flight measurements whose geometry file APC publishes, and compares the measured thrust
and power coefficients with:

- the blade-element model on APC's geometry with NeuralFoil polars, at n_crit 3, 5, 7 and 9;
- the same with the generic section of the QPROP user guide;
- APC's performance table.

n_crit is chosen on every third propeller of each family and the models are compared on the
rest. Operating points are also solved with a fixed motor and battery, with the measured table as
the truth. The results are on the [Validation](../docs/reference/validation.md) page.
