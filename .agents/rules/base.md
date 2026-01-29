---
description: Core project guidelines for the mcp-sync codebase. Apply these rules when working on any code, documentation, or configuration files within the mcp-sync project.
alwaysApply: true
inclusion: always
---

# MCP-Sync Project Structure and Overview

This document provides a structural overview of the mcp-sync project, designed to aid AI code assistants in understanding the codebase.

Please refer to `README.md` for a complete and up-to-date project overview.

## Project Overview

MCP-Sync is a CLI tool that synchronizes MCP (Model Context Protocol) server configurations between global and project-level configs. It enables seamless management of MCP servers across different projects, supporting features like interactive server selection, fuzzy matching, backup creation, and direct sync operations.

## Directory Structure

The project is organized into the following directories:

```
mcp-sync/
├── mcp_sync/                   # Main source code
│   ├── __init__.py             # Package initialization
│   ├── main.py                 # CLI entrypoint
│   ├── cli.py                  # Command-line interface logic
│   ├── sync.py                 # Core sync logic
│   ├── config.py               # Configuration models
│   ├── backup.py               # Backup creation and management
│   ├── direct_sync.py          # Direct sync operations
│   ├── fuzzy_match.py          # Fuzzy matching utilities
│   ├── interactive.py          # Interactive server selection
│   ├── toml_support.py         # TOML configuration support
│   ├── client_definitions.json # Built-in client definitions
│   ├── clients/                # Client-related helpers
│   │   ├── __init__.py
│   │   ├── executor.py
│   │   └── repository.py
│   └── config/                 # Configuration helpers
│       ├── __init__.py
│       ├── models.py
│       └── settings.py
├── tests/                      # Unit and integration tests
│   ├── test_backup.py
│   ├── test_client_management.py
│   ├── test_config_models.py
│   ├── test_direct_sync.py
│   ├── test_fuzzy_match.py
│   ├── test_init.py
│   ├── test_integration.py
│   ├── test_interactive.py
│   ├── test_main.py
│   ├── test_settings.py
│   ├── test_sync.py
│   └── test_toml_support.py
├── scripts/                     # Developer tooling
│   └── setup.sh
├── .mcp.json                    # Project-level MCP config
└── AGENTS.md                    # This file
```

## Build, Test, and Development Commands

- `./scripts/setup.sh` installs dev dependencies via `uv` and sets up pre-commit hooks.
- `uv sync` installs dependencies from `pyproject.toml` and `uv.lock`.
- `uv pip install -e .` installs the package in editable mode for local testing.
- `uv run ruff check .` runs linting; `uv run ruff format .` applies formatting.
- `uv run pytest` runs the test suite (see Testing Guidelines below for PYTHONPATH notes).
- `mcp-sync <command>` runs the CLI once installed (see `README.md` for command list).

## Coding Style & Naming Conventions

- Python 3.12+ is required; follow Ruff defaults with a 100-character line length.
- **After every code change, you MUST run the formatter and linter:**
  - `uv run ruff format .` — applies code formatting
  - `uv run ruff check .` — runs linting checks
- Test files follow `tests/test_*.py` naming.
- If a file exceeds 250 lines, split it into multiple files based on functionality.
- Where non-obvious logic exists, add comments in English to clarify.
- When implementing new features, provide corresponding unit tests.

## Testing Guidelines

- Tests use `pytest` with optional `pytest-cov` in dev dependencies.
- The package must be importable; either run `uv pip install -e .` or set `PYTHONPATH=$PWD`.
- Example: `PYTHONPATH=$PWD uv run pytest`.

### Test Requirements

- **Minimum coverage**: 80% for all new modules
- **All tests must pass** before submitting PR
- **Mock external dependencies** (filesystem, network, user input)
- **Test edge cases**: empty inputs, invalid data, error conditions
- **Use pytest fixtures** for common test setup
- **Follow AAA pattern**: Arrange, Act, Assert

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=mcp_sync --cov-report=term-missing

# Run specific test file
uv run pytest tests/test_backup.py -v

# Run with PYTHONPATH
PYTHONPATH=$PWD uv run pytest
```

## Dependencies and Testing Patterns

- Inject dependencies through function parameters for testability (avoid global state).
- Prefer explicit dependency passing over mocking when feasible.
- When mocking is necessary, use `unittest.mock` or `pytest-mock`.
- Example of injectable dependencies:

  ```python
  def process_data(
      data: dict,
      fetch_client: Callable = default_fetch_client,
      save_fn: Callable = default_save
  ) -> Result:
      # Use injected dependencies instead of direct calls
      response = fetch_client(data["url"])
      return save_fn(response)
  ```

## Commit Messages

- Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification.
- Always include a scope in commit messages.
- Use the format: `type(scope): Description`

  ```
  # Examples:
  feat(cli): Add new sync command
  fix(config): Handle missing env variables
  docs(readme): Update installation guide
  style(format): Apply consistent quoting
  refactor(sync): Split sync into smaller functions
  test(sync): Add tests for edge cases
  chore(deps): Update ruff version
  ```

- Use types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, etc.
- Use scope to indicate the affected part of the codebase (`cli`, `config`, `sync`, `tests`, `deps`, etc.).
- Write description in clear, concise present tense starting with a capital letter.

### Commit Body Guidelines

- Include context about what led to this commit in the commit body.
- Describe the conversation or problem that motivated the change.
- Reference related issues using `#issue-number`.

## Pull Request Guidelines

### PR Checklist

When creating a pull request, ensure the following:

```md
## Checklist

- [ ] Run `uv run ruff format .`
- [ ] Run `uv run ruff check .`
- [ ] Run `uv run pytest`
- [ ] Include a clear summary of the changes
```

- Include a clear summary of the changes at the top.
- Where related issues exist, reference them using `#issue-number`.
- Include test results (command + outcome).
- Note any config or CLI changes.
- Screenshots aren't typically needed for this CLI project.

## PR Review Guidelines

When reviewing pull requests, provide thoughtful feedback on:

- Code quality and best practices
- Potential bugs or issues
- Suggestions for improvements
- Overall architecture and design decisions
- Test coverage for new features

## Security & Configuration Tips

- Project config is stored in `.mcp.json` at the repo root; global config is `~/.mcp-sync/global.json`. Project config should be versioned; global config should not.
- Avoid committing secrets in server `env` definitions; use environment variables instead.
