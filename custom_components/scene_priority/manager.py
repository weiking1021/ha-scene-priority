"""Per-device priority stack manager for Home Assistant scenes."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    CONF_SCENE_PRIORITIES,
    DEFAULT_PRIORITY,
    EVENT_PRIORITY_CHANGED,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)


def priority_sort_key(priority: int) -> tuple[bool, int]:
    """Return sort key where smaller tuple = higher priority.

    > 0: 1 is highest, then 2, 3, ...
    0 (unset): always lowest, beaten by any > 0 priority.
    """
    return (priority == 0, priority)


def wins_over(new_priority: int, current_priority: int) -> bool:
    """Return True if new_priority can overwrite current_priority."""
    return priority_sort_key(new_priority) <= priority_sort_key(current_priority)


class ScenePriorityManager:
    """Manage per-device scene priority locks and fallback queues."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        raw_scene_turn_on: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        self.hass = hass
        self.entry = entry
        self._raw_scene_turn_on = raw_scene_turn_on
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        # device_entity_id -> ordered dict of scene_entity_id -> priority
        self._device_stacks: dict[str, dict[str, int]] = {}
        self._lock = asyncio.Lock()
        self._listeners: list[Callable[[], None]] = []

    @property
    def configured_priorities(self) -> dict[str, int]:
        """Return user-configured priorities from config entry options."""
        raw = self.entry.options.get(CONF_SCENE_PRIORITIES, {})
        return {str(k): int(v) for k, v in raw.items()}

    @property
    def device_locks(self) -> dict[str, dict[str, Any]]:
        """Return summary of currently locked devices and their winning scene/priority."""
        result: dict[str, dict[str, Any]] = {}
        for dev_id, stack in self._device_stacks.items():
            top = self._top_entry(stack)
            if top is not None and top[1] > 0:
                result[dev_id] = {
                    "scene": top[0],
                    "priority": top[1],
                    "stack": dict(stack),
                }
        return result

    @property
    def active_scene(self) -> str | None:
        """Return the highest-priority active scene across all locked devices."""
        winner = self._global_top()
        return winner[0] if winner is not None else None

    @property
    def active_priority(self) -> int:
        """Return the highest active priority (>0) across all devices, or 0 if idle."""
        winner = self._global_top()
        return winner[1] if winner is not None else 0

    def _global_top(self) -> tuple[str, int] | None:
        best: tuple[str, int] | None = None
        for stack in self._device_stacks.values():
            top = self._top_entry(stack)
            if top is None or top[1] == 0:
                continue
            if best is None or priority_sort_key(top[1]) <= priority_sort_key(best[1]):
                best = top
        return best

    @staticmethod
    def _top_entry(stack: dict[str, int]) -> tuple[str, int] | None:
        """Return (scene_id, priority) with highest priority; latest wins ties."""
        if not stack:
            return None
        best_scene: str | None = None
        best_prio: int | None = None
        for scene_id, prio in stack.items():
            if best_prio is None or wins_over(prio, best_prio):
                best_scene = scene_id
                best_prio = prio
        assert best_scene is not None and best_prio is not None
        return best_scene, best_prio

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register a callback invoked whenever locks change."""
        self._listeners.append(listener)

        def _remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _remove

    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()
        self.hass.bus.async_fire(
            EVENT_PRIORITY_CHANGED,
            {
                "active_scene": self.active_scene,
                "active_priority": self.active_priority,
                "device_locks": self.device_locks,
            },
        )

    def resolve_priority(self, scene_entity_id: str, explicit_priority: int | None) -> int:
        """Resolve effective priority: explicit arg > configured option > 0 (unset)."""
        if explicit_priority is not None:
            return int(explicit_priority)
        return self.configured_priorities.get(scene_entity_id, DEFAULT_PRIORITY)

    def get_scene_targets(self, scene_entity_id: str) -> list[str]:
        """Return entity_ids controlled by a scene, falling back to [scene_entity_id]."""
        state = self.hass.states.get(scene_entity_id)
        if state is not None:
            members = state.attributes.get("entity_id")
            if isinstance(members, (list, tuple)) and members:
                return [str(m) for m in members]
        return [scene_entity_id]

    async def async_load(self) -> None:
        """Load persisted device stacks from Home Assistant storage."""
        data = await self._store.async_load()
        if isinstance(data, dict) and isinstance(data.get("device_stacks"), dict):
            loaded: dict[str, dict[str, int]] = {}
            for dev_id, stack in data["device_stacks"].items():
                if isinstance(stack, dict):
                    loaded[str(dev_id)] = {str(s): int(p) for s, p in stack.items()}
            self._device_stacks = loaded

    async def _async_save(self) -> None:
        await self._store.async_save({"device_stacks": self._device_stacks})

    async def async_activate(
        self,
        scene_entity_id: str,
        priority: int | None = None,
        transition: float | None = None,
    ) -> bool:
        """Check per-device priority locks and activate or queue a scene.

        Returns True if the scene was allowed and applied, False if blocked.
        """
        async with self._lock:
            resolved = self.resolve_priority(scene_entity_id, priority)
            targets = self.get_scene_targets(scene_entity_id)

            blocked_by: list[tuple[str, str, int]] = []
            for dev_id in targets:
                stack = self._device_stacks.get(dev_id, {})
                top = self._top_entry(stack)
                if top is not None and not wins_over(resolved, top[1]):
                    blocked_by.append((dev_id, top[0], top[1]))

            # Record this scene on each target device's stack (for fallback if blocked,
            # or as the active lock if allowed and priority > 0).
            for dev_id in targets:
                stack = self._device_stacks.setdefault(dev_id, {})
                stack.pop(scene_entity_id, None)
                stack[scene_entity_id] = resolved

            await self._async_save()

            if blocked_by:
                _LOGGER.info(
                    "Blocked scene %s (priority %s); device locks: %s",
                    scene_entity_id,
                    resolved,
                    blocked_by,
                )
                self._notify()
                return False

            _LOGGER.debug(
                "Activating scene %s at priority %s on targets %s",
                scene_entity_id,
                resolved,
                targets,
            )
            service_data: dict[str, Any] = {"entity_id": scene_entity_id}
            if transition is not None:
                service_data["transition"] = transition
            await self._raw_scene_turn_on(service_data)

            self._notify()
            return True

    async def async_release(
        self, scene_entity_id: str, transition: float | None = None
    ) -> list[str]:
        """Release a scene from all device locks and apply any fallback scenes.

        Returns list of fallback scene entity_ids applied.
        """
        async with self._lock:
            fallbacks_to_apply: list[str] = []
            empty_devices: list[str] = []
            changed = False

            for dev_id, stack in self._device_stacks.items():
                if scene_entity_id not in stack:
                    continue
                changed = True
                prev_top = self._top_entry(stack)
                del stack[scene_entity_id]
                if not stack:
                    empty_devices.append(dev_id)
                    continue
                new_top = self._top_entry(stack)
                if (
                    prev_top is not None
                    and prev_top[0] == scene_entity_id
                    and new_top is not None
                    and new_top[0] not in fallbacks_to_apply
                ):
                    fallbacks_to_apply.append(new_top[0])

            for dev_id in empty_devices:
                del self._device_stacks[dev_id]

            if not changed:
                return []

            await self._async_save()

            for fallback_scene in fallbacks_to_apply:
                _LOGGER.debug(
                    "Released %s; applying fallback scene %s",
                    scene_entity_id,
                    fallback_scene,
                )
                service_data: dict[str, Any] = {"entity_id": fallback_scene}
                if transition is not None:
                    service_data["transition"] = transition
                await self._raw_scene_turn_on(service_data)

            self._notify()
            return fallbacks_to_apply

    async def async_clear(self) -> None:
        """Clear all device priority locks without applying any scene."""
        async with self._lock:
            self._device_stacks.clear()
            await self._async_save()
            self._notify()
