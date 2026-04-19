"""Config flow for cleanliness_tracker.

Setup is split in two layers:

* :class:`CleanlinessTrackerConfigFlow` — the user picks an integration
  name; one ConfigEntry is created.
* :class:`RoomSubentryFlow` — one subentry per room, holding area, presence
  entity, threshold and per-minute weight. Supports create + reconfigure.

All user-facing strings live in ``strings.json`` and the per-language
translations under ``translations/``; this module references translation
keys only.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_NAME
from homeassistant.helpers.selector import (
    AreaSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
)

from .const import (
    CONF_AREA_ID,
    CONF_PRESENCE_ENTITY_ID,
    CONF_THRESHOLD,
    CONF_WEIGHT_PER_MINUTE,
    DEFAULT_PRESENCE_WEIGHT,
    DEFAULT_THRESHOLD,
    DOMAIN,
    SCORE_CAP,
    SUBENTRY_ROOM,
)

_SEL_TEXT = TextSelector()
_SEL_AREA = AreaSelector()
_SEL_PRESENCE = EntitySelector(
    EntitySelectorConfig(domain="binary_sensor"),
)
_SEL_THRESHOLD = NumberSelector(
    NumberSelectorConfig(min=1, max=SCORE_CAP, step=1, mode=NumberSelectorMode.BOX),
)
_SEL_WEIGHT = NumberSelector(
    NumberSelectorConfig(min=0.1, max=10, step=0.1, mode=NumberSelectorMode.BOX),
)


def _normalise_name(value: Any) -> str:
    """Strip and validate a user-provided name."""
    return str(value).strip() if value is not None else ""


def _existing_room_areas(
    entry: ConfigEntry,
    *,
    exclude_subentry_id: str | None = None,
) -> set[str]:
    """Collect the area_ids already covered by other room subentries."""
    return {
        subentry.data[CONF_AREA_ID]
        for subentry in entry.subentries.values()
        if subentry.subentry_type == SUBENTRY_ROOM
        and subentry.subentry_id != exclude_subentry_id
        and CONF_AREA_ID in subentry.data
    }


def _validate_room_input(
    user_input: dict[str, Any],
    *,
    existing_areas: set[str],
) -> tuple[dict[str, Any], dict[str, str]]:
    """Validate + normalise a Room-subentry submission."""
    errors: dict[str, str] = {}
    area = user_input.get(CONF_AREA_ID)
    presence = user_input.get(CONF_PRESENCE_ENTITY_ID)
    threshold = user_input.get(CONF_THRESHOLD, DEFAULT_THRESHOLD)
    weight = user_input.get(CONF_WEIGHT_PER_MINUTE, DEFAULT_PRESENCE_WEIGHT)

    if not area:
        errors[CONF_AREA_ID] = "area_required"
    elif area in existing_areas:
        errors[CONF_AREA_ID] = "area_duplicate"

    if not presence:
        errors[CONF_PRESENCE_ENTITY_ID] = "presence_required"

    threshold_val = float(threshold) if threshold is not None else DEFAULT_THRESHOLD
    if not 0 < threshold_val <= SCORE_CAP:
        errors[CONF_THRESHOLD] = "threshold_out_of_range"

    weight_val = float(weight) if weight is not None else DEFAULT_PRESENCE_WEIGHT
    if weight_val <= 0:
        errors[CONF_WEIGHT_PER_MINUTE] = "weight_out_of_range"

    normalised = {
        CONF_AREA_ID: area,
        CONF_PRESENCE_ENTITY_ID: presence,
        CONF_THRESHOLD: threshold_val,
        CONF_WEIGHT_PER_MINUTE: weight_val,
    }
    return normalised, errors


def _room_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Build the room-subentry form schema.

    ``defaults`` is either the existing subentry data (reconfigure) or the
    user's last submission (when redrawing after errors).
    """
    return vol.Schema(
        {
            vol.Required(
                CONF_AREA_ID, default=defaults.get(CONF_AREA_ID, vol.UNDEFINED)
            ): _SEL_AREA,
            vol.Required(
                CONF_PRESENCE_ENTITY_ID,
                default=defaults.get(CONF_PRESENCE_ENTITY_ID, vol.UNDEFINED),
            ): _SEL_PRESENCE,
            vol.Optional(
                CONF_THRESHOLD,
                default=defaults.get(CONF_THRESHOLD, DEFAULT_THRESHOLD),
            ): _SEL_THRESHOLD,
            vol.Optional(
                CONF_WEIGHT_PER_MINUTE,
                default=defaults.get(CONF_WEIGHT_PER_MINUTE, DEFAULT_PRESENCE_WEIGHT),
            ): _SEL_WEIGHT,
        }
    )


# ---------------------------------------------------------------------------
# Top-level config flow
# ---------------------------------------------------------------------------


class CleanlinessTrackerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Initial setup flow — create the integration entry."""

    VERSION = 1

    @classmethod
    def async_get_supported_subentry_types(
        cls,
        config_entry: ConfigEntry,  # noqa: ARG003 -- required by signature
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Expose the room subentry flow."""
        return {SUBENTRY_ROOM: RoomSubentryFlow}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Prompt for the integration name and create the entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            name = _normalise_name(user_input.get(CONF_NAME))
            if not name:
                errors[CONF_NAME] = "name_required"
            else:
                await self.async_set_unique_id(name.lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=name,
                    data={CONF_NAME: name},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_NAME): _SEL_TEXT}),
            errors=errors,
        )


# ---------------------------------------------------------------------------
# Room subentry flow
# ---------------------------------------------------------------------------


class RoomSubentryFlow(ConfigSubentryFlow):
    """Create or reconfigure a single room.

    Create and reconfigure share schema + validator; only the surrounding
    control flow differs (``async_create_entry`` vs ``async_update_and_abort``).
    """

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Handle the initial room-create step."""
        entry = self._get_entry()
        errors: dict[str, str] = {}
        defaults: dict[str, Any] = dict(user_input or {})

        if user_input is not None:
            normalised, errors = _validate_room_input(
                user_input,
                existing_areas=_existing_room_areas(entry),
            )
            if not errors:
                return self.async_create_entry(
                    title=str(normalised[CONF_AREA_ID]),
                    data=normalised,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_room_schema(defaults),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Handle the room-reconfigure step with prefilled data."""
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}
        defaults: dict[str, Any] = dict(user_input or subentry.data)

        if user_input is not None:
            normalised, errors = _validate_room_input(
                user_input,
                existing_areas=_existing_room_areas(
                    entry, exclude_subentry_id=subentry.subentry_id
                ),
            )
            if not errors:
                return self.async_update_and_abort(
                    entry,
                    subentry,
                    title=str(normalised[CONF_AREA_ID]),
                    data=normalised,
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_room_schema(defaults),
            errors=errors,
        )
