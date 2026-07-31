"""Transform functions for the mapping engine.

Each transform takes a value and optional parameters, returns the transformed value.
"""

from typing import Any, Optional


def identity(value: Any, **kwargs) -> Any:
    """Pass through unchanged."""
    return value


def clamp(value: Any, min_val: float = 0.0, max_val: float = 1.0, **kwargs) -> Any:
    """Clip value to [min_val, max_val] range."""
    if value is None:
        return None
    try:
        v = float(value)
        return max(min_val, min(max_val, v))
    except (TypeError, ValueError):
        return value


def scale(value: Any, factor: float = 1.0, **kwargs) -> Any:
    """Multiply value by factor."""
    if value is None:
        return None
    try:
        return float(value) * factor
    except (TypeError, ValueError):
        return value


def round_value(value: Any, decimals: int = 4, **kwargs) -> Any:
    """Round to N decimal places."""
    if value is None:
        return None
    try:
        return round(float(value), decimals)
    except (TypeError, ValueError):
        return value


# Registry of available transforms
TRANSFORMS = {
    "identity": identity,
    "clamp": clamp,
    "scale": scale,
    "round": round_value,
}


def apply_transform(transform_name: str, value: Any, params: Optional[dict] = None) -> Any:
    """Apply a named transform with optional parameters.

    Args:
        transform_name: Key in the TRANSFORMS registry.
        value: The value to transform.
        params: Optional dict of kwargs passed to the transform function.

    Returns:
        Transformed value.

    Raises:
        ValueError: If transform_name is not recognized.
    """
    func = TRANSFORMS.get(transform_name)
    if func is None:
        raise ValueError(f"Unknown transform: {transform_name}")
    return func(value, **(params or {}))
