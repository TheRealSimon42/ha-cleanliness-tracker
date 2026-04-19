"""Shared pytest fixtures."""

from __future__ import annotations

# TODO(phase-1+): mirror ha-hauskosten conftest pattern (strip stale entries
# from custom_components.__path__ so HA's _get_custom_components survives
# pip-editable installs; load pytest_homeassistant_custom_component lazily).
