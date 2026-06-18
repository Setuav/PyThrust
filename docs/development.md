# Development & Testing

This guide covers local development, tests, examples, and documentation publishing.

## Local Environment

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .[plot,openmdao,dev,docs]
```

## Run Tests

```bash
pytest
```

The CI workflow runs the test suite on Python 3.10, 3.11, and 3.12.

## Run Example Workflows

```bash
PYTHONPATH=. python examples/select_motor.py
PYTHONPATH=. python examples/calibrate_from_datasheet.py
PYTHONPATH=. python examples/optimize_and_plot_propulsion.py
```

See [Examples](examples.md) for a user-facing walkthrough of each script.

Generated plots are written under `docs/images/` and are used by the documentation site.

## Documentation Site

PyThrust uses MkDocs Material for a clean, searchable static documentation site.

Serve locally:

```bash
mkdocs serve
```

Build static HTML:

```bash
mkdocs build --strict
```

Deploy manually to GitHub Pages:

```bash
mkdocs gh-deploy --force
```

## GitHub Pages Publishing

The `Deploy Docs` workflow publishes the MkDocs site when documentation files, `mkdocs.yml`, or the workflow itself change on `main`.

In the GitHub repository settings, configure Pages to publish from the `gh-pages` branch after the first successful deploy.
