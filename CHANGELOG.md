# 版本历史

## v0.5.1

本版是 v0.5 系列的稳定性与分发包整理版本，重点修复吸附态双击展开卡顿，并把打包流程整理为正式便携文件夹。

### 主要更新

**吸附与展开交互修复**
- 修复吸附状态下双击红绿灯时，收缩态与 Expanded 展开态互相抢状态导致卡顿的问题。
- 双击红绿灯现在优先打开会话展开面板，并取消停靠/收缩定时器。
- 保留旧成功机制：吸附后仍可自动停靠；双击非灯区外壳仍可立即停靠。
- 修复停靠态未跟随缩放等级的问题：0.5x/1.5x/2.0x 下迷你灯条尺寸和灯径同步缩放。

**分发包整理**
- `python scripts/build.py` 现在直接生成 `dist/Codex Traffic Lights Portable/` 便携文件夹。
- 分发包根目录包含 `Codex Traffic Lights Portable.exe`、`sounds/` 和 `使用说明.md`。
- 默认音频只放在用户可见的 `sounds/` 文件夹中，避免内部资源目录和外部声音目录并存造成困惑。
- 新增面向用户的 `docs/Portable-User-Guide.md`，打包时复制为 `使用说明.md`。

**文档与版本**
- README 更新为当前便携文件夹分发方式，并修正 4 个默认声音文件名。
- 同步 `pyproject.toml` 与包内 `__version__` 到 `0.5.1`。

### 验证

- `pytest tests -q`：366 passed
- `ruff check src tests scripts`：passed

## v0.5.0

侧边按钮重排、自定义声音管理、声音目录合并、屏幕边缘吸附与停靠收缩态。

### 主要更新

**按钮与 Expanded 模式重排（#19）**
- 侧边按钮新布局：`[展开] [缩小] [放大] [齿轮=声音设置] [电源] [静音]`。
- Expanded 增加 `sessions` / `sound_settings` 双内容模式；展开按钮进入会话，齿轮进入声音设置。
- ESC 收起 Expanded，双击主灯切换会话面板。

**自定义声音文件管理（#20）**
- 新增声音设置面板，4 行：任务完成、待审批确认、计划模式输入、运行异常。
- 支持用户选择 MP3/WAV 自定义提示音，复制到声音目录并持久化配置。
- 播放优先链：用户配置路径 → 默认音效；不支持的格式弹窗提示。

**声音目录合并（#21）**
- 删除内部 `resources/sounds/`，统一为项目根 `sounds/` 目录。
- 删除 `ensure_default_sound_files()` 和 `packaged_sound_path()`，简化回退链为两级。
- 打包脚本更新，`.gitignore` 只入库四个默认音效。

**屏幕边缘吸附与停靠收缩态（#22）**
- 三态模型：FREE（自由 72×220）→ SNAPPED（吸附 72×220）→ DOCKED（停靠 52×24 迷你 LED 条）。
- 拖到屏幕左右 30px 内自动吸附；静置 3 秒或双击立即收缩为迷你指示条。
- 停靠态仅显示 3 颗 10px LED 指示灯，无文字无按钮，灯色跟随 CodexStatus。
- 悬停展开、离开 500ms 收回、拖离边缘返回自由态。
- 修复：窗口半隐藏（超出屏幕边缘）也能触发吸附。

**其他**
- 修复便携 exe 循环启动：`sys.frozen` 保护跳过 hook 安装。
- 修复 `_choose_sound` 未捕获 ValueError 导致崩溃。

### 验证

- `pytest tests -q`：357 passed
- `ruff check src tests`：passed

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
