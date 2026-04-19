"""Tests for the pure-logic soil calculator.

Goal: 100 % line + branch coverage. The module has zero Home Assistant
imports and is exercised purely with stdlib + pytest.
"""

from __future__ import annotations

import math

import pytest

from custom_components.cleanliness_tracker.soil_calculator import (
    apply_delta,
    compute_score_delta,
)

# ---------------------------------------------------------------------------
# compute_score_delta
# ---------------------------------------------------------------------------


class TestComputeScoreDelta:
    def test_zero_seconds_yields_zero_delta(self):
        assert compute_score_delta(0.0, 0.5) == 0.0

    def test_zero_weight_yields_zero_delta(self):
        assert compute_score_delta(600.0, 0.0) == 0.0

    def test_one_minute_with_default_weight(self):
        # 60 s * (0.5 / min) = 0.5
        assert compute_score_delta(60.0, 0.5) == pytest.approx(0.5)

    def test_ten_minutes_with_default_weight(self):
        # 600 s * (0.5 / min) = 5.0
        assert compute_score_delta(600.0, 0.5) == pytest.approx(5.0)

    def test_fractional_minute(self):
        # 30 s * (0.5 / min) = 0.25
        assert compute_score_delta(30.0, 0.5) == pytest.approx(0.25)

    def test_high_weight(self):
        # 30 s * (2.0 / min) = 1.0
        assert compute_score_delta(30.0, 2.0) == pytest.approx(1.0)

    def test_long_session(self):
        # 8 h = 28800 s, weight 0.5 → 240.0 (caller has to cap)
        assert compute_score_delta(28800.0, 0.5) == pytest.approx(240.0)

    @pytest.mark.parametrize("seconds", [-0.0001, -1.0, -1000.0])
    def test_negative_seconds_raise(self, seconds: float):
        with pytest.raises(ValueError, match="presence_seconds"):
            compute_score_delta(seconds, 0.5)

    @pytest.mark.parametrize("weight", [-0.0001, -0.5, -10.0])
    def test_negative_weight_raises(self, weight: float):
        with pytest.raises(ValueError, match="weight_per_minute"):
            compute_score_delta(60.0, weight)

    def test_nan_seconds_raises(self):
        with pytest.raises(ValueError, match="presence_seconds"):
            compute_score_delta(math.nan, 0.5)

    def test_nan_weight_raises(self):
        with pytest.raises(ValueError, match="weight_per_minute"):
            compute_score_delta(60.0, math.nan)


# ---------------------------------------------------------------------------
# apply_delta
# ---------------------------------------------------------------------------


class TestApplyDelta:
    def test_zero_delta_returns_current(self):
        assert apply_delta(42.0, 0.0) == 42.0

    def test_simple_addition(self):
        assert apply_delta(10.0, 5.0) == pytest.approx(15.0)

    def test_caps_at_default_100(self):
        assert apply_delta(95.0, 10.0) == 100.0

    def test_exact_cap_returns_cap(self):
        assert apply_delta(80.0, 20.0) == 100.0

    def test_already_at_cap_stays_at_cap(self):
        assert apply_delta(100.0, 5.0) == 100.0

    def test_custom_cap(self):
        assert apply_delta(40.0, 30.0, cap=50.0) == 50.0

    def test_starts_at_zero(self):
        assert apply_delta(0.0, 25.0) == 25.0

    @pytest.mark.parametrize("current", [-0.001, -1.0, -100.0])
    def test_negative_current_score_raises(self, current: float):
        with pytest.raises(ValueError, match="current_score"):
            apply_delta(current, 5.0)

    @pytest.mark.parametrize("delta", [-0.001, -1.0, -50.0])
    def test_negative_delta_raises(self, delta: float):
        with pytest.raises(ValueError, match="delta"):
            apply_delta(50.0, delta)

    @pytest.mark.parametrize("cap", [0.0, -0.001, -100.0])
    def test_non_positive_cap_raises(self, cap: float):
        with pytest.raises(ValueError, match="cap"):
            apply_delta(10.0, 5.0, cap=cap)

    def test_current_above_cap_clamps_to_cap(self):
        # Defensive: if a stale persisted score exceeds the cap (e.g. after
        # a config change that lowered cap), clamp instead of growing further.
        assert apply_delta(120.0, 0.0, cap=100.0) == 100.0

    def test_nan_current_raises(self):
        with pytest.raises(ValueError, match="current_score"):
            apply_delta(math.nan, 5.0)

    def test_nan_delta_raises(self):
        with pytest.raises(ValueError, match="delta"):
            apply_delta(50.0, math.nan)

    def test_nan_cap_raises(self):
        with pytest.raises(ValueError, match="cap"):
            apply_delta(10.0, 5.0, cap=math.nan)
