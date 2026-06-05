#!/usr/bin/env node
/**
 * Active one-off probe for the VSCode Codex IPC router.
 *
 * This is research tooling, not product code. It connects to the local
 * codex-ipc named pipe, registers as a temporary client, and prints a redacted
 * summary of broadcasts. It intentionally avoids dumping message text, prompts,
 * or file contents.
 */

import crypto from "node:crypto";
import net from "node:net";
import os from "node:os";

const DEFAULT_WINDOWS_PIPE = "\\\\.\\pipe\\codex-ipc";
const INITIALIZING_CLIENT_ID = "initializing-client";
const PROBE_CLIENT_TYPE = "traffic-lights-probe";

function main() {
  const args = parseArgs(process.argv.slice(2));
  const events = [];
  const startedAt = Date.now();
  let buffer = Buffer.alloc(0);
  let finished = false;

  const client = net.createConnection(args.pipe);
  const finish = (success, error = null) => {
    if (finished) {
      return;
    }
    finished = true;
    const result = {
      probe: "vscode-codex-ipc",
      success,
      duration_seconds: Number(((Date.now() - startedAt) / 1000).toFixed(3)),
      error,
      events,
      note: "Summaries intentionally omit prompt text, generated text, and file contents.",
    };
    console.log(JSON.stringify(result, null, args.pretty ? 2 : 0));
    client.destroy();
    process.exit(success ? 0 : 1);
  };

  const timer = setTimeout(() => finish(events.length > 0), args.duration * 1000);
  timer.unref();

  client.on("connect", () => {
    client.write(frame(initializeRequest()));
  });

  client.on("data", (chunk) => {
    buffer = Buffer.concat([buffer, chunk]);
    while (buffer.length >= 4) {
      const length = buffer.readUInt32LE(0);
      if (length > 50 * 1024 * 1024) {
        finish(false, `IPC frame too large: ${length}`);
        return;
      }
      if (buffer.length < 4 + length) {
        return;
      }
      const body = buffer.subarray(4, 4 + length).toString("utf8");
      buffer = buffer.subarray(4 + length);
      try {
        events.push(summarizeMessage(JSON.parse(body)));
      } catch (error) {
        events.push({ parse_error: String(error), raw_length: body.length });
      }
      if (events.length >= args.maxEvents) {
        finish(true);
        return;
      }
    }
  });

  client.on("error", (error) => finish(false, error.message));
  client.on("close", () => finish(events.length > 0));
}

function parseArgs(argv) {
  const result = {
    pipe: DEFAULT_WINDOWS_PIPE,
    duration: 8,
    maxEvents: 20,
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
    } else if (arg === "--help" || arg === "-h") {
      printHelp();
      process.exit(0);
    }
  }
  return result;
}

function printHelp() {
  console.log(`Usage: node test_process/vscode_codex_ipc_probe.mjs [options]

Options:
  --duration SECONDS   Maximum seconds to listen, default 8
  --max-events COUNT   Maximum events to print, default 20
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

function summarizeMessage(message) {
  const summary = {
    type: message?.type,
    method: message?.method,
    result_type: message?.resultType,
  };
  if (message?.params && typeof message.params === "object") {
    summary.param_keys = Object.keys(message.params).sort();
    summary.conversation_id = message.params.conversationId;
    summary.host_id = message.params.hostId;
    if (message.params.change && typeof message.params.change === "object") {
      summary.change = summarizeChange(message.params.change);
    }
  }
  if (message?.result && typeof message.result === "object") {
    summary.result_keys = Object.keys(message.result).sort();
  }
  return redactPaths(summary);
}

function summarizeChange(change) {
  const summary = {
    type: change.type,
    revision: change.revision,
    base_revision: change.baseRevision,
  };
  if (Array.isArray(change.patches)) {
    summary.patch_count = change.patches.length;
    summary.patch_paths = change.patches
      .slice(0, 5)
      .map((patch) => patchPath(patch))
      .filter(Boolean);
  }
  if (change.conversationState && typeof change.conversationState === "object") {
    summary.conversation_state = summarizeConversationState(change.conversationState);
  }
  return summary;
}

function summarizeConversationState(state) {
  const turns = Array.isArray(state.turns) ? state.turns : [];
  const lastTurn = turns.length > 0 ? turns[turns.length - 1] : null;
  const summary = {
    id: state.id,
    session_id: state.sessionId,
    host_id: state.hostId,
    turn_count: turns.length,
  };
  if (lastTurn && typeof lastTurn === "object") {
    summary.last_turn = summarizeTurn(lastTurn);
  }
  return summary;
}

function summarizeTurn(turn) {
  const params = turn.params && typeof turn.params === "object" ? turn.params : {};
  return {
    keys: Object.keys(turn).sort(),
    status: turn.status,
    state: turn.state,
    kind: turn.kind,
    thread_id: params.threadId,
    item_count: Array.isArray(turn.items) ? turn.items.length : null,
    hook_run_count: Array.isArray(turn.hookRuns) ? turn.hookRuns.length : null,
  };
}

function patchPath(patch) {
  if (!patch || !Array.isArray(patch.path)) {
    return "";
  }
  return `/${patch.path.slice(0, 6).map(String).join("/")}`;
}

function redactPaths(value) {
  if (Array.isArray(value)) {
    return value.map((item) => redactPaths(item));
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, redactPaths(item)]));
  }
  if (typeof value === "string") {
    const home = os.homedir();
    return value.replaceAll(home, "%USERPROFILE%");
  }
  return value;
}

main();
