# 阶段 #21 + #22 实施计划

## Summary

两条独立指令。#21 合并声音目录消除重复资源，#22 实现屏幕边缘吸附与停靠收缩态。按 #21 → #22 顺序实施（#21 改动小、风险低，先收掉）。

---

## 阶段 #21：声音目录合并

### 背景

当前声音资源存两份：`src/codex_traffic_lights/resources/sounds/`（打包进 exe 内部，只读）和项目根 `user_sounds/`（外部可写）。启动时 `ensure_default_sound_files()` 从内部复制到外部，运行时 `resolve_sound_path()` 做三级回退（config → user_sounds → resources），过度复杂。

### 目标

合并为单一声音目录 `sounds/`（项目根目录），同时满足版本控制和运行时可写。删除内部 resources/sounds，删除复制逻辑，简化回退链为两级。

### 变更清单

**1. 目录操作**
- 删除 `src/codex_traffic_lights/resources/sounds/` 整个目录（4 个 MP3 文件）
- 重命名 `user_sounds/` → `sounds/`（项目根目录）
- 保留 `src/codex_traffic_lights/resources/icons/app.ico` 不动

**2. `sound_settings.py` 简化**
- 删除 `packaged_sound_path()` 函数
- 删除 `ensure_default_sound_files()` 函数
- `user_sound_dir()` 改名 `sound_dir()`，直接返回 `portable_sound_dir() / "sounds"`
- `resolve_sound_path()` 简化为两级回退：
  ```
  1. config path（AppConfig 中配置的自定义路径，文件存在）→ 使用它
  2. sound_dir() / SOUND_FILE_BY_KIND[kind] → 使用它
  ```
  不再回退到 packaged_sound_path（该函数已删除）

**3. `settings_controller.py`**
- 删除 `ensure_default_sound_files` 的 import 和构造函数中的调用
- `user_sound_dir` import 改为 `sound_dir`

**4. `__main__.py`**
- 所有 `user_sound_dir` 引用改为 `sound_dir`

**5. `widgets/main_window.py`**
- `from codex_traffic_lights.sound_settings import user_sound_dir` → `import sound_dir`

**6. `scripts/build.py`**
- `ADD_DATA` 增加一行：将 `sounds/` 目录打包进输出
- 原有 `resources` 的 `--add-data` 保留（icons 仍需打包）
- 新增 `--add-data "sounds;sounds"` 或等效方式

**7. `.gitignore`**
- 追加：
  ```
  # User custom sounds (keep only defaults)
  sounds/*
  !sounds/任务完成.mp3
  !sounds/待审批确认.mp3
  !sounds/计划模式输入.mp3
  !sounds/运行异常.mp3
  ```

**8. 测试更新**
- `tests/test_sound_settings.py`：删除 `ensure_default_sound_files` 相关测试（`test_ensure_default_sound_files_populates_visible_sound_folder`），`user_sound_dir` 引用改为 `sound_dir`，删除 `packaged_sound_path` 引用
- `tests/test_settings_controller.py`：删除 `test_settings_controller_seeds_visible_default_sounds`，`"user_sounds"` 测试路径改为 `"sounds"`
- `tests/test_sound_player.py`：`resources/sounds` 路径引用更新
- `tests/test_build_script.py`：build command 断言更新，增加 `sounds;sounds` 的 `--add-data`

### 验收标准

- [ ] `src/codex_traffic_lights/resources/sounds/` 目录不存在
- [ ] `sounds/` 目录包含 4 个默认 MP3
- [ ] `sound_settings.py` 中无 `packaged_sound_path` 函数
- [ ] `sound_settings.py` 中无 `ensure_default_sound_files` 函数
- [ ] `resolve_sound_path()` 仅两级回退
- [ ] `settings_controller.py` 不调用 `ensure_default_sound_files`
- [ ] `pytest tests -q` 全量通过
- [ ] `ruff check src tests` 无错误
- [ ] 手测：播放默认音效、选择自定义音效、试听、重启后配置保留

---

## 阶段 #22：屏幕边缘吸附与停靠收缩态

### 背景

当前贴边行为（`main_window.py:357-385`）只有"滑到屏幕外留 6px 条"的隐藏逻辑，没有吸附对齐，没有可见的收缩形态。触发阈值仅 8px 太小，只用 `primaryScreen` 不支持多显示器。

参考 Windows USB 设备检测弹窗的行为：弹窗出现后自动缩回屏幕边缘，留一个可见的小指示图标。本指令实现相同模式——拖到边缘后自动收缩为一个始终可见的迷你指示面板（停靠态），用户通过灯色即可感知 Codex 状态。

### 设计方向

**工业仪表 LED 指示条**——不是"窗口缩小版"，而是像硬件设备边缘的状态 LED 条：暗色窄条上三颗彩色指示灯。保持 `docs/UI-Design-Direction.md` 的工业仪表美学，但渲染层数从 7 层简化到 3 层（10px 直径放不下玻璃质感）。

### 状态机

三种视觉形态，三种位置/行为状态：

```
         释放距边≤30px               静置 3 秒
FREE ────────────────→ SNAPPED ────────────────→ DOCKED
72×220    snap+slide    72×220    auto-dock       52×24
自由态    150ms          吸附态    300ms contract   停靠态
外观=当前compact        外观=同FREE                外观=迷你LED条

FREE   ←─────────────── SNAPPED ←─────────────── DOCKED
拖离边缘>30px            hover展开                 hover展开
unsnap+slide            暂时回SNAPPED              暂时回SNAPPED
```

**三态定义**：

| 状态 | 尺寸 | 外观 | 位置 |
|------|------|------|------|
| FREE | 72×220 | 完整 compact（7 层灯、header、status、buttons） | 屏幕内任意 |
| SNAPPED | 72×220 | 与 FREE 完全相同 | 紧贴屏幕边缘 |
| DOCKED | 52×24 | 迷你 LED 指示条（3 层灯、无文字、无按钮） | 紧贴屏幕边缘 |

### DOCKED 态视觉规格

**面板**：
- 尺寸：52×24 px
- 背景：`#0D0D0F`（与主面板一致，微冷蓝调黑）
- 边框：1px `#2A2A30`
- 圆角：6px

**灯泡（3 层简化渲染）**：
- 直径：10px
- 间距：8px（中心到中心 18px）
- 第 ① 层：底色圆 — 暗色版（红 `#140202`、黄 `#151000`、绿 `#031205`），opacity 0.1 表示灭灯
- 第 ② 层：亮色填充 — 亮色版（红 `#FF625A`、黄 `#FFE066`、绿 `#45E873`），opacity 由动画引擎控制
- 第 ③ 层：细描边 — 1px `#2A2A30`
- 激活灯额外：外微光 2px 扩散，0.15 opacity 灯色径向渐变

**禁用的渲染层**（10px 放不下）：
- groove（外壳凹槽）
- glass gradient（玻璃渐变）
- highlight（玻璃反射高光）
- inner glow（内发光）
- bezel（金属边框环）
- halo（大面积外光晕）→ 替换为 2px 微光

**布局**：
```
┌────────────────────────────┐
│    ●        ●        ●     │
│  10px     10px     10px   │
│  红       黄       绿     │
└────────────────────────────┘
←          52px           →
← 7px →← 18px →← 18px →← 9px →
       center-to-center
```

### 交互行为详规

**FREE → SNAPPED（吸附）**：
- 触发：`mouseReleaseEvent`，窗口左边缘或右边缘距屏幕边缘 ≤ `SNAP_THRESHOLD`（30px）
- 记录 `_snap_edge = "left"` 或 `"right"`
- 动画：纯位移动画，窗口滑到屏幕边缘对齐
- 时长：150ms，InOutCubic
- 外观不变（仍是完整 compact 72×220）
- 吸附完成后启动 3 秒 `QTimer`

**SNAPPED → DOCKED（自动停靠 / 收缩）**：
- 触发：SNAPPED 态下 3 秒定时器到期，或用户双击吸附态窗口
- 动画：同步执行以下变化（300ms，InOutCubic）：
  - 窗口宽度 72 → 52
  - 窗口高度 220 → 24
  - header opacity 1.0 → 0.0（渐隐）
  - status_bar opacity 1.0 → 0.0（渐隐）
  - side_buttons opacity 1.0 → 0.0（渐隐）
  - traffic_light 灯直径 36 → 10
  - traffic_light 切换到 3 层简化渲染模式
  - body 面板圆角 16 → 6
  - 位置保持紧贴屏幕边缘（x 坐标相应调整）
- 收缩完成后隐藏 header / status_bar / side_buttons（`setVisible(False)`）
- 设置 `_edge_state = EdgeState.DOCKED`

**DOCKED → SNAPPED（悬停展开）**：
- 触发：`enterEvent`（鼠标进入停靠态窗口）
- 动画：所有收缩动画反向（250ms，InOutCubic）
  - 宽度 52 → 72
  - 高度 24 → 220
  - 灯直径 10 → 36
  - 切换回 7 层完整渲染
  - header / status_bar / side_buttons 渐显
  - body 圆角 6 → 16
- 展开后临时回到 SNAPPED 态
- 设置 `_edge_state = EdgeState.SNAPPED`

**SNAPPED → DOCKED（离开收回）**：
- 触发：从悬停展开的 SNAPPED 态 `leaveEvent`，500ms 延迟后触发
- 动画：同 SNAPPED → DOCKED 的收缩动画（300ms）
- 如果鼠标在 500ms 内重新进入，取消定时器

**SNAPPED → FREE（解除吸附）**：
- 触发：SNAPPED 态下拖拽释放，释放位置距所有边缘 > `SNAP_THRESHOLD`
- 动画：窗口移动到释放位置（150ms，InOutCubic）
- 设置 `_edge_state = EdgeState.FREE`

**DOCKED → FREE（拖离边缘）**：
- 触发：DOCKED 态下拖拽释放，释放位置距所有边缘 > `SNAP_THRESHOLD`
- 动画：先展开到 SNAPPED 尺寸（250ms），再移动到释放位置（150ms）
- 设置 `_edge_state = EdgeState.FREE`

**禁止的行为**：
- DOCKED 态下不接受 expand / zoom 操作（先 hover 展开再操作）
- SNAPPED / DOCKED 态下 side_buttons 隐藏
- Expanded 模式下不触发吸附（`is_expanded` 为 True 时跳过 snap 检测）

### 多显示器

所有 `QApplication.primaryScreen()` 替换为 `self.screen().availableGeometry()`。吸附到窗口**所在屏幕**的边缘。

### 仅左右边缘

本指令仅实现左/右边缘吸附。上/下边缘留作后续扩展。

### 动画参数

| 常量 | 值 | 用途 |
|------|-----|------|
| `SNAP_THRESHOLD` | 30 | 吸附触发距离（px） |
| `SNAP_SLIDE_MS` | 150 | 吸附滑动时间 |
| `DOCK_CONTRACT_MS` | 300 | 收缩/展开动画时间 |
| `DOCK_EXPAND_MS` | 250 | 悬停展开时间 |
| `DOCK_AUTO_DELAY_MS` | 3000 | 吸附后自动停靠延迟 |
| `DOCK_COLLAPSE_DELAY_MS` | 500 | 离开后收回延迟 |
| `DOCKED_WIDTH` | 52 | 停靠态窗口宽度 |
| `DOCKED_HEIGHT` | 24 | 停靠态窗口高度 |
| `DOCKED_LAMP_DIAMETER` | 10 | 停靠态灯泡直径 |
| `DOCKED_BODY_RADIUS` | 6 | 停靠态面板圆角 |

所有动画使用 `QEasingCurve.InOutCubic`，禁止线性。

### 实现指引

**`models.py` 新增**：
```python
class EdgeState(Enum):
    FREE = "free"
    SNAPPED = "snapped"
    DOCKED = "docked"
```

**`main_window.py` 新增属性**：
```python
self._edge_state = EdgeState.FREE
self._snap_edge: str | None = None  # "left" | "right"
self._dock_timer: QTimer | None = None  # 3 秒自动停靠定时器
self._collapse_timer: QTimer | None = None  # 500ms 离开收回定时器
```

**`main_window.py` 重构**：
- 删除 `_apply_edge_hide()` 和 `_reveal_from_edge()`
- 删除 `EDGE_THRESHOLD`、`EDGE_VISIBLE_WIDTH` 常量
- 用新的三态逻辑替换
- `mouseReleaseEvent` 中增加 snap 检测
- `enterEvent` 中增加 DOCKED 态展开逻辑
- `leaveEvent` 中增加收回定时器逻辑

**`traffic_light.py` 新增方法**：
```python
def set_docked_mode(self, docked: bool) -> None:
    """切换完整 7 层渲染和简化 3 层渲染。"""
```
- `docked=True`：使用 3 层简化渲染（底色圆 + 亮色填充 + 细描边 + 激活微光）
- `docked=False`：恢复 7 层完整渲染（groove → dim glass → lit core → highlight → inner glow → halo → bezel）

**`main_window.py` 尺寸应用**：
- `_apply_size()` 增加 DOCKED 态处理，设置 `DOCKED_WIDTH × DOCKED_HEIGHT`
- `_apply_content_scale()` 增加 DOCKED 态处理，使用 `DOCKED_LAMP_DIAMETER`

### 测试计划

新增 `tests/test_edge_snap.py`：

1. `test_snap_triggers_within_threshold` — mouseRelease 位置在阈值内触发吸附
2. `test_snap_does_not_trigger_outside_threshold` — mouseRelease 位置在阈值外不触发
3. `test_snap_blocked_in_expanded_mode` — Expanded 模式下不触发吸附
4. `test_snap_uses_current_screen_not_primary` — 使用 `self.screen()` 而非 `primaryScreen`
5. `test_auto_dock_after_timeout` — 吸附态 3 秒后自动收缩
6. `test_double_click_skips_dock_delay` — 双击吸附态立即收缩
7. `test_hover_expands_docked` — 悬停停靠态展开
8. `test_leave_collapses_expanded` — 离开展开态 500ms 后收回
9. `test_drag_away_unsnaps` — 从吸附/停靠态拖离返回自由态
10. `test_docked_lamp_renders_simplified` — 停靠态灯使用简化渲染

### 验收标准

- [ ] 拖拽释放到屏幕左/右边缘 30px 内 → 窗口滑动到边缘对齐（150ms）
- [ ] 吸附后外观与 FREE 完全相同（72×220，36px 灯，7 层渲染）
- [ ] 吸附态静置 3 秒 → 平滑收缩为 52×24 迷你指示条（300ms）
- [ ] 收缩后仅显示 3 颗 10px LED 指示灯，无 header/status/buttons
- [ ] 灯光颜色仍跟随当前 CodexStatus，动画引擎仍驱动 opacity
- [ ] 双击吸附态立即收缩（跳过 3 秒等待）
- [ ] 悬停停靠态 → 展开回完整 72×220 形态（250ms）
- [ ] 离开展开态 → 500ms 后自动收回停靠态
- [ ] 从停靠/吸附态拖离边缘 → 返回自由态
- [ ] Expanded 模式下拖拽不触发吸附
- [ ] 多显示器：窗口吸附到所在屏幕边缘
- [ ] 所有动画使用 InOutCubic 缓动，无线性动画
- [ ] `pytest tests -q` 全量通过
- [ ] `ruff check src tests` 无错误

### Module Boundaries

- `EdgeState` 枚举放在 `models.py`（产品状态定义）
- 三态转换逻辑放在 `main_window.py`（窗口行为）
- 停靠态灯泡渲染放在 `traffic_light.py`（`set_docked_mode` + `_paint_docked_lamp`）
- 动画引擎（`animation/engine.py`）不改动，仍通过 opacity 属性驱动
- `side_buttons.py` 不改动，由 MainWindow 控制 visible/opacity

### Assumptions

- 仅实现左/右边缘吸附，上/下留作后续扩展
- 停靠态不显示文字和按钮，仅通过灯色传达状态
- 停靠态下状态变化不自动展开（用户主动 hover 才展开）
- 3 秒自动停靠延迟暂不做成可配置的
- 不删除旧代码中的 `_hidden_edge` 属性——用 `_edge_state` 枚举替代后自然废弃

### 建议提交名

- `feat: consolidate sound directory into single sounds/ folder`
- `feat: add edge snap and docked mini indicator mode`
