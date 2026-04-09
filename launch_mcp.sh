#!/bin/bash
# Launcher script for simple_snowflake_mcp
# Works from both WSL (kiro-cli) and Windows (Kiro IDE via wsl.exe)

export PYTHONPATH="/home/hiltond/ai_coding/mcp/simple_snowflake_mcp/src"
export BROWSER="xdg-open"
export SNOWFLAKE_USER="hiltond@bizcover.com.au"
export SNOWFLAKE_ACCOUNT="bizcover.ap-southeast-2"
export SNOWFLAKE_ROLE="DATAANALYTICS"
export SNOWFLAKE_WH="DEV_QUERY_WH"
export SNOWFLAKE_DB="DEV_DWH_HILTOND"
export SNOWFLAKE_SCHEMA="hiltond"
export SNOWFLAKE_AUTHENTICATOR="externalbrowser"
export SNOWFLAKE_READ_ONLY="true"

cd /home/hiltond/ai_coding/mcp/simple_snowflake_mcp
exec python3 -m simple_snowflake_mcp
