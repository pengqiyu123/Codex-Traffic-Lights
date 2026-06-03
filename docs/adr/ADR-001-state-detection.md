# ADR-001: Codex 状态检测方案

## Status
Superseded by Codex app-server schema audit

## Context
Codex Traffic Lights 需要实时检测 Codex CLI 的当前可观测状态。早期文档中的 8 种状态来自 AI 推测，不是 Codex 的真实公开状态模型。

状态检测的难点在于：
- 进程存在性只能判断在线/离线
- CPU 占用不能可靠代表 Codex 运行状态
- Codex CLI 的稳定可观测状态应来自当前版本 app-server schema，而不是猜测 OTel 事件名

## Decision

采用 Codex app-server 优先、psutil 降级的方案：

### Phase 1 — Codex app-server schema 映射
- 使用 Codex CLI `app-server` v2 协议作为状态真相源
- `ThreadStatus.idle` → `IDLE`
- `ThreadStatus.active` / `TurnStatus.inProgress` → `WORKING`
- `activeFlags.waitingOnApproval` → `WAITING_APPROVAL`
- `activeFlags.waitingOnUserInput` → `WAITING_USER_INPUT`
- `ThreadStatus.systemError` / `TurnStatus.failed` → `ERROR`

### Phase 2 — psutil 降级检测
- app-server 不可用时，用 psutil 判断 Codex 进程存在性
- 无进程 → `OFFLINE`
- 有进程 → `WORKING`
- 进程异常退出 → `ERROR`

## Consequences

**优点**：
- 状态模型与 Codex 当前 schema 对齐
- 避免把 AI 推测伪装成产品事实
- psutil 是成熟稳定的跨平台库

**缺点**：
- app-server 连接和协议监听比单纯 psutil 更复杂
- 降级模式无法区分审批/输入等待
- Codex app-server 标记为 experimental，协议需要版本检查

## Alternatives Considered

1. **8 态 CPU/OTel 推测**：已废弃。`DEEP_WORK`、`NORMAL_WORK`、`QUEUED`、`REVIEW_READY` 没有在当前 schema 中得到稳定状态支持。
2. **纯日志解析**：读取 CODEX_HOME 中的会话记录。问题：日志格式未文档化，可能随版本变化。
3. **进程注入/Hook**：Hook Codex 进程的 stdin/stdout。问题：侵入性太强，可能被安全软件拦截。
4. **HTTP 代理拦截**：在本地搭代理拦截 Codex API 请求。问题：需要修改网络配置，复杂度高。
