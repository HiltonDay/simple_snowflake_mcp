# Simple Snowflake MCP Server

Snowflake MCP server for kiro-cli. Read-only by default, WSL externalbrowser (SSO) auth.

## Tools

| Tool | Description |
|---|---|
| `execute-query` | Execute SQL (SELECT, SHOW, DESCRIBE, EXPLAIN, WITH). Auto-appends LIMIT. |
| `list-databases` | List accessible databases. Optional LIKE pattern. |
| `list-schemas` | List schemas in a database. |
| `list-tables` | List tables in a database/schema. |
| `describe-table` | Column details for a table (supports fully qualified names). |
| `find-table` | Search for a table by name across databases. |
| `find-column` | Find tables containing a column name (exact or partial). |
| `get-connection-info` | Current user, role, database, schema, warehouse. |

## Configuration

All config is via environment variables, set in `launch_mcp.sh`:

| Variable | Required | Default |
|---|---|---|
| `SNOWFLAKE_USER` | Yes | — |
| `SNOWFLAKE_ACCOUNT` | Yes | — |
| `SNOWFLAKE_AUTHENTICATOR` | No | `externalbrowser` |
| `SNOWFLAKE_ROLE` | No | — |
| `SNOWFLAKE_WH` / `SNOWFLAKE_WAREHOUSE` | No | — |
| `SNOWFLAKE_DB` / `SNOWFLAKE_DATABASE` | No | — |
| `SNOWFLAKE_SCHEMA` | No | — |
| `SNOWFLAKE_READ_ONLY` / `MCP_READ_ONLY` | No | `true` |

## kiro-cli Integration

`~/.kiro/settings/mcp.json`:

```json
{
  "mcpServers": {
    "simple_snowflake_mcp": {
      "command": "wsl.exe",
      "args": ["--", "/home/hiltond/ai_coding/mcp/simple_snowflake_mcp/launch_mcp.sh"]
    }
  }
}
```

## Development

```bash
uv sync          # install deps
make run         # start server
make clean       # remove generated files
```

## License

MIT
