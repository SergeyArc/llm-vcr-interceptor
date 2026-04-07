.PHONY: install lint lint-fix type-check test check

install:
	uv pip install -e ".[dev]"

lint:
	uv run ruff check lhi/ tests/
	uv run ruff format --check lhi/ tests/

lint-fix:
	uv run ruff check --fix lhi/ tests/
	uv run ruff format lhi/ tests/

type-check:
	uv run mypy lhi/

test:
	uv run pytest

check: lint type-check test
