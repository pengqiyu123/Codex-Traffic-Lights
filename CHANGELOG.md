# 版本历史

## v0.4.0

本版把提醒系统从 Windows 预置提示音升级为本地 MP3 声音事件，并暂时隐藏托盘通知弹窗，保留更清楚的声音反馈。

### 主要更新

- 新增 4 类声音事件：任务完成、待审批确认、计划模式需要输入、运行异常。
- 将用户确认的 MP3 音效打包进 `resources/sounds/`，不再依赖 Windows 默认提示音。
- 声音播放改用 QtMultimedia，支持本地 MP3 资源。
- 通知弹窗功能暂时隐藏，侧边通知按钮也暂时隐藏；静音按钮继续控制全部声音。
- README 更新为当前 VSCode Codex 状态灯定位，并补充声音提醒说明。

### 验证

- `pytest tests -q`：315 passed
- `ruff check src tests`：passed

## v0.3.0

本版完成 VSCode Codex 6 态真实验收，并补齐计划确认、离线退场和 Expanded UI 的关键体验。

### 主要更新

- 完成 6 个产品状态实测：正在工作、空闲待命、待审批确认、待用户输入、运行异常、离线休眠。
- 计划模式最终“是否实施此计划”通过 `planImplementation.isCompleted = false` 映射为待审批确认。
- IPC 断线后清理 VSCode Codex 会话，Expanded 中断开的项目红灯慢闪 3 秒后隐藏。
- Expanded 项目区改为贴边项目卡片，去掉下部框中框，放大 mini 红绿灯。
- 版本元数据升级到 `0.3.0`。

### 验证

- `pytest tests -q`：296 passed
- `ruff check src tests`：passed

## v0.2.0

本版把产品从“好看的状态灯”推进到“能真实感知 VSCode Codex 插件状态”的版本。

### 主要更新

- 接入 VSCode Codex 私有 IPC 管道，实时读取 Codex 插件状态。
- 增加 Codex-only 多会话显示，过滤 ClaudeCode 会话对 UI 和聚合状态的影响。
- 验证正在工作、空闲待命、待审批确认、待用户输入等核心状态。
- 优化待审批和待用户输入灯效，修复高频状态刷新导致动画重启的问题。
- 优化 Expanded UI 缩放、横向总灯、会话矩阵布局和展开过渡。
- 增加 UI 设计文档和 Windows `start.bat` / `stop.bat` 辅助脚本。

### 已知限制

- 当时运行异常和离线休眠仍需要后续真实场景补测；这些已在 v0.3.0 完成。
