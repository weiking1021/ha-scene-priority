"""Sensor platform for Scene Priority."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .manager import ScenePriorityManager


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Scene Priority active sensor."""
    manager: ScenePriorityManager = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ScenePriorityActiveSensor(entry, manager)])


class ScenePriorityActiveSensor(SensorEntity):
    """Sensor exposing the highest-priority active scene and per-device locks."""

    _attr_has_entity_name = True
    _attr_translation_key = "active_scene"
    _attr_icon = "mdi:layers-triple"

    def __init__(self, entry: ConfigEntry, manager: ScenePriorityManager) -> None:
        self._manager = manager
        self._attr_unique_id = f"{entry.entry_id}_active_scene"

    @property
    def native_value(self) -> str:
        """Return the highest-priority active scene entity_id, or 'idle'."""
        return self._manager.active_scene or "idle"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return active priority, per-device locks, and configured priorities."""
        return {
            "active_priority": self._manager.active_priority,
            "device_locks": self._manager.device_locks,
            "configured_priorities": self._manager.configured_priorities,
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to manager updates."""
        self.async_on_remove(self._manager.add_listener(self._handle_update))

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
