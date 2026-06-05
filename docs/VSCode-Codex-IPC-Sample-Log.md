# VSCode Codex IPC 状态样本日志

日期：2026-06-05
采集工具：`test_process/vscode_codex_ipc_connector.py`
数据源：`\\.\pipe\codex-ipc`

## 脱敏原则

本日志只记录状态字段和计数字段：

- `conversationId`
- `hostId`
- `revision`
- `lastTurn.status`
- `productStatus`
- `turnCount`
- 审批/用户输入等待信号类型和 patch path

未记录 prompt 文本、生成内容、命令文本、文件路径或原始 IPC payload。

## 采集命令

```powershell
$env:PYTHONPATH='test_process'
python test_process\vscode_codex_ipc_connector.py --duration 4 --max-events 6 --reconnect-delay 0.2
```

## 已真实验证状态

### IDLE

观察：VSCode Codex IPC 广播中出现 `lastTurn.status == "completed"`，原型映射为 `IDLE`。

```json
{
  "source": "vscode-ipc",
  "conversationId": "019e8825-161c-7e71-8fda-699303315443",
  "hostId": "local",
  "revision": 261,
  "lastTurn": {
    "status": "completed"
  },
  "productStatus": "IDLE",
  "turnCount": 24,
  "approvalSignals": [],
  "userInputSignals": [],
  "signalPatchPaths": []
}
```

### WORKING

观察：VSCode Codex IPC 广播中出现 `lastTurn.status == "inProgress"`，原型映射为 `WORKING`。

```json
{
  "source": "vscode-ipc",
  "conversationId": "019e8d3a-05c6-7902-abaa-6e13ac9d2c3e",
  "hostId": "local",
  "revision": 1567,
  "lastTurn": {
    "status": "inProgress"
  },
  "productStatus": "WORKING",
  "turnCount": 66,
  "approvalSignals": [],
  "userInputSignals": [],
  "signalPatchPaths": []
}
```

同一次采集中，该会话继续收到 `revision` 1568、1569、1570 的 `inProgress` 更新，说明 IPC 可以持续追踪正在运行的 Codex 会话。

## 尚未真实验证状态

### ERROR

单元测试已覆盖 `lastTurn.status == "failed"` 到 `ERROR` 的映射，但本次真实采集中未捕获 `failed` 样本。

### WAITING_APPROVAL

单元测试已覆盖 item type / patch path 中出现 approval request 信号时映射为 `WAITING_APPROVAL`，并验证不会泄漏 command 或 path payload。当前真实 VSCode Codex 会话尚未稳定触发并采到审批等待样本。

### WAITING_USER_INPUT

单元测试已覆盖 item type / patch path 中出现 user input request 信号时映射为 `WAITING_USER_INPUT`，并验证不会泄漏问题文本。当前真实 VSCode Codex 会话尚未稳定触发并采到用户输入等待样本。

## 结论

`\\.\pipe\codex-ipc` 已被验证为 VSCode Codex 插件的可用状态数据源：

- 可以连接并接收广播。
- 可以区分多个 `conversationId`。
- 可以真实捕获 `completed -> IDLE`。
- 可以真实捕获 `inProgress -> WORKING`。
- 其他等待/错误态需要后续在可复现场景下补充真实样本。
