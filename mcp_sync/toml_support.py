"""TOML configuration support for MCP tools like Codex."""

from __future__ import annotations

import logging
import platform
from pathlib import Path
from typing import Any

import tomlkit
from tomlkit import TOMLDocument

logger = logging.getLogger(__name__)


class CodexConfig:
    """Handler for Codex TOML configuration files."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def read_config(self, path: Path) -> dict[str, Any]:
        """Read and parse a Codex TOML config file.

        Returns a canonical representation of MCP servers.
        """
        if not path.exists():
            return {"mcpServers": {}}

        try:
            content = path.read_text(encoding="utf-8")
            doc = tomlkit.parse(content)

            servers = {}
            mcp_servers = doc.get("mcp_servers", {})

            for server_id, server_config in mcp_servers.items():
                if not isinstance(server_config, dict):
                    continue

                canonical_server = self._parse_codex_server(server_config)
                servers[server_id] = canonical_server

            return {"mcpServers": servers}

        except Exception as e:
            self.logger.error(f"Failed to parse Codex config at {path}: {e}")
            return {"mcpServers": {}}

    def write_config(
        self, path: Path, config: dict[str, Any], preserve_existing: bool = True
    ) -> bool:
        """Write MCP servers to a Codex TOML config file.

        Args:
            path: Path to the config file
            config: Configuration with mcpServers dict
            preserve_existing: Whether to preserve non-MCP sections

        Returns:
            True if successful, False otherwise
        """
        try:
            # Read existing content if preserving
            doc: TOMLDocument
            if preserve_existing and path.exists():
                content = path.read_text(encoding="utf-8")
                try:
                    doc = tomlkit.parse(content)
                except Exception:
                    doc = tomlkit.document()
            else:
                doc = tomlkit.document()

            # Ensure mcp_servers section exists
            if "mcp_servers" not in doc:
                doc["mcp_servers"] = tomlkit.table()

            mcp_servers = doc["mcp_servers"]
            new_servers = config.get("mcpServers", {})

            # Update or add servers
            for server_id, server_config in new_servers.items():
                codex_server = self._format_codex_server(server_config)
                mcp_servers[server_id] = codex_server

            # Remove servers that are no longer in config
            existing_servers = set(mcp_servers.keys())
            new_server_ids = set(new_servers.keys())
            for server_id in existing_servers - new_server_ids:
                del mcp_servers[server_id]

            # Write back
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(tomlkit.dumps(doc), encoding="utf-8")

            return True

        except Exception as e:
            self.logger.error(f"Failed to write Codex config at {path}: {e}")
            return False

    def _parse_codex_server(self, server_config: dict) -> dict[str, Any]:
        """Parse a Codex server configuration into canonical format.

        Handles Windows-specific format with cmd /c wrapper.
        """
        result: dict[str, Any] = {
            "command": None,
            "args": [],
            "env": {},
        }

        # Get command
        command = server_config.get("command", "")
        args = server_config.get("args", [])

        # Handle Windows cmd wrapper
        if command and command.lower() in ("cmd", "cmd.exe"):
            if args and len(args) >= 2:
                # cmd /c <actual_command> <args...>
                first_arg = args[0].lower() if args else ""
                if first_arg in ("/c", "/k"):
                    result["command"] = args[1] if len(args) > 1 else ""
                    result["args"] = list(args[2:]) if len(args) > 2 else []
                else:
                    result["command"] = args[0] if args else ""
                    result["args"] = list(args[1:]) if len(args) > 1 else []
            else:
                result["command"] = ""
                result["args"] = list(args)
        else:
            result["command"] = command
            result["args"] = list(args)

        # Get environment variables
        env = server_config.get("env", {})
        if isinstance(env, dict):
            # Filter out Windows system vars for canonical format
            result["env"] = {
                k: v
                for k, v in env.items()
                if k not in ("SystemRoot", "PROGRAMFILES", "SystemDrive")
            }

        # Get timeout if present
        timeout = server_config.get("startup_timeout_ms")
        if timeout is not None:
            result["timeout_ms"] = timeout

        # Infer type from args
        if "--stdio" in result.get("args", []):
            result["type"] = "stdio"

        return result

    def _format_codex_server(self, server_config: dict) -> tomlkit.items.Table:
        """Format a canonical server configuration for Codex TOML.

        Handles Windows-specific requirements.
        """
        table = tomlkit.table()

        command = server_config.get("command", "npx")
        args = list(server_config.get("args", []))
        env = dict(server_config.get("env", {}))

        is_windows = platform.system().lower() == "windows"

        if is_windows:
            # Windows requires cmd wrapper
            table["command"] = "cmd"

            # Build args with /c prefix
            codex_args = ["/c", command]

            # Ensure -y is present for npx
            if command == "npx" and "-y" not in args:
                codex_args.append("-y")

            codex_args.extend(args)
            table["args"] = codex_args

            # Add required Windows environment variables
            windows_env = {
                "SystemRoot": env.get("SystemRoot", "C:\\Windows"),
                "PROGRAMFILES": env.get("PROGRAMFILES", "C:\\Program Files"),
            }
            # Add user env vars
            for k, v in env.items():
                if k not in windows_env:
                    windows_env[k] = v

            table["env"] = windows_env
        else:
            # macOS/Linux - direct command
            table["command"] = command

            # Ensure -y is present for npx
            if command == "npx" and "-y" not in args:
                args = ["-y"] + args

            table["args"] = args
            table["env"] = env if env else {}

        # Add timeout
        timeout = server_config.get("timeout_ms") or server_config.get("startup_timeout_ms")
        table["startup_timeout_ms"] = timeout if timeout is not None else 60_000

        return table


class TomlConfigManager:
    """Manager for TOML-based MCP configurations."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.codex = CodexConfig()

    def read_config(self, path: Path, config_format: str) -> dict[str, Any]:
        """Read a config file based on its format.

        Args:
            path: Path to the config file
            config_format: Format type ('json', 'toml', etc.)

        Returns:
            Configuration dict with mcpServers key
        """
        if config_format == "toml":
            return self.codex.read_config(path)
        else:
            # Default to JSON
            import json

            if not path.exists():
                return {"mcpServers": {}}
            try:
                with open(path) as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                self.logger.error(f"Failed to read JSON config at {path}: {e}")
                return {"mcpServers": {}}

    def write_config(
        self,
        path: Path,
        config: dict[str, Any],
        config_format: str,
        preserve_existing: bool = True,
    ) -> bool:
        """Write a config file based on its format.

        Args:
            path: Path to the config file
            config: Configuration dict with mcpServers key
            config_format: Format type ('json', 'toml', etc.)
            preserve_existing: Whether to preserve non-MCP sections

        Returns:
            True if successful, False otherwise
        """
        if config_format == "toml":
            return self.codex.write_config(path, config, preserve_existing)
        else:
            # Default to JSON
            import json

            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(path, "w") as f:
                    json.dump(config, f, indent=2)
                return True
            except (OSError, TypeError) as e:
                self.logger.error(f"Failed to write JSON config at {path}: {e}")
                return False


def get_config_format(client_id: str, client_config: dict) -> str:
    """Determine the configuration format for a client.

    Args:
        client_id: Client identifier
        client_config: Client configuration dict

    Returns:
        Format string ('json', 'toml', etc.)
    """
    # Check explicit format
    config_format = client_config.get("config_format", "").lower()
    if config_format:
        return config_format

    # Infer from client ID
    if client_id in ("codex",):
        return "toml"

    # Default to JSON
    return "json"
