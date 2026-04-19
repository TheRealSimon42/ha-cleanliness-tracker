"""Tests for CleanlinessStore.

Mocks ``homeassistant.helpers.storage.Store`` to avoid touching the disk.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.cleanliness_tracker.const import (
    CONF_AREA_ID,
    CONF_PRESENCE_ENTITY_ID,
    CONF_ROOMS,
    CONF_THRESHOLD,
    CONF_WEIGHT_PER_MINUTE,
    DEFAULT_PRESENCE_WEIGHT,
    DEFAULT_THRESHOLD,
    DOMAIN,
    SCORE_CAP,
    STORAGE_VERSION,
    TICK_INTERVAL_SECONDS,
)
from custom_components.cleanliness_tracker.models import (
    RoomConfig,
    RoomState,
    StoredData,
)
from custom_components.cleanliness_tracker.storage import CleanlinessStore


@pytest.fixture
def mock_hass() -> MagicMock:
    return MagicMock(name="HomeAssistant")


def _make_state(**overrides: Any) -> dict[str, Any]:
    base = {
        "current_score": 0.0,
        "presence_started_at": None,
        "last_cleaned_at": None,
        "last_scored_at": None,
    }
    base.update(overrides)
    return base


class TestStoreConstruction:
    def test_uses_per_entry_key(self, mock_hass: MagicMock):
        with patch("custom_components.cleanliness_tracker.storage.Store") as store_cls:
            CleanlinessStore(mock_hass, "abc123")
        store_cls.assert_called_once_with(
            mock_hass, STORAGE_VERSION, f"{DOMAIN}.abc123"
        )

    def test_two_entries_have_distinct_keys(self, mock_hass: MagicMock):
        with patch("custom_components.cleanliness_tracker.storage.Store") as store_cls:
            CleanlinessStore(mock_hass, "first")
            CleanlinessStore(mock_hass, "second")
        keys = [call.args[2] for call in store_cls.call_args_list]
        assert keys == [f"{DOMAIN}.first", f"{DOMAIN}.second"]


class TestLoad:
    async def test_load_when_disk_empty_returns_empty_dict(self, mock_hass: MagicMock):
        with patch("custom_components.cleanliness_tracker.storage.Store") as store_cls:
            store_cls.return_value.async_load = AsyncMock(return_value=None)
            store = CleanlinessStore(mock_hass, "e")
            rooms = await store.async_load()
        assert rooms == {}
        assert store.rooms == {}

    async def test_load_returns_copy(self, mock_hass: MagicMock):
        on_disk = {"rooms": {"living": _make_state(current_score=42.0)}}
        with patch("custom_components.cleanliness_tracker.storage.Store") as store_cls:
            store_cls.return_value.async_load = AsyncMock(return_value=on_disk)
            store = CleanlinessStore(mock_hass, "e")
            rooms = await store.async_load()
        rooms["living"]["current_score"] = 999.0
        # Internal state must not be mutated by changes to the returned dict.
        assert store.get_room_state("living") is not None
        assert store.get_room_state("living")["current_score"] == 42.0

    async def test_rooms_property_returns_defensive_copy(self, mock_hass: MagicMock):
        with patch("custom_components.cleanliness_tracker.storage.Store") as store_cls:
            store_cls.return_value.async_load = AsyncMock(
                return_value={"rooms": {"r": _make_state(current_score=10.0)}}
            )
            store = CleanlinessStore(mock_hass, "e")
            await store.async_load()
        snapshot = store.rooms
        snapshot.pop("r")
        assert "r" in store.rooms


class TestSave:
    async def test_save_writes_in_memory_payload(self, mock_hass: MagicMock):
        with patch("custom_components.cleanliness_tracker.storage.Store") as store_cls:
            store_cls.return_value.async_load = AsyncMock(return_value=None)
            store_cls.return_value.async_save = AsyncMock()
            store = CleanlinessStore(mock_hass, "e")
            await store.async_load()
            store.set_room_state(
                "kitchen",
                _make_state(current_score=12.5),  # type: ignore[arg-type]
            )
            await store.async_save()
        store_cls.return_value.async_save.assert_awaited_once_with(
            {"rooms": {"kitchen": _make_state(current_score=12.5)}}
        )

    async def test_save_can_be_called_before_load(self, mock_hass: MagicMock):
        # Should not crash if a caller saves before loading; payload is empty.
        with patch("custom_components.cleanliness_tracker.storage.Store") as store_cls:
            store_cls.return_value.async_save = AsyncMock()
            store = CleanlinessStore(mock_hass, "e")
            await store.async_save()
        store_cls.return_value.async_save.assert_awaited_once_with({"rooms": {}})


class TestRoomCRUD:
    async def test_get_unknown_room_returns_none(self, mock_hass: MagicMock):
        with patch("custom_components.cleanliness_tracker.storage.Store") as store_cls:
            store_cls.return_value.async_load = AsyncMock(return_value=None)
            store = CleanlinessStore(mock_hass, "e")
            await store.async_load()
        assert store.get_room_state("nope") is None

    async def test_set_then_get_round_trip(self, mock_hass: MagicMock):
        with patch("custom_components.cleanliness_tracker.storage.Store") as store_cls:
            store_cls.return_value.async_load = AsyncMock(return_value=None)
            store = CleanlinessStore(mock_hass, "e")
            await store.async_load()
            state = _make_state(
                current_score=5.5,
                presence_started_at="2026-04-19T13:00:00+00:00",
            )
            store.set_room_state("bath", state)  # type: ignore[arg-type]
        got = store.get_room_state("bath")
        assert got == state

    async def test_remove_existing_room(self, mock_hass: MagicMock):
        with patch("custom_components.cleanliness_tracker.storage.Store") as store_cls:
            store_cls.return_value.async_load = AsyncMock(
                return_value={"rooms": {"r": _make_state(current_score=1.0)}}
            )
            store = CleanlinessStore(mock_hass, "e")
            await store.async_load()
            store.remove_room("r")
        assert store.get_room_state("r") is None
        assert store.rooms == {}

    async def test_remove_unknown_room_is_noop(self, mock_hass: MagicMock):
        with patch("custom_components.cleanliness_tracker.storage.Store") as store_cls:
            store_cls.return_value.async_load = AsyncMock(return_value=None)
            store = CleanlinessStore(mock_hass, "e")
            await store.async_load()
            store.remove_room("does-not-exist")  # must not raise
        assert store.rooms == {}


class TestModelsSurface:
    def test_constants_exposed(self):
        assert DOMAIN == "cleanliness_tracker"
        assert STORAGE_VERSION == 1
        assert CONF_ROOMS == "rooms"
        assert CONF_AREA_ID == "area_id"
        assert CONF_PRESENCE_ENTITY_ID == "presence_entity_id"
        assert CONF_THRESHOLD == "threshold"
        assert CONF_WEIGHT_PER_MINUTE == "weight_per_minute"
        assert DEFAULT_THRESHOLD == 80.0
        assert DEFAULT_PRESENCE_WEIGHT == 0.5
        assert TICK_INTERVAL_SECONDS == 300
        assert SCORE_CAP == 100.0

    def test_models_have_expected_keys(self):
        assert set(RoomConfig.__annotations__) == {
            "id",
            "area_id",
            "presence_entity_id",
            "threshold",
            "weight_per_minute",
        }
        assert set(RoomState.__annotations__) == {
            "current_score",
            "presence_started_at",
            "last_cleaned_at",
            "last_scored_at",
        }
        assert set(StoredData.__annotations__) == {"rooms"}
