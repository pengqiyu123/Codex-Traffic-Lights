# Codex 开发命令

> 本文档包含发给 Codex CLI 执行的完整开发命令。按 Task 顺序逐条发给 Codex。
> 每个 Task 是一个独立的 Codex 会话，包含上下文说明 + 具体指令。

重要纠偏：前版 8 状态是 AI 推测，已废弃。所有开发任务必须先读取 `docs/Codex-State-Audit.md`，以 Codex app-server schema 中的真实可观测状态为准。

---

## 前置准备（手动执行）

```bash
cd "d:\python\Codex Traffic Lights"
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

---

## Task 1：数据模型层

```
请在 src/codex_traffic_lights/ 目录下创建数据模型层。

先读取 docs/Codex-State-Audit.md 和 docs/PRD.md。不要实现旧版 8 态；CodexStatus 只能包含当前确认的 6 个产品状态。

### 1. src/codex_traffic_lights/models.py
- CodexStatus 枚举：6 个成员（OFFLINE, IDLE, WORKING, WAITING_APPROVAL, WAITING_USER_INPUT, ERROR）
- 每个枚举成员包含：label(中文状态文字)、light_state(三灯各自的状态)
- LightMode 枚举：OFF, SOLID, SLOW_BREATH, INTERMITTENT_BLINK, SLOW_FLASH, FAST_FLASH
- LightState dataclass(frozen)：red(LightMode), yellow(LightMode), green(LightMode)
- AppConfig dataclass(frozen)：
  - poll_interval_ms(int=2000)
  - codex_process_name(str="codex")
  - app_server_url(str | None=None)
  - window_scale(float=1.0)
  - notification_enabled(bool=True)
  - sound_enabled(bool=True)

状态灯效：
- OFFLINE：红灯 SOLID
- IDLE：绿灯 SOLID
- WORKING：黄灯 SLOW_BREATH
- WAITING_APPROVAL：黄灯 SLOW_FLASH + 绿灯 SLOW_FLASH
- WAITING_USER_INPUT：黄灯 INTERMITTENT_BLINK
- ERROR：红灯 FAST_FLASH + 黄灯 FAST_FLASH

### 2. src/codex_traffic_lights/__init__.py
- 导出 __version__ = "0.1.0"

### 3. src/codex_traffic_lights/config.py
- ConfigManager 类：
  - __init__(self, config_path: Path | None = None)：默认 ~/.codex-traffic-lights/config.json
  - load(self) -> AppConfig：读取 JSON，缺失字段用 AppConfig 默认值补全
  - save(self, config: AppConfig) -> None：写入 JSON
  - 处理文件不存在、JSON 格式错误等异常情况，失败时返回默认配置

### 4. tests/test_models.py
- 测试 CodexStatus 有且仅有 6 个成员
- 测试不包含 DEEP_WORK、NORMAL_WORK、QUEUED、REVIEW_READY、AWAITING_APPROVAL
- 测试每个成员的 label 非空且是中文
- 测试 AppConfig 默认值正确
- 测试 AppConfig frozen（不可修改）

### 5. tests/test_config.py
- 测试 load 在文件不存在时返回默认 AppConfig
- 测试 save + load 往返一致
- 测试 JSON 格式错误时返回默认配置
- 测试部分字段缺失时用默认值补全

约束：
- models.py 零外部依赖（不导入 PyQt5、psutil）
- 全部 type hints
- 全部公共类和公共方法有 docstring
```

---

## Task 2：Codex 状态映射层

```
请实现 Codex app-server schema 到产品状态的纯映射层。

先读取 docs/Codex-State-Audit.md。不要通过 CPU 阈值推断 DEEP_WORK/NORMAL_WORK；不要实现 QUEUED/REVIEW_READY。

### 1. src/codex_traffic_lights/state_mapper.py
- CodexStateMapper 类或纯函数：
  - map_thread_status(status: Mapping[str, object]) -> CodexStatus
  - map_turn_status(status: str) -> CodexStatus | None
  - map_event(event: Mapping[str, object]) -> CodexStatus | None
- 映射规则：
  - {"type": "idle"} → IDLE
  - {"type": "systemError"} → ERROR
  - {"type": "active", "activeFlags": ["waitingOnApproval"]} → WAITING_APPROVAL
  - {"type": "active", "activeFlags": ["waitingOnUserInput"]} → WAITING_USER_INPUT
  - {"type": "active", "activeFlags": []} → WORKING
  - TurnStatus "inProgress" → WORKING
  - TurnStatus "failed" → ERROR
  - TurnStatus "completed" / "interrupted" → None（不强行改空闲，等待 thread/status/changed）
  - 未知/格式错误输入 → None

### 2. tests/test_state_mapper.py
- 覆盖 ThreadStatus 四种 type
- 覆盖 activeFlags 两种等待标志
- 覆盖 TurnStatus 四种值
- 覆盖未知字段和坏输入返回 None
- 增加负向测试：不存在 8 态推测状态输出

约束：
- state_mapper.py 为纯 Python，不导入 PyQt5、psutil
- 不读取磁盘、不启动进程、不访问网络
- 全部 type hints
```

---

## Task 3：进程监控与降级检测

```
请在 src/codex_traffic_lights/ 目录下创建进程监控模块。

先读取 docs/Codex-State-Audit.md 和 docs/PRD.md 的状态检测方案。MVP 可以先完成 psutil 降级检测和状态信号，app-server 连接可以留扩展接口，但状态输出必须遵守 6 状态模型。

### 1. src/codex_traffic_lights/process_monitor.py
- ProcessMonitor(QThread)：
  - __init__(self, config: AppConfig, parent=None)
  - run(self)：每 config.poll_interval_ms 毫秒轮询一次降级状态
  - _detect_fallback_status(self) -> CodexStatus：
    - psutil.process_iter() 遍历所有进程
    - 查找 name 包含 config.codex_process_name 或 cmdline 包含 config.codex_process_name 的进程
    - 如果没找到 → OFFLINE
    - 如果之前在线现在离线 → ERROR
    - 如果找到 codex 进程 → WORKING
  - apply_app_server_event(self, event: Mapping[str, object]) -> None：
    - 调用 state_mapper.map_event
    - 映射出状态时发射 status_changed
  - status_changed = pyqtSignal(CodexStatus)：状态变化时发射
  - _previous_status: CodexStatus 跟踪上次状态

### 2. tests/test_process_monitor.py
- Mock psutil.process_iter 测试：
  - 无 codex 进程 → OFFLINE
  - codex 进程存在 → WORKING
  - 之前在线 → 现在离线 → ERROR
- 测试 apply_app_server_event 能把 thread/status/changed 映射为 WAITING_APPROVAL、WAITING_USER_INPUT、IDLE、ERROR
- 测试 status_changed 信号只在状态变化时发射

约束：
- psutil 调用必须在测试中被 mock
- 不使用 CPU 阈值做状态分类
- 全部 type hints
```

---

## Task 4：灯光动画引擎

```
请在 src/codex_traffic_lights/animation/ 目录下创建灯光动画引擎。

读取 docs/PRD.md 中的产品状态灯效定义，实现以下文件：

### 1. src/codex_traffic_lights/animation/effects.py
- LightEffectParams(NamedTuple)：
  - mode: LightMode
  - min_opacity: float (0.0-1.0)
  - max_opacity: float (0.0-1.0)
  - period_ms: int (完整周期毫秒)
  - halo_enabled: bool (是否显示外圈光晕)
  - halo_spread: int (光晕扩散像素)
- STATUS_EFFECTS: dict[CodexStatus, tuple[LightEffectParams, LightEffectParams, LightEffectParams]]
  - 覆盖全部 6 个 CodexStatus
  - OFF：mode=OFF, min_opacity=0.1, max_opacity=0.15, period_ms=0
  - SOLID：mode=SOLID, min_opacity=0.95, max_opacity=1.0, period_ms=0
  - SLOW_BREATH：min_opacity=0.3, max_opacity=1.0, period_ms=3000
  - INTERMITTENT_BLINK：min_opacity=0.1, max_opacity=0.6, period_ms=1000
  - SLOW_FLASH：min_opacity=0.2, max_opacity=0.8, period_ms=2000
  - FAST_FLASH：min_opacity=0.2, max_opacity=1.0, period_ms=300

### 2. src/codex_traffic_lights/animation/engine.py
- LightAnimationEngine：
  - __init__(self, traffic_light_widget: QWidget)
  - set_status(self, status: CodexStatus) -> None：
    - 停止当前所有动画
    - 获取 STATUS_EFFECTS[status]
    - 为每个灯创建 QVariantAnimation 或定时器驱动 opacity 变化
  - _create_animation(self, effect: LightEffectParams)
  - _stop_all(self) -> None

### 3. tests/test_effects.py
- 测试 STATUS_EFFECTS 覆盖全部 6 个 CodexStatus
- 测试每个状态的三个灯效果参数合法（period_ms >= 0, 0 <= opacity <= 1）
- 测试 OFFLINE 状态只有红灯非 OFF
- 测试 IDLE 状态只有绿灯非 OFF
- 测试 WAITING_APPROVAL 状态黄灯和绿灯非 OFF

约束：
- effects.py 不导入 PyQt5（纯数据定义）
- engine.py 可以导入 PyQt5
- 全部 type hints
```

---

## Task 5：UI 基础壳与交互

```
请在 src/codex_traffic_lights/widgets/ 目录下创建 UI 基础组件和交互组件。

读取 docs/PRD.md 中的「UI 视觉规范」「颜色定义」「交互功能」和「右侧按钮」表格，实现以下文件：

### 1. src/codex_traffic_lights/widgets/header.py
- HeaderWidget(QWidget)：绘制 Codex 图标区域和 CODEX 文字，固定高度 70px

### 2. src/codex_traffic_lights/widgets/traffic_light.py
- TrafficLightWidget(QWidget)：用 QPainter 绘制红黄绿三灯、灭色、亮色、光晕
- 提供 set_light_opacity(red: float, yellow: float, green: float) -> None
- 提供 red_opacity, yellow_opacity, green_opacity 属性供动画驱动

### 3. src/codex_traffic_lights/widgets/status_bar.py
- StatusBarWidget(QWidget)：显示黄色中文状态文字
- set_status_text(self, text: str) -> None

### 4. src/codex_traffic_lights/widgets/side_buttons.py
- SideButtonsWidget(QWidget)：6 枚半透明按钮
- 信号：notification_toggled, zoom_in, zoom_out, settings_requested, power_toggled, sound_toggled

### 5. src/codex_traffic_lights/widgets/main_window.py
- FramelessMainWindow(QWidget)：
  - 无边框、置顶、圆角深色背景
  - 组装 Header + TrafficLight + StatusBar + SideButtons
  - set_status(self, status: CodexStatus) -> None：更新状态文字和灯效
  - 支持拖拽移动、贴边隐藏、缩放 50%-200%

### 6. tests/test_side_buttons.py
- 测试每个按钮的点击信号正确发射
- 测试缩放范围限制(50%-200%)

约束：
- 用户可见文案使用 6 状态模型中的中文 label
- 不在 UI 中显示 ThreadStatus、activeFlags 等内部字段
- 全部 type hints
```

---

## Task 6：集成 + 入口 + 打包

```
请创建项目入口和打包配置，完成全模块集成。

### 1. src/codex_traffic_lights/__main__.py
- main() 函数：
  - 创建 QApplication
  - 设置应用名、组织名
  - 加载 ConfigManager
  - 创建 ProcessMonitor
  - 创建 FramelessMainWindow
  - 创建 TrayIcon
  - 连接 ProcessMonitor.status_changed → MainWindow.set_status
  - 启动 ProcessMonitor
  - app.exec()

### 2. src/codex_traffic_lights/tray.py
- TrayIcon：
  - QSystemTrayIcon
  - 右键菜单：显示主窗口 / 隐藏 / 分隔线 / 退出
  - 双击托盘图标显示/隐藏主窗口
  - show_message(title, text) 显示气泡通知

### 3. scripts/build.py
- PyInstaller 打包脚本：
  --onefile --windowed --name codex-traffic-lights
  --add-data "src/codex_traffic_lights/resources;codex_traffic_lights/resources"
  --icon src/codex_traffic_lights/resources/icons/app.ico

### 4. 验证
- 执行 pytest 确认所有测试通过
- 手动启动应用，验证：
  - 无 Codex 进程时红灯常亮
  - 启动 Codex 后黄灯呼吸
  - 模拟 app-server waitingOnApproval 后黄绿慢闪
  - 模拟 app-server waitingOnUserInput 后黄灯间歇闪
  - 关闭 Codex 后恢复红灯或异常态

约束：
- 入口文件不超过 80 行
- 全部 type hints
- 不恢复旧版 8 状态
```

---

## 使用方式

将每个 Task 块的内容复制粘贴到 Codex CLI 会话中执行。

推荐顺序：Task 1 → Task 2 → Task 3 → Task 4 → Task 5 → Task 6

每个 Task 完成后运行 `pytest` 确认测试通过，再进入下一个 Task。
