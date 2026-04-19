"""Per-room tracker — owns presence state and computes score updates.

The tracker is **independent of any Home Assistant runtime API** beyond the
TypedDicts in :mod:`models`. It accepts ``datetime`` instances from the
caller (which sources them via ``homeassistant.util.dt``) and returns
score / "due" snapshots for the sensors. Persistence is handled separately
by :class:`CleanlinessStore`.

Authoritative spec: ``docs/SCORE_MODEL.md``.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from .const import DEFAULT_PRESENCE_WEIGHT, DEFAULT_THRESHOLD, SCORE_CAP
from .models import RoomConfig, RoomState
from .soil_calculator import apply_delta, compute_score_delta

__all__ = ["RoomTracker"]


def _empty_state() -> RoomState:
    """Return the RoomState used for a freshly added room."""
    return {
        "current_score": 0.0,
        "presence_started_at": None,
        "last_cleaned_at": None,
        "last_scored_at": None,
    }


def _parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO-8601 string to a tz-aware datetime, or return ``None``."""
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        # Defensive: the store contract is "ISO-8601 with timezone", but if a
        # naive value sneaks in (e.g. legacy data, hand-edited file), tag it
        # as UTC rather than crashing the integration.
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _to_iso(value: datetime) -> str:
    """Serialise a tz-aware datetime to ISO-8601.

    All call sites validate timezone-awareness via :meth:`RoomTracker._require_aware`
    *before* serialising, so this helper assumes the precondition holds.
    """
    return value.isoformat()


class RoomTracker:
    """In-memory per-room state plus presence/score lifecycle methods.

    Construction takes a :class:`RoomConfig` (immutable across the lifetime
    of the tracker) and an optional :class:`RoomState` snapshot loaded from
    the store. All time arguments must be tz-aware ``datetime`` instances —
    pass ``homeassistant.util.dt.utcnow()`` from the integration setup.
    """

    def __init__(
        self,
        config: RoomConfig,
        state: RoomState | None = None,
    ) -> None:
        """Initialise a tracker.

        Args:
            config: Per-room configuration (area, presence entity, threshold,
                weight). Treated as read-only.
            state: Optional persisted state. ``None`` means "fresh room";
                a default zero-score state will be created.
        """
        self._config = config
        self._state: RoomState = state if state is not None else _empty_state()

    # ------------------------------------------------------------------
    # Read-only views
    # ------------------------------------------------------------------

    @property
    def config(self) -> RoomConfig:
        """Return the room configuration."""
        return self._config

    @property
    def state(self) -> RoomState:
        """Return the current persisted-shape state.

        Callers may pass the returned dict to :meth:`CleanlinessStore.set_room_state`.
        Mutations to the returned dict mutate the tracker's internal state —
        treat as read-only.
        """
        return self._state

    @property
    def score(self) -> float:
        """Current score (0..SCORE_CAP)."""
        return self._state["current_score"]

    @property
    def is_due(self) -> bool:
        """``True`` once the score has reached or passed the configured threshold."""
        threshold = self._config.get("threshold", DEFAULT_THRESHOLD)
        return self._state["current_score"] >= threshold

    @property
    def last_cleaned_at(self) -> datetime | None:
        """Datetime of the last :meth:`mark_cleaned` call, or ``None``."""
        return _parse_iso(self._state["last_cleaned_at"])

    @property
    def is_presence_active(self) -> bool:
        """``True`` while a presence interval is open (off-event still pending)."""
        return self._state["presence_started_at"] is not None

    # ------------------------------------------------------------------
    # Lifecycle methods
    # ------------------------------------------------------------------

    def on_presence_start(self, now: datetime) -> None:
        """Record the start of a presence interval.

        Idempotent: if a presence interval is already open (no off-event
        observed since the last on-event), the original start time is kept.
        This avoids losing accrued presence when HA emits duplicate
        ``on``-events for noisy sensors.
        """
        self._require_aware(now)
        if self._state["presence_started_at"] is not None:
            return
        self._state["presence_started_at"] = _to_iso(now)
        self._state["last_scored_at"] = _to_iso(now)

    def on_presence_end(self, now: datetime) -> None:
        """Close an open presence interval and apply the accrued score delta.

        No-op if no presence interval is currently open.
        """
        self._require_aware(now)
        started_iso = self._state["presence_started_at"]
        if started_iso is None:
            return
        anchor = self._scoring_anchor(started_iso)
        self._accrue_from(anchor, now)
        self._state["presence_started_at"] = None
        self._state["last_scored_at"] = None

    def periodic_update(self, now: datetime) -> None:
        """Apply a partial score delta for an *ongoing* presence interval.

        Triggered by the integration's periodic tick so the score keeps
        growing during long presence sessions even when no state-change
        events fire. No-op if presence is currently inactive.
        """
        self._require_aware(now)
        started_iso = self._state["presence_started_at"]
        if started_iso is None:
            return
        anchor = self._scoring_anchor(started_iso)
        if now <= anchor:
            return
        self._accrue_from(anchor, now)
        self._state["last_scored_at"] = _to_iso(now)

    def mark_cleaned(self, now: datetime) -> None:
        """Reset the score to zero and stamp ``last_cleaned_at``.

        Leaves a presence interval untouched — the user may still be in the
        room when the cleaner is done — but resets the scoring anchor so we
        do not double-count the seconds that already produced the score
        we just wiped.
        """
        self._require_aware(now)
        self._state["current_score"] = 0.0
        self._state["last_cleaned_at"] = _to_iso(now)
        if self._state["presence_started_at"] is not None:
            self._state["last_scored_at"] = _to_iso(now)

    def reset(self, now: datetime) -> None:
        """Set the score to zero without touching ``last_cleaned_at``.

        Useful for ``cleanliness_tracker.reset`` when the user just wants
        to clear an erroneous accrual (e.g. after a presence sensor false
        positive) without claiming the room was actually cleaned.
        """
        self._require_aware(now)
        self._state["current_score"] = 0.0
        if self._state["presence_started_at"] is not None:
            self._state["last_scored_at"] = _to_iso(now)

    def set_score(self, score: float, *, cap: float = SCORE_CAP) -> None:
        """Override the current score (manual ``set_score`` service).

        Args:
            score: Target value. Must be a finite number in ``[0, cap]``.
            cap: Upper bound for validation (defaults to :data:`SCORE_CAP`).

        Raises:
            ValueError: If ``score`` is NaN, negative, or above ``cap``.
        """
        if math.isnan(score) or score < 0 or score > cap:
            raise ValueError(
                f"score must be a finite value in [0, {cap}], got {score!r}",
            )
        self._state["current_score"] = float(score)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _scoring_anchor(self, started_iso: str) -> datetime:
        """Return the timestamp from which the next delta should be measured."""
        last_scored = _parse_iso(self._state["last_scored_at"])
        if last_scored is not None:
            return last_scored
        # Fallback: legacy state without last_scored_at — fall back to
        # presence_started_at so we still accrue something rather than
        # silently dropping the interval.
        return _parse_iso(started_iso) or datetime.now(UTC)

    def _accrue_from(self, anchor: datetime, now: datetime) -> None:
        """Add the score delta for the elapsed seconds between anchor and now."""
        elapsed = max(0.0, (now - anchor).total_seconds())
        if elapsed == 0.0:
            return
        weight = self._config.get("weight_per_minute", DEFAULT_PRESENCE_WEIGHT)
        delta = compute_score_delta(elapsed, weight)
        self._state["current_score"] = apply_delta(
            self._state["current_score"],
            delta,
        )

    @staticmethod
    def _require_aware(value: datetime) -> None:
        """Reject naive datetimes early — HA always passes tz-aware values."""
        if value.tzinfo is None:
            raise ValueError(
                "RoomTracker received a naive datetime; pass a tz-aware "
                "value (homeassistant.util.dt.utcnow()).",
            )
