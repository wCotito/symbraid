"""Perform a real stdio or loopback Streamable HTTP MCP handshake."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import socket
import subprocess
import urllib.error
import urllib.request
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


EXPECTED_TOOLS = {"semantic_search", "index_status", "list_index_sources"}


def _command() -> str:
    command = os.environ.get("SYMBRAID_COMMAND", "symbraid").strip()
    if not command:
        raise SystemExit("SYMBRAID_COMMAND must name the Symbraid executable")
    return command


async def verify_stdio() -> None:
    command = _command()
    parameters = StdioServerParameters(command=command, args=["mcp", "--transport", "stdio"])
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = {tool.name for tool in (await session.list_tools()).tools}
    if tools != EXPECTED_TOOLS:
        raise SystemExit(
            "Unexpected MCP tools: "
            + json.dumps({"expected": sorted(EXPECTED_TOOLS), "actual": sorted(tools)})
        )
    print(json.dumps({"status": "ok", "transport": "stdio", "command": command, "tools": sorted(tools)}))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _http_post(
    endpoint: str,
    payload: dict[str, Any],
    token: str | None = None,
    session_id: str | None = None,
) -> tuple[int, dict[str, str], str]:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, dict(response.headers.items()), response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers.items()), error.read().decode("utf-8", "replace")


def _payload(body: str) -> dict[str, Any]:
    stripped = body.strip()
    if stripped.startswith("{"):
        return json.loads(stripped)
    for line in stripped.splitlines():
        if line.startswith("data:"):
            candidate = line[5:].strip()
            if candidate:
                return json.loads(candidate)
    raise ValueError(f"MCP response did not contain a JSON payload: {body[:200]}")


def _header(headers: dict[str, str], name: str) -> str | None:
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return None


def _http_initialize(endpoint: str, token: str) -> tuple[str | None, set[str]]:
    status, headers, body = _http_post(
        endpoint,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "symbraid-verify", "version": "1"},
            },
        },
        token,
    )
    if not 200 <= status < 300:
        raise RuntimeError(f"initialize returned HTTP {status}: {body[:200]}")
    session_id = _header(headers, "Mcp-Session-Id")
    status, _, body = _http_post(
        endpoint,
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        token,
        session_id,
    )
    if status not in (200, 202, 204):
        raise RuntimeError(f"initialized notification returned HTTP {status}: {body[:200]}")
    status, _, body = _http_post(
        endpoint,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        token,
        session_id,
    )
    if not 200 <= status < 300:
        raise RuntimeError(f"tools/list returned HTTP {status}: {body[:200]}")
    result = _payload(body).get("result", {})
    return session_id, {str(tool.get("name")) for tool in result.get("tools", [])}


async def verify_http() -> None:
    command = _command()
    port = _free_port()
    token_name = "SYMBRAID_VERIFY_MCP_TOKEN"
    token = secrets.token_hex(32)
    endpoint = f"http://127.0.0.1:{port}/mcp"
    environment = os.environ.copy()
    environment[token_name] = token
    process = await asyncio.create_subprocess_exec(
        command,
        "mcp",
        "--transport",
        "streamable-http",
        "--allow-all-projects",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--auth-token-env",
        token_name,
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        deadline = asyncio.get_running_loop().time() + 20
        unauthorized = False
        last_error: Exception | None = None
        while asyncio.get_running_loop().time() < deadline:
            try:
                status, _, _ = await asyncio.to_thread(
                    _http_post,
                    endpoint,
                    {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}},
                    None,
                )
                unauthorized = status == 401
                if not unauthorized:
                    raise RuntimeError(f"unauthenticated request returned HTTP {status}, expected 401")
                _session, tools = await asyncio.to_thread(_http_initialize, endpoint, token)
                if tools != EXPECTED_TOOLS:
                    raise RuntimeError(
                        "Unexpected HTTP MCP tools: "
                        + json.dumps({"expected": sorted(EXPECTED_TOOLS), "actual": sorted(tools)})
                    )
                print(json.dumps({"status": "ok", "transport": "streamable-http", "command": command, "tools": sorted(tools)}))
                return
            except Exception as error:
                last_error = error
                await asyncio.sleep(0.25)
        raise RuntimeError(f"HTTP MCP verification timed out: {last_error}")
    finally:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        await process.communicate()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    args = parser.parse_args()
    if args.transport == "streamable-http":
        asyncio.run(verify_http())
    else:
        asyncio.run(verify_stdio())


if __name__ == "__main__":
    main()
