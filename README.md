# Codex Traffic Lights

Windows 桌面悬浮 Codex CLI 状态指示灯组件。

通过红黄绿三色灯实时显示 Codex 当前可观测状态，支持拖拽贴边、系统托盘、快捷按钮。

## 快速开始

```bash
# 安装
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"

# 运行
python -m codex_traffic_lights

# 打包为单 exe
pyinstaller --onefile --windowed --name codex-traffic-lights src/codex_traffic_lights/__main__.py
```

## 状态灯效

| 状态 | 红灯 | 黄灯 | 绿灯 | 说明 |
|------|------|------|------|------|
| 离线休眠 | 常亮 | 灭 | 灭 | Codex 进程未运行 |
| 正在工作 | 灭 | 慢呼吸 | 灭 | Codex turn 进行中 |
| 待审批 | 灭 | 慢闪 | 慢闪 | `waitingOnApproval` |
| 待输入 | 灭 | 间歇闪 | 灭 | `waitingOnUserInput` |
| 空闲待命 | 灭 | 灭 | 常亮 | Codex 线程空闲 |
| 运行异常 | 快闪 | 快闪 | 灭 | 系统错误/turn 失败/进程异常 |

状态模型以 Codex app-server schema 为准。前版文档中的 8 态是 AI 推测，已废弃；调查记录见 [docs/Codex-State-Audit.md](docs/Codex-State-Audit.md)。

## 功能特性

- 🔴🟡🟢 三色灯实时状态指示
- 📌 桌面置顶悬浮
- ↔️ 拖拽移动 + 贴边自动隐藏
- 🔔 右侧快捷按钮（通知/缩放/设置/电源/静音）
- 🖥️ 系统托盘图标
- 📦 PyInstaller 单 exe 打包

## 技术栈

Python 3.10+ / PyQt5 / psutil / QPropertyAnimation / PyInstaller

## 许可证

MIT
