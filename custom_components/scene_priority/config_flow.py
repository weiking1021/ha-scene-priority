"""Config flow for Scene Priority integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_SCENE_PRIORITIES,
    DEFAULT_PRIORITY,
    DOMAIN,
    MAX_PRIORITY,
    MIN_PRIORITY,
)


class ScenePriorityConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Scene Priority."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(
                title="Scene Priority",
                data={},
                options={CONF_SCENE_PRIORITIES: {}},
            )

        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> ScenePriorityOptionsFlow:
        """Return the options flow handler."""
        return ScenePriorityOptionsFlow()


class ScenePriorityOptionsFlow(config_entries.OptionsFlow):
    """Manage per-scene default priority mappings."""

    def _format_current_list(self, current: dict[str, Any]) -> str:
        if not current:
            return "—"
        lines: list[str] = []
        for scene_id, prio in sorted(
            current.items(), key=lambda x: (int(x[1]) == 0, int(x[1]))
        ):
            state = self.hass.states.get(scene_id)
            name = state.attributes.get("friendly_name") if state else None
            label = f"{name} ({scene_id})" if name else scene_id
            lines.append(f"- {label}: {prio}")
        return "\n".join(lines)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show menu to add/update or remove a scene priority."""
        current = dict(self.config_entry.options.get(CONF_SCENE_PRIORITIES, {}))
        menu_options = ["set_priority"]
        if current:
            menu_options.append("remove_priority")
        return self.async_show_menu(
            step_id="init",
            menu_options=menu_options,
            description_placeholders={"current_list": self._format_current_list(current)},
        )

    async def async_step_set_priority(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add or update a scene's default priority."""
        if user_input is not None:
            current = dict(self.config_entry.options.get(CONF_SCENE_PRIORITIES, {}))
            current[user_input["scene_entity_id"]] = int(user_input["priority"])
            return self.async_create_entry(
                title="",
                data={CONF_SCENE_PRIORITIES: current},
            )

        schema = vol.Schema(
            {
                vol.Required("scene_entity_id"): EntitySelector(
                    EntitySelectorConfig(domain="scene")
                ),
                vol.Required("priority", default=DEFAULT_PRIORITY): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_PRIORITY,
                        max=MAX_PRIORITY,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="set_priority", data_schema=schema)

    async def async_step_remove_priority(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Remove a configured scene priority."""
        current = dict(self.config_entry.options.get(CONF_SCENE_PRIORITIES, {}))
        if user_input is not None:
            scene_id = user_input["scene_entity_id"]
            current.pop(scene_id, None)

            # Clean up the corresponding number entity from the entity registry.
            ent_reg = er.async_get(self.hass)
            unique_id = f"{self.config_entry.entry_id}_prio_{scene_id}"
            entity_id = ent_reg.async_get_entity_id("number", DOMAIN, unique_id)
            if entity_id:
                ent_reg.async_remove(entity_id)

            return self.async_create_entry(
                title="",
                data={CONF_SCENE_PRIORITIES: current},
            )

        options = []
        for scene_id, prio in sorted(
            current.items(), key=lambda x: (int(x[1]) == 0, int(x[1]))
        ):
            state = self.hass.states.get(scene_id)
            name = state.attributes.get("friendly_name") if state else None
            label = f"{name} ({scene_id}) — {prio}" if name else f"{scene_id} — {prio}"
            options.append({"value": scene_id, "label": label})

        schema = vol.Schema(
            {
                vol.Required("scene_entity_id"): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )
        return self.async_show_form(step_id="remove_priority", data_schema=schema)
