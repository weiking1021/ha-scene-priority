"""Scene Priority integration for Home Assistant."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_PRIORITY,
    ATTR_SCENE_ENTITY_ID,
    ATTR_TRANSITION,
    DOMAIN,
    MAX_PRIORITY,
    MIN_PRIORITY,
    PLATFORMS,
    SERVICE_ACTIVATE,
    SERVICE_CLEAR,
    SERVICE_RELEASE,
)
from .manager import ScenePriorityManager

_LOGGER = logging.getLogger(__name__)

ACTIVATE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_SCENE_ENTITY_ID): cv.entity_domain("scene"),
        vol.Optional(ATTR_PRIORITY): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_PRIORITY, max=MAX_PRIORITY)
        ),
        vol.Optional(ATTR_TRANSITION): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=300)
        ),
    }
)

RELEASE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_SCENE_ENTITY_ID): cv.entity_domain("scene"),
        vol.Optional(ATTR_TRANSITION): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=300)
        ),
    }
)

CLEAR_SCHEMA = vol.Schema({})


def _extract_scene_entity_ids(call: ServiceCall) -> list[str]:
    """Extract target scene entity_ids from call.data."""
    raw = call.data.get("entity_id")
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, (list, tuple)):
        return [str(item) for item in raw]
    return []


def _is_manual_ui_call(call: ServiceCall) -> bool:
    """Return True if a service call was triggered directly by a user in the UI."""
    return call.context.user_id is not None and call.context.parent_id is None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Scene Priority from a config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {})

    # Capture original scene.turn_on handler once so we can wrap and restore it.
    if "orig_scene_turn_on" not in domain_data:
        scene_services = getattr(hass.services, "_services", {}).get("scene", {})
        orig_service = scene_services.get("turn_on")
        if orig_service is not None:
            domain_data["orig_scene_turn_on"] = orig_service

    orig_service = domain_data.get("orig_scene_turn_on")

    async def _raw_scene_turn_on(service_data: dict[str, Any]) -> None:
        if orig_service is not None:
            await orig_service.job.target(
                ServiceCall(hass, "scene", "turn_on", service_data)
            )
        else:
            await hass.services.async_call(
                "scene", "turn_on", service_data, blocking=True
            )

    manager = ScenePriorityManager(hass, entry, _raw_scene_turn_on)
    await manager.async_load()
    domain_data["manager"] = manager
    domain_data[entry.entry_id] = manager

    if orig_service is not None:

        async def _wrapped_scene_turn_on(call: ServiceCall) -> None:
            # Never block direct human button clicks in the UI/App.
            if _is_manual_ui_call(call):
                _LOGGER.debug(
                    "Allowing direct manual UI scene.turn_on call: %s", call.data
                )
                await orig_service.job.target(call)
                return

            scene_ids = _extract_scene_entity_ids(call)
            if not scene_ids:
                await orig_service.job.target(call)
                return

            transition = call.data.get(ATTR_TRANSITION)
            for scene_id in scene_ids:
                await manager.async_activate(
                    scene_entity_id=scene_id,
                    priority=None,
                    transition=transition,
                )

        hass.services.async_register(
            "scene",
            "turn_on",
            _wrapped_scene_turn_on,
            schema=orig_service.schema,
        )

    async def _handle_activate(call: ServiceCall) -> None:
        await manager.async_activate(
            scene_entity_id=call.data[ATTR_SCENE_ENTITY_ID],
            priority=call.data.get(ATTR_PRIORITY),
            transition=call.data.get(ATTR_TRANSITION),
        )

    async def _handle_release(call: ServiceCall) -> None:
        await manager.async_release(
            scene_entity_id=call.data[ATTR_SCENE_ENTITY_ID],
            transition=call.data.get(ATTR_TRANSITION),
        )

    async def _handle_clear(call: ServiceCall) -> None:
        await manager.async_clear()

    hass.services.async_register(
        DOMAIN, SERVICE_ACTIVATE, _handle_activate, schema=ACTIVATE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RELEASE, _handle_release, schema=RELEASE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CLEAR, _handle_clear, schema=CLEAR_SCHEMA
    )

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle config entry options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Scene Priority config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        domain_data = hass.data.get(DOMAIN, {})
        domain_data.pop(entry.entry_id, None)
        domain_data.pop("manager", None)

        # Restore original scene.turn_on handler if we wrapped it.
        orig_service = domain_data.pop("orig_scene_turn_on", None)
        if orig_service is not None:
            hass.services.async_register(
                "scene",
                "turn_on",
                orig_service.job.target,
                schema=orig_service.schema,
            )

        for service in (SERVICE_ACTIVATE, SERVICE_RELEASE, SERVICE_CLEAR):
            hass.services.async_remove(DOMAIN, service)
    return unload_ok
