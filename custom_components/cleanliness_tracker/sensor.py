"""Sensor platform: per-room cleanliness score and last-cleaned datetime."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .tracker import RoomTracker


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create sensors for every room tracker in this entry.

    Added per subentry so the entity + device registries record the
    subentry link. Adding all entities in a single batch without the
    ``config_subentry_id`` kwarg would register the device under the
    entry's "no subentry" bucket.
    """
    trackers: dict[str, RoomTracker] = hass.data[DOMAIN][entry.entry_id]["trackers"]
    for room_id, tracker in trackers.items():
        async_add_entities(
            [
                _ScoreSensor(entry.entry_id, room_id, tracker),
                _LastCleanedSensor(entry.entry_id, room_id, tracker),
            ],
            config_subentry_id=room_id,
        )


class _RoomEntityBase(SensorEntity):
    """Common plumbing for per-room sensors.

    * `_attr_should_poll = False` — we are pushed by the tracker.
    * `_attr_has_entity_name = True` — entity friendly-names use the
      `translation_key` rather than a manually concatenated string.
    """

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, entry_id: str, room_id: str, tracker: RoomTracker) -> None:
        self._entry_id = entry_id
        self._room_id = room_id
        self._tracker = tracker
        self._unsub: object | None = None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}.{room_id}")},
            name=tracker.config["area_id"],
            manufacturer="simon42",
            model="Cleanliness Tracker Room",
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to tracker updates so the sensor re-renders on score change."""
        self._unsub = self._tracker.add_update_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Drop the tracker subscription on entity removal."""
        if self._unsub is not None:
            self._unsub()  # type: ignore[operator]
            self._unsub = None


class _ScoreSensor(_RoomEntityBase):
    """0-100 % cleanliness score for one room."""

    _attr_translation_key = "score"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, entry_id: str, room_id: str, tracker: RoomTracker) -> None:
        super().__init__(entry_id, room_id, tracker)
        self._attr_unique_id = f"{entry_id}.{room_id}.score"

    @property
    def native_value(self) -> float:
        return round(self._tracker.score, 2)


class _LastCleanedSensor(_RoomEntityBase):
    """Datetime of the last `mark_cleaned` call for one room."""

    _attr_translation_key = "last_cleaned"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, entry_id: str, room_id: str, tracker: RoomTracker) -> None:
        super().__init__(entry_id, room_id, tracker)
        self._attr_unique_id = f"{entry_id}.{room_id}.last_cleaned"

    @property
    def native_value(self) -> datetime | None:
        return self._tracker.last_cleaned_at
