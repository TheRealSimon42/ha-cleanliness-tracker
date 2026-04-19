"""Tests for the config flow + room subentry flow.

Uses the in-memory HA + ConfigEntry helpers from
``pytest_homeassistant_custom_component`` so the flow is exercised without
real disk persistence.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData

from custom_components.cleanliness_tracker.config_flow import _validate_room_input
from custom_components.cleanliness_tracker.const import (
    CONF_AREA_ID,
    CONF_PRESENCE_ENTITY_ID,
    CONF_THRESHOLD,
    CONF_WEIGHT_PER_MINUTE,
    DEFAULT_PRESENCE_WEIGHT,
    DEFAULT_THRESHOLD,
    DOMAIN,
    SUBENTRY_ROOM,
)

# ---------------------------------------------------------------------------
# Top-level flow
# ---------------------------------------------------------------------------


class TestUserFlow:
    async def test_happy_path_creates_entry(self, hass: HomeAssistant):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_NAME: "Wohnung EG"}
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["title"] == "Wohnung EG"
        assert result["data"] == {CONF_NAME: "Wohnung EG"}

    async def test_blank_name_shows_error(self, hass: HomeAssistant):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_NAME: "   "}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {CONF_NAME: "name_required"}

    async def test_duplicate_name_aborts(self, hass: HomeAssistant):
        # First entry succeeds.
        existing = MockConfigEntry(
            domain=DOMAIN,
            title="Wohnung EG",
            data={CONF_NAME: "Wohnung EG"},
            unique_id="wohnung eg",
        )
        existing.add_to_hass(hass)

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_NAME: "Wohnung EG"}
        )
        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "already_configured"


# ---------------------------------------------------------------------------
# Room subentry flow
# ---------------------------------------------------------------------------


def _valid_room_input(**overrides: Any) -> dict[str, Any]:
    base = {
        CONF_AREA_ID: "wohnzimmer",
        CONF_PRESENCE_ENTITY_ID: "binary_sensor.wohnzimmer_presence",
        CONF_THRESHOLD: DEFAULT_THRESHOLD,
        CONF_WEIGHT_PER_MINUTE: DEFAULT_PRESENCE_WEIGHT,
    }
    base.update(overrides)
    return base


async def _make_entry(hass: HomeAssistant, *, title: str = "EG") -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=title,
        data={CONF_NAME: title},
        unique_id=title.lower(),
    )
    entry.add_to_hass(hass)
    return entry


class TestRoomCreate:
    async def test_happy_path_creates_subentry(self, hass: HomeAssistant):
        entry = await _make_entry(hass)
        result = await hass.config_entries.subentries.async_init(
            (entry.entry_id, SUBENTRY_ROOM),
            context={"source": "user"},
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"

        result = await hass.config_entries.subentries.async_configure(
            result["flow_id"], _valid_room_input()
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"] == {
            CONF_AREA_ID: "wohnzimmer",
            CONF_PRESENCE_ENTITY_ID: "binary_sensor.wohnzimmer_presence",
            CONF_THRESHOLD: float(DEFAULT_THRESHOLD),
            CONF_WEIGHT_PER_MINUTE: float(DEFAULT_PRESENCE_WEIGHT),
        }

    async def test_duplicate_area_is_rejected(self, hass: HomeAssistant):
        entry = await _make_entry(hass)
        # Pretend wohnzimmer is already configured.
        hass.config_entries.async_update_entry(entry)
        result = await hass.config_entries.subentries.async_init(
            (entry.entry_id, SUBENTRY_ROOM),
            context={"source": "user"},
        )
        result = await hass.config_entries.subentries.async_configure(
            result["flow_id"], _valid_room_input()
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY  # first one fine

        # Second attempt on same area must fail.
        result = await hass.config_entries.subentries.async_init(
            (entry.entry_id, SUBENTRY_ROOM),
            context={"source": "user"},
        )
        result = await hass.config_entries.subentries.async_configure(
            result["flow_id"], _valid_room_input()
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {CONF_AREA_ID: "area_duplicate"}

    async def test_threshold_out_of_range(self, hass: HomeAssistant):
        entry = await _make_entry(hass)
        result = await hass.config_entries.subentries.async_init(
            (entry.entry_id, SUBENTRY_ROOM),
            context={"source": "user"},
        )
        # Schema enforces min=1, max=100 for threshold; submitting 150 raises
        # a vol.MultipleInvalid before our validator runs.
        with pytest.raises(InvalidData):
            await hass.config_entries.subentries.async_configure(
                result["flow_id"], _valid_room_input(threshold=150)
            )

    async def test_weight_out_of_range_via_schema(self, hass: HomeAssistant):
        entry = await _make_entry(hass)
        result = await hass.config_entries.subentries.async_init(
            (entry.entry_id, SUBENTRY_ROOM),
            context={"source": "user"},
        )
        # Schema enforces min=0.1; vol catches it before our validator. The
        # validator's own branch is covered by ``TestValidatorUnit`` below.
        with pytest.raises(InvalidData):
            await hass.config_entries.subentries.async_configure(
                result["flow_id"], _valid_room_input(weight_per_minute=0)
            )


class TestRoomReconfigure:
    async def test_reconfigure_updates_existing_subentry(self, hass: HomeAssistant):
        entry = await _make_entry(hass)
        sub = ConfigSubentry(
            data={
                CONF_AREA_ID: "wohnzimmer",
                CONF_PRESENCE_ENTITY_ID: "binary_sensor.old_presence",
                CONF_THRESHOLD: 80.0,
                CONF_WEIGHT_PER_MINUTE: 0.5,
            },
            subentry_type=SUBENTRY_ROOM,
            title="wohnzimmer",
            unique_id=None,
        )
        hass.config_entries.async_add_subentry(entry, sub)

        result = await hass.config_entries.subentries.async_init(
            (entry.entry_id, SUBENTRY_ROOM),
            context={"source": "reconfigure", "subentry_id": sub.subentry_id},
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "reconfigure"

        result = await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            {
                CONF_AREA_ID: "wohnzimmer",
                CONF_PRESENCE_ENTITY_ID: "binary_sensor.new_presence",
                CONF_THRESHOLD: 60,
                CONF_WEIGHT_PER_MINUTE: 1.5,
            },
        )
        # Reconfigure aborts with reconfigure_successful (HA convention).
        assert result["type"] is FlowResultType.ABORT
        # Data was written back.
        updated = entry.subentries[sub.subentry_id]
        assert updated.data[CONF_PRESENCE_ENTITY_ID] == "binary_sensor.new_presence"
        assert updated.data[CONF_THRESHOLD] == 60.0
        assert updated.data[CONF_WEIGHT_PER_MINUTE] == 1.5

    async def test_reconfigure_redraws_form_on_validation_error(
        self, hass: HomeAssistant
    ):
        entry = await _make_entry(hass)
        existing_other = ConfigSubentry(
            data={
                CONF_AREA_ID: "kueche",
                CONF_PRESENCE_ENTITY_ID: "binary_sensor.k",
                CONF_THRESHOLD: 80.0,
                CONF_WEIGHT_PER_MINUTE: 0.5,
            },
            subentry_type=SUBENTRY_ROOM,
            title="kueche",
            unique_id=None,
        )
        target = ConfigSubentry(
            data={
                CONF_AREA_ID: "wohnzimmer",
                CONF_PRESENCE_ENTITY_ID: "binary_sensor.w",
                CONF_THRESHOLD: 80.0,
                CONF_WEIGHT_PER_MINUTE: 0.5,
            },
            subentry_type=SUBENTRY_ROOM,
            title="wohnzimmer",
            unique_id=None,
        )
        hass.config_entries.async_add_subentry(entry, existing_other)
        hass.config_entries.async_add_subentry(entry, target)

        result = await hass.config_entries.subentries.async_init(
            (entry.entry_id, SUBENTRY_ROOM),
            context={"source": "reconfigure", "subentry_id": target.subentry_id},
        )
        # Try to migrate `target` onto an area already used by `existing_other`
        # — must be rejected, form is re-rendered with errors.
        result = await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            {
                CONF_AREA_ID: "kueche",
                CONF_PRESENCE_ENTITY_ID: "binary_sensor.w",
                CONF_THRESHOLD: 80,
                CONF_WEIGHT_PER_MINUTE: 0.5,
            },
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {CONF_AREA_ID: "area_duplicate"}

    async def test_reconfigure_excludes_self_from_duplicate_check(
        self, hass: HomeAssistant
    ):
        entry = await _make_entry(hass)
        sub = ConfigSubentry(
            data={
                CONF_AREA_ID: "wohnzimmer",
                CONF_PRESENCE_ENTITY_ID: "binary_sensor.p",
                CONF_THRESHOLD: 80.0,
                CONF_WEIGHT_PER_MINUTE: 0.5,
            },
            subentry_type=SUBENTRY_ROOM,
            title="wohnzimmer",
            unique_id=None,
        )
        hass.config_entries.async_add_subentry(entry, sub)

        result = await hass.config_entries.subentries.async_init(
            (entry.entry_id, SUBENTRY_ROOM),
            context={"source": "reconfigure", "subentry_id": sub.subentry_id},
        )
        # Submit unchanged area — must NOT trigger area_duplicate.
        result = await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            {
                CONF_AREA_ID: "wohnzimmer",
                CONF_PRESENCE_ENTITY_ID: "binary_sensor.p",
                CONF_THRESHOLD: 80,
                CONF_WEIGHT_PER_MINUTE: 0.5,
            },
        )
        assert result["type"] is FlowResultType.ABORT


# ---------------------------------------------------------------------------
# Validator helper unit tests (cover branches that the live flow can't reach
# because schema enforcement happens first).
# ---------------------------------------------------------------------------


class TestValidatorUnit:
    def test_missing_area_flags_required(self):
        normalised, errors = _validate_room_input(
            {
                CONF_AREA_ID: "",
                CONF_PRESENCE_ENTITY_ID: "binary_sensor.p",
                CONF_THRESHOLD: 50,
                CONF_WEIGHT_PER_MINUTE: 1.0,
            },
            existing_areas=set(),
        )
        assert errors == {CONF_AREA_ID: "area_required"}
        assert normalised[CONF_THRESHOLD] == 50.0

    def test_missing_presence_flags_required(self):
        _, errors = _validate_room_input(
            {
                CONF_AREA_ID: "k",
                CONF_PRESENCE_ENTITY_ID: None,
                CONF_THRESHOLD: 50,
                CONF_WEIGHT_PER_MINUTE: 1.0,
            },
            existing_areas=set(),
        )
        assert errors == {CONF_PRESENCE_ENTITY_ID: "presence_required"}

    def test_threshold_out_of_range_unit(self):
        _, errors = _validate_room_input(
            {
                CONF_AREA_ID: "k",
                CONF_PRESENCE_ENTITY_ID: "binary_sensor.p",
                CONF_THRESHOLD: 150,
                CONF_WEIGHT_PER_MINUTE: 1.0,
            },
            existing_areas=set(),
        )
        assert errors == {CONF_THRESHOLD: "threshold_out_of_range"}

    def test_weight_out_of_range_unit(self):
        _, errors = _validate_room_input(
            {
                CONF_AREA_ID: "k",
                CONF_PRESENCE_ENTITY_ID: "binary_sensor.p",
                CONF_THRESHOLD: 50,
                CONF_WEIGHT_PER_MINUTE: 0,
            },
            existing_areas=set(),
        )
        assert errors == {CONF_WEIGHT_PER_MINUTE: "weight_out_of_range"}

    def test_uses_defaults_when_optional_missing(self):
        normalised, errors = _validate_room_input(
            {
                CONF_AREA_ID: "k",
                CONF_PRESENCE_ENTITY_ID: "binary_sensor.p",
            },
            existing_areas=set(),
        )
        assert errors == {}
        assert normalised[CONF_THRESHOLD] == DEFAULT_THRESHOLD
        assert normalised[CONF_WEIGHT_PER_MINUTE] == DEFAULT_PRESENCE_WEIGHT
