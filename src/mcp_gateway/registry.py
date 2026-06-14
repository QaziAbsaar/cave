"""ToolRegistry — maps tool names to MCP servers, and agent names to allowed tool sets."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server process."""

    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    tools: List[str] = field(default_factory=list)
    description: str = ""


# ── Built-in server definitions ─────────────────────────────────────────────

FILESYSTEM_SANDBOX_ROOT: str = os.getenv(
    "MCP_FILESYSTEM_ROOT",
    "/tmp/cave-sandbox",
)

_DEFAULT_SERVERS: Dict[str, MCPServerConfig] = {
    "filesystem": MCPServerConfig(
        name="filesystem",
        command="python",
        args=["-m", "src.mcp_gateway.servers.filesystem"],
        env={"MCP_FILESYSTEM_ROOT": FILESYSTEM_SANDBOX_ROOT},
        tools=["read_file", "write_file", "list_directory", "file_exists"],
        description="Read/write files in the sandbox workspace",
    ),
    "supabase": MCPServerConfig(
        name="supabase",
        command="python",
        args=["-m", "src.mcp_gateway.servers.supabase"],
        env={
            "SUPABASE_URL": os.getenv("SUPABASE_URL", ""),
            "SUPABASE_SERVICE_KEY": os.getenv("SUPABASE_SERVICE_KEY", ""),
        },
        tools=["execute_sql", "list_tables", "describe_table"],
        description="Execute SQL DDL/RPC against the project's Supabase database",
    ),
    "sast": MCPServerConfig(
        name="sast",
        command="python",
        args=["-m", "src.mcp_gateway.servers.sast"],
        tools=["run_semgrep", "run_linter", "check_dependencies"],
        description="Static analysis and code quality scanning",
    ),
}

# ── Per-agent tool bindings ─────────────────────────────────────────────────

_AGENT_TOOLS: Dict[str, List[str]] = {
    "database_agent": ["execute_sql", "list_tables", "describe_table"],
    "backend_agent":  ["write_file", "read_file", "list_directory", "file_exists"],
    "frontend_agent": ["write_file", "read_file", "list_directory", "file_exists"],
    "security_agent": ["run_semgrep", "run_linter", "check_dependencies",
                       "read_file", "list_directory", "file_exists"],
}


class ToolRegistry:
    """Central registry mapping tool names to MCP servers and agents to tools.

    Typical usage:
        registry = ToolRegistry()
        registry.start_all_servers()          # via MCPGateway
        server = registry.get_server("sast")
        tools = registry.get_agent_tools("security_agent")
    """

    def __init__(
        self,
        servers: Optional[Dict[str, MCPServerConfig]] = None,
        agent_tools: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        self._servers: Dict[str, MCPServerConfig] = servers or dict(_DEFAULT_SERVERS)
        self._agent_tools: Dict[str, List[str]] = agent_tools or dict(_AGENT_TOOLS)

        # Build reverse index: tool_name → server_name
        self._tool_to_server: Dict[str, str] = {}
        for srv_name, cfg in self._servers.items():
            for tool in cfg.tools:
                self._tool_to_server[tool] = srv_name

    # ------------------------------------------------------------------
    # Server queries
    # ------------------------------------------------------------------

    def list_servers(self) -> List[str]:
        """Return names of all registered MCP servers."""
        return list(self._servers.keys())

    def get_server(self, name: str) -> MCPServerConfig:
        """Return the config for a named server."""
        cfg = self._servers.get(name)
        if cfg is None:
            raise KeyError(f"MCP server '{name}' not found in registry")
        return cfg

    def get_server_for_tool(self, tool_name: str) -> str:
        """Return the server name that provides a given tool."""
        srv = self._tool_to_server.get(tool_name)
        if srv is None:
            raise KeyError(f"Tool '{tool_name}' is not registered with any MCP server")
        return srv

    def list_tools(self) -> List[str]:
        """Return all registered tool names."""
        return list(self._tool_to_server.keys())

    # ------------------------------------------------------------------
    # Agent queries
    # ------------------------------------------------------------------

    def get_agent_tools(self, agent_name: str) -> List[str]:
        """Return the list of tool names available to a given agent."""
        return list(self._agent_tools.get(agent_name, []))

    def register_agent_tools(self, agent_name: str, tools: List[str]) -> None:
        """Assign a set of tools to an agent (replaces any existing binding)."""
        self._agent_tools[agent_name] = list(tools)

    # ------------------------------------------------------------------
    # Dynamic registration
    # ------------------------------------------------------------------

    def register_server(self, config: MCPServerConfig) -> None:
        """Register a new MCP server at runtime."""
        self._servers[config.name] = config
        for tool in config.tools:
            self._tool_to_server[tool] = config.name

    def unregister_server(self, name: str) -> None:
        """Remove a server and its tools from the registry."""
        cfg = self._servers.pop(name, None)
        if cfg is not None:
            for tool in cfg.tools:
                self._tool_to_server.pop(tool, None)
