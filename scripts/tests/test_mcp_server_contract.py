"""Contract tests for the token-reduce MCP server (mcp/server.mjs).

Historically the server had no automated coverage. The `anthropic_cache_plan`
tool shipped an invalid JSON Schema (a property with no ``type``; ``array``
properties with no ``items``), which strict MCP clients can reject on load --
the plausible reason the plugin's ``mcpServers`` registration was disabled by
an unattributed local edit. These tests pin the two things that matter:

1. The server completes the JSON-RPC handshake and lists its tools, and every
   tool's ``inputSchema`` is well-formed (every property has a ``type``; every
   ``array`` property declares ``items``).
2. ``.claude-plugin/plugin.json`` still registers the server -- so an accidental
   (or drive-by) removal of the integration fails CI instead of silently
   shipping.

Skipped automatically where ``node`` is unavailable so the Python suite stays
runnable without a JS toolchain.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER = REPO_ROOT / "mcp" / "server.mjs"
PLUGIN_JSON = REPO_ROOT / ".claude-plugin" / "plugin.json"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not available"
)


def _frame(obj: dict) -> bytes:
    body = json.dumps(obj).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8") + body


def _parse_frames(raw: bytes) -> list[dict]:
    messages: list[dict] = []
    while True:
        sep = raw.find(b"\r\n\r\n")
        if sep == -1:
            break
        header = raw[:sep].decode("utf-8", "replace")
        marker = "Content-Length:"
        idx = header.lower().find(marker.lower())
        if idx == -1:
            break
        length = int(header[idx + len(marker):].split()[0])
        start = sep + 4
        end = start + length
        if len(raw) < end:
            break
        messages.append(json.loads(raw[start:end].decode("utf-8")))
        raw = raw[end:]
    return messages


def _handshake() -> list[dict]:
    stdin = b"".join(
        (
            _frame({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {}}}),
            _frame({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
        )
    )
    proc = subprocess.run(
        ["node", str(SERVER)],
        input=stdin,
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=30,
    )
    return _parse_frames(proc.stdout)


def test_initialize_advertises_tools_capability() -> None:
    messages = _handshake()
    init = next((m for m in messages if m.get("id") == 1), None)
    assert init is not None, f"no initialize response; got {messages!r}"
    result = init["result"]
    assert result["protocolVersion"] == "2024-11-05"
    # listChanged must be present and False (the server never emits list-changed).
    assert result["capabilities"]["tools"] == {"listChanged": False}
    assert result["serverInfo"]["name"] == "token-reduce-mcp"


def test_every_tool_inputschema_is_wellformed() -> None:
    messages = _handshake()
    listing = next((m for m in messages if m.get("id") == 2), None)
    assert listing is not None, f"no tools/list response; got {messages!r}"
    tools = listing["result"]["tools"]
    assert tools, "server advertised zero tools"

    problems: list[str] = []
    for tool in tools:
        schema = tool.get("inputSchema", {})
        for prop_name, prop in (schema.get("properties") or {}).items():
            if "type" not in prop:
                problems.append(f"{tool['name']}.{prop_name}: missing 'type'")
            if prop.get("type") == "array" and "items" not in prop:
                problems.append(f"{tool['name']}.{prop_name}: array missing 'items'")
    assert not problems, "malformed tool schemas: " + "; ".join(problems)


def test_plugin_json_still_registers_the_mcp_server() -> None:
    """Guards the deliberate decision to keep the MCP server registered.

    An unattributed local edit removed this block; investigation found the server
    works and is documented/maintained, so the registration stays. If a future
    change intends to remove it, that intent should update this test explicitly.
    """
    plugin = json.loads(PLUGIN_JSON.read_text())
    servers = plugin.get("mcpServers", {})
    assert "token-reduce-mcp" in servers, (
        "plugin.json must register the token-reduce-mcp server"
    )
    assert servers["token-reduce-mcp"]["args"] == ["mcp/server.mjs"]
