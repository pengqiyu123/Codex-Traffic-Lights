# Codex 状态调查报告

面向：ClaudeCode 产品经理

结论：现有文档里的 8 种状态是 AI 推测，不是 Codex 的真实公开状态模型。后续开发必须以 Codex CLI 当前可观测接口为准。

## 调查方法

- 本机 Codex 版本：`codex-cli 0.118.0`
- 使用 Codex 自带协议导出命令：

```powershell
codex app-server generate-ts --experimental --out $env:TEMP\codex-app-ts
```

- 核对导出的 app-server v2 类型定义：
  - `$env:TEMP\codex-app-ts\v2\ThreadStatus.ts`
  - `$env:TEMP\codex-app-ts\v2\ThreadActiveFlag.ts`
  - `$env:TEMP\codex-app-ts\v2\TurnStatus.ts`
  - `$env:TEMP\codex-app-ts\v2\ThreadStatusChangedNotification.ts`

## Codex 真实可观测状态

`ThreadStatus`：

```ts
export type ThreadStatus =
  | { "type": "notLoaded" }
  | { "type": "idle" }
  | { "type": "systemError" }
  | { "type": "active", activeFlags: Array<ThreadActiveFlag> };
```

`ThreadActiveFlag`：

```ts
export type ThreadActiveFlag =
  | "waitingOnApproval"
  | "waitingOnUserInput";
```

`TurnStatus`：

```ts
export type TurnStatus =
  | "completed"
  | "interrupted"
  | "failed"
  | "inProgress";
```

核心通知：

```ts
export type ThreadStatusChangedNotification = {
  threadId: string,
  status: ThreadStatus,
};
```

## 产品状态映射

Codex Traffic Lights 的 `CodexStatus` 应该是产品显示层对 Codex schema 的映射，不应伪装成 Codex 原生状态。

| 产品状态 | 来源 | 说明 |
|---|---|---|
| `OFFLINE` | app-server 未连接 / Codex 进程不存在 | 本应用级状态 |
| `IDLE` | `ThreadStatus.type == "idle"` | Codex 线程空闲 |
| `WORKING` | `ThreadStatus.type == "active"` 且无等待标志，或 `TurnStatus == "inProgress"` | Codex 正在执行 |
| `WAITING_APPROVAL` | `activeFlags` 包含 `waitingOnApproval` | 等待用户审批 |
| `WAITING_USER_INPUT` | `activeFlags` 包含 `waitingOnUserInput` | 等待用户输入 |
| `ERROR` | `ThreadStatus.type == "systemError"` 或 `TurnStatus == "failed"` 或进程异常退出 | 异常态 |

## 被废弃的 8 态推测

以下状态不得作为 Codex 原生状态实现：

- `DEEP_WORK`：CPU 高负载推断，不是 Codex 状态。
- `NORMAL_WORK`：CPU 中低负载推断，不是 Codex 状态。
- `QUEUED`：当前 schema 未发现稳定可观测字段。
- `REVIEW_READY`：当前 schema 未发现稳定运行态；`review` 是非交互 turn 类型，不等价于“待审阅完成”。
- `AWAITING_APPROVAL`：含义真实，但命名应对齐 schema 为 `WAITING_APPROVAL`。

如果后续确实需要“负载强弱”灯效，只能作为 `WORKING` 的附加显示强度，例如 `WorkingIntensity.HIGH`，不能扩展为 Codex 官方状态。

## 给 ClaudeCode 的开发指令

请停止按 8 态 PRD 下发任务。Task 1 起改为实现 6 个产品状态：

`OFFLINE`、`IDLE`、`WORKING`、`WAITING_APPROVAL`、`WAITING_USER_INPUT`、`ERROR`

检测优先级：

1. 优先接入 Codex app-server v2 协议，监听 `thread/status/changed`、`turn/started`、`turn/completed` 等事件。
2. app-server 不可用时，允许使用 psutil 做降级检测：无进程为 `OFFLINE`，有进程为 `WORKING`，进程异常退出为 `ERROR`。
3. 不允许用 CPU 阈值制造 `DEEP_WORK` / `NORMAL_WORK` / `QUEUED` / `REVIEW_READY`。

验收标准：

- 代码枚举只有上述 6 个产品状态。
- 测试必须覆盖 `ThreadStatus`、`ThreadActiveFlag`、`TurnStatus` 到产品状态的映射。
- README/PRD/开发命令不得再声称 Codex 有 8 个真实运行状态。
