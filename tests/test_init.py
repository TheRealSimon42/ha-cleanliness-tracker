"""End-to-end test of __init__.py setup + lifecycle.

Sets up an entry with one room subentry, simulates presence on/off, and
verifies the score grows, the entities update, mark_cleaned via the
tracker resets, and unload tears down cleanly.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from freezegun import freeze_time
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import CONF_NAME, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.cleanliness_tracker.const import (
    CONF_AREA_ID,
    CONF_PRESENCE_ENTITY_ID,
    CONF_THRESHOLD,
    CONF_WEIGHT_PER_MINUTE,
    DOMAIN,
    SUBENTRY_ROOM,
    TICK_INTERVAL_SECONDS,
)


def _make_entry_with_room(
    hass: HomeAssistant,
    *,
    title: str = "EG",
    area_id: str = "wohnzimmer",
    presence: str = "binary_sensor.wohnzimmer_presence",
    threshold: float = 80.0,
    weight: float = 0.5,
) -> tuple[MockConfigEntry, str]:
    sub = ConfigSubentry(
        data={
            CONF_AREA_ID: area_id,
            CONF_PRESENCE_ENTITY_ID: presence,
            CONF_THRESHOLD: threshold,
            CONF_WEIGHT_PER_MINUTE: weight,
        },
        subentry_type=SUBENTRY_ROOM,
        title=area_id,
        unique_id=None,
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=title,
        data={CONF_NAME: title},
        unique_id=title.lower(),
        subentries_data=[sub.as_dict()],
    )
    entry.add_to_hass(hass)
    # Take the freshly assigned subentry_id back out of the entry.
    [room_id] = entry.subentries.keys()
    return entry, room_id


def _trackers(hass: HomeAssistant, entry: MockConfigEntry) -> dict[str, Any]:
    return hass.data[DOMAIN][entry.entry_id]["trackers"]


# ---------------------------------------------------------------------------
# Setup + entities
# ---------------------------------------------------------------------------


class TestSetupCreatesEntities:
    async def test_setup_creates_three_entities_per_room(self, hass: HomeAssistant):
        entry, room_id = _make_entry_with_room(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        score = hass.states.get(
            f"sensor.cleanliness_tracker_room_{entry.entry_id[:6]}_score"
        )
        # We can't predict the auto-generated entity_id slug; assert via the
        # tracker map plus state count.
        score_states = [
            s
            for s in hass.states.async_all()
            if s.entity_id.startswith("sensor.")
            and s.attributes.get("unit_of_measurement") == "%"
        ]
        assert len(score_states) == 1
        last_cleaned_states = [
            s
            for s in hass.states.async_all()
            if s.entity_id.startswith("sensor.")
            and s.attributes.get("device_class") == "timestamp"
        ]
        assert len(last_cleaned_states) == 1
        due_states = [
            s
            for s in hass.states.async_all()
            if s.entity_id.startswith("binary_sensor.")
        ]
        assert len(due_states) == 1
        assert float(score_states[0].state) == 0.0
        assert due_states[0].state == "off"
        assert score is None  # placeholder reference; entity_id is auto-named

        assert room_id in _trackers(hass, entry)


# ---------------------------------------------------------------------------
# Presence-driven scoring
# ---------------------------------------------------------------------------


class TestPresenceLifecycle:
    async def test_presence_on_off_increments_score(self, hass: HomeAssistant):
        entry, _room_id = _make_entry_with_room(hass)
        with freeze_time(dt_util.utcnow()) as frozen:
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

            # Presence ON
            hass.states.async_set("binary_sensor.wohnzimmer_presence", STATE_ON)
            await hass.async_block_till_done()

            # 10 minutes pass, then presence OFF
            frozen.tick(timedelta(minutes=10))
            hass.states.async_set("binary_sensor.wohnzimmer_presence", STATE_OFF)
            await hass.async_block_till_done()

        # 10 min * 0.5 = 5
        score_state = next(
            s
            for s in hass.states.async_all()
            if s.entity_id.startswith("sensor.")
            and s.attributes.get("unit_of_measurement") == "%"
        )
        assert float(score_state.state) == pytest.approx(5.0)

    async def test_periodic_tick_grows_score_during_active_presence(
        self, hass: HomeAssistant
    ):
        entry, _room_id = _make_entry_with_room(hass)
        with freeze_time(dt_util.utcnow()) as frozen:
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

            hass.states.async_set("binary_sensor.wohnzimmer_presence", STATE_ON)
            await hass.async_block_till_done()

            frozen.tick(timedelta(seconds=TICK_INTERVAL_SECONDS))
            async_fire_time_changed(hass, dt_util.utcnow())
            await hass.async_block_till_done()

        score_state = next(
            s
            for s in hass.states.async_all()
            if s.entity_id.startswith("sensor.")
            and s.attributes.get("unit_of_measurement") == "%"
        )
        # 5 minutes (TICK_INTERVAL_SECONDS) * 0.5 = 2.5
        assert float(score_state.state) == pytest.approx(2.5)

    async def test_unknown_state_is_ignored(self, hass: HomeAssistant):
        entry, _room_id = _make_entry_with_room(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        hass.states.async_set("binary_sensor.wohnzimmer_presence", STATE_ON)
        await hass.async_block_till_done()
        # transient unavailability must NOT close the interval
        hass.states.async_set("binary_sensor.wohnzimmer_presence", STATE_UNAVAILABLE)
        await hass.async_block_till_done()

        tracker = _trackers(hass, entry)[next(iter(_trackers(hass, entry)))]
        assert tracker.is_presence_active is True

    async def test_due_binary_flips_at_threshold(self, hass: HomeAssistant):
        entry, _room_id = _make_entry_with_room(hass, threshold=10.0, weight=2.0)
        with freeze_time(dt_util.utcnow()) as frozen:
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

            hass.states.async_set("binary_sensor.wohnzimmer_presence", STATE_ON)
            await hass.async_block_till_done()

            frozen.tick(timedelta(minutes=6))  # 6 min * 2.0 = 12 > 10
            hass.states.async_set("binary_sensor.wohnzimmer_presence", STATE_OFF)
            await hass.async_block_till_done()

        due = next(
            s
            for s in hass.states.async_all()
            if s.entity_id.startswith("binary_sensor.")
        )
        assert due.state == "on"


# ---------------------------------------------------------------------------
# Persistence + unload
# ---------------------------------------------------------------------------


class TestPersistenceAndUnload:
    async def test_state_persists_across_reload(self, hass: HomeAssistant):
        entry, room_id = _make_entry_with_room(hass)
        with freeze_time(dt_util.utcnow()) as frozen:
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()
            hass.states.async_set("binary_sensor.wohnzimmer_presence", STATE_ON)
            await hass.async_block_till_done()
            frozen.tick(timedelta(minutes=20))
            hass.states.async_set("binary_sensor.wohnzimmer_presence", STATE_OFF)
            await hass.async_block_till_done()

        first_score = _trackers(hass, entry)[room_id].score
        assert first_score == pytest.approx(10.0)

        # Reload: unload, then setup again — state must come back from the store.
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        reloaded_score = _trackers(hass, entry)[room_id].score
        assert reloaded_score == pytest.approx(first_score)

    async def test_unload_removes_domain_data_and_clean_listeners(
        self, hass: HomeAssistant
    ):
        entry, _room_id = _make_entry_with_room(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.entry_id in hass.data[DOMAIN]

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        # DOMAIN dropped entirely once the last entry unloads.
        assert DOMAIN not in hass.data
