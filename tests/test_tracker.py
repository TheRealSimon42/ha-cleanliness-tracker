"""Tests for RoomTracker.

Time is controlled with ``freezegun`` so we can reason about deltas down
to the second without flake.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from freezegun import freeze_time

from custom_components.cleanliness_tracker.const import (
    DEFAULT_PRESENCE_WEIGHT,
    DEFAULT_THRESHOLD,
    SCORE_CAP,
)
from custom_components.cleanliness_tracker.models import RoomConfig, RoomState
from custom_components.cleanliness_tracker.tracker import RoomTracker

# Reference epoch used by every test that does not need a specific clock.
T0 = datetime(2026, 4, 19, 12, 0, 0, tzinfo=UTC)


def _make_config(**overrides: Any) -> RoomConfig:
    base: dict[str, Any] = {
        "id": "wohnzimmer",
        "area_id": "wohnzimmer",
        "presence_entity_id": "binary_sensor.wohnzimmer_presence",
        "threshold": DEFAULT_THRESHOLD,
        "weight_per_minute": DEFAULT_PRESENCE_WEIGHT,
    }
    base.update(overrides)
    return base  # type: ignore[return-value]


def _make_state(**overrides: Any) -> RoomState:
    base: dict[str, Any] = {
        "current_score": 0.0,
        "presence_started_at": None,
        "last_cleaned_at": None,
        "last_scored_at": None,
    }
    base.update(overrides)
    return base  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Construction + read-only views
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_defaults_to_empty_state(self):
        tracker = RoomTracker(_make_config())
        assert tracker.score == 0.0
        assert tracker.is_presence_active is False
        assert tracker.last_cleaned_at is None
        assert tracker.is_due is False

    def test_exposes_config(self):
        cfg = _make_config(id="bath", area_id="bath")
        tracker = RoomTracker(cfg)
        assert tracker.config is cfg

    def test_loads_provided_state(self):
        state = _make_state(
            current_score=42.0,
            last_cleaned_at="2026-04-18T08:00:00+00:00",
        )
        tracker = RoomTracker(_make_config(), state)
        assert tracker.score == 42.0
        assert tracker.last_cleaned_at == datetime(2026, 4, 18, 8, 0, 0, tzinfo=UTC)

    def test_is_due_uses_configured_threshold(self):
        tracker = RoomTracker(
            _make_config(threshold=50.0),
            _make_state(current_score=49.99),
        )
        assert tracker.is_due is False
        tracker.set_score(50.0)
        assert tracker.is_due is True

    def test_naive_last_cleaned_in_state_is_treated_as_utc(self):
        # Defensive parsing for legacy/hand-edited persisted data.
        tracker = RoomTracker(
            _make_config(),
            _make_state(last_cleaned_at="2026-04-18T08:00:00"),
        )
        assert tracker.last_cleaned_at == datetime(2026, 4, 18, 8, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# on_presence_start / on_presence_end
# ---------------------------------------------------------------------------


class TestPresenceStart:
    def test_marks_presence_active(self):
        tracker = RoomTracker(_make_config())
        tracker.on_presence_start(T0)
        assert tracker.is_presence_active is True
        assert tracker.state["presence_started_at"] == T0.isoformat()
        assert tracker.state["last_scored_at"] == T0.isoformat()

    def test_idempotent_when_already_active(self):
        tracker = RoomTracker(_make_config())
        tracker.on_presence_start(T0)
        tracker.on_presence_start(T0 + timedelta(minutes=1))  # duplicate event
        # First start time wins so we don't lose the accrued seconds.
        assert tracker.state["presence_started_at"] == T0.isoformat()

    def test_rejects_naive_datetime(self):
        tracker = RoomTracker(_make_config())
        with pytest.raises(ValueError, match="naive"):
            tracker.on_presence_start(datetime(2026, 4, 19, 12, 0, 0))


class TestPresenceEnd:
    def test_no_presence_no_score_change(self):
        tracker = RoomTracker(_make_config())
        tracker.on_presence_end(T0)  # no open interval
        assert tracker.score == 0.0
        assert tracker.is_presence_active is False

    def test_full_interval_adds_delta(self):
        tracker = RoomTracker(_make_config())
        tracker.on_presence_start(T0)
        tracker.on_presence_end(T0 + timedelta(minutes=10))
        # 10 min * 0.5 = 5.0
        assert tracker.score == pytest.approx(5.0)
        assert tracker.is_presence_active is False
        assert tracker.state["last_scored_at"] is None

    def test_zero_duration_interval(self):
        tracker = RoomTracker(_make_config())
        tracker.on_presence_start(T0)
        tracker.on_presence_end(T0)  # noisy sensor: on/off in the same tick
        assert tracker.score == 0.0
        assert tracker.is_presence_active is False

    def test_caps_score_at_100(self):
        tracker = RoomTracker(_make_config())
        tracker.on_presence_start(T0)
        # 8 hours of presence at 0.5/min would yield 240, must clamp to 100.
        tracker.on_presence_end(T0 + timedelta(hours=8))
        assert tracker.score == SCORE_CAP


class TestPeriodicUpdate:
    def test_noop_when_presence_inactive(self):
        tracker = RoomTracker(_make_config())
        tracker.periodic_update(T0)
        assert tracker.score == 0.0

    def test_partial_delta_during_active_presence(self):
        tracker = RoomTracker(_make_config())
        tracker.on_presence_start(T0)
        tracker.periodic_update(T0 + timedelta(minutes=5))
        # 5 min * 0.5 = 2.5
        assert tracker.score == pytest.approx(2.5)
        assert (
            tracker.state["last_scored_at"] == (T0 + timedelta(minutes=5)).isoformat()
        )

    def test_consecutive_ticks_do_not_double_count(self):
        tracker = RoomTracker(_make_config())
        tracker.on_presence_start(T0)
        tracker.periodic_update(T0 + timedelta(minutes=5))  # +2.5
        tracker.periodic_update(T0 + timedelta(minutes=10))  # +2.5 (not +5.0)
        assert tracker.score == pytest.approx(5.0)

    def test_end_after_periodic_uses_last_scored(self):
        tracker = RoomTracker(_make_config())
        tracker.on_presence_start(T0)
        tracker.periodic_update(T0 + timedelta(minutes=4))  # +2.0
        tracker.on_presence_end(T0 + timedelta(minutes=10))  # +3.0 (6 more min)
        assert tracker.score == pytest.approx(5.0)

    def test_clock_going_backwards_is_a_noop(self):
        tracker = RoomTracker(_make_config())
        tracker.on_presence_start(T0 + timedelta(minutes=5))
        tracker.periodic_update(T0)  # `now` < anchor — nothing accrues
        assert tracker.score == 0.0

    def test_legacy_state_without_last_scored_uses_started_at(self):
        # Persisted state from a prior version may have presence_started_at
        # set but never recorded last_scored_at. The tracker should still
        # accrue from started_at rather than dropping the interval.
        state = _make_state(
            current_score=0.0,
            presence_started_at=T0.isoformat(),
            last_scored_at=None,
        )
        tracker = RoomTracker(_make_config(), state)
        tracker.periodic_update(T0 + timedelta(minutes=10))  # 10 * 0.5 = 5
        assert tracker.score == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# mark_cleaned / reset / set_score
# ---------------------------------------------------------------------------


class TestMarkCleaned:
    def test_resets_score_and_stamps_last_cleaned(self):
        tracker = RoomTracker(_make_config(), _make_state(current_score=80.0))
        tracker.mark_cleaned(T0)
        assert tracker.score == 0.0
        assert tracker.last_cleaned_at == T0

    def test_keeps_presence_open_but_resets_anchor(self):
        tracker = RoomTracker(_make_config())
        tracker.on_presence_start(T0)
        tracker.periodic_update(T0 + timedelta(minutes=10))  # score = 5.0
        tracker.mark_cleaned(T0 + timedelta(minutes=10))
        # Clean while still in the room: presence stays active so the next
        # tick keeps measuring, but does not double-count the wiped seconds.
        assert tracker.is_presence_active is True
        tracker.periodic_update(T0 + timedelta(minutes=15))
        assert tracker.score == pytest.approx(2.5)


class TestReset:
    def test_resets_score_without_changing_last_cleaned(self):
        tracker = RoomTracker(
            _make_config(),
            _make_state(
                current_score=80.0,
                last_cleaned_at="2026-04-18T08:00:00+00:00",
            ),
        )
        original_cleaned = tracker.last_cleaned_at
        tracker.reset(T0)
        assert tracker.score == 0.0
        assert tracker.last_cleaned_at == original_cleaned

    def test_reset_during_presence_resets_scoring_anchor(self):
        tracker = RoomTracker(_make_config())
        tracker.on_presence_start(T0)
        tracker.periodic_update(T0 + timedelta(minutes=10))  # score = 5
        tracker.reset(T0 + timedelta(minutes=10))
        tracker.periodic_update(T0 + timedelta(minutes=15))  # +2.5, not +7.5
        assert tracker.score == pytest.approx(2.5)


class TestSetScore:
    @pytest.mark.parametrize("value", [0.0, 25.0, 80.0, 100.0])
    def test_accepts_valid_values(self, value: float):
        tracker = RoomTracker(_make_config())
        tracker.set_score(value)
        assert tracker.score == value

    @pytest.mark.parametrize("value", [-0.001, 100.001, math.nan])
    def test_rejects_invalid_values(self, value: float):
        tracker = RoomTracker(_make_config())
        with pytest.raises(ValueError, match="score"):
            tracker.set_score(value)

    def test_respects_custom_cap(self):
        tracker = RoomTracker(_make_config())
        tracker.set_score(50.0, cap=50.0)
        assert tracker.score == 50.0
        with pytest.raises(ValueError, match="score"):
            tracker.set_score(50.001, cap=50.0)


# ---------------------------------------------------------------------------
# Defaults fallback when config dict misses optional keys
# ---------------------------------------------------------------------------


class TestConfigDefaults:
    def test_falls_back_to_default_threshold_when_missing(self):
        cfg: RoomConfig = {  # type: ignore[typeddict-item]
            "id": "x",
            "area_id": "x",
            "presence_entity_id": "binary_sensor.x",
            "weight_per_minute": DEFAULT_PRESENCE_WEIGHT,
            # threshold deliberately absent
        }
        tracker = RoomTracker(cfg, _make_state(current_score=DEFAULT_THRESHOLD))
        assert tracker.is_due is True

    def test_falls_back_to_default_weight_when_missing(self):
        cfg: RoomConfig = {  # type: ignore[typeddict-item]
            "id": "x",
            "area_id": "x",
            "presence_entity_id": "binary_sensor.x",
            "threshold": DEFAULT_THRESHOLD,
            # weight_per_minute deliberately absent
        }
        tracker = RoomTracker(cfg)
        tracker.on_presence_start(T0)
        tracker.on_presence_end(T0 + timedelta(minutes=10))
        # 10 min * default 0.5 = 5.0
        assert tracker.score == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# Cooperate with freezegun for callers that prefer a frozen clock
# ---------------------------------------------------------------------------


class TestFreezeTimeIntegration:
    def test_freeze_time_drives_presence_lifecycle(self):
        with freeze_time(T0) as frozen:
            tracker = RoomTracker(_make_config())
            tracker.on_presence_start(datetime.now(UTC))
            frozen.tick(timedelta(minutes=10))
            tracker.on_presence_end(datetime.now(UTC))
        assert tracker.score == pytest.approx(5.0)
