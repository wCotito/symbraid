"""Perform a real stdio handshake with the portable Symbraid MCP command."""

from __future__ import annotations

import asyncio
import json
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


EXPECTED_TOOLS = {"semantic_search", "index_status", "list_index_sources"}


async def verify() -> None:
    command = os.environ.get("SYMBRAID_COMMAND", "symbraid").strip()
    if not command:
        raise SystemExit("SYMBRAID_COMMAND must name the Symbraid executable")

    parameters = StdioServerParameters(
        command=command,
        args=["mcp", "--transport", "stdio"],
    )
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = {tool.name for tool in (await session.list_tools()).tools}

    if tools != EXPECTED_TOOLS:
        raise SystemExit(
            "Unexpected MCP tools: "
            + json.dumps({"expected": sorted(EXPECTED_TOOLS), "actual": sorted(tools)})
        )
    print(json.dumps({"status": "ok", "command": command, "tools": sorted(tools)}))


if __name__ == "__main__":
    asyncio.run(verify())
