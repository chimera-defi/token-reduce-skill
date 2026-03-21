#!/usr/bin/env node

import fs from "node:fs";
import process from "node:process";

function approxTokens(value) {
  if (value == null) return 0;
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return Math.ceil(text.length / 4);
}

function clone(value) {
  return value == null ? value : JSON.parse(JSON.stringify(value));
}

function normalizeSystem(system) {
  if (!system) return [];
  if (typeof system === "string") return [{ type: "text", text: system }];
  if (Array.isArray(system)) return clone(system);
  return [clone(system)];
}

function normalizeContent(content) {
  if (typeof content === "string") return [{ type: "text", text: content }];
  if (Array.isArray(content)) return clone(content);
  if (content && typeof content === "object") return [clone(content)];
  return [];
}

function addCacheControlToLastTextBlock(blocks) {
  for (let i = blocks.length - 1; i >= 0; i -= 1) {
    if (blocks[i]?.type === "text") {
      blocks[i] = { ...blocks[i], cache_control: { type: "ephemeral" } };
      return true;
    }
  }
  return false;
}

function estimateSavings(cacheableTokens, repeatedCalls) {
  if (cacheableTokens <= 0 || repeatedCalls <= 1) {
    return { repeatedCalls, writeCostUnits: 0, readCostUnits: 0, savedVsNormalUnits: 0 };
  }

  const writeCostUnits = cacheableTokens * 1.25;
  const readCostUnits = cacheableTokens * 0.1 * (repeatedCalls - 1);
  const normalCostUnits = cacheableTokens * repeatedCalls;
  const cachedCostUnits = writeCostUnits + readCostUnits;

  return {
    repeatedCalls,
    writeCostUnits,
    readCostUnits,
    savedVsNormalUnits: Math.max(0, normalCostUnits - cachedCostUnits),
  };
}

function planAnthropicCaching(payload) {
  const minTokensToCache = Number(payload.minTokensToCache ?? 1024);
  const repeatedCalls = Number(payload.repeatedCalls ?? 3);
  const cacheSystemPrompt = payload.cacheSystemPrompt !== false;
  const cacheToolDefinitions = payload.cacheToolDefinitions !== false;
  const cacheLargeUserMessages = payload.cacheLargeUserMessages !== false;

  const optimizedSystem = normalizeSystem(payload.system);
  const optimizedTools = Array.isArray(payload.tools) ? clone(payload.tools) : [];
  const optimizedMessages = Array.isArray(payload.messages) ? clone(payload.messages) : [];
  const analysis = [];
  let breakpointsAdded = 0;
  let stablePrefixTokens = 0;
  let totalCacheableTokens = 0;

  if (optimizedSystem.length > 0) {
    const systemTokens = approxTokens(optimizedSystem);
    stablePrefixTokens += systemTokens;
    const canCache = cacheSystemPrompt && stablePrefixTokens >= minTokensToCache;
    analysis.push({
      name: "system",
      approxTokens: systemTokens,
      cacheable: canCache,
      reason: canCache ? "Stable prefix exceeds cache threshold." : "Below threshold or system caching disabled.",
    });
    if (canCache && addCacheControlToLastTextBlock(optimizedSystem)) {
      breakpointsAdded += 1;
      totalCacheableTokens += stablePrefixTokens;
    }
  }

  if (optimizedTools.length > 0) {
    const toolTokens = approxTokens(optimizedTools);
    stablePrefixTokens += toolTokens;
    const canCache = cacheToolDefinitions && stablePrefixTokens >= minTokensToCache;
    analysis.push({
      name: "tools",
      approxTokens: toolTokens,
      cacheable: canCache,
      reason: canCache ? "System + tools form a cacheable stable prefix." : "Below threshold or tool caching disabled.",
    });
    if (canCache) {
      optimizedTools[optimizedTools.length - 1] = {
        ...optimizedTools[optimizedTools.length - 1],
        cache_control: { type: "ephemeral" },
      };
      breakpointsAdded += 1;
      totalCacheableTokens += stablePrefixTokens;
    }
  }

  optimizedMessages.forEach((message, index) => {
    const blocks = normalizeContent(message?.content);
    const blockTokens = approxTokens(blocks);
    const cacheable = cacheLargeUserMessages && message?.role === "user" && blockTokens >= minTokensToCache;
    analysis.push({
      name: `message:${index}:${message?.role ?? "unknown"}`,
      approxTokens: blockTokens,
      cacheable,
      reason: cacheable ? "Large user payload is independently cacheable." : "Not a large user payload or below threshold.",
    });
    if (cacheable && addCacheControlToLastTextBlock(blocks)) {
      optimizedMessages[index] = { ...message, content: blocks };
      breakpointsAdded += 1;
      totalCacheableTokens += blockTokens;
    } else if (typeof message?.content === "string") {
      optimizedMessages[index] = { ...message, content: blocks };
    }
  });

  return {
    optimizedSystem,
    optimizedTools,
    optimizedMessages,
    analysis,
    breakpointsAdded,
    minTokensToCache,
    estimatedSavings: estimateSavings(totalCacheableTokens, repeatedCalls),
    disclaimer:
      "Anthropic-only helper. This annotates your own Anthropic API payloads with cache_control and does not affect Codex or Claude Code's built-in session caching.",
  };
}

function readInput() {
  const inputArg = process.argv.find((arg) => arg.startsWith("--input="));
  if (inputArg) return fs.readFileSync(inputArg.slice("--input=".length), "utf8");
  if (!process.stdin.isTTY) return fs.readFileSync(0, "utf8");
  throw new Error("Pass --input=payload.json or pipe JSON via stdin.");
}

const payload = JSON.parse(readInput());
process.stdout.write(JSON.stringify(planAnthropicCaching(payload), null, 2) + "\n");
