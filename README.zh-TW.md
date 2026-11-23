# Scene Priority（場景優先權 `scene_priority`）

[English](README.md) | **繁體中文**

一個輕量級的 Home Assistant 自訂整合（相容 HACS / Marketplace），為 Home Assistant 原生的 `scene.*` 場景加上**裝置級優先權鎖與自動補套用佇列**，讓不同自動化之間完全不需互相依賴或判斷彼此狀態。

---

## 為什麼需要 Scene Priority？

Home Assistant 的場景（Scene）本身是無狀態的一次性快照（`scene.turn_on`）。當「日落自動開燈」這類排程自動化，遇上「看電影關燈」這類情境自動化時，低優先權的排程會直接把正在進行的高優先權場景覆蓋掉；而傳統解法往往得在各個自動化之間互寫一堆條件，導致越來越難維護。

**Scene Priority** 用最純淨的方式解決這個問題：
- **零跨自動化耦合**：每個自動化只需要管好自己的場景。
- **保留原生 `scene.*` 習慣**：不用放棄原本的 Scene，現有自動化繼續用 `scene.turn_on` 就能生效。
- **裝置級優先權鎖**：自動讀取每個 Scene 內包含的實體，只鎖定該場景有碰到的裝置；沒有重疊裝置的場景互不干擾。
- **高壓低與自動補套用**：當高優先權場景（如看電影）鎖住裝置時，期間觸發的低優先權場景（如日落夜間）不會打斷當前狀態，而是安全地記在底層；等高優先權釋放後，系統會自動補套用底層次高優先權的場景。
- **不擋人為手動操作**：在 UI／App 直接手動點擊 `scene.turn_on` 按鈕（具備 `user_id` 且無 `parent_id`）會直接放行，只對自動化觸發進行優先權攔截。
- **實體化管理與雙語介面**：提供 `sensor.active_scene`、各場景獨立的 `number` 優先權實體，以及完整繁體中文／英文介面。

---

## 優先權規則

- **`0`（預設／未設定）**：最低優先權。所有未特別設定的場景預設皆為 `0`。
- **`> 0`（`1`、`2`、`3`…）**：有效鎖定優先權，**`1` 最大（最高優先權）**，其次為 `2`、`3`…。
- **任何 `> 0` 永遠可覆蓋 `0`**：優先權高於或等於目前鎖定值時才會覆蓋（`1` 可蓋 `2`；`2` 可蓋 `0`；`0` 無法覆蓋任何 `> 0`）。

---

## 安裝方式

### 方式一：透過 HACS / Home Assistant Marketplace（自訂儲存庫）
1. 在 Home Assistant 打開 **HACS / Marketplace**。
2. 將本專案 GitHub 網址加入**自訂儲存庫**，類別選擇 **整合（Integration）**。
3. 下載 **Scene Priority** 並重新啟動 Home Assistant。
4. 到 **設定 → 裝置與服務 → 新增整合**，搜尋並加入 **Scene Priority**。

### 方式二：手動安裝（本機測試）
1. 將 `custom_components/scene_priority` 資料夾複製到 Home Assistant 的 `/config/custom_components/scene_priority/`。
2. 重新啟動 Home Assistant。
3. 到 **設定 → 裝置與服務 → 新增整合**，搜尋並加入 **Scene Priority**。

---

## 設定方式

1. 到 **設定 → 裝置與服務 → Scene Priority → 設定（Configure）**。
2. 選單上方會直接列出目前已設定的場景優先權清單，可隨時新增、更新或移除各場景的優先權（`0`–`100`）。
3. 每個已設定優先權的場景都會自動建立對應的 **`number.<場景>_priority`** 實體，可直接從裝置頁面或儀表板調整數字。

---

## 提供服務（Services）

| 服務 | 說明 |
| :--- | :--- |
| `scene_priority.activate` | 依設定或指定優先權啟動場景並鎖定目標裝置；若被更高優先權鎖住則排入底層佇列。 |
| `scene_priority.release` | 釋放指定場景對所有裝置的鎖定，並自動補執行底層次高優先權的場景（若有）。 |
| `scene_priority.clear` | 清空所有裝置的優先權鎖定，不執行任何場景。 |

> **提示**：自動化或腳本呼叫原生的 `scene.turn_on` 時也會自動經過優先權檢查，因此既有的自動化無需改寫啟動方式即可直接使用。

---

## 使用範例：日落場景 vs. 看電影場景

1. `scene.sunset`（日落／夜間）維持預設 **`0`**，將 `scene.movie_night`（看電影）設為 **`1`**。
2. **`日落場景` 自動化**（完全不需知道看電影的存在）：
   ```yaml
   triggers:
     - trigger: sun
       event: sunset
   actions:
     - action: scene.turn_on
       target:
         entity_id: scene.sunset
   ```
3. **`看電影場景` 自動化**：
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

日落前開電視時，`看電影` 會以優先權 `1` 鎖住客廳燈；看到一半遇上日落時，`日落` 場景會被安全擋下並排在底層；等到關電視執行 `scene_priority.release` 時，系統就會自動補執行 `日落` 場景把燈打開。

---

## 提供實體

- **`sensor.active_scene`**（目前生效場景）：顯示目前鎖定中的最高優先權場景（或 `idle`／待機中），屬性包含 `active_priority`、`device_locks` 與 `configured_priorities`。
- **`number.<場景>_priority`**（`<場景> 優先權`）：為每個已設定優先權的場景建立的可編輯數字實體。
