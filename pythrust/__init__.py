"""PyThrust package."""

from pathlib import Path

__version__ = "0.4.2"


def dataset_dir() -> Path:
    """Return the directory of the bundled example battery cell dataset."""
    return Path(__file__).resolve().parent / "data"

