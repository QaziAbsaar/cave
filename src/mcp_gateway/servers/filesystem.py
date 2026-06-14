"""Filesystem MCP Server — read/write files in a sandboxed workspace.

Run as a stdio MCP server:
    python -m src.mcp_gateway.servers.filesystem

Tools:
    - read_file(path)        → file contents as text
    - write_file(path, content) → confirm write
    - list_directory(path)   → list of filenames
    - file_exists(path)      → boolean
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent

# ── Sandbox root — all file operations are bounded to this directory ────────

SANDBOX_ROOT: Path = Path(
    os.getenv("MCP_FILESYSTEM_ROOT", "/tmp/cave-sandbox")
).resolve()

server = Server("cave-filesystem")


# ── Helpers ─────────────────────────────────────────────────────────────────


def _resolve(path_str: str) -> Path:
    """Resolve a path relative to SANDBOX_ROOT and validate it stays inside."""
    given = Path(path_str)
    if given.is_absolute():
        resolved = given.resolve()
    else:
        resolved = (SANDBOX_ROOT / given).resolve()

    if not str(resolved).startswith(str(SANDBOX_ROOT)):
        raise ValueError(
            f"Path '{path_str}' resolves outside sandbox root '{SANDBOX_ROOT}'"
        )
    return resolved


def _ensure_sandbox() -> None:
    """Create the sandbox root directory if it doesn't exist."""
    SANDBOX_ROOT.mkdir(parents=True, exist_ok=True)


# ── Tool implementations ───────────────────────────────────────────────────


@server.tool("read_file")
async def read_file(path: str) -> list[TextContent]:
    """Read the contents of a file in the sandbox.

    Args:
        path: Relative or absolute path within the sandbox.
    """
    _ensure_sandbox()
    resolved = _resolve(path)
    if not resolved.is_file():
        raise FileNotFoundError(f"File not found: {resolved}")
    content = resolved.read_text(encoding="utf-8")
    return [TextContent(type="text", text=content)]


@server.tool("write_file")
async def write_file(path: str, content: str) -> list[TextContent]:
    """Write content to a file in the sandbox (creates parent dirs).

    Args:
        path: Relative or absolute path within the sandbox.
        content: Text content to write.
    """
    _ensure_sandbox()
    resolved = _resolve(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")
    return [TextContent(type="text", text=f"OK: wrote {len(content)} bytes to {resolved}")]


@server.tool("list_directory")
async def list_directory(path: str = ".") -> list[TextContent]:
    """List files and directories in a sandbox path.

    Args:
        path: Directory path within the sandbox (default: root).
    """
    _ensure_sandbox()
    resolved = _resolve(path)
    if not resolved.is_dir():
        raise NotADirectoryError(f"Not a directory: {resolved}")

    entries = []
    for entry in sorted(resolved.iterdir()):
        suffix = "/" if entry.is_dir() else ""
        entries.append(f"{entry.name}{suffix}")

    return [TextContent(type="text", text="\n".join(entries))]


@server.tool("file_exists")
async def file_exists(path: str) -> list[TextContent]:
    """Check whether a file exists in the sandbox.

    Args:
        path: File path within the sandbox.
    """
    _ensure_sandbox()
    resolved = _resolve(path)
    return [TextContent(type="text", text=str(resolved.exists() or resolved.is_dir()).lower())]


# ── Entry point ─────────────────────────────────────────────────────────────


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import anyio
    anyio.run(main)
