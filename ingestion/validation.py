"""Validation rule engine for the mapping engine.

Validates transformed values against configurable rules before writing to the metric store.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional


def validate_range(value: Any, min_val: float = None, max_val: float = None) -> tuple[bool, Optional[str]]:
    """Check if value is within [min_val, max_val].

    Returns:
        (True, None) if valid, (False, reason) if invalid.
    """
    if value is None:
        return False, "Value is None"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False, f"Value is not numeric: {value!r}"

    if min_val is not None and v < min_val:
        return False, f"Value {v} below minimum {min_val}"
    if max_val is not None and v > max_val:
        return False, f"Value {v} above maximum {max_val}"
    return True, None


def validate_not_null(value: Any) -> tuple[bool, Optional[str]]:
    """Check that value is not None or empty string."""
    if value is None or value == "":
        return False, "Value is null or empty"
    return True, None


def validate_numeric(value: Any) -> tuple[bool, Optional[str]]:
    """Check that value is numeric (int or float)."""
    if value is None:
        return False, "Value is None"
    try:
        float(value)
        return True, None
    except (TypeError, ValueError):
        return False, f"Value is not numeric: {value!r}"


def validate_timestamp_not_future(timestamp: str, tolerance_minutes: int = 5) -> tuple[bool, Optional[str]]:
    """Check that timestamp is not unreasonably in the future.

    Args:
        timestamp: ISO 8601 timestamp string.
        tolerance_minutes: How far in the future is acceptable.

    Returns:
        (True, None) if valid, (False, reason) if invalid.
    """
    try:
        ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        max_allowed = datetime.now(timezone.utc) + timedelta(minutes=tolerance_minutes)
        if ts > max_allowed:
            return False, f"Timestamp {timestamp} is in the future"
        return True, None
    except (ValueError, AttributeError):
        return False, f"Invalid timestamp format: {timestamp!r}"


# Rule registry mapping rule names to validator functions
VALIDATION_RULES = {
    "range": validate_range,
    "not_null": validate_not_null,
    "numeric": validate_numeric,
    "timestamp_not_future": validate_timestamp_not_future,
}


def run_validation_rules(rules: list[dict], value: Any, timestamp: str = None) -> tuple[bool, Optional[str]]:
    """Run a list of validation rules against a value.

    Args:
        rules: List of rule dicts, each with "rule" key and optional params.
            Example: [{"rule": "range", "min": 0, "max": 1}, {"rule": "not_null"}]
        value: The value to validate.
        timestamp: Optional timestamp for timestamp-related rules.

    Returns:
        (True, None) if all rules pass, (False, first_failure_reason) on first failure.
    """
    for rule_def in rules:
        rule_name = rule_def.get("rule")
        if rule_name not in VALIDATION_RULES:
            continue

        if rule_name == "range":
            ok, reason = validate_range(value, rule_def.get("min"), rule_def.get("max"))
        elif rule_name == "not_null":
            ok, reason = validate_not_null(value)
        elif rule_name == "numeric":
            ok, reason = validate_numeric(value)
        elif rule_name == "timestamp_not_future":
            ok, reason = validate_timestamp_not_future(
                timestamp or "", rule_def.get("tolerance_minutes", 5)
            )
        else:
            continue

        if not ok:
            return False, reason

    return True, None
