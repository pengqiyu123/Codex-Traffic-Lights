# ClaudeCode Handoff: Current Project State

日期：2026-06-08

## Summary

Codex Traffic Lights 已从通用 hook 状态灯收敛为 VSCode Codex 插件状态灯。核心检测链路是 VSCode Codex 私有 IPC：

```text
\\.\pipe\codex-ipc
```

当前准备发布 `v0.3.0`：6 个产品状态均已完成实测验证，Expanded UI 已改为贴边项目卡片布局。

当前质量门：

```text
pytest tests -q -> 296 passed
ruff check src tests -> passed
```

## Recent Modification History

- `987ba17`：将 VSCode Codex IPC connector 接入产品主流程，开始读取 `thread-stream-state-changed`。
- `56071bf`：移除 5 分钟长任务超时降级，改用 `threadRuntimeStatus.type`；同时过滤 Claude 会话，UI 只显示 Codex。
- `73c4a5e` / `bebceac`：优化等待态灯效。`WAITING_APPROVAL` 改黄绿交替慢闪，`WAITING_USER_INPUT` 改 700ms 黄灯间歇闪，并避免同状态刷新重启动画。
- `4201488` / `425e2d1`：优化 Expanded UI 缩放、横向总灯、状态文字高度和空白问题。
- `238f3fc` / `c2e49d5`：增强计划确认态诊断和 session 名称自适应；mini 红绿灯缩放已由用户复测成功。
- `d46e559` 之后：完成计划最终确认态、OFFLINE 断线清理、ERROR 实测验收，以及 Expanded 项目卡片 UI 调整。

## Current Status Matrix

| 状态 | 当前判定 | 说明 |
|------|----------|------|
| `WORKING` | 已验证 | VSCode Codex 执行任务时黄灯慢呼吸 |
| `IDLE` | 已验证 | 任务完成后绿灯常亮 |
| `WAITING_APPROVAL` | 已验证 | sandbox/权限批准请求和计划最终确认均已验证 |
| `WAITING_USER_INPUT` | 已验证，复测通过 | 计划模式提问机制触发黄灯 700ms 间歇闪 |
| `ERROR` | 已验证 | 临时改错 VSCode Codex 配置触发真实失败样本 |
| `OFFLINE` | 已验证 | 关闭/删除 Codex 项目后总灯回红，Expanded 退场列红灯慢闪 3 秒后隐藏 |

## Current Key Bug And Evidence

计划模式最终“是否实施此计划”曾显示 `IDLE`。真实 IPC 证据显示：

```text
threadRuntimeStatus.type = idle
threadGoalResumeConfirmation = null
planImplementation.isCompleted = false
```

退出确认框后 patch 为：

```text
/turns/.../items/.../isCompleted = true
```

因此正确映射是：

```text
type == "planImplementation" && isCompleted == false -> WAITING_APPROVAL
isCompleted == true -> 清除对应等待信号
```

实现只读取 `type` 和 `isCompleted`，不读取或记录 `planContent`、prompt、命令、路径或 diff。

## v0.3.0 Release Notes Draft

```text
- 完成 VSCode Codex 6 态实测验收：WORKING / IDLE / WAITING_APPROVAL / WAITING_USER_INPUT / ERROR / OFFLINE。
- 计划模式最终“是否实施此计划”识别为 WAITING_APPROVAL。
- OFFLINE 断线清理和 Expanded 退场提示稳定工作。
- Expanded UI 调整为无外框项目卡片，卡片贴边填满下部区域，移除多余弧线装饰。
```
