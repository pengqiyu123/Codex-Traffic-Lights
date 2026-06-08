#!/usr/bin/env node
/**
 * Redacted approval-state probe for the VSCode Codex IPC router.
 *
 * This is diagnosis tooling, not product code. It captures only structural
 * status fields from thread-stream-state-changed broadcasts: keys, patch paths,
 * type/status/state/kind values, active flags, and list lengths. It never writes
 * prompt text, generated content, command text, file paths, or raw payloads.
 */

import crypto from "node:crypto";
import fs from "node:fs";
import net from "node:net";
import { pathToFileURL } from "node:url";

const DEFAULT_WINDOWS_PIPE = "\\\\.\\pipe\\codex-ipc";
const INITIALIZING_CLIENT_ID = "initializing-client";
const PROBE_CLIENT_TYPE = "traffic-lights-approval-probe";
const MAX_FRAME_BYTES = 50 * 1024 * 1024;
const SAFE_VALUE_KEYS = new Set([
  "activeFlags",
  "kind",
  "method",
  "op",
  "resultType",
  "role",
  "state",
  "status",
  "type",
]);
const INTERESTING_OBJECT_KEYS = new Set([
  "activeFlags",
  "items",
  "lastTurn",
  "patches",
  "status",
  "threadGoalResumeConfirmation",
  "threadRuntimeStatus",
  "turns",
]);

function main() {
  const args = parseArgs(process.argv.slice(2));
  const result = {
    probe: "vscode-codex-approval-probe",
    started_at: new Date().toISOString(),
    success: false,
    duration_seconds: 0,
    events: [],
    note:
      "Redacted structural capture: no prompt text, generated content, command text, file paths, or raw payloads.",
  };
  const startedAt = Date.now();
  let buffer = Buffer.alloc(0);
  let finished = false;
  let client = null;

  const finish = (success, error = null) => {
    if (finished) {
      return;
    }
    finished = true;
    result.success = success;
    result.error = error;
    result.finished_at = new Date().toISOString();
    result.duration_seconds = Number(((Date.now() - startedAt) / 1000).toFixed(3));
    const output = JSON.stringify(result, null, args.pretty ? 2 : 0);
    if (args.output) {
      fs.writeFileSync(args.output, `${output}\n`, "utf8");
    }
    console.log(output);
    if (client) {
      client.destroy();
    }
    process.exit(success ? 0 : 1);
  };

  const timer = setTimeout(
    () => finish(result.events.length > 0, result.events.length > 0 ? null : "no events"),
    args.duration * 1000,
  );
  timer.unref();

  client = net.createConnection(args.pipe);

  client.on("connect", () => {
    client.write(frame(initializeRequest()));
  });

  client.on("data", (chunk) => {
    buffer = Buffer.concat([buffer, chunk]);
    while (buffer.length >= 4) {
      const length = buffer.readUInt32LE(0);
      if (length > MAX_FRAME_BYTES) {
        finish(false, `IPC frame too large: ${length}`);
        return;
      }
      if (buffer.length < 4 + length) {
        return;
      }
      const body = buffer.subarray(4, 4 + length).toString("utf8");
      buffer = buffer.subarray(4 + length);
      try {
        const summary = summarizeMessage(JSON.parse(body));
        if (summary) {
          result.events.push(summary);
        }
      } catch (error) {
        result.events.push({ parse_error: String(error), raw_length: body.length });
      }
      if (result.events.length >= args.maxEvents) {
        finish(true);
        return;
      }
    }
  });

  client.on("error", (error) => finish(false, error.message));
  client.on("close", () => finish(result.events.length > 0));
}

function parseArgs(argv) {
  const result = {
    pipe: DEFAULT_WINDOWS_PIPE,
    duration: 60,
    maxEvents: 80,
    output: "",
    pretty: false,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--pretty") {
      result.pretty = true;
    } else if (arg === "--pipe") {
      result.pipe = argv[++index] ?? result.pipe;
    } else if (arg === "--duration") {
      result.duration = Number(argv[++index] ?? result.duration);
    } else if (arg === "--max-events") {
      result.maxEvents = Number(argv[++index] ?? result.maxEvents);
    } else if (arg === "--output") {
      result.output = argv[++index] ?? result.output;
    } else if (arg === "--help" || arg === "-h") {
      printHelp();
      process.exit(0);
    }
  }
  return result;
}

function printHelp() {
  console.log(`Usage: node test_process/vscode_codex_approval_probe.mjs [options]

Options:
  --duration SECONDS   Maximum seconds to listen, default 60
  --max-events COUNT   Maximum events to capture, default 80
  --output PATH        Optional JSON output path
  --pipe PATH          Named pipe path, default ${DEFAULT_WINDOWS_PIPE}
  --pretty             Pretty-print JSON output
`);
}

function initializeRequest() {
  return {
    type: "request",
    requestId: crypto.randomUUID(),
    sourceClientId: INITIALIZING_CLIENT_ID,
    version: 0,
    method: "initialize",
    params: { clientType: PROBE_CLIENT_TYPE },
  };
}

function frame(message) {
  const body = Buffer.from(JSON.stringify(message), "utf8");
  const header = Buffer.alloc(4);
  header.writeUInt32LE(body.length, 0);
  return Buffer.concat([header, body]);
}

export function summarizeMessage(message) {
  const summary = {
    type: safeScalar(message?.type, "type"),
    method: safeScalar(message?.method, "method"),
    resultType: safeScalar(message?.resultType, "resultType"),
  };
  if (message?.params && typeof message.params === "object") {
    summary.params = {
      keys: Object.keys(message.params).sort(),
      conversationIdTail: tail(message.params.conversationId),
      hostId: safeScalar(message.params.hostId, "hostId"),
    };
    if (message.params.change && typeof message.params.change === "object") {
      summary.change = summarizeChange(message.params.change);
    }
  }
  if (!summary.change && summary.method !== "thread-stream-state-changed") {
    return summary;
  }
  return summary;
}

function summarizeChange(change) {
  const summary = {
    keys: Object.keys(change).sort(),
    type: safeScalar(change.type, "type"),
    revision: safeNumber(change.revision),
    baseRevision: safeNumber(change.baseRevision),
  };
  if (Array.isArray(change.patches)) {
    summary.patchCount = change.patches.length;
    summary.patches = change.patches.slice(0, 20).map(summarizePatch);
  }
  if (change.conversationState && typeof change.conversationState === "object") {
    summary.conversationState = summarizeConversationState(change.conversationState);
  }
  return summary;
}

function summarizeConversationState(state) {
  const turns = Array.isArray(state.turns) ? state.turns : [];
  return {
    keys: Object.keys(state).sort(),
    idTail: tail(state.id),
    sessionIdTail: tail(state.sessionId),
    hostId: safeScalar(state.hostId, "hostId"),
    threadRuntimeStatus: summarizeObjectShape(state.threadRuntimeStatus, 0),
    threadGoalResumeConfirmation: summarizeObjectShape(
      state.threadGoalResumeConfirmation,
      0,
    ),
    activeFlags: summarizeList(state.activeFlags, "activeFlags", 0),
    turnCount: turns.length,
    recentTurns: turns.slice(-3).map((turn, index) => summarizeTurn(turn, turns.length - 3 + index)),
  };
}

function summarizeTurn(turn, index) {
  if (!turn || typeof turn !== "object") {
    return { index, kind: typeof turn };
  }
  const params = turn.params && typeof turn.params === "object" ? turn.params : {};
  return {
    index,
    keys: Object.keys(turn).sort(),
    status: safeScalar(turn.status, "status"),
    state: safeScalar(turn.state, "state"),
    kind: safeScalar(turn.kind, "kind"),
    threadIdTail: tail(params.threadId),
    itemCount: Array.isArray(turn.items) ? turn.items.length : null,
    itemTypes: Array.isArray(turn.items)
      ? turn.items.slice(-12).map((item, itemIndex) => summarizeItem(item, itemIndex))
      : [],
    hookRunCount: Array.isArray(turn.hookRuns) ? turn.hookRuns.length : null,
  };
}

function summarizeItem(item, index) {
  if (!item || typeof item !== "object") {
    return { index, kind: typeof item };
  }
  const summary = {
    index,
    keys: Object.keys(item).sort(),
    type: safeScalar(item.type, "type"),
    status: safeScalar(item.status, "status"),
    state: safeScalar(item.state, "state"),
    kind: safeScalar(item.kind, "kind"),
    activeFlags: summarizeList(item.activeFlags, "activeFlags", 0),
  };
  if (item.type === "planImplementation" && typeof item.isCompleted === "boolean") {
    summary.isCompleted = item.isCompleted;
  }
  return summary;
}

function summarizePatch(patch) {
  if (!patch || typeof patch !== "object") {
    return { kind: typeof patch };
  }
  const path = Array.isArray(patch.path) ? patch.path.slice(0, 8).map(String) : [];
  const valueKey = safePatchValueKey(path);
  return {
    op: safeScalar(patch.op, "op"),
    path: `/${path.join("/")}`,
    value:
      valueKey === ""
        ? summarizeObjectShape(patch.value, 0)
        : summarizePrimitive(patch.value, valueKey),
  };
}

function safePatchValueKey(path) {
  if (path[0] !== "threadGoalResumeConfirmation") {
    const lastPart = path[path.length - 1] ?? "";
    return lastPart === "isCompleted" ? lastPart : "";
  }
  const lastPart = path[path.length - 1] ?? "";
  return SAFE_VALUE_KEYS.has(lastPart) ? lastPart : "";
}

function summarizeObjectShape(value, depth) {
  if (value === null || value === undefined) {
    return { kind: String(value) };
  }
  if (Array.isArray(value)) {
    return summarizeList(value, "", depth);
  }
  if (typeof value !== "object") {
    return summarizePrimitive(value, "");
  }

  const keys = Object.keys(value).sort();
  const summary = { kind: "object", keys };
  for (const key of keys) {
    const item = value[key];
    if (key === "activeFlags") {
      summary[key] = summarizeList(item, "activeFlags", depth + 1);
    } else if (SAFE_VALUE_KEYS.has(key)) {
      summary[key] = summarizePrimitive(item, key);
    } else if (INTERESTING_OBJECT_KEYS.has(key) && depth < 2) {
      summary[key] = summarizeObjectShape(item, depth + 1);
    }
  }
  return summary;
}

function summarizeList(value, key, depth) {
  if (!Array.isArray(value)) {
    return summarizePrimitive(value, key);
  }
  const summary = { kind: "array", length: value.length };
  if (key === "activeFlags" || depth < 2) {
    summary.items = value.slice(0, 12).map((item) => summarizeObjectShape(item, depth + 1));
  }
  return summary;
}

function summarizePrimitive(value, key) {
  if (typeof value === "string") {
    if (SAFE_VALUE_KEYS.has(key)) {
      return value;
    }
    return { kind: "string", length: value.length };
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return value;
  }
  if (value === null || value === undefined) {
    return value;
  }
  return { kind: typeof value };
}

function safeScalar(value, key) {
  const summarized = summarizePrimitive(value, key);
  return typeof summarized === "object" ? undefined : summarized;
}

function safeNumber(value) {
  return typeof value === "number" ? value : undefined;
}

function tail(value) {
  return typeof value === "string" && value.length > 6 ? value.slice(-6) : value;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main();
}
