"""
Snowflake MCP Server — consolidated from simple_snowflake_mcp + snowflake server.

Features:
- Persistent connection with automatic reconnect
- Read-only mode with SQL injection protection
- WSL-compatible externalbrowser auth (auto-opens Windows browser)
- Parameterized queries where possible, allowlist-based write protection
- Configurable via config.yaml + env vars
"""

import asyncio
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import mcp.server.stdio
import mcp.types as types
import snowflake.connector
import yaml
import pandas as pd
from dotenv import load_dotenv
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions

# Ensure WSL can open Windows browser for SSO
if not os.environ.get("BROWSER"):
    os.environ["BROWSER"] = "xdg-open"

load_dotenv()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def load_config() -> dict[str, Any]:
    config_file = os.getenv("CONFIG_FILE", "config.yaml")
    config_path = Path(__file__).parent.parent.parent / config_file
    default: dict[str, Any] = {
        "logging": {
            "level": "INFO",
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        },
        "server": {
            "name": "simple_snowflake_mcp",
            "version": "0.3.0",
        },
        "snowflake": {
            "read_only": True,
            "default_query_limit": 1000,
            "max_query_limit": 50000,
        },
    }
    try:
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}

            def _merge(base: dict, override: dict) -> dict:
                for k, v in override.items():
                    if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                        _merge(base[k], v)
                    else:
                        base[k] = v
                return base

            return _merge(default, loaded)
    except Exception as e:
        print(f"Config load error: {e}, using defaults", file=sys.stderr)
    return default


CONFIG = load_config()

logging.basicConfig(
    level=getattr(logging, CONFIG["logging"].get("level", "INFO").upper(), logging.INFO),
    format=CONFIG["logging"].get("format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
    force=True,
)
# Keep snowflake connector quiet unless we're debugging
logging.getLogger("snowflake.connector").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

MCP_READ_ONLY = os.getenv(
    "MCP_READ_ONLY",
    os.getenv("SNOWFLAKE_READ_ONLY", str(CONFIG["snowflake"]["read_only"])),
).lower() == "true"
DEFAULT_QUERY_LIMIT = CONFIG["snowflake"]["default_query_limit"]
MAX_QUERY_LIMIT = CONFIG["snowflake"]["max_query_limit"]


# ---------------------------------------------------------------------------
# Snowflake connection (persistent, auto-reconnect)
# ---------------------------------------------------------------------------

# Write-operation keywords (blocked in read-only mode)
_WRITE_OPS = frozenset([
    "INSERT", "UPDATE", "DELETE", "MERGE", "TRUNCATE",
    "CREATE", "DROP", "ALTER", "GRANT", "REVOKE",
])

# Read-only allowed first keywords
_READ_OPS = frozenset(["SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN", "WITH", "LIST"])


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"--.*$", "", sql, flags=re.MULTILINE)
    return re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)


def _first_keyword(sql: str) -> str:
    cleaned = _strip_comments(sql).strip()
    return cleaned.split()[0].upper() if cleaned else ""


class SnowflakeConnection:
    """Manages a persistent Snowflake connection with auto-reconnect."""

    def __init__(self) -> None:
        self._conn: snowflake.connector.SnowflakeConnection | None = None

        # Build config from env — support both SNOWFLAKE_WAREHOUSE and SNOWFLAKE_WH etc.
        self.config: dict[str, Any] = {
            "user": os.getenv("SNOWFLAKE_USER"),
            "account": os.getenv("SNOWFLAKE_ACCOUNT"),
        }

        auth = os.getenv("SNOWFLAKE_AUTHENTICATOR", "externalbrowser")
        if auth == "externalbrowser":
            self.config["authenticator"] = "externalbrowser"
        else:
            self.config["authenticator"] = auth
            pw = os.getenv("SNOWFLAKE_PASSWORD")
            if pw:
                self.config["password"] = pw

        for env_key, cfg_key in [
            ("SNOWFLAKE_ROLE", "role"),
            ("SNOWFLAKE_WAREHOUSE", "warehouse"),
            ("SNOWFLAKE_WH", "warehouse"),
            ("SNOWFLAKE_DATABASE", "database"),
            ("SNOWFLAKE_DB", "database"),
            ("SNOWFLAKE_SCHEMA", "schema"),
        ]:
            val = os.getenv(env_key)
            if val:
                self.config[cfg_key] = val

        missing = [k for k in ("user", "account") if not self.config.get(k)]
        if missing:
            raise ValueError(f"Missing required env vars: {missing}")

        # Sanitised config for logging (no passwords/tokens)
        safe = {k: v for k, v in self.config.items() if k not in ("password", "token")}
        logger.info("Snowflake config: %s | read_only=%s", safe, MCP_READ_ONLY)

    def _connect(self) -> snowflake.connector.SnowflakeConnection:
        conn = snowflake.connector.connect(
            **{k: v for k, v in self.config.items() if v is not None},
            client_session_keep_alive=True,
            network_timeout=30,
            login_timeout=120,
        )
        conn.cursor().execute("ALTER SESSION SET TIMEZONE = 'UTC'")
        logger.info("Snowflake connection established")
        return conn

    def _ensure_conn(self) -> snowflake.connector.SnowflakeConnection:
        if self._conn is None:
            self._conn = self._connect()
            return self._conn
        try:
            self._conn.cursor().execute("SELECT 1")
            return self._conn
        except Exception:
            logger.info("Connection stale, reconnecting...")
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = self._connect()
            return self._conn

    def execute(self, sql: str) -> dict[str, Any]:
        kw = _first_keyword(sql)

        if MCP_READ_ONLY and kw in _WRITE_OPS:
            return {
                "success": False,
                "error": f"Write operation '{kw}' blocked — read-only mode is enabled.",
                "data": None,
            }

        t0 = time.time()
        try:
            conn = self._ensure_conn()
            cur = conn.cursor()

            if self.config.get("role"):
                cur.execute(f"USE ROLE {self.config['role']}")

            cur.execute(sql)
            elapsed = time.time() - t0

            if cur.description:
                cols = [d[0] for d in cur.description]
                rows = cur.fetchmany(MAX_QUERY_LIMIT)
                data = [dict(zip(cols, r)) for r in rows]
                logger.info("Query returned %d rows in %.2fs", len(data), elapsed)
                # Echo results to console (stderr) for visibility
                print(f"\n{'─'*80}", file=sys.stderr)
                print(f"  Query ({len(data)} rows, {elapsed:.2f}s):", file=sys.stderr)
                print(f"  {sql[:200]}{'...' if len(sql) > 200 else ''}", file=sys.stderr)
                print(f"{'─'*80}", file=sys.stderr)
                _print_table(cols, rows[:50], file=sys.stderr)
                if len(data) > 50:
                    print(f"  ... ({len(data) - 50} more rows)", file=sys.stderr)
                print(file=sys.stderr)
            else:
                data = [{"status": "success", "rows_affected": cur.rowcount}]
                logger.info("Query executed in %.2fs", elapsed)

            return {"success": True, "data": data}

        except Exception as e:
            logger.error("Query error: %s", e)
            return {"success": False, "error": str(e), "data": None}

    def close(self) -> None:
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def fetch_dataframe(self, sql: str) -> pd.DataFrame:
        """Execute a query and return results as a pandas DataFrame."""
        conn = self._ensure_conn()
        cur = conn.cursor()
        if self.config.get("role"):
            cur.execute(f"USE ROLE {self.config['role']}")
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        return pd.DataFrame(rows, columns=cols)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _md_table(data: list[dict[str, Any]]) -> str:
    if not data:
        return "No results."
    cols = list(data[0].keys())
    header = "| " + " | ".join(cols) + " |"
    sep = "|" + "---|" * len(cols)
    rows = "\n".join("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |" for r in data)
    return f"{header}\n{sep}\n{rows}"


def _format_result(data: list[dict[str, Any]], fmt: str = "json") -> str:
    if fmt == "markdown":
        return _md_table(data)
    return json.dumps(data, indent=2, default=str)


def _print_table(cols: list[str], rows: list[tuple], file=sys.stderr) -> None:
    """Print a compact aligned table to the given file handle."""
    str_rows = [[str(v) if v is not None else "" for v in r] for r in rows]
    widths = [max(len(c), *(len(r[i]) for r in str_rows)) if str_rows else len(c) for i, c in enumerate(cols)]
    # Cap column width to keep output readable
    cap = 40
    widths = [min(w, cap) for w in widths]
    def _trunc(s, w):
        return s[:w-1] + "…" if len(s) > w else s.ljust(w)
    header = "  " + " │ ".join(_trunc(c, w) for c, w in zip(cols, widths))
    sep = "  " + "─┼─".join("─" * w for w in widths)
    print(header, file=file)
    print(sep, file=file)
    for r in str_rows:
        print("  " + " │ ".join(_trunc(r[i], w) for i, w in enumerate(widths)), file=file)


def _safe_identifier(name: str) -> str:
    """Validate a Snowflake identifier to prevent injection."""
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_$.]*$", name):
        raise ValueError(f"Invalid identifier: {name}")
    return name


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

server = Server("simple_snowflake_mcp")
db: SnowflakeConnection | None = None


def _db() -> SnowflakeConnection:
    global db
    if db is None:
        db = SnowflakeConnection()
    return db


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="execute-query",
            description=(
                "Execute a SQL query on Snowflake. Read-only mode is on by default. "
                "Supports SELECT, SHOW, DESCRIBE, EXPLAIN, WITH."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "SQL query to execute", "minLength": 1},
                    "format": {
                        "type": "string",
                        "enum": ["json", "markdown"],
                        "default": "json",
                        "description": "Output format",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_QUERY_LIMIT,
                        "description": f"Max rows (default {DEFAULT_QUERY_LIMIT})",
                    },
                },
                "required": ["sql"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="list-databases",
            description="List all accessible Snowflake databases",
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "LIKE pattern filter (e.g. 'PROD_%')",
                    },
                },
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="list-schemas",
            description="List schemas in a database",
            inputSchema={
                "type": "object",
                "properties": {
                    "database": {"type": "string", "description": "Database name (uses current if omitted)"},
                },
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="list-tables",
            description="List tables in a database/schema",
            inputSchema={
                "type": "object",
                "properties": {
                    "database": {"type": "string", "description": "Database name"},
                    "schema": {"type": "string", "description": "Schema name"},
                },
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="describe-table",
            description="Get column info for a table (fully qualified: db.schema.table)",
            inputSchema={
                "type": "object",
                "properties": {
                    "table": {"type": "string", "description": "Table name", "minLength": 1},
                },
                "required": ["table"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="find-table",
            description="Find which database/schema contains a table",
            inputSchema={
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "Table name (case-insensitive)", "minLength": 1},
                },
                "required": ["table_name"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="find-column",
            description="Find tables containing a column name (exact or partial match)",
            inputSchema={
                "type": "object",
                "properties": {
                    "column_name": {"type": "string", "description": "Column name to search", "minLength": 1},
                    "partial": {
                        "type": "boolean",
                        "default": False,
                        "description": "Use LIKE partial match instead of exact",
                    },
                },
                "required": ["column_name"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="get-connection-info",
            description="Get current Snowflake connection status",
            inputSchema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="profile-table",
            description=(
                "Statistical profile of a table using pandas describe(). "
                "Returns count, unique, top, freq for string columns and "
                "count, mean, std, min, 25%, 50%, 75%, max for numeric columns. "
                "Samples up to 100k rows. Requires fully qualified name: db.schema.table"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "table": {
                        "type": "string",
                        "description": "Fully qualified table name (db.schema.table)",
                        "minLength": 1,
                    },
                    "sample_size": {
                        "type": "integer",
                        "minimum": 100,
                        "maximum": 100000,
                        "default": 10000,
                        "description": "Number of rows to sample (default 10000)",
                    },
                },
                "required": ["table"],
                "additionalProperties": False,
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent]:
    args = arguments or {}

    try:
        if name == "execute-query":
            sql = args["sql"]
            fmt = args.get("format", "json")
            limit = min(args.get("limit", DEFAULT_QUERY_LIMIT), MAX_QUERY_LIMIT)

            kw = _first_keyword(sql)
            if MCP_READ_ONLY and kw not in _READ_OPS:
                return [types.TextContent(type="text", text=f"Blocked: '{kw}' not allowed in read-only mode.")]

            # Auto-append LIMIT for SELECT without one
            if kw == "SELECT" and "LIMIT" not in sql.upper():
                sql += f" LIMIT {limit}"

            result = _db().execute(sql)
            if result["success"]:
                return [types.TextContent(type="text", text=_format_result(result["data"], fmt))]
            return [types.TextContent(type="text", text=f"Error: {result['error']}")]

        elif name == "list-databases":
            pattern = args.get("pattern")
            q = "SHOW DATABASES"
            if pattern:
                _safe_identifier(pattern.replace("%", "").replace("_", ""))
                q += f" LIKE '{pattern}'"
            result = _db().execute(q)

        elif name == "list-schemas":
            database = args.get("database")
            if database:
                q = f"SHOW SCHEMAS IN DATABASE {_safe_identifier(database)}"
            else:
                q = "SHOW SCHEMAS"
            result = _db().execute(q)

        elif name == "list-tables":
            parts = []
            if args.get("database"):
                parts.append(f"IN DATABASE {_safe_identifier(args['database'])}")
            if args.get("schema"):
                parts.append(f"IN SCHEMA {_safe_identifier(args['schema'])}")
            q = "SHOW TABLES " + " ".join(parts) if parts else "SHOW TABLES"
            result = _db().execute(q)

        elif name == "describe-table":
            table = args["table"]
            # Validate each part of a potentially qualified name
            for part in table.split("."):
                _safe_identifier(part)
            result = _db().execute(f"DESCRIBE TABLE {table}")

        elif name == "find-table":
            table_name = _safe_identifier(args["table_name"])
            result = _db().execute(
                f"SELECT table_catalog AS database_name, table_schema AS schema_name, "
                f"table_name, table_type "
                f"FROM information_schema.tables "
                f"WHERE UPPER(table_name) = UPPER('{table_name}') "
                f"ORDER BY table_catalog, table_schema"
            )

        elif name == "find-column":
            col = _safe_identifier(args["column_name"])
            op = f"LIKE UPPER('%{col}%')" if args.get("partial") else f"= UPPER('{col}')"
            result = _db().execute(
                f"SELECT table_catalog AS database_name, table_schema AS schema_name, "
                f"table_name, column_name, data_type, is_nullable "
                f"FROM information_schema.columns "
                f"WHERE UPPER(column_name) {op} "
                f"ORDER BY table_catalog, table_schema, table_name"
            )

        elif name == "get-connection-info":
            result = _db().execute(
                "SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_DATABASE(), "
                "CURRENT_SCHEMA(), CURRENT_WAREHOUSE(), CURRENT_VERSION()"
            )
            if result["success"]:
                info = {
                    "connection": result["data"][0] if result["data"] else {},
                    "read_only_mode": MCP_READ_ONLY,
                    "server_version": CONFIG["server"]["version"],
                    "timestamp": datetime.now().isoformat(),
                }
                return [types.TextContent(type="text", text=json.dumps(info, indent=2, default=str))]
            return [types.TextContent(type="text", text=f"Error: {result['error']}")]

        elif name == "profile-table":
            table = args["table"]
            for part in table.split("."):
                _safe_identifier(part)
            sample_size = min(args.get("sample_size", 10000), 100000)

            t0 = time.time()
            df = _db().fetch_dataframe(f"SELECT * FROM {table} TABLESAMPLE ({sample_size} ROWS)")
            elapsed = time.time() - t0

            # Build one-row-per-column profile
            profile_rows = []
            null_counts = df.isnull().sum()
            null_pct = (null_counts / len(df) * 100).round(2)

            for col in df.columns:
                s = df[col]
                row = {
                    "column": col,
                    "dtype": str(s.dtype),
                    "non_null": int(s.count()),
                    "null_count": int(null_counts[col]),
                    "null_pct": float(null_pct[col]),
                }
                if pd.api.types.is_numeric_dtype(s):
                    desc = s.describe()
                    row.update({
                        "mean": round(float(desc.get("mean", 0)), 4),
                        "std": round(float(desc.get("std", 0)), 4),
                        "min": desc.get("min"),
                        "p25": desc.get("25%"),
                        "p50": desc.get("50%"),
                        "p75": desc.get("75%"),
                        "max": desc.get("max"),
                    })
                else:
                    row.update({
                        "unique": int(s.nunique()),
                        "top": str(s.mode().iloc[0]) if not s.mode().empty else "",
                        "top_freq": int(s.value_counts().iloc[0]) if not s.value_counts().empty else 0,
                    })
                profile_rows.append(row)

            profile_df = pd.DataFrame(profile_rows).fillna("")

            sections = [
                f"Table: {table}",
                f"Sampled rows: {len(df)} (requested {sample_size}) in {elapsed:.2f}s",
                f"Columns: {len(df.columns)}",
                "",
                profile_df.to_string(index=False),
            ]

            output = "\n".join(sections)
            print(f"\n{'─'*80}", file=sys.stderr)
            print(f"  profile-table: {table}", file=sys.stderr)
            print(f"{'─'*80}", file=sys.stderr)
            print(output, file=sys.stderr)
            print(file=sys.stderr)
            return [types.TextContent(type="text", text=output)]

        else:
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]

        # Default result handler for tools that set `result`
        if result["success"]:
            return [types.TextContent(type="text", text=_format_result(result["data"]))]
        return [types.TextContent(type="text", text=f"Error: {result['error']}")]

    except ValueError as e:
        return [types.TextContent(type="text", text=f"Validation error: {e}")]
    except Exception as e:
        logger.error("Tool %s failed: %s", name, e)
        return [types.TextContent(type="text", text=f"Error: {e}")]


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def main() -> None:
    logger.info("Starting %s v%s", CONFIG["server"]["name"], CONFIG["server"]["version"])

    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name=CONFIG["server"]["name"],
                server_version=CONFIG["server"]["version"],
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
