# Scene Priority (`scene_priority`)

**English** | [繁體中文](README.zh-TW.md)

A lightweight Home Assistant custom integration (HACS / Marketplace compatible) that adds **per-device priority locks and fallback queuing** on top of native Home Assistant `scene.*` entities — without requiring your automations to know about each other.

---

## Why Scene Priority?

Home Assistant scenes are stateless snapshots (`scene.turn_on`). Without priority arbitration, a scheduled automation (e.g. sunset lighting) can accidentally overwrite an active contextual scene (e.g. watching a movie) unless you couple your automations together with messy helper conditions.

**Scene Priority** solves this cleanly:
- **Zero cross-automation coupling**: Each automation only manages its own scene.
- **Native `scene.*` first**: Keep using your existing Home Assistant scenes and `scene.turn_on` actions.
- **Per-device locks**: Automatically inspects the entities inside each scene and only locks the devices that scene actually touches. Unrelated scenes never block each other.
- **Automatic fallback**: If a lower-priority scene (e.g. sunset) fires while a higher-priority scene (e.g. movie) holds the lock, it does not interrupt the current state — instead, it is queued underneath and automatically applied when the higher-priority scene is released.
- **Manual UI clicks stay free**: Direct human clicks on `scene.turn_on` in the UI/App (`user_id` present with no `parent_id`) bypass automation locks so manual control is never blocked.
- **Editable entities & bilingual UI**: Exposes `sensor.active_scene`, an editable `number` entity for every configured scene, and full English / Traditional Chinese translations.

---

## Priority Rules

- **`0` (Default / Unset)**: Lowest priority. Every unconfigured scene defaults to `0`.
- **`> 0` (`1`, `2`, `3`, ...)**: Active priority levels where **`1` is highest**, `2` is next, and so on.
- **Any `> 0` priority always overrides `0`**. Equal or higher priorities overwrite lower ones (`1` beats `2`; `2` beats `0`; `0` cannot overwrite `> 0`).

---

## Installation

### Option 1: HACS / Home Assistant Marketplace (Custom Repository)
1. Open **HACS / Marketplace** in Home Assistant.
2. Add this repository URL as a **Custom Repository** with category **Integration**.
3. Download **Scene Priority** and restart Home Assistant.
4. Go to **Settings → Devices & Services → Add Integration** and add **Scene Priority**.

### Option 2: Manual Installation
1. Copy `custom_components/scene_priority` into your Home Assistant `/config/custom_components/scene_priority/` directory.
2. Restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration** and add **Scene Priority**.

---

## Configuration

1. Open **Settings → Devices & Services → Scene Priority → Configure**.
2. View currently configured priorities at the top of the menu, and add, update, or remove default priorities (`0`–`100`) for any `scene.*` entity.
3. Every configured scene also creates an editable **`number.<scene>_priority`** entity so you can inspect or adjust its priority directly from entity panels or dashboards.

---

## Services

| Service | Description |
| :--- | :--- |
| `scene_priority.activate` | Push a scene onto its target devices' priority locks (uses configured priority or optional `priority` override). |
| `scene_priority.release` | Release `scene_entity_id` from all device locks and automatically apply the next-highest queued scene underneath, if any. |
| `scene_priority.clear` | Clear all device priority locks without applying any scene. |

> **Note:** Native `scene.turn_on` calls from automations/scripts are automatically intercepted and checked against the priority locks, so existing automations work without needing to switch away from `scene.turn_on`.

---

## Example: Sunset vs. Movie Night

1. Leave `scene.sunset` at default priority **`0`** (or set it to `10`), and set `scene.movie_night` to priority **`1`**.
2. **Sunset automation** (completely unaware of movie mode):
   ```yaml
   triggers:
     - trigger: sun
       event: sunset
   actions:
     - action: scene.turn_on
       target:
         entity_id: scene.sunset
   ```
3. **Movie automation**:
   ```yaml
   triggers:
     - trigger: state
       entity_id: remote.living_room_tv
       to: "on"
       id: tv_on
     - trigger: state
       entity_id: remote.living_room_tv
       from: "on"
       to: ["off", "unavailable"]
       id: tv_off
   actions:
     - choose:
         - conditions:
             - condition: trigger
               id: tv_on
           sequence:
             - action: scene.turn_on
               target:
                 entity_id: scene.movie_night
         - conditions:
             - condition: trigger
               id: tv_off
           sequence:
             - action: scene_priority.release
               data:
                 scene_entity_id: scene.movie_night
   ```

If the TV turns on before sunset, `scene.movie_night` locks the living room lights at priority `1`. When sunset fires, `scene.sunset` is queued underneath without turning the lights on. Once the TV turns off and `scene_priority.release` runs, `scene.sunset` is automatically applied.

---

## Entities

- **`sensor.active_scene`**: Shows the currently active locked scene entity ID (or `idle`), with attributes `active_priority`, `device_locks`, and `configured_priorities`.
- **`number.<scene>_priority`**: Created for each scene with a configured priority.
