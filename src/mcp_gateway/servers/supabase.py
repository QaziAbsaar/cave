"""Supabase MCP Server — execute SQL DDL and inspect database schema.

Run as a stdio MCP server:
    python -m src.mcp_gateway.servers.supabase

Requires environment variables:
    SUPABASE_URL      — Supabase project URL (https://*.supabase.co)
    SUPABASE_SERVICE_KEY — service_role key (bypasses RLS)

Tools:
    - execute_sql(sql)        → execution result
    - list_tables(schema)     → table names in a schema (default: public)
    - describe_table(table_name, schema) → column info for a table
"""

from __future__ import annotations

import json
import os
import sys

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent

# ── Configuration ───────────────────────────────────────────────────────────

SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")

server = Server("cave-supabase")

# ── Client helpers ──────────────────────────────────────────────────────────


def _supabase_rest_headers() -> dict:
    """Return headers for Supabase REST API calls."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in environment"
        )
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


async def _execute_sql_raw(sql: str) -> dict:
    """Execute SQL via the Supabase REST API /sql endpoint."""
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/rpc/"
    # Use httpx to POST the SQL to pg_dump or use the SQL endpoint
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Supabase pg_graphql or direct DB query via REST
        response = await client.post(
            f"{SUPABASE_URL.rstrip('/')}/rest/v1/",
            headers=_supabase_rest_headers(),
            params={"query": sql},  # pg_graphql style
            json={"query": sql},
        )
        if response.status_code >= 400:
            body = response.text[:500]
            raise RuntimeError(f"Supabase SQL error ({response.status_code}): {body}")
        try:
            return response.json()
        except json.JSONDecodeError:
            return {"status": "ok", "raw": response.text}


# ── Tool implementations ───────────────────────────────────────────────────


@server.tool("execute_sql")
async def execute_sql(sql: str) -> list[TextContent]:
    """Execute a SQL statement (DDL or DML) against the Supabase project.

    Args:
        sql: The SQL statement to execute.
    """
    if not sql.strip():
        return [TextContent(type="text", text="ERROR: empty SQL statement")]

    result = await _execute_sql_raw(sql)
    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


@server.tool("list_tables")
async def list_tables(schema: str = "public") -> list[TextContent]:
    """List all tables in a database schema.

    Args:
        schema: Schema name (default: public).
    """
    query = f"""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = '{schema}'
          AND table_type = 'BASE TABLE'
        ORDER BY table_name;
    """
    try:
        result = await _execute_sql_raw(query)
        if isinstance(result, list):
            tables = [row.get("table_name", "") for row in result]
        elif isinstance(result, dict):
            tables = result.get("data", result.get("rows", []))
            if isinstance(tables, list) and tables and isinstance(tables[0], dict):
                tables = [row.get("table_name", str(row)) for row in tables]
            else:
                tables = [str(result)]
        else:
            tables = [str(result)]

        text = "\n".join(f"  - {t}" for t in tables if t) if tables else "(no tables found)"
        return [TextContent(type="text", text=f"Tables in '{schema}':\n{text}")]
    except Exception as exc:
        return [TextContent(type="text", text=f"ERROR listing tables: {exc}")]


@server.tool("describe_table")
async def describe_table(table_name: str, schema: str = "public") -> list[TextContent]:
    """Describe columns, types, and constraints of a table.

    Args:
        table_name: Name of the table.
        schema: Schema name (default: public).
    """
    query = f"""
        SELECT
            c.column_name,
            c.data_type,
            c.is_nullable,
            c.column_default,
            tc.constraint_type
        FROM information_schema.columns c
        LEFT JOIN information_schema.key_column_usage kcu
            ON c.table_schema = kcu.table_schema
            AND c.table_name = kcu.table_name
            AND c.column_name = kcu.column_name
        LEFT JOIN information_schema.table_constraints tc
            ON kcu.constraint_name = tc.constraint_name
            AND kcu.table_schema = tc.table_schema
        WHERE c.table_schema = '{schema}'
          AND c.table_name = '{table_name}'
        ORDER BY c.ordinal_position;
    """
    try:
        result = await _execute_sql_raw(query)
        rows = result if isinstance(result, list) else result.get("data", [])
        if not rows:
            return [TextContent(type="text", text=f"Table '{schema}.{table_name}' not found or has no columns")]

        lines = [f"Columns of '{schema}.{table_name}':"]
        for row in rows:
            col = row.get("column_name", "?")
            dtype = row.get("data_type", "?")
            nullable = "NULL" if row.get("is_nullable") == "YES" else "NOT NULL"
            default = f" DEFAULT {row['column_default']}" if row.get("column_default") else ""
            constr = f" [{row.get('constraint_type', '')}]" if row.get("constraint_type") else ""
            lines.append(f"  {col:25s} {dtype:15s} {nullable:10s}{default}{constr}")

        return [TextContent(type="text", text="\n".join(lines))]
    except Exception as exc:
        return [TextContent(type="text", text=f"ERROR describing table: {exc}")]


# ── Entry point ─────────────────────────────────────────────────────────────


async def main() -> None:
    if not SUPABASE_URL:
        print("WARNING: SUPABASE_URL not set — supabase MCP server will fail at runtime", file=sys.stderr)
    if not SUPABASE_SERVICE_KEY:
        print("WARNING: SUPABASE_SERVICE_KEY not set — supabase MCP server will fail at runtime", file=sys.stderr)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import anyio
    anyio.run(main)
