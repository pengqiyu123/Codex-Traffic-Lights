# VSCode Codex WAITING_APPROVAL Diagnosis

日期：2026-06-06

## 结论

`WAITING_APPROVAL` 当前验收不通过。

在用户触发审批相关操作后，红绿灯仍显示 `WORKING`。两轮 live IPC 采集均未捕获到可映射为审批等待的 VSCode Codex IPC 信号：

- 未出现 `waitingOnApproval`
- 未出现 `approval_request`
- 未出现其他包含 `approval` 的 item type / patch value
- 活动会话的 `threadRuntimeStatus.type` 为 `active`
- 活动会话的 `threadRuntimeStatus.activeFlags` 为空数组
- 最后 turn 仍是 `status = inProgress`

因此当前产品没有真实上游数据可把该场景映射为 `WAITING_APPROVAL`。按项目数据采集规则，不能凭猜测修改产品状态逻辑。

## 采集方式

新增一次性诊断工具：

```text
test_process/vscode_codex_approval_probe.mjs
```

采集命令：

```powershell
node test_process\vscode_codex_approval_probe.mjs --duration 90 --max-events 120 --pretty --output test_process\approval-diagnosis-activeflags.json
```

数据源：

```text
\\.\pipe\codex-ipc
```

脱敏规则：

- 不记录 prompt 文本
- 不记录生成内容
- 不记录命令文本
- 不记录文件路径
- 不记录原始 IPC payload
- 只记录结构化状态字段：keys、type、status、state、kind、activeFlags、patch path、列表长度、conversationId 尾号

## 关键观察

### 初始化成功

IPC probe 成功连接 VSCode Codex IPC，并收到初始化响应：

```json
{
  "type": "response",
  "method": "initialize",
  "resultType": "success"
}
```

说明诊断工具确实连到了 VSCode Codex 插件 IPC，而不是没有数据源。

### 活动会话仍是 WORKING 形状

第二轮采集中的活动会话摘要：

```json
{
  "method": "thread-stream-state-changed",
  "change": {
    "type": "snapshot",
    "revision": 4178,
    "conversationState": {
      "threadRuntimeStatus": {
        "keys": ["activeFlags", "type"],
        "activeFlags": {
          "kind": "array",
          "length": 0,
          "items": []
        },
        "type": "active"
      },
      "recentTurns": [
        {
          "status": "inProgress",
          "itemTypes": [
            {"type": "fileChange", "status": "completed"},
            {"type": "commandExecution", "status": "completed"},
            {"type": "commandExecution", "status": "inProgress"}
          ]
        }
      ]
    }
  }
}
```

这正是现有产品映射为 `WORKING` 的形状：`activeFlags` 为空，最后 turn 是 `inProgress`。

### 未发现审批信号

两轮采集检索结果：

| 信号 | 结果 |
|------|------|
| `waitingOnApproval` | 未出现 |
| `approval_request` | 未出现 |
| `approval` item type | 未出现 |
| approval patch value | 未出现 |
| `activeFlags` 非空 | 未出现 |

第一轮采集使用的 probe 对 `activeFlags` 摘要不够细，只显示为 object；第二轮已修正 probe，明确显示 `activeFlags.length = 0`。

## 对产品逻辑的影响

当前 `vscode_ipc.py` 的审批映射逻辑是合理但缺少 live 上游样本：

- 如果 item type 或 patch value 中出现 approval 相关字段，产品会映射为 `WAITING_APPROVAL`
- 但本轮真实 VSCode IPC 广播没有提供这些字段

所以这轮不应修改 `src/` 产品逻辑。否则会把普通 `WORKING` 误判为审批等待。

## 判定

`WAITING_APPROVAL` 在当前 VSCode Codex 插件 IPC 场景下暂不可支持。

更精确地说：当前测试触发方式下，VSCode Codex IPC 只暴露了 `active + inProgress`，没有暴露审批等待信号。红绿灯继续显示 `WORKING` 是对现有 IPC 数据的正确反映，但不满足用户期望，因此该状态验收失败。

## 后续建议

1. 保留 `WAITING_APPROVAL` 产品状态和 mock 测试，但在产品状态表中标注“VSCode IPC live sample 未验证”。
2. 如果后续 VSCode Codex 插件版本暴露 `waitingOnApproval` 或 approval item type，再用 live transcript 更新映射。
3. 不要把 `fileChange`、`commandExecution` 或普通 `inProgress` 推断成审批等待；这些字段也会出现在正常工作流中。
4. 若必须支持审批提醒，需要另找数据源，例如 VSCode UI 状态、扩展日志、或更底层的插件内部状态，而不是当前 `thread-stream-state-changed` 摘要。

## 2026-06-07 计划最终确认态补充

用户复测发现：计划模式最后停在“是否实施此计划”确认界面时，产品仍显示 `IDLE`。

本轮没有放宽产品映射，也没有把普通 `completed` / `idle` 推断为审批态。原因是旧诊断 JSON 只能证明 `conversationState` 中存在 `threadGoalResumeConfirmation` 这个 key，不能证明它在确认弹窗期间的值形态。

已增强诊断工具：

```text
test_process/vscode_codex_approval_probe.mjs
```

新增脱敏能力：

- snapshot 中记录 `threadGoalResumeConfirmation` 的 object keys 和安全状态字段
- patch 中记录 `/threadGoalResumeConfirmation/...` 路径和安全值
- 安全值仅包括 `status` / `state` / `type` / `kind` / `phase`、布尔值、null、数组长度、object keys
- 不记录计划正文、prompt、生成内容、命令文本、cwd、文件路径或 diff

复测采集命令：

```powershell
node test_process\vscode_codex_approval_probe.mjs --duration 90 --max-events 120 --pretty --output test_process\approval-diagnosis-plan-confirmation.json
```

采集流程：

1. 启动上面的 probe。
2. 在 VSCode Codex 中进入计划模式。
3. 停在“是否实施此计划”确认界面 15-30 秒。
4. 再选择实施或取消，让确认态退出。
5. 检查输出中的 `threadGoalResumeConfirmation` 摘要。

后续判定规则：

- 如果安全字段明确为 `pending` / `waiting` / `confirm` / `apply-plan` / `resume`，可以补产品映射。
- 如果非空对象只在确认界面存在、退出后消失，且没有 resolved/completed 字段，可以考虑把非空 confirmation 对象映射为 `WAITING_APPROVAL`。
- 如果字段始终为 null/空对象，或 IPC 只暴露 `completed` / `idle`，则记录为上游不可观测，不改产品逻辑。
