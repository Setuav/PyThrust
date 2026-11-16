"""PyThrust package."""

from pathlib import Path

__version__ = "0.4.0"


def dataset_dir() -> Path:
    """Return the bundled motor/propeller/battery dataset directory."""
    return Path(__file__).resolve().parent / "data"

