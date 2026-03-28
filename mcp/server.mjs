#!/usr/bin/env node

import { spawn } from "node:child_process";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import path from "node:path";
import process from "node:process";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SERVER = {
  name: "token-reduce-mcp",
  version: "0.1.0",
};

const TOOLS = [
  {
    name: "token_reduce_paths",
    description: "Return the smallest useful candidate path list for a repo query.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Words describing the target context." },
      },
      required: ["query"],
      additionalProperties: false,
    },
  },
  {
    name: "token_reduce_snippet",
    description: "Return a path-first result plus one ranked excerpt when needed.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Words describing the target context." },
      },
      required: ["query"],
      additionalProperties: false,
    },
  },
  {
    name: "token_reduce_benchmark",
    description: "Run the local token-reduction benchmark and return the summary table.",
    inputSchema: {
      type: "object",
      properties: {},
      additionalProperties: false,
    },
  },
  {
    name: "token_reduce_measure",
    description: "Measure recent token-reduce adoption and write fresh repo-local artifacts.",
    inputSchema: {
      type: "object",
      properties: {},
      additionalProperties: false,
    },
  },
  {
    name: "token_reduce_self_review",
    description: "Generate a telemetry-driven self-review with prioritized next improvements.",
    inputSchema: {
      type: "object",
      properties: {},
      additionalProperties: false,
    },
  },
  {
    name: "token_reduce_install_info",
    description: "Return plugin and MCP install instructions for this repo.",
    inputSchema: {
      type: "object",
      properties: {},
      additionalProperties: false,
    },
  },
  {
    name: "token_reduce_setup",
    description: "Run the one-command full setup: installs QMD (BM25 search) and RTK (output compression), wires both hook layers into Claude Code globally, and indexes the repo. Safe to re-run.",
    inputSchema: {
      type: "object",
      properties: {},
      additionalProperties: false,
    },
  },
  {
    name: "anthropic_cache_plan",
    description: "Annotate Anthropic API payloads with cache_control and estimate repeated-call savings.",
    inputSchema: {
      type: "object",
      properties: {
        system: {
          description: "Anthropic system prompt content.",
        },
        tools: {
          type: "array",
          description: "Anthropic tool definition array.",
        },
        messages: {
          type: "array",
          description: "Anthropic messages array.",
        },
        minTokensToCache: {
          type: "number",
          description: "Approximate threshold for cacheable content. Default 1024.",
        },
        repeatedCalls: {
          type: "number",
          description: "How many repeated calls to estimate. Default 3.",
        },
      },
      required: ["messages"],
      additionalProperties: true,
    },
  },
];

let buffer = Buffer.alloc(0);

process.stdin.on("data", (chunk) => {
  buffer = Buffer.concat([buffer, chunk]);
  parseMessages();
});

function parseMessages() {
  while (true) {
    const headerEnd = buffer.indexOf("\r\n\r\n");
    if (headerEnd === -1) return;

    const header = buffer.slice(0, headerEnd).toString("utf8");
    const match = header.match(/Content-Length:\s*(\d+)/i);
    if (!match) {
      buffer = Buffer.alloc(0);
      return;
    }

    const length = Number(match[1]);
    const total = headerEnd + 4 + length;
    if (buffer.length < total) return;

    const body = buffer.slice(headerEnd + 4, total).toString("utf8");
    buffer = buffer.slice(total);

    let message;
    try {
      message = JSON.parse(body);
    } catch {
      continue;
    }

    void handleMessage(message);
  }
}

function send(payload) {
  const body = JSON.stringify(payload);
  process.stdout.write(`Content-Length: ${Buffer.byteLength(body, "utf8")}\r\n\r\n${body}`);
}

function sendResult(id, result) {
  send({ jsonrpc: "2.0", id, result });
}

function sendError(id, code, message) {
  send({ jsonrpc: "2.0", id, error: { code, message } });
}

async function handleMessage(message) {
  if (!message || message.jsonrpc !== "2.0") return;
  if (!message.id && !message.method) return;

  if (message.method === "notifications/initialized") return;

  try {
    switch (message.method) {
      case "initialize":
        sendResult(message.id, {
          protocolVersion: "2024-11-05",
          capabilities: { tools: {} },
          serverInfo: SERVER,
        });
        return;
      case "tools/list":
        sendResult(message.id, { tools: TOOLS });
        return;
      case "tools/call":
        sendResult(message.id, await callTool(message.params ?? {}));
        return;
      default:
        sendError(message.id, -32601, `Method not found: ${message.method}`);
    }
  } catch (error) {
    sendError(message.id, -32000, error instanceof Error ? error.message : String(error));
  }
}

async function callTool(params) {
  const { name, arguments: args = {} } = params;
  switch (name) {
    case "token_reduce_paths":
      return commandResult(await runProcess("./scripts/token-reduce-paths.sh", [String(args.query ?? "")]));
    case "token_reduce_snippet":
      return commandResult(await runProcess("./scripts/token-reduce-snippet.sh", [String(args.query ?? "")]));
    case "token_reduce_benchmark":
      return commandResult(
        await runProcess("uv", ["run", "--with", "tiktoken", "scripts/benchmark-token-reduce.py"])
      );
    case "token_reduce_measure":
      return commandResult(await runProcess("./scripts/baseline-measurement.sh", ["--scope", "repo"]));
    case "token_reduce_self_review":
      return commandResult(await runProcess("uv", ["run", "scripts/review_token_reduction.py", "--scope", "repo"]));
    case "token_reduce_setup":
      return commandResult(await runProcess("./scripts/setup.sh", []));
    case "token_reduce_install_info":
      return {
        content: [
          {
            type: "text",
            text: [
              "Full install (QMD + RTK + hooks):",
              "  git clone https://github.com/chimera-defi/token-reduce-skill tools/token-reduce-skill",
              "  ./tools/token-reduce-skill/scripts/setup.sh",
              "",
              "Claude Code plugin:",
              "  claude plugin marketplace add chimera-defi/token-reduce-skill",
              "  claude plugin install token-reduce@chimera-defi",
              "",
              "Generic MCP:",
              '  { "mcpServers": { "token-reduce-mcp": { "command": "node", "args": ["/absolute/path/to/token-reduce-skill/mcp/server.mjs"] } } }',
            ].join("\n"),
          },
        ],
      };
    case "anthropic_cache_plan":
      return commandResult(
        await runProcess("node", ["scripts/anthropic-cache-plan.mjs"], JSON.stringify(args))
      );
    default:
      return {
        content: [{ type: "text", text: `Unknown tool: ${name}` }],
        isError: true,
      };
  }
}

function commandResult(result) {
  return {
    content: [{ type: "text", text: result.output }],
    isError: result.exitCode !== 0,
  };
}

function runProcess(command, args, stdinText = "") {
  return new Promise((resolve) => {
    const child = spawn(command, args, {
      cwd: ROOT,
      stdio: ["pipe", "pipe", "pipe"],
    });

    if (stdinText) {
      child.stdin.write(stdinText);
    }
    child.stdin.end();

    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("error", (error) => {
      resolve({ exitCode: 1, output: `Failed to start ${command}: ${error.message}` });
    });
    child.on("close", (code) => {
      resolve({
        exitCode: code ?? 1,
        output: [stdout.trim(), stderr.trim()].filter(Boolean).join("\n\n").trim(),
      });
    });
  });
}
