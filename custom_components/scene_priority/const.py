"""Constants for the Scene Priority integration."""

DOMAIN = "scene_priority"

PLATFORMS = ["sensor", "number"]

STORAGE_KEY = f"{DOMAIN}.stack"
STORAGE_VERSION = 1

# 0 = unset (lowest); > 0 = active priority where 1 is highest.
DEFAULT_PRIORITY = 0
MIN_PRIORITY = 0
MAX_PRIORITY = 100

CONF_SCENE_PRIORITIES = "scene_priorities"

ATTR_SCENE_ENTITY_ID = "scene_entity_id"
ATTR_PRIORITY = "priority"
ATTR_TRANSITION = "transition"

SERVICE_ACTIVATE = "activate"
SERVICE_RELEASE = "release"
SERVICE_CLEAR = "clear"

EVENT_PRIORITY_CHANGED = f"{DOMAIN}_changed"
