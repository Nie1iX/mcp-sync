# Repository Guidelines

## Project Structure & Module Organization
- `mcp_sync/` holds the core package code (CLI entrypoint in `mcp_sync/main.py`, sync logic in `mcp_sync/sync.py`, config models in `mcp_sync/config.py`, and built-in client definitions in `mcp_sync/client_definitions.json`).
- `mcp_sync/clients/` and `mcp_sync/config/` contain client- and config-related helpers.
- `tests/` contains pytest test modules (for example `tests/test_sync.py`, `tests/test_main.py`).
- `scripts/` includes developer tooling like `scripts/setup.sh`.

## Build, Test, and Development Commands
- `./scripts/setup.sh` installs dev dependencies via `uv` and sets up pre-commit hooks.
- `uv sync` installs dependencies from `pyproject.toml` and `uv.lock`.
- `uv pip install -e .` installs the package in editable mode for local testing.
- `uv run ruff check .` runs linting; `uv run ruff format .` applies formatting.
- `uv run pytest` runs the test suite (see Testing Guidelines below for PYTHONPATH notes).
- `mcp-sync <command>` runs the CLI once installed (see `README.md` for command list).

## Coding Style & Naming Conventions
- Python 3.12+ is required; follow Ruff defaults with a 100-character line length.
- Formatting and linting are enforced via `ruff` (use `uv run ruff format .` before commits).
- Test files follow `tests/test_*.py` naming.

## Testing Guidelines
- Tests use `pytest` with optional `pytest-cov` in dev dependencies.
- The package must be importable; either run `uv pip install -e .` or set `PYTHONPATH=$PWD`.
- Example: `PYTHONPATH=$PWD uv run pytest`.

## Commit & Pull Request Guidelines
- Recent commits generally follow Conventional Commit style (`feat:`, `fix:`, `chore:`), but older history includes plain “Bump version …” messages. Prefer `type: summary` going forward.
- PRs should include: a clear description of the change, linked issue(s) if applicable, test results (command + outcome), and notes about config or CLI changes. Screenshots aren’t typically needed for this CLI project.

## Security & Configuration Tips
- Project config is stored in `.mcp.json` at the repo root; global config is `~/.mcp-sync/global.json`. Project config should be versioned; global config should not.
- Avoid committing secrets in server `env` definitions; use environment variables instead.
