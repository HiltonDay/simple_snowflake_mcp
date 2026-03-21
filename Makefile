.PHONY: help install dev test lint format run build clean

help:
	@echo "Available commands:"
	@echo "  install  - Install production dependencies"
	@echo "  dev      - Install all dependencies (including dev)"
	@echo "  test     - Run tests"
	@echo "  lint     - Check code with ruff + mypy"
	@echo "  format   - Format code with ruff"
	@echo "  run      - Start the MCP server"
	@echo "  build    - Build the package"
	@echo "  clean    - Remove generated files"

install:
	uv sync --frozen

dev:
	uv sync --all-extras

test:
	uv run pytest tests/ -v --cov=src

lint:
	uv run ruff check src/
	uv run mypy src/

format:
	uv run ruff format src/
	uv run ruff check --fix src/

run:
	uv run simple-snowflake-mcp

build:
	uv build

clean:
	rm -rf dist/ .pytest_cache/ .coverage .mypy_cache/ .ruff_cache/
	find . -type d -name "__pycache__" -exec rm -rf {} +
