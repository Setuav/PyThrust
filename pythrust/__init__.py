"""PyThrust package."""

from pathlib import Path

__version__ = "0.2.2"


def dataset_dir() -> Path:
    """Return the bundled motor/propeller/battery dataset directory."""
    return Path(__file__).resolve().parent / "data"

