# AGENTS.md

Codex 开发代理指南。本文件为 Codex CLI 提供项目上下文和开发约束。

## 项目定位

Windows 桌面悬浮小组件，显示 Codex CLI 运行状态（红黄绿灯）。Python + PyQt5 技术栈，PyInstaller 打包为单 exe。

## 开发约束

### 代码风格
- Python 3.10+，使用 type hints
- 数据类用 `@dataclass(frozen=True)` 不可变模式
- 类名 PascalCase，函数名 snake_case，常量 UPPER_SNAKE_CASE
- 错误用结构化异常（code + message）
- 中文面向用户的文字（状态文字、提示），英文面向代码（变量、注释）

### 模块边界
- `models.py`：纯数据定义，零外部依赖（无 PyQt、无 psutil）
- `state_mapper.py`：纯映射逻辑，把 Codex app-server schema 映射为 CodexStatus，不读取磁盘/网络
- `process_monitor.py`：负责连接 app-server 和 psutil 降级检测，调用 state_mapper，发射信号，不操作 UI
- `widgets/`：只负责 UI 渲染和交互，不直接访问 psutil 或 app-server
- `animation/`：只负责动画效果定义和驱动，不包含业务逻辑
- `config.py`：只负责配置读写，不包含业务逻辑

### 依赖方向
```
__main__.py → MainWindow → ProcessMonitor → state_mapper → models
                         → TrafficLight → AnimationEngine → effects → models
                         → StatusBar → models
                         → SideButtons → config
                         → TrayIcon → config
```
严禁反向依赖。

### 测试要求
- 每个 `models.py` 中的枚举/数据类必须有单元测试
- `process_monitor.py` 的 psutil 调用必须 mock
- 灯效参数（呼吸周期、闪烁频率）必须有验证测试
- UI 组件用 `pytest-qt` 测试信号/槽连接

### 禁止事项
- 不硬编码密钥、路径、进程名
- 不在 models.py 中导入 PyQt 或 psutil
- 不在动画模块中包含业务逻辑判断
- 不使用 `any` 类型或省略类型标注
- 不创建空 catch 块

## 文件命名

| 类别 | 命名 | 示例 |
|------|------|------|
| 模块 | snake_case | `process_monitor.py` |
| 类 | PascalCase | `TrafficLightWidget` |
| 测试 | `test_<name>` | `test_process_monitor.py` |
| 常量 | UPPER_SNAKE_CASE | `DEFAULT_POLL_INTERVAL_MS` |

## 提交规范

```
feat: 新增拖拽贴边隐藏功能
fix: 修复呼吸动画周期计算错误
refactor: 拆分灯效参数到独立 effects 模块
test: 补充 ProcessMonitor 单元测试
docs: 更新 PRD 状态检测方案
chore: 更新 PyInstaller 打包配置
```
