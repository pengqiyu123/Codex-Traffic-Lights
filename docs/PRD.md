# Codex Traffic Lights — PRD

## Background

开发者使用 OpenAI Codex CLI 进行日常编码时，需要频繁切换到终端窗口查看 Codex 工作状态。本项目提供一个 Windows 桌面悬浮指示灯组件，通过红黄绿三色灯直观显示 Codex 当前可观测状态，让开发者一目了然。

## Goals

1. 实时检测 Codex CLI 可观测状态并映射到桌面灯效
2. 提供美观的竖版黑底三灯视觉设计
3. 支持拖拽贴边、系统托盘、快捷按钮等桌面交互
4. PyInstaller 打包为便携文件夹，零配置双击即用

## Codex 真实状态模型

前版文档中的 8 种状态是 AI 推测，不是 Codex 的真实公开状态模型。以 Codex CLI `0.118.0` 自带 `app-server` schema 为准，当前可观测状态来自：

- `ThreadStatus`：`notLoaded`、`idle`、`systemError`、`active`
- `ThreadActiveFlag`：`waitingOnApproval`、`waitingOnUserInput`
- `TurnStatus`：`completed`、`interrupted`、`failed`、`inProgress`

详见 [Codex-State-Audit.md](Codex-State-Audit.md)。

## 产品状态灯效定义

| # | 状态名 | 英文 Key | 红灯 | 黄灯 | 绿灯 | 底部文字 | 来源 |
|---|--------|----------|------|------|------|---------|------|
| 1 | 离线休眠 | `OFFLINE` | 常亮 | 灭 | 灭 | 待机离线 | VSCode Codex IPC 未连接 / 无 Codex 会话 |
| 2 | 正在工作 | `WORKING` | 灭 | 慢呼吸(3s) | 灭 | 正在工作 | `ThreadStatus.active` / `TurnStatus.inProgress` |
| 3 | 待审批确认 | `WAITING_APPROVAL` | 灭 | 慢闪 | 慢闪 | 待审批确认 | `activeFlags` 包含 `waitingOnApproval` |
| 4 | 待用户输入 | `WAITING_USER_INPUT` | 灭 | 间歇闪(0.7s) | 灭 | 待用户输入 | `activeFlags` 包含 `waitingOnUserInput` |
| 5 | 空闲就绪 | `IDLE` | 灭 | 灭 | 常亮(无光晕) | 空闲待命 | `ThreadStatus.idle` |
| 6 | 运行异常 | `ERROR` | 快闪 | 快闪 | 灭 | 运行异常 | `ThreadStatus.systemError` / `TurnStatus.failed` / 进程异常退出 |

**灯效参数定义**：
- **常亮**：稳定发光，无动画
- **慢呼吸**：亮度在 30%-100% 间正弦波变化，3 秒完整周期，细黄光环
- **间歇闪**：快速亮起 → 峰值保持 → 熄灭 → 暗态保持，0.7 秒周期
- **慢闪**：亮度在 20%-80% 间交替，2 秒周期
- **快闪**：亮度在 20%-100% 间交替，0.3 秒周期

## 状态检测方案

### Phase 1 — Codex app-server schema 映射

优先启动或连接本机 Codex app-server，监听 v2 协议事件并映射为产品状态：

| Codex 事件/字段 | 产品状态 |
|----------|---------|
| VSCode Codex IPC 不可连接，且无 Codex 会话 | `OFFLINE` |
| `ThreadStatus.type == "idle"` | `IDLE` |
| `ThreadStatus.type == "active"` 且 `activeFlags` 为空 | `WORKING` |
| `TurnStatus == "inProgress"` | `WORKING` |
| `activeFlags` 包含 `waitingOnApproval` | `WAITING_APPROVAL` |
| `activeFlags` 包含 `waitingOnUserInput` | `WAITING_USER_INPUT` |
| `ThreadStatus.type == "systemError"` 或 `TurnStatus == "failed"` | `ERROR` |

### Phase 2 — psutil 降级检测

当 app-server 无法连接时，允许使用 psutil 做保守降级：

| 检测条件 | 产品状态 |
|----------|---------|
| 无 codex 进程 | `OFFLINE` |
| codex 进程存在 | `WORKING` |
| codex 进程异常退出（先运行后消失） | `ERROR` |

降级模式不得输出 `WAITING_APPROVAL` 或 `WAITING_USER_INPUT`，因为 psutil 无法读取 Codex 内部线程标志。

## UI 视觉规范

### 整体布局
- **外形**：竖向圆角长条形悬浮窗体，哑光深黑底色(#1A1A1A)，永久置顶
- **尺寸**：默认 80px × 240px，可缩放(50%-200%)
- **顶部**：蓝紫渐变云朵图标 + `_>_`终端符号，下方白色大写「CODEX」
- **中部**：三个圆形指示灯（红→黄→绿 从上到下），直径 40px
- **底部**：黄色(#FFD700)中文状态文字，跟随实时状态自动切换
- **右侧**：6 枚半透明(30% opacity)悬浮按钮，鼠标悬浮 100% opacity

### 右侧按钮（从上→下）
| 位置 | 图标 | 功能 |
|------|------|------|
| 1 | 展开 | 打开/关闭 Expanded 会话面板 |
| 2 | ─ 缩小 | 缩小组件尺寸 |
| 3 | ＋ 放大 | 放大组件尺寸 |
| 4 | 齿轮 | 打开/关闭声音设置 |
| 5 | ⏻ 电源 | 启动/关闭 Codex 后台进程 |
| 6 | 🔇 静音 | 状态切换提示音开关 |

### 颜色定义
| 用途 | 色值 |
|------|------|
| 背景底色 | #1A1A1A |
| 红灯亮色 | #FF4444 |
| 红灯灭色 | #3A1111 |
| 黄灯亮色 | #FFD700 |
| 黄灯灭色 | #3A3300 |
| 绿灯亮色 | #44FF44 |
| 绿灯灭色 | #113A11 |
| 光晕色 | 与灯色同色，低透明度 |
| 文字色 | #FFD700 |
| 按钮常态 | rgba(255,255,255,0.3) |
| 按钮悬浮 | rgba(255,255,255,1.0) |

## 交互功能

1. **置顶悬浮**：`Qt.WindowStaysOnTopHint` 永远在最上层
2. **拖拽移动**：按住组件主体区域自由拖动
3. **贴边停靠**：靠近屏幕左右边缘时吸附，静置后收缩为 52×24 迷你灯条，鼠标移入临时展开
4. **缩放**：通过 ± 按钮调整组件整体大小(50%-200%)
5. **系统托盘**：最小化到托盘，右键菜单（显示/隐藏/退出）
6. **设置面板**：选择/试听 4 类本地声音提醒
7. **开机自启**：写入注册表启动项

## 技术栈

| 项目 | 选择 |
|------|------|
| 语言 | Python 3.10+ |
| GUI 框架 | PyQt5 |
| 进程检测 | psutil |
| 动画 | QPropertyAnimation |
| 配置 | JSON 文件 |
| 打包 | PyInstaller (--onedir --windowed) 便携文件夹 |
| 测试 | pytest + pytest-qt + pytest-cov |
| Lint | ruff |
| 类型检查 | mypy (strict) |

## Non-Functional Requirements

- **性能**：空闲时 CPU 占用 < 1%，内存 < 50MB
- **响应**：状态切换到灯效变化延迟 < 500ms
- **兼容**：Windows 10/11 x64
- **安全**：不读取 Codex 凭证，不暴露 API key

## Priority

**High**：Phase 1 全部功能
**Medium**：Codex app-server 连接稳定性、自动重连、协议版本检查
**Low**：开机自启、自定义光晕颜色

## Out of Scope

- macOS / Linux 支持
- Codex Cloud 状态检测
- 多 Codex 实例并行监控
- 网络远程监控

---

## 模块拆解与文件清单

```
codex_traffic_lights/
├── __init__.py                 # 包初始化，导出版本号
├── __main__.py                 # 入口：QApplication + MainWindow + 事件循环
├── models.py                   # CodexStatus(6枚举)、LightMode、AppConfig(dataclass)
├── config.py                   # ConfigManager：JSON 读写 + 默认值合并
├── state_mapper.py             # Codex app-server schema → CodexStatus 纯映射（无 IO、无 UI）
├── process_monitor.py          # ProcessMonitor(QThread)：app-server 事件监听 + psutil 降级检测
├── animation/
│   ├── __init__.py
│   ├── engine.py               # LightAnimationEngine：管理 QPropertyAnimation 组
│   └── effects.py              # LightEffectParams 定义 + 6 种产品状态灯效预设
├── widgets/
│   ├── __init__.py
│   ├── main_window.py          # FramelessMainWindow：置顶+拖拽+贴边+缩放
│   ├── traffic_light.py        # TrafficLightWidget(QWidget)：QPainter 绘制三灯+光晕
│   ├── header.py               # HeaderWidget：Logo + CODEX 文字
│   ├── status_bar.py           # StatusBarWidget：状态文字 QLabel
│   └── side_buttons.py         # SideButtonsWidget：6枚悬浮按钮竖排
├── tray.py                     # TrayIcon：QSystemTrayIcon + 右键菜单
└── resources/
    └── icons/
        └── app.ico             # 应用图标
```

---

## Phase 1 开发任务分解（Codex 执行顺序）

> 详细开发命令见 [Codex-Commands.md](Codex-Commands.md)，以下为摘要。

### Task 1：数据模型层（models.py + config.py）
**输入**：Codex-State-Audit 中的 6 状态映射 + 配置需求
**产出**：
- `models.py`：`CodexStatus` 枚举(6成员) + `LightMode` 枚举 + `AppConfig` frozen dataclass
- `config.py`：`ConfigManager` 类，JSON 配置读写，默认值合并
- `tests/test_models.py` + `tests/test_config.py`

### Task 2：状态映射层（state_mapper.py）
**输入**：Codex-State-Audit 中的 ThreadStatus / ThreadActiveFlag / TurnStatus schema
**产出**：
- `state_mapper.py`：纯函数，把 Codex app-server 事件映射为 `CodexStatus`，无 IO、无 UI
- `tests/test_state_mapper.py`：覆盖全部 schema 类型 + 坏输入 + 负向测试（不输出旧 8 态）

### Task 3：进程监控与降级检测（process_monitor.py）
**输入**：app-server schema 映射 + psutil 降级方案
**产出**：
- `process_monitor.py`：`ProcessMonitor(QThread)`，调用 state_mapper 解析事件，psutil 做降级
- `tests/test_process_monitor.py`：mock psutil + app-server 事件映射测试

### Task 4：灯光动画引擎（animation/）
**输入**：PRD 灯效参数定义
**产出**：
- `animation/effects.py`：`LightEffectParams`(NamedTuple) + 6 种产品状态灯效预设字典
- `animation/engine.py`：`LightAnimationEngine`，接收 CodexStatus → 停止旧动画 → 启动新动画
- `tests/test_effects.py`：灯效参数验证

### Task 5：UI 基础壳与交互（widgets/ + tray.py）
**输入**：PRD UI 视觉规范 + 交互功能 + 右侧按钮
**产出**：
- `widgets/` 全部组件：Header + TrafficLight + StatusBar + SideButtons + MainWindow
- `tray.py`：TrayIcon，系统托盘 + 右键菜单
- MainWindow 支持 set_status / 拖拽 / 贴边隐藏 / 缩放
- `tests/test_side_buttons.py`

### Task 6：集成 + 入口 + 打包
**输入**：所有模块
**产出**：
- `__main__.py`：完整入口，组装所有组件（≤80 行）
- `scripts/build.py`：PyInstaller 构建脚本
- 全流程验证
