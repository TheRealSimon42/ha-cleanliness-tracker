"""Typed data models for cleanliness_tracker.

Two layers:

* :class:`RoomConfig` is what the config-flow subentry produces and what
  ``__init__.py`` hands down to the per-room tracker. Immutable in spirit.
* :class:`RoomState` is what the :class:`CleanlinessStore` persists. All
  datetime-shaped fields are stored as ISO-8601 strings (with timezone) so
  the JSON-backed store stays roundtrip-safe.

Authoritative spec: ``docs/ARCHITECTURE.md`` ("Persistence-Schema").
"""

from __future__ import annotations

from typing import TypedDict

__all__ = [
    "RoomConfig",
    "RoomState",
    "StoredData",
]


class RoomConfig(TypedDict):
    """Per-room configuration produced by the config-flow subentry.

    Attributes:
        id: Stable identifier of the subentry. Used as the room key in the
            store and as part of the entity unique-id.
        area_id: The HA area the room belongs to. Used by the blueprint to
            target ``vacuum.clean_area``.
        presence_entity_id: The presence/motion/occupancy entity that drives
            the score. Referenced by ``entity_id`` (never ``device_id``).
        threshold: Score above which the room is considered "due" (0..100).
        weight_per_minute: Score increment per minute of presence.
    """

    id: str
    area_id: str
    presence_entity_id: str
    threshold: float
    weight_per_minute: float


class RoomState(TypedDict):
    """Per-room mutable state — what gets persisted to the store.

    All datetime fields are ISO-8601 strings *with* timezone. ``None``
    indicates "not set yet" (e.g. presence is currently off, or the room
    has never been marked cleaned).
    """

    current_score: float
    presence_started_at: str | None
    last_cleaned_at: str | None
    last_scored_at: str | None


class StoredData(TypedDict):
    """Top-level shape of the JSON document persisted by the store."""

    rooms: dict[str, RoomState]
