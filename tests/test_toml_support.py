"""Tests for TOML configuration support."""

import json
from unittest.mock import patch

import tomlkit

from mcp_sync.toml_support import (
    CodexConfig,
    TomlConfigManager,
    get_config_format,
)


class TestCodexConfig:
    """Tests for CodexConfig class."""

    def test_read_config_empty_file(self, tmp_path):
        """Test reading empty/non-existent config file."""
        config_path = tmp_path / "config.toml"
        codex = CodexConfig()

        result = codex.read_config(config_path)

        assert result == {"mcpServers": {}}

    def test_read_config_with_servers(self, tmp_path):
        """Test reading config with MCP servers."""
        config_path = tmp_path / "config.toml"

        # Create TOML content
        doc = tomlkit.document()
        doc["mcp_servers"] = tomlkit.table()
        doc["mcp_servers"]["test-server"] = tomlkit.table()
        doc["mcp_servers"]["test-server"]["command"] = "npx"
        doc["mcp_servers"]["test-server"]["args"] = ["-y", "test-package"]
        doc["mcp_servers"]["test-server"]["env"] = {"API_KEY": "test"}
        doc["mcp_servers"]["test-server"]["startup_timeout_ms"] = 60_000

        config_path.write_text(tomlkit.dumps(doc))

        codex = CodexConfig()
        result = codex.read_config(config_path)

        assert "mcpServers" in result
        assert "test-server" in result["mcpServers"]
        server = result["mcpServers"]["test-server"]
        assert server["command"] == "npx"
        assert server["args"] == ["-y", "test-package"]
        assert server["env"] == {"API_KEY": "test"}

    def test_read_config_windows_cmd_wrapper(self, tmp_path):
        """Test reading Windows-style cmd wrapper config."""
        config_path = tmp_path / "config.toml"

        doc = tomlkit.document()
        doc["mcp_servers"] = tomlkit.table()
        doc["mcp_servers"]["windows-server"] = tomlkit.table()
        doc["mcp_servers"]["windows-server"]["command"] = "cmd"
        doc["mcp_servers"]["windows-server"]["args"] = ["/c", "npx", "-y", "package"]
        doc["mcp_servers"]["windows-server"]["env"] = {
            "SystemRoot": "C:\\Windows",
            "API_KEY": "test",
        }

        config_path.write_text(tomlkit.dumps(doc))

        codex = CodexConfig()
        result = codex.read_config(config_path)

        server = result["mcpServers"]["windows-server"]
        # Should extract actual command from cmd wrapper
        assert server["command"] == "npx"
        assert server["args"] == ["-y", "package"]
        # Should filter out Windows system vars
        assert "SystemRoot" not in server["env"]
        assert server["env"] == {"API_KEY": "test"}

    def test_write_config_new_file(self, tmp_path):
        """Test writing config to new file."""
        config_path = tmp_path / "config.toml"

        config = {
            "mcpServers": {
                "new-server": {
                    "command": "python",
                    "args": ["/path/to/server.py"],
                    "env": {"VAR": "value"},
                }
            }
        }

        codex = CodexConfig()
        success = codex.write_config(config_path, config)

        assert success is True
        assert config_path.exists()

        # Verify content
        content = config_path.read_text()
        doc = tomlkit.parse(content)
        assert "mcp_servers" in doc
        assert "new-server" in doc["mcp_servers"]

    def test_write_config_preserves_existing(self, tmp_path):
        """Test that writing config preserves non-MCP sections."""
        config_path = tmp_path / "config.toml"

        # Create existing config with other sections
        doc = tomlkit.document()
        doc["other_section"] = tomlkit.table()
        doc["other_section"]["key"] = "value"
        doc["mcp_servers"] = tomlkit.table()

        config_path.write_text(tomlkit.dumps(doc))

        config = {
            "mcpServers": {
                "test-server": {
                    "command": "npx",
                    "args": ["-y", "package"],
                }
            }
        }

        codex = CodexConfig()
        codex.write_config(config_path, config, preserve_existing=True)

        # Verify other_section is preserved
        content = config_path.read_text()
        doc = tomlkit.parse(content)
        assert "other_section" in doc
        assert doc["other_section"]["key"] == "value"

    @patch("platform.system")
    def test_write_config_windows_format(self, mock_system, tmp_path):
        """Test Windows-specific config format."""
        mock_system.return_value = "Windows"

        config_path = tmp_path / "config.toml"
        config = {
            "mcpServers": {
                "test-server": {
                    "command": "npx",
                    "args": ["package"],
                    "env": {"API_KEY": "test"},
                }
            }
        }

        codex = CodexConfig()
        codex.write_config(config_path, config)

        content = config_path.read_text()
        doc = tomlkit.parse(content)
        server = doc["mcp_servers"]["test-server"]

        # Should use cmd wrapper on Windows
        assert server["command"] == "cmd"
        assert server["args"][0] == "/c"
        assert "SystemRoot" in server["env"]
        assert "PROGRAMFILES" in server["env"]

    @patch("platform.system")
    def test_write_config_macos_format(self, mock_system, tmp_path):
        """Test macOS/Linux config format."""
        mock_system.return_value = "Darwin"

        config_path = tmp_path / "config.toml"
        config = {
            "mcpServers": {
                "test-server": {
                    "command": "npx",
                    "args": ["package"],
                }
            }
        }

        codex = CodexConfig()
        codex.write_config(config_path, config)

        content = config_path.read_text()
        doc = tomlkit.parse(content)
        server = doc["mcp_servers"]["test-server"]

        # Should use direct command on macOS
        assert server["command"] == "npx"
        assert "/c" not in server["args"]

    def test_infer_stdio_type(self, tmp_path):
        """Test that --stdio arg infers type."""
        config_path = tmp_path / "config.toml"

        doc = tomlkit.document()
        doc["mcp_servers"] = tomlkit.table()
        doc["mcp_servers"]["stdio-server"] = tomlkit.table()
        doc["mcp_servers"]["stdio-server"]["command"] = "npx"
        doc["mcp_servers"]["stdio-server"]["args"] = ["-y", "package", "--stdio"]

        config_path.write_text(tomlkit.dumps(doc))

        codex = CodexConfig()
        result = codex.read_config(config_path)

        assert result["mcpServers"]["stdio-server"]["type"] == "stdio"


class TestTomlConfigManager:
    """Tests for TomlConfigManager class."""

    def test_read_json_config(self, tmp_path):
        """Test reading JSON config."""
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"mcpServers": {"test": {"command": "npx"}}}))

        manager = TomlConfigManager()
        result = manager.read_config(config_path, "json")

        assert result["mcpServers"]["test"]["command"] == "npx"

    def test_read_toml_config(self, tmp_path):
        """Test reading TOML config."""
        config_path = tmp_path / "config.toml"

        doc = tomlkit.document()
        doc["mcp_servers"] = tomlkit.table()
        doc["mcp_servers"]["test"] = tomlkit.table()
        doc["mcp_servers"]["test"]["command"] = "python"

        config_path.write_text(tomlkit.dumps(doc))

        manager = TomlConfigManager()
        result = manager.read_config(config_path, "toml")

        assert result["mcpServers"]["test"]["command"] == "python"

    def test_write_json_config(self, tmp_path):
        """Test writing JSON config."""
        config_path = tmp_path / "config.json"
        config = {"mcpServers": {"test": {"command": "npx"}}}

        manager = TomlConfigManager()
        success = manager.write_config(config_path, config, "json")

        assert success is True
        assert json.loads(config_path.read_text()) == config

    def test_write_toml_config(self, tmp_path):
        """Test writing TOML config."""
        config_path = tmp_path / "config.toml"
        config = {"mcpServers": {"test": {"command": "npx"}}}

        manager = TomlConfigManager()
        success = manager.write_config(config_path, config, "toml")

        assert success is True
        assert config_path.exists()


class TestGetConfigFormat:
    """Tests for get_config_format function."""

    def test_explicit_format(self):
        """Test explicit config_format in client config."""
        client_config = {"config_format": "toml"}
        assert get_config_format("test", client_config) == "toml"

    def test_codex_client(self):
        """Test Codex client auto-detection."""
        assert get_config_format("codex", {}) == "toml"

    def test_default_json(self):
        """Test default format is JSON."""
        assert get_config_format("unknown", {}) == "json"
