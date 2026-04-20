"""Cleanliness Tracker integration setup + lifecycle wiring.

Event-driven architecture (no DataUpdateCoordinator):

* Build one :class:`RoomTracker` per room subentry, hydrated from the
  per-entry :class:`CleanlinessStore`.
* ``async_track_state_change_event`` for every room's presence entity
  drives ``on_presence_start`` / ``on_presence_end``.
* ``async_track_time_interval`` (every TICK_INTERVAL_SECONDS) calls
  ``periodic_update`` so the score keeps growing during long presence
  sessions even when no events fire.
* Sensors / binary_sensors subscribe to per-tracker update listeners.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_AREA_ID,
    CONF_PRESENCE_ENTITY_ID,
    CONF_THRESHOLD,
    CONF_WEIGHT_PER_MINUTE,
    DEFAULT_PRESENCE_WEIGHT,
    DEFAULT_THRESHOLD,
    DOMAIN,
    SUBENTRY_ROOM,
    TICK_INTERVAL_SECONDS,
)
from .models import RoomConfig
from .services import async_register_services, async_unregister_services
from .storage import CleanlinessStore
from .tracker import RoomTracker

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

PLATFORMS: list[str] = ["sensor", "binary_sensor"]

# State values that mean "presence is on" / "presence is off".  Anything else
# (unknown, unavailable, restoring) is treated as a transient gap and is
# ignored — we don't want a Wi-Fi blip to wipe an open interval.
_PRESENCE_ON: frozenset[str] = frozenset({STATE_ON})
_PRESENCE_OFF: frozenset[str] = frozenset({STATE_OFF})


def _build_room_config(subentry_id: str, data: dict[str, Any]) -> RoomConfig:
    """Project a subentry's raw data dict into a RoomConfig TypedDict."""
    return {
        "id": subentry_id,
        "area_id": data[CONF_AREA_ID],
        "presence_entity_id": data[CONF_PRESENCE_ENTITY_ID],
        "threshold": float(data.get(CONF_THRESHOLD, DEFAULT_THRESHOLD)),
        "weight_per_minute": float(
            data.get(CONF_WEIGHT_PER_MINUTE, DEFAULT_PRESENCE_WEIGHT)
        ),
    }


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a cleanliness_tracker config entry.

    Loads persisted state, builds one tracker per room subentry, wires up
    state-change + tick listeners, and forwards to the sensor platforms.
    """
    store = CleanlinessStore(hass, entry.entry_id)
    persisted = await store.async_load()

    trackers: dict[str, RoomTracker] = {}
    device_reg = dr.async_get(hass)
    for subentry_id, subentry in entry.subentries.items():
        if subentry.subentry_type != SUBENTRY_ROOM:
            continue
        config = _build_room_config(subentry_id, dict(subentry.data))
        trackers[subentry_id] = RoomTracker(config, persisted.get(subentry_id))
        # Migration: v0.1.0 registered the per-room device via DeviceInfo
        # on the entity (no config_subentry_id), which left an (entry_id,
        # None) "orphan" link in config_entries_subentries. The HA UI then
        # shows the device BOTH under its subentry and under a "devices
        # not belonging to any subentry" bucket. Strip that orphan link
        # here; the sensor platform now adds entities per subentry via
        # async_add_entities(..., config_subentry_id=...), so new installs
        # don't create the orphan link in the first place.
        device = device_reg.async_get_device(
            identifiers={(DOMAIN, f"{entry.entry_id}.{subentry_id}")}
        )
        if device is not None and None in device.config_entries_subentries.get(
            entry.entry_id, set()
        ):
            device_reg.async_update_device(
                device.id,
                remove_config_entry_id=entry.entry_id,
                remove_config_subentry_id=None,
            )

    presence_to_room: dict[str, str] = {
        tracker.config["presence_entity_id"]: room_id
        for room_id, tracker in trackers.items()
    }

    async def _save_state() -> None:
        for room_id, tracker in trackers.items():
            store.set_room_state(room_id, tracker.state)
        await store.async_save()

    @callback
    def _on_presence_change(event: Event[EventStateChangedData]) -> None:
        new_state = event.data["new_state"]
        room_id = presence_to_room.get(event.data["entity_id"])
        if room_id is None or new_state is None:
            return
        tracker = trackers[room_id]
        now = dt_util.utcnow()
        if new_state.state in _PRESENCE_ON:
            tracker.on_presence_start(now)
        elif new_state.state in _PRESENCE_OFF:
            tracker.on_presence_end(now)
        else:
            # unknown / unavailable / restoring -> leave the interval as-is
            return
        hass.async_create_task(_save_state())

    @callback
    def _periodic_tick(now: datetime) -> None:
        any_change = False
        for tracker in trackers.values():
            if tracker.is_presence_active:
                tracker.periodic_update(now)
                any_change = True
        if any_change:
            hass.async_create_task(_save_state())

    unsub_state = (
        async_track_state_change_event(
            hass, list(presence_to_room.keys()), _on_presence_change
        )
        if presence_to_room
        else None
    )
    unsub_tick = async_track_time_interval(
        hass, _periodic_tick, timedelta(seconds=TICK_INTERVAL_SECONDS)
    )

    # Subentry lifecycle: HA does NOT automatically reload the config entry
    # when the user adds / edits / removes a room subentry, so the newly
    # added room would be invisible until a manual reload. Wire up an update
    # listener that reloads the entry on any such change.
    unsub_update = entry.add_update_listener(_async_reload_on_update)

    domain_data = hass.data.setdefault(DOMAIN, {})
    is_first_entry = not domain_data
    domain_data[entry.entry_id] = {
        "trackers": trackers,
        "store": store,
        "save_state": _save_state,
        "_unsub_state": unsub_state,
        "_unsub_tick": unsub_tick,
        "_unsub_update": unsub_update,
    }
    if is_first_entry:
        async_register_services(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_reload_on_update(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its subentries / options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Tear down listeners, persist final state, and unload platforms."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unloaded:
        return False

    data = hass.data[DOMAIN].pop(entry.entry_id)
    if data["_unsub_state"] is not None:
        data["_unsub_state"]()
    data["_unsub_tick"]()
    data["_unsub_update"]()

    # Final flush so any in-flight presence interval that ended right before
    # the unload is on disk for the next start.
    await data["save_state"]()

    if not hass.data[DOMAIN]:
        async_unregister_services(hass)
        hass.data.pop(DOMAIN)

    return True


# Re-export STATE_UNKNOWN/STATE_UNAVAILABLE for tests that want to assert
# the listener treats them as no-ops.
__all__ = [
    "PLATFORMS",
    "STATE_UNAVAILABLE",
    "STATE_UNKNOWN",
    "async_setup_entry",
    "async_unload_entry",
]
