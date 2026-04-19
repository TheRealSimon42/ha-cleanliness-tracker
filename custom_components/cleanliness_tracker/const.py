"""Constants for the cleanliness_tracker integration.

Authoritative spec for defaults: ``docs/SCORE_MODEL.md``.
"""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "cleanliness_tracker"

# Storage --------------------------------------------------------------------

STORAGE_VERSION: Final = 1

# Config-flow / subentry keys -----------------------------------------------

CONF_ROOMS: Final = "rooms"
CONF_AREA_ID: Final = "area_id"
CONF_PRESENCE_ENTITY_ID: Final = "presence_entity_id"
CONF_THRESHOLD: Final = "threshold"
CONF_WEIGHT_PER_MINUTE: Final = "weight_per_minute"

# Subentry types -------------------------------------------------------------

SUBENTRY_ROOM: Final = "room"

# Defaults -------------------------------------------------------------------

DEFAULT_THRESHOLD: Final = 80.0
DEFAULT_PRESENCE_WEIGHT: Final = 0.5
TICK_INTERVAL_SECONDS: Final = 300
SCORE_CAP: Final = 100.0
