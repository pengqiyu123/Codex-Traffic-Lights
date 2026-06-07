# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Codex Traffic Lights** 是一个 Windows 桌面悬浮小组件，实时显示 OpenAI Codex CLI 当前可观测状态。采用竖版黑底红绿灯视觉设计，支持拖拽贴边、右侧快捷按钮、系统托盘、开机自启等交互功能。

**目标用户**：使用 Codex CLI 进行日常开发的程序员，需要在不切换终端窗口的情况下感知 Codex 工作状态。

## Commands

```bash
# 安装依赖
cd "d:\python\Codex Traffic Lights"
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"

# 运行
python -m codex_traffic_lights

# 测试
pytest

# 类型检查
mypy src/

# Lint
ruff check src/ tests/

# 格式化
ruff format src/ tests/

# 打包为单 exe
pyinstaller --onefile --windowed --name codex-traffic-lights src/codex_traffic_lights/__main__.py

# 视觉验收截图（Windows PowerShell）
powershell -ExecutionPolicy Bypass -File .agents/skills/screenshot/scripts/take_screenshot.ps1 -Mode temp -ActiveWindow
# 或指定区域
powershell -ExecutionPolicy Bypass -File .agents/skills/screenshot/scripts/take_screenshot.ps1 -Mode temp -Region 100,200,800,600
```

## Repository Structure

```
src/codex_traffic_lights/    # 核心代码包
├── __main__.py              # 入口：创建 QApplication + MainWindow
├── models.py                # CodexStatus 枚举(6态)、AppConfig 数据类
├── config.py                # JSON 配置读写
├── state_mapper.py          # Codex app-server schema → CodexStatus 纯映射
├── process_monitor.py       # app-server 事件监听 + psutil 降级检测
├── animation/               # 灯光动画引擎
│   ├── engine.py            # QPropertyAnimation 驱动呼吸/闪烁效果
│   └── effects.py           # 每种状态对应的灯效参数定义
├── widgets/                 # PyQt5 UI 组件
│   ├── main_window.py       # 无边框置顶悬浮主窗口（拖拽/贴边）
│   ├── traffic_light.py     # 三灯绘制（QPainter 红黄绿圆 + 光晕）
│   ├── header.py            # 顶部 Codex Logo/图标区域
│   ├── status_bar.py        # 底部中文状态文字
│   └── side_buttons.py      # 右侧 6 枚半透明快捷按钮
├── tray.py                  # 系统托盘图标 + 右键菜单
└── resources/               # 图标等静态资源
tests/                       # pytest 测试
docs/                        # PRD、ADR、状态审计
scripts/                     # 构建脚本
```

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   MainWindow                     │
│  ┌──────────┐  ┌──────────────┐  ┌───────────┐ │
│  │  Header   │  │ TrafficLight │  │ SideBtns  │ │
│  │ (Logo)    │  │ (3 circles)  │  │ (6 btns)  │ │
│  ├──────────┤  │  R ●          │  │ 🔔        │ │
│  │ StatusBar │  │  Y ●          │  │ ─        │ │
│  │ (文字)    │  │  G ●          │  │ ＋        │ │
│  └──────────┘  └──────────────┘  │ ⋮        │ │
│                                  │ ⏻        │ │
│                                  │ 🔇       │ │
│                                  └───────────┘ │
└─────────────────────────────────────────────────┘
        ▲                    ▲
        │  CodexStatus       │  app-server events / fallback poll
        │                    │
  ┌─────┴──────┐    ┌───────┴──────────┐
  │ ConfigMgr  │    │ ProcessMonitor    │
  │ (JSON)     │    │ (app-server + psutil fallback) │
  └────────────┘    └──────────────────┘
```

**数据流**：`ProcessMonitor` 优先解析 Codex app-server v2 状态事件 → 输出 `CodexStatus` 枚举 → `MainWindow` 接收状态 → 更新 `TrafficLight` 灯效 + `StatusBar` 文字。app-server 不可用时使用 psutil 做保守降级。

## Key Technical Facts

1. **状态真相源**：以 Codex CLI 当前 app-server schema 为准，不以早期 PRD 的 8 态推测为准。
2. **Codex CLI 可观测状态**：`ThreadStatus` 为 `notLoaded` / `idle` / `systemError` / `active`，`activeFlags` 为 `waitingOnApproval` / `waitingOnUserInput`，`TurnStatus` 为 `completed` / `interrupted` / `failed` / `inProgress`。
3. **产品状态**：`CodexStatus` 仅包含 `OFFLINE`、`IDLE`、`WORKING`、`WAITING_APPROVAL`、`WAITING_USER_INPUT`、`ERROR`。
4. **降级检测**：psutil 只能判断离线/有进程/异常退出，不允许用 CPU 阈值制造 `DEEP_WORK`、`NORMAL_WORK`、`QUEUED`、`REVIEW_READY`。
5. **无边框窗口**：`Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint`，通过 `QPainter` 绘制圆角和灯效。
6. **动画**：使用 `QPropertyAnimation` + `QGraphicsOpacityEffect` 实现呼吸/闪烁效果，避免阻塞主线程。
7. **贴边隐藏**：检测窗口位置是否靠近屏幕边缘，触发 `QPropertyAnimation` 滑出/滑入。
8. **打包**：PyInstaller 单 exe，`--windowed` 隐藏控制台窗口。

## UI 设计规范

**设计方向文档**：[docs/UI-Design-Direction.md](docs/UI-Design-Direction.md)（必须先读再改 UI 代码）

**核心审美**：工业仪表 / 精密设备指示灯（航空仪表盘 LED、服务器状态灯），不是网页/App。

**关键约束**：
1. 灯光要有物理质感：玻璃罩、金属边框、内发光、外光晕，不是扁平色块
2. 灭灯用同色系极暗版本，不是灰色
3. 底色 #0D0D0F（微冷蓝调黑），不是中性 #1A1A1A
4. 按钮：QPainter 矢量图标，禁止 emoji
5. 字体：Consolas / JetBrains Mono 等宽，禁止 Arial/system font
6. 动画：InOutSine 缓动，禁止线性
7. Compact（72x220）+ Expanded（~200x400）双形态

**禁止事项**：见 UI-Design-Direction.md 末尾 Anti-Slop 清单。

## Known Issues

- 前版 8 态 PRD 是 AI 推测，已废弃。ClaudeCode 下发任务时必须先参考 `docs/Codex-State-Audit.md`。
- app-server 不可用时，降级检测无法准确区分审批等待/用户输入等待，只能显示 `WORKING`。
- Windows 某些安全软件可能阻止无边框置顶窗口。
- 多 VSCode Codex 插件实例：需要 app-server 连接后通过 threadId 聚合，纯 psutil 无法解决。

## Contribution Guidelines

- Commit 格式：`feat: xxx` / `fix: xxx` / `refactor: xxx`
- 提交前执行：`pytest && ruff check src/ tests/ && mypy src/`
- 分支命名：`feature/xxx`、`fix/xxx`
