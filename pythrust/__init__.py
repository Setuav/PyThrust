"""PyThrust package."""

from pathlib import Path

__version__ = "0.5.0"


def dataset_dir() -> Path:
    """Return the directory of the bundled example battery cell dataset."""
    return Path(__file__).resolve().parent / "data"

