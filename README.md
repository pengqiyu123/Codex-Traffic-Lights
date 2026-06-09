# Codex Traffic Lights

Windows 桌面悬浮 VSCode Codex 状态指示灯组件。

通过红黄绿三色灯实时显示 VSCode Codex 当前可观测状态，支持拖拽贴边、系统托盘、多会话展开面板和本地声音提醒。

## 快速开始

```bash
# 安装
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"

# 运行
python -m codex_traffic_lights

# 打包为便携文件夹
python scripts/build.py
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

状态模型以 VSCode Codex IPC 的真实可观测信号为准。前版文档中的 8 态是 AI 推测，已废弃；调查记录见 [docs/Codex-State-Audit.md](docs/Codex-State-Audit.md)。

## 声音提醒

当前版本使用本地 MP3 资源播放 4 类声音提醒：

| 事件 | 触发条件 | 声音文件 |
|------|----------|----------|
| 任务完成 | 工作/等待状态回到空闲 | `任务完成.mp3` |
| 待审批确认 | 进入待审批状态 | `待审批确认.mp3` |
| 计划模式需要输入 | 进入待用户输入状态 | `计划模式输入.mp3` |
| 运行异常 | 进入异常状态 | `运行异常.mp3` |

声音按钮控制全部声音提醒。声音设置面板会显示当前文件名，默认声音位于项目或分发包根目录的 `sounds/`。

托盘通知弹窗当前暂时隐藏，后续会以更合适的通知形态重新设计。

## 功能特性

- 🔴🟡🟢 三色灯实时状态指示
- 📌 桌面置顶悬浮
- ↔️ 拖拽移动 + 贴边吸附/迷你灯条停靠
- 🧭 Expanded 多会话状态面板
- 🔊 4 类本地 MP3 声音提醒
- 🎛️ 右侧快捷按钮（缩放/展开/电源/静音；通知按钮暂隐藏）
- 🖥️ 系统托盘图标
- 📦 PyInstaller 便携文件夹打包

## 分发包

运行 `python scripts/build.py` 后会生成：

```text
dist/Codex Traffic Lights Portable/
├── Codex Traffic Lights Portable.exe
├── sounds/
├── 使用说明.md
└── _internal/
```

`使用说明.md` 是面向用户的简短说明，适合随分发包一起发送。

## 技术栈

Python 3.10+ / PyQt5 / QtMultimedia / psutil / QPropertyAnimation / PyInstaller

## 版本历史

见 [CHANGELOG.md](CHANGELOG.md)。GitHub Releases 保留每个版本的中文更新说明，方便回看迭代进度。

## 许可证

MIT
