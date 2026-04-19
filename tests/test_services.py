"""Tests for the domain-level services."""

from __future__ import annotations

from datetime import timedelta

import pytest
from freezegun import freeze_time
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import CONF_NAME, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from custom_components.cleanliness_tracker.const import (
    CONF_AREA_ID,
    CONF_PRESENCE_ENTITY_ID,
    CONF_THRESHOLD,
    CONF_WEIGHT_PER_MINUTE,
    DOMAIN,
    SUBENTRY_ROOM,
)


def _add_entry(
    hass: HomeAssistant,
    *,
    title: str,
    rooms: list[tuple[str, str]],
) -> MockConfigEntry:
    subs_data = []
    for area_id, presence in rooms:
        sub = ConfigSubentry(
            data={
                CONF_AREA_ID: area_id,
                CONF_PRESENCE_ENTITY_ID: presence,
                CONF_THRESHOLD: 80.0,
                CONF_WEIGHT_PER_MINUTE: 0.5,
            },
            subentry_type=SUBENTRY_ROOM,
            title=area_id,
            unique_id=None,
        )
        subs_data.append(sub.as_dict())
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=title,
        data={CONF_NAME: title},
        unique_id=title.lower(),
        subentries_data=subs_data,
    )
    entry.add_to_hass(hass)
    return entry


def _score_entity_id(hass: HomeAssistant) -> str:
    """Return the first cleanliness score sensor entity_id."""
    return next(
        s.entity_id
        for s in hass.states.async_all()
        if s.entity_id.startswith("sensor.")
        and s.attributes.get("unit_of_measurement") == "%"
    )


# ---------------------------------------------------------------------------
# Service registration / unregistration
# ---------------------------------------------------------------------------


class TestRegistration:
    async def test_registers_three_services(self, hass: HomeAssistant):
        entry = _add_entry(
            hass,
            title="EG",
            rooms=[("wohnzimmer", "binary_sensor.wohnzimmer_p")],
        )
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        for service in ("mark_cleaned", "reset", "set_score"):
            assert hass.services.has_service(DOMAIN, service)

    async def test_unloads_remove_services(self, hass: HomeAssistant):
        entry = _add_entry(
            hass,
            title="EG",
            rooms=[("wohnzimmer", "binary_sensor.wohnzimmer_p")],
        )
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

        for service in ("mark_cleaned", "reset", "set_score"):
            assert not hass.services.has_service(DOMAIN, service)


# ---------------------------------------------------------------------------
# mark_cleaned
# ---------------------------------------------------------------------------


class TestMarkCleaned:
    async def test_targets_specific_entity(self, hass: HomeAssistant):
        entry = _add_entry(
            hass,
            title="EG",
            rooms=[("wohnzimmer", "binary_sensor.wohnzimmer_p")],
        )
        with freeze_time(dt_util.utcnow()) as frozen:
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()
            hass.states.async_set("binary_sensor.wohnzimmer_p", STATE_ON)
            await hass.async_block_till_done()
            frozen.tick(timedelta(minutes=20))
            hass.states.async_set("binary_sensor.wohnzimmer_p", STATE_OFF)
            await hass.async_block_till_done()
            score_eid = _score_entity_id(hass)
            assert float(hass.states.get(score_eid).state) == pytest.approx(10.0)

            await hass.services.async_call(
                DOMAIN,
                "mark_cleaned",
                {"entity_id": score_eid},
                blocking=True,
            )

        assert float(hass.states.get(score_eid).state) == 0.0
        # last_cleaned should now be a timestamp, not "unknown".
        last_cleaned_state = next(
            s
            for s in hass.states.async_all()
            if s.entity_id.startswith("sensor.")
            and s.attributes.get("device_class") == "timestamp"
        )
        assert last_cleaned_state.state not in ("unknown", "unavailable")

    async def test_no_target_resets_every_room(self, hass: HomeAssistant):
        entry = _add_entry(
            hass,
            title="EG",
            rooms=[
                ("wohnzimmer", "binary_sensor.wohnzimmer_p"),
                ("kueche", "binary_sensor.kueche_p"),
            ],
        )
        with freeze_time(dt_util.utcnow()) as frozen:
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()
            for presence in ("binary_sensor.wohnzimmer_p", "binary_sensor.kueche_p"):
                hass.states.async_set(presence, STATE_ON)
            await hass.async_block_till_done()
            frozen.tick(timedelta(minutes=10))
            for presence in ("binary_sensor.wohnzimmer_p", "binary_sensor.kueche_p"):
                hass.states.async_set(presence, STATE_OFF)
            await hass.async_block_till_done()

            await hass.services.async_call(DOMAIN, "mark_cleaned", {}, blocking=True)

        scores = [
            float(s.state)
            for s in hass.states.async_all()
            if s.entity_id.startswith("sensor.")
            and s.attributes.get("unit_of_measurement") == "%"
        ]
        assert len(scores) == 2
        assert all(s == 0.0 for s in scores)


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------


class TestReset:
    async def test_clears_score_but_not_last_cleaned(self, hass: HomeAssistant):
        entry = _add_entry(
            hass,
            title="EG",
            rooms=[("wohnzimmer", "binary_sensor.wohnzimmer_p")],
        )
        with freeze_time(dt_util.utcnow()) as frozen:
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()
            hass.states.async_set("binary_sensor.wohnzimmer_p", STATE_ON)
            await hass.async_block_till_done()
            frozen.tick(timedelta(minutes=10))
            hass.states.async_set("binary_sensor.wohnzimmer_p", STATE_OFF)
            await hass.async_block_till_done()
            score_eid = _score_entity_id(hass)
            await hass.services.async_call(
                DOMAIN, "mark_cleaned", {"entity_id": score_eid}, blocking=True
            )
            last_cleaned_before = next(
                s
                for s in hass.states.async_all()
                if s.entity_id.startswith("sensor.")
                and s.attributes.get("device_class") == "timestamp"
            ).state

            # Accrue a bit, then reset (NOT mark_cleaned).
            hass.states.async_set("binary_sensor.wohnzimmer_p", STATE_ON)
            await hass.async_block_till_done()
            frozen.tick(timedelta(minutes=10))
            hass.states.async_set("binary_sensor.wohnzimmer_p", STATE_OFF)
            await hass.async_block_till_done()
            assert float(hass.states.get(score_eid).state) == pytest.approx(5.0)

            await hass.services.async_call(
                DOMAIN, "reset", {"entity_id": score_eid}, blocking=True
            )

        assert float(hass.states.get(score_eid).state) == 0.0
        last_cleaned_after = next(
            s
            for s in hass.states.async_all()
            if s.entity_id.startswith("sensor.")
            and s.attributes.get("device_class") == "timestamp"
        ).state
        assert last_cleaned_after == last_cleaned_before


# ---------------------------------------------------------------------------
# set_score
# ---------------------------------------------------------------------------


class TestSetScore:
    async def test_sets_explicit_value(self, hass: HomeAssistant):
        entry = _add_entry(
            hass,
            title="EG",
            rooms=[("wohnzimmer", "binary_sensor.wohnzimmer_p")],
        )
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        score_eid = _score_entity_id(hass)

        await hass.services.async_call(
            DOMAIN,
            "set_score",
            {"entity_id": score_eid, "score": 42.5},
            blocking=True,
        )

        assert float(hass.states.get(score_eid).state) == pytest.approx(42.5)

    async def test_rejects_unknown_entity(self, hass: HomeAssistant):
        entry = _add_entry(
            hass,
            title="EG",
            rooms=[("wohnzimmer", "binary_sensor.wohnzimmer_p")],
        )
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN,
                "set_score",
                {"entity_id": "sensor.does_not_exist", "score": 50},
                blocking=True,
            )
