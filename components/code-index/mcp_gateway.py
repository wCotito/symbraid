from __future__ import annotations

from typing import Optional

from mcp.server.fastmcp import FastMCP
from code_index.service import CodeIndexService


mcp = FastMCP(
    "code-index-search",
    instructions=(
        "Read-only semantic code discovery. Verify indexed candidates with exact search, "
        "AST/symbol search, and the current source file before edits."
    ),
)


@mcp.tool()
def semantic_search(query: str, project_path: str, top_k: int = 10, path_filter: Optional[str] = None) -> dict:
    """Search the active semantic index source for a registered project."""
    return CodeIndexService().search(query, project_path, top_k, path_filter)


@mcp.tool()
def index_status(project_path: str) -> dict:
    """Return active source, backend, ownership, completeness, and index metadata."""
    return CodeIndexService().status(project_path)


@mcp.tool()
def list_index_sources(project_path: str) -> dict:
    """List configured sources and the active source without modifying them."""
    return CodeIndexService().list_sources(project_path)


def run_mcp() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run_mcp()
