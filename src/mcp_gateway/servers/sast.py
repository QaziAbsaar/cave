"""SAST MCP Server — static analysis and code quality scanning.

Run as a stdio MCP server:
    python -m src.mcp_gateway.servers.sast

Tools:
    - run_semgrep(target_dir, rules) → semgrep findings (JSON)
    - run_linter(target_dir, tool)    → lint results (default: ruff)
    - check_dependencies(deps)       → dependency vulnerability check
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent

server = Server("cave-sast")

# ── Helpers ─────────────────────────────────────────────────────────────────


async def _run_command(cmd: List[str], cwd: Optional[str] = None, timeout: int = 120) -> Dict[str, Any]:
    """Run a shell command and return stdout, stderr, and exit code."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return {
            "returncode": proc.returncode,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
        }
    except asyncio.TimeoutError:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": f"Command timed out after {timeout}s",
        }
    except FileNotFoundError:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": f"Command not found: {' '.join(cmd)}",
        }


import asyncio


# ── Tool implementations ───────────────────────────────────────────────────


@server.tool("run_semgrep")
async def run_semgrep(
    target_dir: str,
    rules: Optional[str] = None,
) -> list[TextContent]:
    """Run Semgrep SAST scan on a target directory.

    Args:
        target_dir: Directory to scan (absolute or relative to sandbox).
        rules: Optional rule string (e.g. "p/python", "r/javascript.express.security").
               Defaults to "p/default" (all community rules).
    """
    resolved = Path(target_dir).resolve()
    if not resolved.is_dir():
        return [TextContent(type="text", text=f"ERROR: target directory not found: {resolved}")]

    rule_ref = rules or "p/default"
    cmd = ["semgrep", "--json", "--metrics=off", f"--config={rule_ref}", str(resolved)]

    result = await _run_command(cmd)
    output: Dict[str, Any] = {"command": " ".join(cmd), "returncode": result["returncode"]}

    if result["stderr"] and "error" in result["stderr"].lower():
        output["stderr"] = result["stderr"]

    if result["stdout"]:
        try:
            parsed = json.loads(result["stdout"])
            output["results"] = parsed.get("results", [])
            output["errors"] = parsed.get("errors", [])
            output["summary"] = {
                "total_findings": len(output["results"]),
                "total_errors": len(output["errors"]),
            }
        except json.JSONDecodeError:
            output["raw_stdout"] = result["stdout"][:2000]

    return [TextContent(type="text", text=json.dumps(output, indent=2))]


@server.tool("run_linter")
async def run_linter(
    target_dir: str,
    tool: str = "ruff",
) -> list[TextContent]:
    """Run a linter on the target directory.

    Args:
        target_dir: Directory to lint.
        tool: Linter to use — "ruff", "flake8", or "pylint" (default: "ruff").
    """
    resolved = Path(target_dir).resolve()
    if not resolved.is_dir():
        return [TextContent(type="text", text=f"ERROR: target directory not found: {resolved}")]

    tool_map = {
        "ruff": ["ruff", "check", "--no-cache", "--format=json", str(resolved)],
        "flake8": ["flake8", "--format=json", str(resolved)],
        "pylint": ["pylint", "--output-format=json", str(resolved)],
    }

    cmd = tool_map.get(tool)
    if cmd is None:
        return [TextContent(type="text", text=f"ERROR: unsupported linter '{tool}'. Use: {', '.join(tool_map)}")]

    result = await _run_command(cmd)
    output: Dict[str, Any] = {
        "tool": tool,
        "target": str(resolved),
        "returncode": result["returncode"],
    }

    if result["stdout"]:
        try:
            output["findings"] = json.loads(result["stdout"])
            output["summary"] = {"total_findings": len(output["findings"])}
        except json.JSONDecodeError:
            output["stdout"] = result["stdout"][:2000]

    if result["stderr"]:
        output["stderr"] = result["stderr"][:1000]

    return [TextContent(type="text", text=json.dumps(output, indent=2))]


@server.tool("check_dependencies")
async def check_dependencies(deps: str) -> list[TextContent]:
    """Check a list of dependencies for known vulnerabilities.

    Args:
        deps: JSON string or comma-separated list of package==version strings.
    """
    try:
        dep_list = json.loads(deps) if deps.strip().startswith("[") else [d.strip() for d in deps.split(",") if d.strip()]
    except json.JSONDecodeError:
        dep_list = [d.strip() for d in deps.split(",") if d.strip()]

    if not dep_list:
        return [TextContent(type="text", text="No dependencies provided.")]

    # Use pip-audit if available, otherwise do a best-effort scan
    cmd = ["pip-audit", "--format=json", "--no-deps"]
    for dep in dep_list:
        cmd.extend(["-r", dep])

    result = await _run_command(cmd)

    output: Dict[str, Any] = {
        "dependencies_checked": dep_list,
    }

    if result["returncode"] == 0 and result["stdout"]:
        try:
            audit = json.loads(result["stdout"])
            output["vulnerabilities"] = audit.get("vulnerabilities", [])
            output["summary"] = {
                "total_vulnerabilities": len(output["vulnerabilities"]),
            }
        except json.JSONDecodeError:
            output["stdout"] = result["stdout"][:2000]
    elif result["returncode"] != 0 and "not found" in result["stderr"].lower():
        output["note"] = "pip-audit not installed — install with: pip install pip-audit"
        output["dependencies"] = dep_list
    else:
        output["stdout"] = result["stdout"][:2000]
        output["stderr"] = result["stderr"][:1000]

    return [TextContent(type="text", text=json.dumps(output, indent=2))]


# ── Entry point ─────────────────────────────────────────────────────────────


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import anyio
    anyio.run(main)
