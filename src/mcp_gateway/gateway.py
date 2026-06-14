"""MCPGateway — manages MCP server subprocesses and routes tool calls for agents.

Architecture:
    MCPGateway owns a pool of MCP server subprocesses (one per registered server),
    each communicating via stdio transport. Agents call tools through the gateway
    without needing to manage server lifecycle directly.

    ┌────────────────────────────────────────────┐
    │              MCPGateway                     │
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
    │  │ filesystem│  │ supabase │  │   sast   │  │
    │  │ (stdio)   │  │ (stdio)  │  │ (stdio)  │  │
    │  └──────────┘  └──────────┘  └──────────┘  │
    └────────────────────────────────────────────┘
              ▲                    ▲
              │    call_tool()     │
              └──────────┬─────────┘
                      Agent
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, TextContent

from src.mcp_gateway.registry import MCPServerConfig, ToolRegistry

logger = logging.getLogger(__name__)

# How long to wait for a server process to shut down gracefully
_SHUTDOWN_TIMEOUT: int = int(os.getenv("MCP_SHUTDOWN_TIMEOUT", "10"))


class MCPGatewayError(Exception):
    """Raised when an MCP tool call or server operation fails."""


class MCPGateway:
    """Lifecycle manager for MCP server connections.

    Usage:
        registry = ToolRegistry()
        async with MCPGateway(registry) as gateway:
            result = await gateway.call_tool("write_file", {
                "path": "/tmp/hello.txt",
                "content": "Hello, world!",
            })
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry
        self._sessions: Dict[str, ClientSession] = {}
        self._exit_stack = AsyncExitStack()
        self._server_params: Dict[str, StdioServerParameters] = {}
        self._read_streams: Dict[str, Any] = {}
        self._write_streams: Dict[str, Any] = {}
        self._initialized = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def __aenter__(self) -> MCPGateway:
        await self.start_all()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.shutdown()

    async def start_all(self) -> None:
        """Start all registered MCP servers and establish sessions."""
        if self._initialized:
            logger.warning("MCPGateway already initialized — skipping start_all")
            return

        for name in self.registry.list_servers():
            await self._start_server(name)

        self._initialized = True
        logger.info(
            "MCPGateway initialized with %d server(s): %s",
            len(self._sessions),
            ", ".join(self._sessions.keys()),
        )

    async def _start_server(self, name: str) -> None:
        """Start a single MCP server and establish a client session."""
        cfg: MCPServerConfig = self.registry.get_server(name)
        logger.info("Starting MCP server '%s': %s %s", name, cfg.command, " ".join(cfg.args))

        params = StdioServerParameters(
            command=cfg.command,
            args=list(cfg.args),
            env={**os.environ, **cfg.env} if cfg.env else None,
        )
        self._server_params[name] = params

        try:
            # stdio_client returns (read_stream, write_stream) as an async context
            streams = await self._exit_stack.enter_async_context(
                stdio_client(params)
            )
            read_stream, write_stream = streams
            self._read_streams[name] = read_stream
            self._write_streams[name] = write_stream

            session = await self._exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await session.initialize()
            self._sessions[name] = session

            logger.info("MCP server '%s' initialized successfully", name)

        except Exception as exc:
            logger.error("Failed to start MCP server '%s': %s", name, exc)
            raise MCPGatewayError(f"Failed to start MCP server '{name}': {exc}") from exc

    async def shutdown(self) -> None:
        """Shut down all MCP server connections gracefully."""
        logger.info("Shutting down MCPGateway (%d active server(s))", len(self._sessions))
        self._initialized = False
        try:
            await asyncio.wait_for(
                self._exit_stack.aclose(),
                timeout=_SHUTDOWN_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning("MCPGateway shutdown timed out after %ds", _SHUTDOWN_TIMEOUT)
        self._sessions.clear()
        self._read_streams.clear()
        self._write_streams.clear()
        logger.info("MCPGateway shut down complete")

    async def restart_server(self, name: str) -> None:
        """Restart a single MCP server (e.g. after a crash or config change)."""
        if name in self._sessions:
            # Close existing session and streams by removing from exit stack
            session = self._sessions.pop(name)
            await session.__aexit__(None, None, None)
            # The exit_stack handles clean-up; we just re-create
        await self._start_server(name)

    # ------------------------------------------------------------------
    # Tool calling
    # ------------------------------------------------------------------

    async def call_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        server_name: Optional[str] = None,
    ) -> Any:
        """Call a tool on the appropriate MCP server.

        Args:
            tool_name: Name of the tool to invoke (e.g. "write_file", "execute_sql").
            arguments: Dict of arguments passed to the tool.
            server_name: Optional override — if omitted, resolved via registry.

        Returns:
            Tool result content. For TextContent results, returns concatenated text.
            For structured results, returns the raw CallToolResult.

        Raises:
            MCPGatewayError: If the server or tool is unavailable, or the call fails.
        """
        if not self._initialized:
            raise MCPGatewayError(
                "MCPGateway not initialized — call start_all() or use async context manager"
            )

        if server_name is None:
            server_name = self.registry.get_server_for_tool(tool_name)

        session = self._sessions.get(server_name)
        if session is None:
            raise MCPGatewayError(
                f"MCP server '{server_name}' is not running — call start_server('{server_name}') first"
            )

        args = arguments or {}

        try:
            result: CallToolResult = await session.call_tool(tool_name, args)
        except Exception as exc:
            logger.exception(
                "MCP tool call failed: %s on server '%s' with args=%s",
                tool_name,
                server_name,
                args,
            )
            raise MCPGatewayError(
                f"MCP tool '{tool_name}' on server '{server_name}' failed: {exc}"
            ) from exc

        if result.isError:
            error_detail = _extract_text(result)
            raise MCPGatewayError(
                f"MCP tool '{tool_name}' on server '{server_name}' returned error: {error_detail}"
            )

        return result

    async def call_tool_text(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        server_name: Optional[str] = None,
    ) -> str:
        """Convenience wrapper around call_tool that returns concatenated text content."""
        result = await self.call_tool(tool_name, arguments, server_name)
        return _extract_text(result)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def is_running(self, server_name: str) -> bool:
        """Check if a specific server session is active."""
        return server_name in self._sessions

    @property
    def active_servers(self) -> List[str]:
        """List of currently connected MCP server names."""
        return list(self._sessions.keys())

    @property
    def is_initialized(self) -> bool:
        return self._initialized


# ── Helpers ─────────────────────────────────────────────────────────────────


def _extract_text(result: CallToolResult) -> str:
    """Extract plain text from a CallToolResult's TextContent items."""
    parts: List[str] = []
    for item in result.content:
        if isinstance(item, TextContent):
            parts.append(item.text)
    return "\n".join(parts)
