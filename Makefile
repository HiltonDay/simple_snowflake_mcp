.PHONY: help install run clean

help:
	@echo "  install  - Install dependencies"
	@echo "  run      - Start the MCP server"
	@echo "  clean    - Remove generated files"

install:
	uv sync --frozen

run:
	uv run simple-snowflake-mcp

clean:
	rm -rf dist/ .pytest_cache/ .mypy_cache/ .ruff_cache/
	find . -type d -name "__pycache__" -exec rm -rf {} +
