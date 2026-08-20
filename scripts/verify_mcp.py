"""Perform a real stdio handshake with the installed read-only MCP gateway."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


EXPECTED_TOOLS = {"semantic_search", "index_status", "list_index_sources"}


async def verify() -> None:
    launcher = Path(os.environ["LOCALAPPDATA"]) / "CodeIndex" / "bin" / "code-index-mcp.cmd"
    if not launcher.is_file():
        raise SystemExit(f"MCP launcher not found: {launcher}")

    parameters = StdioServerParameters(command="cmd.exe", args=["/d", "/s", "/c", str(launcher)])
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = {tool.name for tool in (await session.list_tools()).tools}

    if tools != EXPECTED_TOOLS:
        raise SystemExit(
            "Unexpected MCP tools: "
            + json.dumps({"expected": sorted(EXPECTED_TOOLS), "actual": sorted(tools)})
        )
    print(json.dumps({"status": "ok", "tools": sorted(tools)}))


if __name__ == "__main__":
    asyncio.run(verify())
