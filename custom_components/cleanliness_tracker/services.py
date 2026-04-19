"""Domain-level services for cleanliness_tracker.

Three services, all targeting one or more score-sensor entity_ids:

* ``mark_cleaned`` — score → 0 + stamp ``last_cleaned_at`` (no entity_id =
  every room of every entry).
* ``reset`` — score → 0 without touching ``last_cleaned_at``.
* ``set_score`` — set one room's score to an explicit value.

Service handlers map an entity_id back to its ``(entry_id, room_id, tracker)``
triple via the entity registry; the unique_id pattern
``"{entry_id}.{room_id}.<role>"`` is what makes the round-trip cheap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import voluptuous as vol

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import DOMAIN, SCORE_CAP

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall

    from .tracker import RoomTracker


SERVICE_MARK_CLEANED = "mark_cleaned"
SERVICE_RESET = "reset"
SERVICE_SET_SCORE = "set_score"

_ATTR_SCORE = "score"
_MIN_UNIQUE_ID_PARTS = 2  # "{entry_id}.{room_id}.<role>"

_SCHEMA_OPTIONAL_TARGET = vol.Schema(
    {vol.Optional(ATTR_ENTITY_ID): vol.Any(str, [str])}
)
_SCHEMA_SET_SCORE = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): vol.Any(str, [str]),
        vol.Required(_ATTR_SCORE): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=SCORE_CAP)
        ),
    }
)


def _resolve_tracker(
    hass: HomeAssistant, entity_id: str
) -> tuple[str, str, RoomTracker] | None:
    """Map an entity_id to its (entry_id, room_id, tracker)."""
    ent_reg = er.async_get(hass)
    entry = ent_reg.async_get(entity_id)
    if entry is None or entry.platform != DOMAIN or entry.unique_id is None:
        return None
    parts = entry.unique_id.split(".")
    if len(parts) < _MIN_UNIQUE_ID_PARTS:
        return None
    entry_id, room_id = parts[0], parts[1]
    domain_data = hass.data.get(DOMAIN, {}).get(entry_id)
    if domain_data is None:
        return None
    tracker = domain_data["trackers"].get(room_id)
    if tracker is None:
        return None
    return entry_id, room_id, tracker


def _all_trackers(
    hass: HomeAssistant,
) -> list[tuple[str, str, RoomTracker]]:
    """Return every ``(entry_id, room_id, tracker)`` triple in the domain."""
    triples: list[tuple[str, str, RoomTracker]] = []
    for entry_id, data in hass.data.get(DOMAIN, {}).items():
        for room_id, tracker in data["trackers"].items():
            triples.append((entry_id, room_id, tracker))
    return triples


def _coerce_entity_ids(raw: object) -> list[str]:
    """Normalise the ``entity_id`` field into a clean string list."""
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, (list, tuple)):
        return [str(item) for item in raw]
    return [str(raw)]


def _resolve_targets(
    hass: HomeAssistant,
    call: ServiceCall,
    *,
    require_target: bool,
) -> list[tuple[str, str, RoomTracker]]:
    """Resolve the service-call targets to a list of trackers.

    If no entity_id is given and ``require_target`` is False, every tracker
    in the domain is returned. Unknown / wrong-domain entities raise
    :class:`ServiceValidationError`.
    """
    entity_ids = _coerce_entity_ids(call.data.get(ATTR_ENTITY_ID))
    if not entity_ids:
        if require_target:
            raise ServiceValidationError("Service requires an entity_id target.")
        return _all_trackers(hass)

    triples: list[tuple[str, str, RoomTracker]] = []
    seen: set[tuple[str, str]] = set()
    for eid in entity_ids:
        resolved = _resolve_tracker(hass, eid)
        if resolved is None:
            raise ServiceValidationError(
                f"Entity {eid!r} is not a cleanliness_tracker entity."
            )
        if (resolved[0], resolved[1]) in seen:
            continue
        seen.add((resolved[0], resolved[1]))
        triples.append(resolved)
    return triples


async def _save_for(hass: HomeAssistant, entry_ids: set[str]) -> None:
    for entry_id in entry_ids:
        save = hass.data[DOMAIN][entry_id]["save_state"]
        await save()


def async_register_services(hass: HomeAssistant) -> None:
    """Register all cleanliness_tracker services. Idempotent."""

    async def _mark_cleaned(call: ServiceCall) -> None:
        triples = _resolve_targets(hass, call, require_target=False)
        now = dt_util.utcnow()
        for _entry_id, _room_id, tracker in triples:
            tracker.mark_cleaned(now)
        await _save_for(hass, {entry_id for entry_id, _, _ in triples})

    async def _reset(call: ServiceCall) -> None:
        triples = _resolve_targets(hass, call, require_target=False)
        now = dt_util.utcnow()
        for _entry_id, _room_id, tracker in triples:
            tracker.reset(now)
        await _save_for(hass, {entry_id for entry_id, _, _ in triples})

    async def _set_score(call: ServiceCall) -> None:
        triples = _resolve_targets(hass, call, require_target=True)
        score = float(call.data[_ATTR_SCORE])
        for _entry_id, _room_id, tracker in triples:
            tracker.set_score(score)
        await _save_for(hass, {entry_id for entry_id, _, _ in triples})

    hass.services.async_register(
        DOMAIN, SERVICE_MARK_CLEANED, _mark_cleaned, schema=_SCHEMA_OPTIONAL_TARGET
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RESET, _reset, schema=_SCHEMA_OPTIONAL_TARGET
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_SCORE, _set_score, schema=_SCHEMA_SET_SCORE
    )


def async_unregister_services(hass: HomeAssistant) -> None:
    """Remove all cleanliness_tracker services. Safe to call repeatedly."""
    for service in (SERVICE_MARK_CLEANED, SERVICE_RESET, SERVICE_SET_SCORE):
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)
