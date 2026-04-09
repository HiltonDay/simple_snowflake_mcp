# Simple Snowflake MCP Server

A lightweight MCP server for Snowflake, designed for WSL environments with externalbrowser (SSO) authentication. Read-only by default with SQL injection protection.

## Tools

| Tool | Description |
|---|---|
| `execute-query` | Execute SQL (SELECT, SHOW, DESCRIBE, EXPLAIN, WITH). Auto-appends LIMIT. Output as JSON or markdown. |
| `list-databases` | List accessible databases. Optional LIKE pattern filter. |
| `list-schemas` | List schemas in a database (or current database if omitted). |
| `list-tables` | List tables in a database/schema. |
| `describe-table` | Get column details for a table (supports fully qualified names). |
| `find-table` | Search for a table by name across databases. |
| `find-column` | Find tables containing a column name (exact or partial match). |
| `get-connection-info` | Show current user, role, database, schema, warehouse, and server version. |
| `profile-table` | Statistical profile of a table using pandas `describe()`. Returns count, mean, std, min/max for numeric columns and count, unique, top, freq for string columns. Samples up to 100k rows. |

## Setup

### Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) package manager
- Snowflake account with externalbrowser auth (or password auth)

### Install

```bash
git clone <repo-url>
cd simple_snowflake_mcp
uv sync
```

### Configure

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Required variables:
- `SNOWFLAKE_USER` — your Snowflake username
- `SNOWFLAKE_ACCOUNT` — your Snowflake account identifier

Optional variables:
- `SNOWFLAKE_AUTHENTICATOR` — auth method (default: `externalbrowser`)
- `SNOWFLAKE_PASSWORD` — only needed for password auth
- `SNOWFLAKE_ROLE` — Snowflake role to use
- `SNOWFLAKE_WAREHOUSE` / `SNOWFLAKE_WH` — warehouse name
- `SNOWFLAKE_DATABASE` / `SNOWFLAKE_DB` — default database
- `SNOWFLAKE_SCHEMA` — default schema
- `SNOWFLAKE_READ_ONLY` / `MCP_READ_ONLY` — read-only mode (default: `true`)

### Server Configuration

Edit `config.yaml` to customise logging, query limits, etc.:

```yaml
logging:
  level: INFO
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

server:
  name: "simple_snowflake_mcp"
  version: "0.3.0"

snowflake:
  read_only: true
  default_query_limit: 1000
  max_query_limit: 50000
```

Override the config file path with `CONFIG_FILE=custom_config.yaml`.

## Usage

### Run directly

```bash
uv run simple-snowflake-mcp
```

### MCP client configuration

#### VS Code

Already configured in `.vscode/mcp.json`:

```json
{
  "servers": {
    "simple-snowflake-mcp": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "simple-snowflake-mcp"]
    }
  }
}
```

#### Claude Desktop

```json
{
  "mcpServers": {
    "simple_snowflake_mcp": {
      "command": "uv",
      "args": ["--directory", "/path/to/simple_snowflake_mcp", "run", "simple-snowflake-mcp"]
    }
  }
}
```

#### Kiro CLI

Add to your `~/.kiro/settings/mcp.json`:

```json
{
  "mcpServers": {
    "snowflake": {
      "command": "uv",
      "args": ["--directory", "/path/to/simple_snowflake_mcp", "run", "simple-snowflake-mcp"]
    }
  }
}
```

### Debugging

```bash
npx @modelcontextprotocol/inspector uv run simple-snowflake-mcp
```

## Development

```bash
# Install with dev dependencies
uv sync --all-extras

# Lint
make lint

# Format
make format

# See all commands
make help
```

## Security

- Read-only mode enabled by default — blocks INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, GRANT, REVOKE
- SQL injection protection via identifier validation
- Passwords/tokens excluded from log output
- WSL-compatible: auto-sets `BROWSER=xdg-open` for SSO flow

## License

MIT — see [LICENSE](LICENSE).
