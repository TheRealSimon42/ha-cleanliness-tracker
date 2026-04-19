"""Persistent store for per-room cleanliness state.

One :class:`homeassistant.helpers.storage.Store` per :class:`ConfigEntry`,
keyed ``cleanliness_tracker.<entry_id>``. All datetimes live in the
:class:`RoomState` TypedDict as ISO-8601 strings with timezone, so the
JSON file is roundtrip-safe.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_VERSION
from .models import RoomState, StoredData

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

__all__ = ["CleanlinessStore"]


def _empty_data() -> StoredData:
    """Return a fresh, empty store payload."""
    return {"rooms": {}}


class CleanlinessStore:
    """Wrapper around ``Store`` that handles per-entry persistence.

    The wrapper keeps an in-memory copy of the room states so synchronous
    callers (the tracker, sensors) can read without going through ``await``.
    Writes are explicit via :meth:`async_save`.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialise a store bound to a single config entry.

        Args:
            hass: The Home Assistant instance.
            entry_id: The config-entry identifier; embedded in the storage
                key so multiple entries do not clash.
        """
        self._store: Store[StoredData] = Store(
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}.{entry_id}",
        )
        self._data: StoredData = _empty_data()

    async def async_load(self) -> dict[str, RoomState]:
        """Load persisted room state from disk.

        Returns:
            A copy of the room-id → RoomState mapping. Mutating the returned
            dict does **not** affect the store; use :meth:`set_room_state` /
            :meth:`async_save` to write back.
        """
        loaded = await self._store.async_load()
        self._data = loaded if loaded is not None else _empty_data()
        return copy.deepcopy(self._data["rooms"])

    async def async_save(self) -> None:
        """Persist the current in-memory state to disk."""
        await self._store.async_save(self._data)

    @property
    def rooms(self) -> dict[str, RoomState]:
        """Return a deep, defensive copy of the current rooms map."""
        return copy.deepcopy(self._data["rooms"])

    def get_room_state(self, room_id: str) -> RoomState | None:
        """Return the persisted state for a room, or ``None`` if unknown."""
        return self._data["rooms"].get(room_id)

    def set_room_state(self, room_id: str, state: RoomState) -> None:
        """Replace the persisted state of one room (in-memory; call save)."""
        self._data["rooms"][room_id] = state

    def remove_room(self, room_id: str) -> None:
        """Drop a room from the store (in-memory; call save).

        Quietly returns if the room is not tracked.
        """
        self._data["rooms"].pop(room_id, None)
