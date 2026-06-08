# ClaudeCode Handoff: Current Project State

日期：2026-06-08

## Summary

Codex Traffic Lights 已从通用 hook 状态灯收敛为 VSCode Codex 插件状态灯。核心检测链路是 VSCode Codex 私有 IPC：

```text
\\.\pipe\codex-ipc
```

本地 `main` 当前比 `origin/main` ahead 2，另有一组未提交修复，主要解决计划模式最终“是否实施此计划”确认框被误判为 `IDLE` 的问题。

当前质量门：

```text
pytest tests -q -> 275 passed
ruff check src tests -> passed
```

## Recent Modification History

- `987ba17`：将 VSCode Codex IPC connector 接入产品主流程，开始读取 `thread-stream-state-changed`。
- `56071bf`：移除 5 分钟长任务超时降级，改用 `threadRuntimeStatus.type`；同时过滤 Claude 会话，UI 只显示 Codex。
- `73c4a5e` / `bebceac`：优化等待态灯效。`WAITING_APPROVAL` 改黄绿交替慢闪，`WAITING_USER_INPUT` 改 700ms 黄灯间歇闪，并避免同状态刷新重启动画。
- `4201488` / `425e2d1`：优化 Expanded UI 缩放、横向总灯、状态文字高度和空白问题。
- `238f3fc` / `c2e49d5`：增强计划确认态诊断和 session 名称自适应；mini 红绿灯缩放已由用户复测成功。
- 当前未提交变更：已把 live sample 证明的 `planImplementation.isCompleted = false -> true` 接入 `vscode_ipc.py`，并补充 probe、文档和测试。

## Current Status Matrix

| 状态 | 当前判定 | 说明 |
|------|----------|------|
| `WORKING` | 已验证 | VSCode Codex 执行任务时黄灯慢呼吸 |
| `IDLE` | 已验证 | 任务完成后绿灯常亮 |
| `WAITING_APPROVAL` | 部分需复测 | sandbox/权限批准请求已验证；计划最终确认子场景已接入产品映射，仍需实机复测灯效 |
| `WAITING_USER_INPUT` | 已验证，复测通过 | 计划模式提问机制触发黄灯 700ms 间歇闪 |
| `ERROR` | 待验证 | 只接受真实 IPC `failed` 或 `systemError` |
| `OFFLINE` | 待独立验证 | 关闭 VSCode/Codex 后应红灯常亮；若旧 session 残留，需要补断线清理 |

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

## Next Steps

1. 真实复测计划最终确认态：进入计划模式，停在“是否实施此计划”确认框，观察是否变为黄绿交替慢闪；点击实施/取消后应回到绿灯或下一真实状态。
2. 复测通过后整理提交当前未提交变更，建议提交名：

```text
fix: detect plan implementation approval state
```

3. 继续测试 `ERROR` 和 `OFFLINE`。如果 `OFFLINE` 失败，优先实现 IPC 断线后清理 `vscode-ipc::` sessions。
4. 不提交 `test_process/approval-diagnosis-*.json` 原始诊断文件，只提交脱敏 Markdown 结论。
