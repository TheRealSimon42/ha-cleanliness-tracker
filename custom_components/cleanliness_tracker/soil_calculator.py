"""Pure-logic soil calculator for ha-cleanliness-tracker.

Authoritative spec: ``docs/SCORE_MODEL.md``.

This module is **free of Home Assistant imports**. It uses only the standard
library and is the single source of truth for the score formulas. All
functions are pure, synchronous, and side-effect free; mutation of inputs
is forbidden. The module is exercised at 100 % line + branch coverage from
plain pytest (see ``tests/test_soil_calculator.py``).
"""

from __future__ import annotations

import math

__all__ = [
    "apply_delta",
    "compute_score_delta",
]

_SECONDS_PER_MINUTE = 60.0


def _validate_finite_non_negative(value: float, name: str) -> None:
    """Raise ``ValueError`` if ``value`` is NaN or strictly negative."""
    if math.isnan(value) or value < 0:
        raise ValueError(f"{name} must be a finite non-negative number, got {value!r}")


def compute_score_delta(
    presence_seconds: float,
    weight_per_minute: float,
) -> float:
    """Compute the score increment for a presence interval.

    ``delta = (presence_seconds / 60) * weight_per_minute``

    Both inputs are interpreted as already-elapsed quantities — no clock is
    consulted here. Callers (the tracker) are responsible for measuring the
    interval against ``homeassistant.util.dt`` and choosing the appropriate
    per-room weight.

    Args:
        presence_seconds: Duration of presence in seconds. Must be finite and
            non-negative.
        weight_per_minute: Weight that converts one minute of presence into a
            score increment. Must be finite and non-negative. Typical default
            is ``0.5``; configurable per room.

    Returns:
        The score increment as a float (no rounding, no cap). The caller is
        responsible for applying any cap via :func:`apply_delta`.

    Raises:
        ValueError: If either argument is NaN or strictly negative.
    """
    _validate_finite_non_negative(presence_seconds, "presence_seconds")
    _validate_finite_non_negative(weight_per_minute, "weight_per_minute")
    return (presence_seconds / _SECONDS_PER_MINUTE) * weight_per_minute


def apply_delta(
    current_score: float,
    delta: float,
    cap: float = 100.0,
) -> float:
    """Add ``delta`` to ``current_score`` and clamp at ``cap``.

    If ``current_score`` already exceeds ``cap`` (e.g. because a persisted
    state was loaded after the cap was lowered via configuration), the result
    is clamped to ``cap`` rather than growing further.

    Args:
        current_score: Score before the increment. Must be finite and
            non-negative. Values above ``cap`` are tolerated and clamped.
        delta: Score increment to apply. Must be finite and non-negative.
            Decreases (e.g. for ``mark_cleaned``) are not modelled here —
            those operations set the score directly via the tracker.
        cap: Upper bound for the resulting score. Must be finite and strictly
            positive. Defaults to ``100.0``.

    Returns:
        ``min(current_score + delta, cap)``.

    Raises:
        ValueError: If any argument is NaN, if ``current_score`` or ``delta``
            is strictly negative, or if ``cap`` is non-positive.
    """
    _validate_finite_non_negative(current_score, "current_score")
    _validate_finite_non_negative(delta, "delta")
    if math.isnan(cap) or cap <= 0:
        raise ValueError(f"cap must be a finite positive number, got {cap!r}")
    return min(current_score + delta, cap)
