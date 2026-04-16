#!/bin/bash
# Launcher script for simple_snowflake_mcp
# Works from: WSL (kiro-cli / Kiro IDE), native Linux, Windows (via wsl.exe)

# --- Detect browser ---
if grep -qi microsoft /proc/version 2>/dev/null; then
  # WSL: use Windows Edge
  EDGE="/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
  if [ -x "$EDGE" ]; then
    export BROWSER="$EDGE"
  else
    # Fallback: try sensible-browser or xdg-open
    export BROWSER="${BROWSER:-xdg-open}"
  fi
else
  # Native Linux: use xdg-open (respects default browser)
  export BROWSER="${BROWSER:-xdg-open}"
fi

# --- Snowflake config ---
export SNOWFLAKE_USER="hiltond@bizcover.com.au"
export SNOWFLAKE_ACCOUNT="bizcover.ap-southeast-2"
export SNOWFLAKE_ROLE="DATAANALYTICS"
export SNOWFLAKE_WH="DEV_QUERY_WH"
export SNOWFLAKE_DB="DEV_DWH_HILTOND"
export SNOWFLAKE_SCHEMA="hiltond"
export SNOWFLAKE_AUTHENTICATOR="externalbrowser"
export SNOWFLAKE_READ_ONLY="true"

# --- Launch ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
export PYTHONPATH="$SCRIPT_DIR/src"
cd "$SCRIPT_DIR"
exec "$WORKSPACE_DIR/.venv/bin/python" -m simple_snowflake_mcp
