"""Number platform exposing each configured scene's priority as an entity."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_SCENE_PRIORITIES, MAX_PRIORITY, MIN_PRIORITY


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create a NumberEntity for every scene with a configured priority."""
    configured = entry.options.get(CONF_SCENE_PRIORITIES, {})
    entities = [
        ScenePriorityNumber(hass, entry, str(scene_id))
        for scene_id in configured
    ]
    async_add_entities(entities)


class ScenePriorityNumber(NumberEntity):
    """Editable number entity representing a scene's configured priority."""

    _attr_has_entity_name = True
    _attr_translation_key = "scene_priority"
    _attr_native_min_value = float(MIN_PRIORITY)
    _attr_native_max_value = float(MAX_PRIORITY)
    _attr_native_step = 1.0
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:sort-numeric-ascending"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        scene_entity_id: str,
    ) -> None:
        self.hass = hass
        self._entry = entry
        self._scene_entity_id = scene_entity_id
        self._attr_unique_id = f"{entry.entry_id}_prio_{scene_entity_id}"

        state = hass.states.get(scene_entity_id)
        friendly = (
            state.attributes.get("friendly_name")
            if state is not None
            else None
        )
        label = friendly or scene_entity_id.removeprefix("scene.")
        self._attr_translation_placeholders = {"scene_name": str(label)}

    @property
    def native_value(self) -> float:
        """Return the current configured priority for this scene."""
        configured = self._entry.options.get(CONF_SCENE_PRIORITIES, {})
        return float(configured.get(self._scene_entity_id, 0))

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Expose the linked scene entity_id."""
        return {"scene_entity_id": self._scene_entity_id}

    async def async_set_native_value(self, value: float) -> None:
        """Update the scene's priority in config entry options."""
        updated = dict(self._entry.options.get(CONF_SCENE_PRIORITIES, {}))
        updated[self._scene_entity_id] = int(value)
        self.hass.config_entries.async_update_entry(
            self._entry,
            options={**self._entry.options, CONF_SCENE_PRIORITIES: updated},
        )
