"""Binary sensor platform: per-room 'due' indicator (score >= threshold)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .tracker import RoomTracker


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one due-binary-sensor per room tracker."""
    trackers: dict[str, RoomTracker] = hass.data[DOMAIN][entry.entry_id]["trackers"]
    async_add_entities(
        _DueBinarySensor(entry.entry_id, room_id, tracker)
        for room_id, tracker in trackers.items()
    )


class _DueBinarySensor(BinarySensorEntity):
    """`on` once the room's score reaches the configured threshold."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "due"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, entry_id: str, room_id: str, tracker: RoomTracker) -> None:
        self._entry_id = entry_id
        self._room_id = room_id
        self._tracker = tracker
        self._unsub: object | None = None
        self._attr_unique_id = f"{entry_id}.{room_id}.due"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}.{room_id}")},
            name=tracker.config["area_id"],
            manufacturer="simon42",
            model="Cleanliness Tracker Room",
        )

    async def async_added_to_hass(self) -> None:
        self._unsub = self._tracker.add_update_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub is not None:
            self._unsub()  # type: ignore[operator]
            self._unsub = None

    @property
    def is_on(self) -> bool:
        return self._tracker.is_due
