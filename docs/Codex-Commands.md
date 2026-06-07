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

## Task 1：数据模型层（✅ 已完成）

## Task 2：Codex 状态映射层（✅ 已完成）

## Task 3：进程监控与降级检测（✅ 已完成）

## Task 4：灯光动画引擎（✅ 已完成）

## Task 5：UI 基础壳与交互（✅ 已完成）

## Task 6：集成 + 入口 + 打包（✅ 已完成）

---

## Task 7：Compact 视觉重做

> 独立于多会话功能，用户可立刻看到工业仪表风格改善。

```
请在现有代码基础上完成 Compact 模式的 UI 视觉重做。

必读文档：docs/UI-Design-Direction.md（设计方向和详细规范）
必读文档：docs/PRD.md（产品状态定义不变）

### 1. 重画 TrafficLightWidget（widgets/traffic_light.py）

按 UI-Design-Direction.md 的「灯光质感」7 层绘制规范重写 paintEvent：
- 层 1：外壳凹槽（比背景更暗的圆形底）
- 层 2：灭色填充（同色系极暗版本，不是灰色）
- 层 3：亮色径向渐变（中心亮→边缘过渡到灭色）
- 层 4：高光点（左上角小白点，模拟玻璃反射）
- 层 5：内发光（亮色半透明边缘光）
- 层 6：外光晕（仅亮灯时启用，径向渐变扩散）
- 层 7：金属边框（1px 细灰色描边）

新色彩系统（替换旧常量）：
- 底色 #0D0D0F、面板色 #16161A、边框色 #2A2A30
- 红灯系：亮 #FF3B30 / 灭 #2A0808 / 光晕 rgba(255,59,48,0.25)
- 黄灯系：亮 #FFCC00 / 灭 #2A2400 / 光晕 rgba(255,204,0,0.25)
- 绿灯系：亮 #34C759 / 灭 #082A10 / 光晕 rgba(52,199,89,0.25)

IDLE 状态的绿灯：常亮但无光晕（低功耗待机）。
灭灯（LightMode.OFF）：只显示层 1 凹槽 + 层 2 灭色填充，无亮色、无光晕。

### 2. 重写 SideButtonsWidget（widgets/side_buttons.py）

去掉全部 emoji 文字按钮，改为 QPainter 矢量图标：
- 通知：小铃铛轮廓 SVG path
- 缩小：水平线
- 放大：十字
- 设置：齿轮 SVG path
- 电源：IEC 电源符号（圆圈+竖线）
- 静音：扬声器轮廓+对角线

样式：
- 常态：rgba(255,255,255,0.08) 圆形底 + 0.35 opacity 图标
- Hover：rgba(255,255,255,0.15) 圆形底 + 0.9 opacity 图标 + 1px 边框
- Pressed：rgba(255,255,255,0.22) 圆形底 + 1.0 opacity 图标
- Active（checkable）：当前灯色的 0.15 底色 + 灯色图标

每个按钮实现 paintEvent 自绘图标，不用 QPushButton 文字模式。
保留全部 6 个 pyqtSignal 不变。

### 3. 重写 HeaderWidget（widgets/header.py）

- 小矩形色块（16x12px，#56D7FF）内含 `>_` 终端符号（Consolas 8px）
- 下方 "CODEX" 文字：Consolas Bold 10px，字间距 +2px，颜色 #6A6A70
- 整体高度从 70px 缩减到 50px

### 4. 更新 StatusBarWidget（widgets/status_bar.py）

- 字体改为 Consolas / JetBrains Mono，字号 10px
- 文字颜色跟随当前灯色（红灯时红色文字，绿灯时绿色文字等）
- 新增 set_status_color(color: str) 方法，由 MainWindow 在 set_status 时同步调用

### 5. 更新 FramelessMainWindow（widgets/main_window.py）

- 底色改为 #0D0D0F（替换 #1A1A1A）
- 圆角从 12px 改为 16px
- set_status 同时更新 StatusBar 颜色
- Compact 默认尺寸改为 72x220（替换 80x240）
- 贴边隐藏改为 QPropertyAnimation 滑动（200ms InOutCubic），不再是直接 move
- 新增 expanded 模式框架：点击侧边设置按钮或双击灯区域切换 expanded
  - Expanded 尺寸 ~200x400
  - 展开动画 200ms InOutCubic
  - expanded 模式内容先留空 placeholder（为多会话列表预留）

### 6. 更新 animation/effects.py

- IDLE 状态绿灯：halo_enabled 改为 False（低功耗待机无光晕）
- 更新 OFF_EFFECT：min_opacity=0.08, max_opacity=0.12（更暗的灭灯）

### 7. 确保现有测试全部通过

- 运行 `pytest` 确认 92+ tests passed
- 新增 test: 验证新色彩常量在 PaintEvent 中被正确使用
- 新增 test: 验证 IDLE 状态绿灯 halo_enabled=False

约束：
- 不改变 CodexStatus 枚举、state_mapper、process_monitor 的逻辑代码
- 不改变任何 pyqtSignal 接口
- 全部 QPainter 绘制，不使用样式表（StatusBar 文字颜色除外）
- 全部 type hints
- 修改后运行 `python -m codex_traffic_lights` 做视觉 smoke test
- 完成后用 screenshot skill 截图验证
```

---

## Task 8：多会话数据模型 + 聚合器

> 为多 Codex 会话显示提供数据基础。纯 Python 模块，不涉及 UI 和网络。

```
请创建多会话数据模型和状态聚合器。

必读文档：docs/Codex-State-Audit.md（app-server schema）
必读文档：docs/UI-Design-Direction.md（多会话显示方案）

### 1. src/codex_traffic_lights/session_models.py

SessionStatus dataclass(frozen)：
- session_key: str（唯一键，格式 "endpointId::threadId"）
- thread_id: str
- endpoint_id: str
- display_name: str（workspace/repo 短名，fallback 到 threadId 短码）
- status: CodexStatus
- last_updated: float（time.time() 时间戳）

SessionRegistry 类：
- __init__(self) -> None
- update(self, session: SessionStatus) -> None：更新或添加一个 session
- remove(self, session_key: str) -> None：移除一个 session
- get_all(self) -> list[SessionStatus]：返回全部 session，按 display_name 排序
- get(self, session_key: str) -> SessionStatus | None
- count(self) -> int

### 2. src/codex_traffic_lights/status_aggregator.py

STATUS_PRIORITY 常量（从高到低）：
  ERROR=0, WAITING_APPROVAL=1, WAITING_USER_INPUT=2, WORKING=3, IDLE=4, OFFLINE=5

aggregate_status(sessions: list[SessionStatus]) -> CodexStatus：
  - 如果 sessions 为空 → OFFLINE
  - 否则返回优先级最高的（数值最小的 STATUS_PRIORITY）那个 session 的 status

aggregate_display_text(sessions: list[SessionStatus], status: CodexStatus) -> str：
  - Compact 模式状态栏文字
  - 1 个会话：正常 label（如 "正在工作"）
  - 多个会话：label + 会话数（如 "待审批确认 · 3 会话"）

### 3. tests/test_session_models.py

- 测试 SessionStatus frozen
- 测试 SessionRegistry：add / update / remove / get_all / count / get
- 测试 SessionRegistry 按 display_name 排序
- 测试 session_key 格式 "endpointId::threadId"

### 4. tests/test_status_aggregator.py

- 测试空列表 → OFFLINE
- 测试单 session 返回其状态
- 测试多 session 聚合优先级：ERROR > WAITING_APPROVAL > WORKING > IDLE
- 测试全部 IDLE 时 → IDLE
- 测试 display_text：1 会话 vs 多会话
- 负向测试：不包含旧 8 态

约束：
- session_models.py 和 status_aggregator.py 为纯 Python
- 不导入 PyQt5、psutil
- 不读取磁盘、不访问网络
- 全部 type hints + docstring
```

---

## Task 9A：Hook 文件桥（低风险，先做）

> 通过 Codex/Claude Code hooks 写入 JSON 文件获取精确状态。
> 参考：https://github.com/starlight36/vibecoding-signal-light（仅参考事件映射，不照搬代码）
> 它是 Python+GPIO 硬件项目，不支持 Windows。我们只借鉴 hook 事件映射逻辑。

```
请实现 Hook 文件桥，让 Codex CLI 和 Claude Code CLI 的 hook 事件驱动状态更新。

### 调研（先执行）

1. 确认 Codex hooks 配置文件路径和格式：`~/.codex/hooks.json`
2. 确认 Claude Code hooks 配置文件路径和格式：`~/.claude/settings.json` 中的 hooks 部分
3. 确认 hook 脚本接收事件的方式（CLI 参数 / stdin JSON / 环境变量）
4. 确认哪些事件可用：SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, PermissionRequest, Stop, SessionEnd 等
将结论写入代码注释。

### Hook 事件到 CodexStatus 的映射

基于 vibecoding-signal-light 项目的映射逻辑（已验证可用），适配我们的 6 态模型：

Codex hooks:
- SessionStart → IDLE
- UserPromptSubmit / PreToolUse / PostToolUse → WORKING
- PermissionRequest → WAITING_APPROVAL
- PostToolUseFailure / Stop(error) → ERROR
- Stop(normal) → IDLE
- SessionEnd → 从 registry 移除该 session

Claude Code hooks:
- SessionStart → IDLE
- UserPromptSubmit / PreToolUse / PostToolUse / PreCompact / SubagentStart → WORKING
- PostToolUseFailure / Stop(error/max_tokens) → ERROR
- PermissionRequest → WAITING_APPROVAL
- Notification → WAITING_USER_INPUT
- SubagentStop / Stop(normal) → IDLE
- SessionEnd → 从 registry 移除该 session

### 1. src/codex_traffic_lights/hook_bridge.py

HookEventMapper 类（纯函数）：
- map_codex_event(event_name: str, payload: dict) -> CodexStatus | None
- map_claude_event(event_name: str, payload: dict) -> CodexStatus | None
- _extract_session_key(payload: dict) -> str：
  优先级链：session_id > conversation_id > thread_id > cwd basename > "global"
- 全部 classmethod 或 staticmethod，纯逻辑无 IO

HookFileWatcher(QThread)：
- __init__(self, config: AppConfig, registry: SessionRegistry, parent=None)
- run(self)：每 1 秒扫描 hook 写入的 session 文件目录
- _scan_sessions_dir(self) -> None：
  - 读取 ~/.codex-traffic-lights/sessions/ 下所有 JSON 文件
  - 解析每个文件为 SessionStatus
  - 更新 registry
  - 清理超时 session（5 分钟无更新）
- _cleanup_stale(self) -> None：移除超过 5 分钟未更新的 session
- status_changed = pyqtSignal(CodexStatus)：聚合后状态变化时发射

### 2. src/codex_traffic_lights/hook_scripts/

两个 hook 入口脚本（用户安装到 hooks 配置中）：

codex_hook.py：
- 入口函数，Codex hooks 通过 CLI 参数或 stdin 传入事件名
- 解析事件 → 映射 CodexStatus → 写入 ~/.codex-traffic-lights/sessions/<session_key>.json
- JSON 格式：{"session_key": "xxx", "status": "WORKING", "display_name": "project-name", "updated_at": 1709123456.789}

claude_code_hook.py：
- 入口函数，Claude Code hooks 通过 stdin JSON 传入事件
- 解析事件 → 映射 CodexStatus → 写入同一个 sessions 目录

### 3. src/codex_traffic_lights/hook_installer.py

HookInstaller 类：
- install_codex_hooks() -> None：安装到 ~/.codex/hooks.json（备份原文件）
- install_claude_hooks() -> None：安装到 ~/.claude/settings.json（备份原文件）
- uninstall() -> None：移除已安装的 hooks
- is_installed() -> bool：检查安装状态
- 不修改用户已有的其他 hooks，只追加或更新我们的条目

### 4. tests/test_hook_bridge.py

- 测试 map_codex_event 全部事件映射
- 测试 map_claude_event 全部事件映射
- 测试 _extract_session_key 优先级链
- 测试坏输入/未知事件返回 None
- 负向测试：不输出旧 8 态

### 5. tests/test_hook_file_watcher.py

- Mock 文件系统，测试 _scan_sessions_dir 正确解析 JSON 文件
- 测试 registry 更新：新 session 添加、状态变化更新
- 测试 _cleanup_stale：5 分钟超时的 session 被移除
- 测试 status_changed 只在聚合状态变化时发射

约束：
- hook_bridge.py 为纯 Python，不导入 PyQt5、psutil
- hook_scripts/ 为可独立执行的 Python 脚本，最小依赖
- Windows 兼容：用 os.replace 做原子写入，不用 fcntl（POSIX only）
- 全部 type hints
```

---

## Task 9B：app-server Connector（高风险，后做）

> ⚠️ 高风险任务。Codex app-server 标记为 experimental。
> 有了 Task 9A 的 Hook 文件桥兜底，此任务不再是阻塞项。
> 执行前必须先完成技术预研，确认本机连接方式。

```
请实现 Codex app-server 协议连接器，支持多 thread 状态监听。

必读文档：docs/Codex-State-Audit.md（app-server schema 和通知类型）

### 技术预研（先执行，结果写入代码注释）

在本机执行以下命令确认 app-server 连接方式：
1. `codex app-server --help` 查看可用选项
2. `codex app-server generate-ts --experimental` 确认 schema 版本
3. 检查 app-server 默认端口/transport（stdio / WebSocket / SSE）
4. 确认是否可以同时连接多个 app-server 实例

将预研结论写入 src/codex_traffic_lights/app_server_connector.py 文件顶部注释。

### 1. src/codex_traffic_lights/app_server_connector.py

AppServerConnector(QThread)：
- __init__(self, config: AppConfig, registry: SessionRegistry, parent=None)
- run(self)：连接 app-server，订阅 thread/status/changed 通知
- _connect(self) -> bool：建立连接
- _subscribe_threads(self) -> None：调用 thread/loaded/list 发现所有 thread，逐一订阅
- _handle_notification(self, method: str, params: dict) -> None：
  - 解析 thread/status/changed → 提取 threadId + endpointId
  - 调用 state_mapper.map_event 映射为 CodexStatus
  - 构造 SessionStatus 更新到 registry
  - 发射 session_updated 信号
- _handle_thread_started(self, params: dict) -> None：新 thread 出现时订阅
- _handle_thread_closed(self, params: dict) -> None：thread 关闭时从 registry 移除
- session_updated = pyqtSignal(SessionStatus)
- status_changed = pyqtSignal(CodexStatus)：聚合后的全局状态

连接失败时的行为：
- 不崩溃，不阻塞主线程
- 每 5 秒重试一次
- 重试期间 HookFileWatcher 和 psutil 降级检测继续工作

### 2. 更新 process_monitor.py

- 新增 registry: SessionRegistry 属性
- apply_app_server_event 改为：从事件提取 threadId + endpointId → 更新 registry → 聚合状态
- 降级检测不变

### 3. tests/test_app_server_connector.py

- Mock 连接，测试 _handle_notification 正确解析 thread/status/changed
- 测试 _subscribe_threads 从 thread/loaded/list 响应中提取 thread 列表
- 测试 session_updated 信号发射正确的 SessionStatus
- 测试连接失败时优雅降级（不发信号，不崩溃）
- 测试 registry 更新：新 thread 添加、状态变化更新、thread 关闭移除

约束：
- 网络连接必须在测试中被 mock
- 不硬编码端口号，从 config 读取
- 全部 type hints
- 预研结论必须写入代码注释
```

---

## Task 10：Expanded Mini Traffic Light 矩阵 UI

> 多会话展开面板。依赖 Task 8 的数据模型和 Task 9 的数据源。
> 可以先用 mock 数据开发 UI，再接入真实数据。

```
请创建 Expanded 模式的多列 mini traffic light 矩阵面板。

必读文档：docs/UI-Design-Direction.md（多会话显示方案）
前置依赖：Task 8（session_models + status_aggregator）

### 尺寸设计（像素级锁定）

Expanded 面板尺寸：240x420px
- 顶部全局状态区：主灯（复用现有 TrafficLightWidget，缩小到 60%）+ 状态文字，高度 180px
- 分隔线：1px #2A2A30
- 底部会话矩阵区：剩余空间，上下 padding 8px

每个会话列：
- 列宽：44px（240px / 5 列 ≈ 48px，减去 padding 和间距）
- 最多显示 5 列，超出时显示 "+N" 标记
- 每列内容从上到下：
  1. 3 个 mini 灯（直径 10px，间距 4px，总高 38px）
  2. 名称文字（Consolas 7px，居中，单行截断，高度 12px）
  3. 状态灯点（6px 圆点，颜色=当前状态灯色，高度 10px）
- 列间距：6px
- 每列 Tooltip：显示完整 workspace、threadId、状态中文、最后更新时间

### 1. src/codex_traffic_lights/widgets/session_column.py

SessionColumnWidget(QWidget)：
- __init__(self, session: SessionStatus, parent=None)
- set_session(self, session: SessionStatus) -> None：更新状态和重绘
- paintEvent：绘制 3 个 mini 灯 + 名称文字 + 状态灯点
- 使用新色彩系统（与主灯一致）
- mini 灯的灯效由 engine 驱动（呼吸/闪烁/常亮）
- Tooltip 显示完整信息

### 2. src/codex_traffic_lights/widgets/session_matrix.py

SessionMatrixWidget(QWidget)：
- __init__(self, parent=None)
- set_sessions(self, sessions: list[SessionStatus]) -> None：
  - 更新列数（最多 5 列）
  - 创建/更新/移除 SessionColumnWidget
  - 超出 5 列时在最右侧显示 "+N" 标记

### 3. 更新 FramelessMainWindow（widgets/main_window.py）

Expanded 模式实现：
- expanded 布局：顶部全局状态区（主灯 + 状态文字）+ SessionMatrixWidget
- 切换动画：QPropertyAnimation 200ms InOutCubic
- 切换触发：点击设置按钮 或 双击灯区域
- ESC 键收回 Compact

### 4. 集成 StatusAggregator

- ProcessMonitor 持有 SessionRegistry
- 状态变化时：
  - Compact：显示 aggregate_status 的灯效 + aggregate_display_text
  - Expanded：显示全局灯效 + 每列独立灯效
- __main__.py 连接信号

### 5. tests/test_session_column.py + tests/test_session_matrix.py

- 测试 SessionColumnWidget 根据 SessionStatus 正确绘制
- 测试 SessionMatrixWidget 最多显示 5 列
- 测试超出 5 列时显示 "+N"
- 测试 Expanded ↔ Compact 切换

约束：
- mini 灯复用主灯的 7 层绘制逻辑（提取为共享函数）
- 全部 QPainter 绘制
- 全部 type hints
- 可先用 mock SessionStatus 列表开发 UI
```

---

## 使用方式

将每个 Task 块的内容复制粘贴到 Codex CLI 会话中执行。

**推荐顺序**：

```
Task 1-6（已完成）
→ Task 7（视觉重做，独立执行，用户立刻看到改善）
→ Task 8（多会话数据模型）
→ Task 9A（Hook 文件桥，低风险先做）
→ Task 9B（app-server connector，高风险后做）
→ Task 10（Expanded 多会话 UI）
```

数据源三层架构：`app-server (9B) → Hook 文件桥 (9A) → psutil (已有)`

每个 Task 完成后运行 `pytest` 确认测试通过，再进入下一个 Task。

---

## Task 11：代码清理（✅ 已完成）

---

## Task 12：启动集成 + 视觉调优

> 解决三个用户反馈问题：状态不准（Hook 未安装）、灯色对比度低、电源按钮无功能。
> 都是小幅改动，一个 Task 内完成。

```
请在现有代码基础上完成三项改进。改动量小，不涉及新模块创建。

必读文档：CLAUDE.md（架构约束、psutil 降级限制）
必读文档：docs/Codex-State-Audit.md（状态映射参考）

### 1. Hook 启动自动安装（P0 — 最高优先级）

当前问题：HookFileWatcher 在运行，但 hook 没有安装，所以 hook 脚本永远不会被 Codex/Claude Code 调用。

修改 src/codex_traffic_lights/__main__.py：

- 在 `monitor = ProcessMonitor(config)` 之前，创建 `HookInstaller()` 并调用安装：
  ```python
  from codex_traffic_lights.hook_installer import HookInstaller
  installer = HookInstaller()
  try:
      installer.install_codex_hooks()
      installer.install_claude_hooks()
      print("[Codex Traffic Lights] Hooks installed successfully.")
  except Exception as exc:
      print(f"[Codex Traffic Lights] Hook install failed (non-fatal): {exc}")
  ```
- 安装失败不阻塞启动（降级到 psutil 检测）
- 不要修改 hook_installer.py 本身，它已经完整

### 2. LED 灭灯对比度调优（P1）

当前问题：灭灯 opacity 过高（0.08~0.12），亮灯与灭灯区分不明显。

修改 src/codex_traffic_lights/animation/effects.py 中的参数：

OFF_EFFECT（灭灯基础）：
- min_opacity: 0.08 → 0.03
- max_opacity: 0.12 → 0.06

INTERMITTENT_BLINK_EFFECT（WAITING_USER_INPUT 状态黄灯）：
- min_opacity: 0.1 → 0.05
- max_opacity: 0.6 → 0.75

SLOW_FLASH_EFFECT（WAITING_APPROVAL 状态黄/绿灯）：
- min_opacity: 0.2 → 0.08
- max_opacity: 0.8 → 0.95

目标效果：亮灯更亮、灭灯更暗，对比度从 ~10:1 提升到 ~30:1。
不要改变 SOLID_EFFECT、SLOW_BREATH_EFFECT、FAST_FLASH_EFFECT 的参数。

### 3. 电源按钮功能实装（P2）

当前问题：side_buttons.py 发射 power_toggled 信号，但无连接处理。

修改 src/codex_traffic_lights/__main__.py：

- 连接 power_toggled 信号到隐藏窗口 + 显示托盘通知：
  ```python
  def _on_power_toggled(checked: bool) -> None:
      if checked:
          window.hide()
          tray.show_message("Codex Traffic Lights", "已最小化到托盘，双击图标恢复")
      else:
          window.show()
          window.raise_()
          window.activateWindow()
  window.side_buttons.power_toggled.connect(_on_power_toggled)
  ```
- 不修改 side_buttons.py 和 tray.py，只修改 __main__.py 的信号连接

### 4. 确保现有测试全部通过

- 运行 `pytest` 确认全部测试通过
- 新增 test: 验证 OFF_EFFECT min_opacity < 0.05, max_opacity < 0.08
- 新增 test: 验证亮灯效果 max_opacity >= 0.75
- 新增 test: 验证 HookInstaller.install_codex_hooks 和 install_claude_hooks 被调用时不崩溃（mock 文件写入）

### 约束

- 只修改 3 个文件：`__main__.py`、`animation/effects.py`、以及新增测试文件
- 不修改 hook_installer.py、side_buttons.py、tray.py
- 不修改 CodexStatus 枚举、state_mapper、process_monitor 的逻辑代码
- 不改变任何 pyqtSignal 接口
- 安装 Hook 失败时必须继续启动（graceful degradation）
- 全部 type hints
- 完成后运行 `python -m codex_traffic_lights` 做视觉 smoke test
```
