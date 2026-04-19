"""Shared pytest fixtures for cleanliness_tracker.

Loads ``pytest_homeassistant_custom_component`` only when installed so the
pure-logic tests (``test_soil_calculator.py``) can still run in lean envs
without the full HA dependency tree.
"""

from __future__ import annotations

import pathlib
from importlib.util import find_spec

import pytest

if find_spec("pytest_homeassistant_custom_component") is not None:
    pytest_plugins = ["pytest_homeassistant_custom_component"]

    # Editable pip installs (pip install -e .) inject a fake placeholder path
    # into custom_components.__path__ which HA's _get_custom_components then
    # tries to iterate. Strip non-existent entries once per session so the
    # real on-disk integration is discoverable.
    import custom_components

    _real_paths = [
        p for p in list(custom_components.__path__) if pathlib.Path(p).is_dir()
    ]
    custom_components.__path__[:] = _real_paths

    @pytest.fixture(autouse=True)
    def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
        """Enable loading of custom integrations in tests."""
        return enable_custom_integrations
