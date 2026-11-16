"""PyThrust package."""

from pathlib import Path

__version__ = "0.4.1"


def dataset_dir() -> Path:
    """Return the bundled motor/propeller/battery dataset directory."""
    return Path(__file__).resolve().parent / "data"

