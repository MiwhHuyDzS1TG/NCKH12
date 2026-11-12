"""Shared JSON-boundary normalization for measured Product V2 evidence."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


def to_jsonable(value: Any) -> Any:
    """Recursively convert supported NumPy containers/scalars to JSON natives.

    Measured numeric values remain numeric. Unsupported objects raise instead
    of being stringified or silently discarded.
    """
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.ndarray):
        return to_jsonable(value.tolist())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: to_jsonable(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(nested) for nested in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
