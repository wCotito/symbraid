from __future__ import annotations

import argparse
import hmac
import ipaddress
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from .registry import normalize_project_path
from .redaction import error_payload, write_json
from .secrets import env_reference, get_secret
from .service import SymbraidService


INSTRUCTIONS = (
    "Read-only semantic code discovery. Verify indexed candidates with exact search, "
    "AST/symbol search, and the current source file before edits."
)


def _loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _resolve_project(bound_project: str | None, requested: str | None) -> str:
    if bound_project:
        if requested and normalize_project_path(requested) != normalize_project_path(bound_project):
            raise PermissionError("This MCP server is bound to a different project")
        return str(Path(bound_project).expanduser().resolve())
    if not requested:
        raise ValueError("project_path is required when the MCP server is not project-bound")
    return str(Path(requested).expanduser().resolve())


def build_server(
    bound_project: str | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> FastMCP:
    allowed_hosts = [f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"]
    allowed_origins = [f"http://127.0.0.1:{port}", f"http://localhost:{port}", f"http://[::1]:{port}"]
    server = FastMCP(
        "symbraid-search",
        instructions=INSTRUCTIONS,
        host=host,
        port=port,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts,
            allowed_origins=allowed_origins,
        ),
    )

    @server.tool()
    def semantic_search(
        query: str,
        project_path: Optional[str] = None,
        top_k: int = 10,
        path_filter: Optional[str] = None,
    ) -> dict:
        """Search the active semantic index source for a registered project."""
        project = _resolve_project(bound_project, project_path)
        return SymbraidService().search(query, project, top_k, path_filter)

    @server.tool()
    def index_status(project_path: Optional[str] = None) -> dict:
        """Return the active managed source, backend, completeness, and index metadata."""
        return SymbraidService().status(_resolve_project(bound_project, project_path))

    @server.tool()
    def list_index_sources(project_path: Optional[str] = None) -> dict:
        """List configured sources and the active source without modifying them."""
        return SymbraidService().list_sources(_resolve_project(bound_project, project_path))

    return server


class _HttpSecurity:
    def __init__(self, app: Any, token: str, port: int):
        self.app = app
        self.token = token.encode("utf-8")
        self.hosts = {
            f"127.0.0.1:{port}",
            f"localhost:{port}",
            f"[::1]:{port}",
        }
        self.origins = {
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
            f"http://[::1]:{port}",
        }

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        host = headers.get(b"host", b"").decode("latin-1")
        origin = headers.get(b"origin", b"").decode("latin-1")
        authorization = headers.get(b"authorization", b"")
        expected = b"Bearer " + self.token
        if host not in self.hosts or (origin and origin not in self.origins):
            await self._reject(send, 403, "request origin is not allowed")
            return
        if not hmac.compare_digest(authorization, expected):
            await self._reject(send, 401, "bearer authentication required")
            return
        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(send, status: int, message: str) -> None:
        body = json.dumps({"error": message}).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        })
        await send({"type": "http.response.body", "body": body})


def run_mcp(
    transport: str = "stdio",
    project: str | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    token_env: str | None = None,
) -> None:
    if transport == "stdio":
        build_server(project).run(transport="stdio")
        return
    if transport != "streamable-http":
        raise ValueError(f"Unsupported MCP transport: {transport}")
    if not project:
        raise ValueError("--project is required for streamable-http")
    if not _loopback(host) or host not in {"127.0.0.1", "::1"}:
        raise ValueError("Streamable HTTP may bind only to 127.0.0.1 or ::1")
    reference = token_env or os.environ.get("SYMBRAID_MCP_TOKEN_ENV", "")
    if reference.startswith("env:"):
        reference = reference[4:]
    if not reference:
        raise ValueError("--token-env or SYMBRAID_MCP_TOKEN_ENV is required")
    token = get_secret(env_reference(reference))
    if not token:
        raise ValueError("The configured MCP bearer token environment variable is empty")
    import uvicorn

    server = build_server(project, host=host, port=port)
    uvicorn.run(_HttpSecurity(server.streamable_http_app(), token, port), host=host, port=port)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="symbraid-mcp")
    parser.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    parser.add_argument("--project")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--token-env")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        run_mcp(args.transport, args.project, args.host, args.port, args.token_env)
        return 0
    except Exception as exc:
        write_json(error_payload(exc), stream=sys.stderr)
        return 1


mcp = build_server()


if __name__ == "__main__":
    raise SystemExit(main())
