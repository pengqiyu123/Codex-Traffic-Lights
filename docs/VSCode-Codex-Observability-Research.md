# VSCode Codex 可观测性研究

日期：2026-06-05  
面向：ClaudeCode 产品经理  
范围：只研究 VSCode Codex 插件状态信号，不实现产品代码。

## 结论

VSCode Codex 插件**有可用的外部状态路径**，但不是现有的 Hook 文件桥，也不是 psutil。

最有价值路径是 VSCode 插件创建的本机 IPC 路由：

```text
\\.\pipe\codex-ipc
```

主动探针已验证第三方客户端可以连接该管道，发送 `initialize` 请求后收到实时广播：

- `thread-stream-state-changed`
- payload 包含 `conversationId`、`hostId`、`change.type`
- `snapshot` 中包含 `conversationState.turns[*].status`
- 当前实测两个不同 `conversationId` 的最后 turn 均为 `status: "inProgress"`

这解释了当前产品状态不准的根因：真实 VSCode Codex 状态在 `codex-ipc` 里，而产品目前主要依赖 Hook 文件桥和 psutil；Hook 只捕获 ClaudeCode/Codex CLI，不捕获 VSCode Codex 插件会话。

## 已产出探针

| 文件 | 类型 | 作用 |
|---|---|---|
| `test_process/vscode_codex_observability_probe.py` | 只读 | 扫描扩展目录、VSCode storage、Codex.log、进程、命名管道 |
| `test_process/vscode_codex_ipc_probe.mjs` | 主动 | 连接 `\\.\pipe\codex-ipc`，注册临时 client，脱敏输出广播摘要 |

运行方式：

```powershell
python test_process\vscode_codex_observability_probe.py --pretty --log-limit 3
node test_process\vscode_codex_ipc_probe.mjs --duration 5 --max-events 6 --pretty
```

## 路径 1：文件系统 / VSCode Storage

### 尝试方法

- 检查扩展安装目录：
  - `%USERPROFILE%\.vscode\extensions\openai.chatgpt-26.601.21317-win32-x64`
  - `%USERPROFILE%\.vscode\extensions\openai.chatgpt-26.602.30954-win32-x64`
- 读取 `package.json`
- 检查 `%APPDATA%\Code\User\globalStorage\state.vscdb`
- 检查 `%APPDATA%\Code\User\workspaceStorage\*\state.vscdb`
- 检查 `chatEditingSessions\*\state.json`

### 观察结果

- 插件包名为 `openai.chatgpt`，显示名为 Codex，入口为 `./out/extension.js`。
- 插件贡献了 VSCode chat session：
  - `type: "openai-codex"`
- 插件配置包含：
  - `chatgpt.cliExecutable`
  - 描述明确写着这是开发用 Codex CLI executable 路径。
- `globalStorage` 有 `openai.chatgpt` 持久化键，但主要是 NUX、提示历史、UI 持久状态。
- `workspaceStorage` 主要有 `codexSecondaryViewContainer` 和 webview 可见性状态。
- `chatEditingSessions` 是 VSCode 编辑会话快照，不包含 Codex 运行态。

### 可行性评估

不可作为状态数据源。

Storage 可以证明插件安装和 UI 状态，但没有稳定的 per-thread `idle/inProgress/approval/userInput/error` 运行态。不能用这些文件驱动灯光。

## 路径 2：VSCode Codex 日志

### 尝试方法

扫描：

```text
%APPDATA%\Code\logs\*\window*\exthost\openai.chatgpt\Codex.log
```

关键词：

- `thread-stream-state-changed`
- `thread-read-state-changed`
- `client-status-changed`
- `thread/status/changed`
- `turn/started`
- `turn/completed`
- `waitingOnApproval`
- `waitingOnUserInput`

### 观察结果

最近日志中大量出现：

```text
[IpcClient] Received broadcast but no handler is configured method=thread-stream-state-changed
```

实测计数示例：

- `thread-stream-state-changed`: 10,000+ 次
- `thread-read-state-changed`: 少量
- `client-status-changed`: 少量
- `thread/status/changed`: 0 次

这些日志行只有方法名，没有 payload。少量 `waitingOnApproval` / `waitingOnUserInput` 出现在 bundled JS 或非事件上下文中，不能证明实时状态。

### 可行性评估

只适合诊断，不适合产品状态源。

日志能证明内部广播存在，但不能还原具体 thread、状态、审批、用户输入等待等信息。不能把“日志沉默”当作空闲。

## 路径 3：进程 / 网络 / app-server

### 尝试方法

- 枚举 VSCode / Codex 进程树
- 检查 `codex.exe app-server` 子进程
- `Get-NetTCPConnection -OwningProcess <pid>`
- 检查扩展 `out/extension.js` 如何启动 Codex

### 观察结果

VSCode 插件启动了 app-server 子进程：

```text
codex.exe app-server --analytics-default-enabled
```

实测有两个 VSCode 插件窗口对应两个 app-server 子进程。命令行没有 `--listen ws://...`，因此使用默认 transport：

```text
stdio://
```

`Get-NetTCPConnection` 对这些 `codex.exe` PID 没有发现 TCP 监听。扩展代码中可见：

- `startCodexProcess()`
- `Spawning codex app-server`
- `registerInternalNotificationHandler`
- `thread/status/changed`
- `turn/completed`

### 可行性评估

直接网络连接不可行；stdio 被 VSCode extension host 私有持有。

但 `chatgpt.cliExecutable` 是一个可选入口。理论上可以把它指向代理程序，由代理程序启动真实 `codex.exe app-server`，中继 stdin/stdout 并镜像 JSON-RPC 通知。这个方案侵入 VSCode 设置，且配置项标为 development only，可靠性中等、维护成本中高。

## 路径 4：VSCode Codex IPC

### 尝试方法

1. 检查命名管道列表，发现：

```text
\\.\pipe\codex-ipc
```

2. 反查扩展 bundle，发现 IPC 帧协议：

- 4 字节 little-endian 长度前缀
- JSON body
- `initialize` 请求
- `broadcast` / `request` / `response`

3. 使用 `test_process/vscode_codex_ipc_probe.mjs` 主动连接并发送：

```json
{
  "type": "request",
  "method": "initialize",
  "params": { "clientType": "traffic-lights-probe" }
}
```

### 观察结果

探针收到初始化成功：

```json
{
  "type": "response",
  "method": "initialize",
  "result_type": "success"
}
```

随后收到实时广播：

```json
{
  "type": "broadcast",
  "method": "thread-stream-state-changed",
  "conversation_id": "019e8d3a-05c6-7902-abaa-6e13ac9d2c3e",
  "change": {
    "type": "snapshot",
    "conversation_state": {
      "turn_count": 65,
      "last_turn": {
        "status": "inProgress",
        "thread_id": "019e8d3a-05c6-7902-abaa-6e13ac9d2c3e"
      }
    }
  }
}
```

同一次采样中出现两个不同 `conversation_id`，说明这条路径支持多 VSCode Codex 会话区分。

另外，扩展代码中 `thread-stream-state-changed` 后面的 `7` 是 IPC 广播 schema version，不是“Codex 有 7 个产品状态”。

### 可行性评估

可作为下一阶段最优数据源，但需要谨慎实现。

优点：

- 真实 VSCode Codex 插件数据
- 多会话可区分：`conversationId`
- 实时广播，不需要轮询日志
- 可拿到 turn status：例如 `inProgress`

风险：

- 私有协议，OpenAI 插件更新可能改字段或版本
- payload 可能包含用户 prompt、生成文本、文件路径，产品代码必须只提取状态字段，不能落盘敏感内容
- 需要处理 snapshot + patches，两者都可能更新状态
- 需要确认更多真实状态样本：completed、failed、approval request、user input request

## 产品状态映射建议

保持 `CodexStatus` 产品状态为当前 6 态，直到 IPC 采到更多真实样本：

| IPC 观察字段 | 建议产品状态 |
|---|---|
| 无 `codex-ipc` / 无插件 app-server | `OFFLINE` |
| last turn `status == "inProgress"` | `WORKING` |
| last turn `status == "completed"` | `IDLE` |
| last turn `status == "failed"` 或 turn/error | `ERROR` |
| patch path / item 显示 approval request | 待实测后映射 `WAITING_APPROVAL` |
| patch path / item 显示 request user input | 待实测后映射 `WAITING_USER_INPUT` |

不要从 `thread-stream-state-changed: 7` 推导第 7 种产品状态。它是协议版本号。

## 下一步建议

建议新开 Task 13：VSCode Codex IPC Connector 技术验证，不直接改 UI。

范围：

- 新建 `test_process/vscode_codex_ipc_state_capture.mjs` 或 Python/Node connector prototype
- 维护每个 `conversationId` 的内存 conversation state
- 支持 `snapshot` 和 JSON patch 更新
- 只输出脱敏状态转录：
  - `conversationId`
  - `revision`
  - `lastTurn.status`
  - approval/user-input 相关 item 类型或 patch path
- 用户用两个 VSCode Codex 会话模拟：
  - 工作中
  - 完成/空闲
  - 失败
  - 审批等待
  - 用户输入等待

只有捕获到这些真实样本后，再把 IPC Connector 纳入产品主流程。Hook 文件桥可以保留给 CLI/ClaudeCode，但对“只监控 VSCode Codex”场景，默认优先级应调整为：

```text
VSCode codex-ipc → app-server WebSocket（手动配置）→ Hook 文件桥（CLI）→ psutil fallback
```
