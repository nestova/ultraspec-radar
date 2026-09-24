"""Minimal MCP (Model Context Protocol) client over the Streamable HTTP transport.

Implemented with httpx to avoid pulling the official ``mcp`` package, whose
starlette dependency conflicts with FastAPI's pinned version.  Only the two
JSON-RPC methods the app needs are supported: ``initialize`` and ``tools/call``.
"""

from __future__ import annotations

import json
import logging

import httpx

logger = logging.getLogger(__name__)

_PROTOCOL_VERSION = "2024-11-05"
_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def _parse_sse(text: str) -> dict | None:
    """Extract the first ``event: message`` JSON payload from an SSE stream."""
    for block in text.split("event: message"):
        block = block.strip()
        if not block:
            continue
        for line in block.splitlines():
            if line.startswith("data: "):
                try:
                    return json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
    return None


class MCPClient:
    """Stateless MCP client — the Tracerfy server carries auth in the URL, not a session."""

    def __init__(self, server_url: str, timeout: float = 60.0) -> None:
        self._url = server_url
        self._timeout = timeout
        self._id = 0
        self._initialized = False

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _post(self, message: dict) -> dict | None:
        with httpx.Client(timeout=self._timeout) as client:
            r = client.post(self._url, json=message, headers=_HEADERS)
            r.raise_for_status()
            if "text/event-stream" in r.headers.get("content-type", ""):
                return _parse_sse(r.text)
            try:
                return r.json()
            except json.JSONDecodeError:
                return None

    def initialize(self) -> None:
        if self._initialized:
            return
        msg = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": _PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "ultraspec-radar", "version": "0.1.0"},
                },
            }
        )
        if msg and msg.get("error"):
            raise RuntimeError(f"MCP initialize failed: {msg['error']}")
        # Fire-and-forget initialized notification
        with httpx.Client(timeout=self._timeout) as client:
            client.post(
                self._url,
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                headers=_HEADERS,
            )
        self._initialized = True
        logger.info("MCP session initialized with %s", self._url)

    def call_tool(self, name: str, arguments: dict | None = None) -> object:
        """Call an MCP tool and return its parsed result (JSON object or plain text)."""
        self.initialize()
        msg = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments or {}},
            }
        )
        if not msg:
            raise RuntimeError(f"MCP tool '{name}' returned no response")
        if msg.get("error"):
            raise RuntimeError(f"MCP tool '{name}' error: {msg['error'].get('message', msg['error'])}")
        result = msg.get("result", {})
        if result.get("isError"):
            content = result.get("content", [])
            text = next((c.get("text", "") for c in content if c.get("type") == "text"), "")
            if not text:
                text = f"unknown error (result={json.dumps(result)})"
            raise RuntimeError(f"MCP tool '{name}' returned an error: {text}")
        content = result.get("content", [])
        for item in content:
            if item.get("type") == "text":
                text = item["text"]
                try:
                    return json.loads(text)
                except (json.JSONDecodeError, TypeError):
                    return text
        return result
