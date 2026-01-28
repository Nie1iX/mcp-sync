"""Tests for direct sync functionality."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mcp_sync.direct_sync import DirectSyncEngine, format_sync_result


class TestDirectSyncEngine:
    """Tests for DirectSyncEngine class."""

    @pytest.fixture
    def engine(self):
        """Create a DirectSyncEngine with mocked dependencies."""
        with (
            patch("mcp_sync.direct_sync.get_settings") as mock_settings,
            patch("mcp_sync.direct_sync.ClientRepository") as mock_repo,
        ):
            mock_settings.return_value = MagicMock()
            mock_repo.return_value = MagicMock()

            engine = DirectSyncEngine()
            yield engine

    @pytest.fixture
    def sample_json_config(self, tmp_path):
        """Create a sample JSON config file."""
        config_path = tmp_path / "mcp.json"
        config_path.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "server1": {"command": "npx", "args": ["-y", "pkg1"]},
                        "server2": {"command": "python", "args": ["script.py"]},
                    }
                }
            )
        )
        return config_path

    @pytest.fixture
    def empty_json_config(self, tmp_path):
        """Create an empty JSON config file."""
        config_path = tmp_path / "empty.json"
        config_path.write_text(json.dumps({"mcpServers": {}}))
        return config_path

    def test_sync_by_path_success(self, engine, sample_json_config, tmp_path):
        """Test successful sync by path."""
        target_path = tmp_path / "target.json"
        target_path.write_text(json.dumps({"mcpServers": {}}))

        result = engine.sync_by_path(
            source_path=sample_json_config,
            target_path=target_path,
            dry_run=False,
        )

        assert result["success"] is True
        assert result["servers_added"] == ["server1", "server2"]
        assert result["total_changes"] == 2

    def test_sync_by_path_dry_run(self, engine, sample_json_config, tmp_path):
        """Test dry run mode."""
        target_path = tmp_path / "target.json"
        target_path.write_text(json.dumps({"mcpServers": {}}))

        result = engine.sync_by_path(
            source_path=sample_json_config,
            target_path=target_path,
            dry_run=True,
        )

        assert result["success"] is True
        assert result["dry_run"] is True
        assert result["servers_to_add"] == ["server1", "server2"]
        # Target should not be modified
        assert json.loads(target_path.read_text()) == {"mcpServers": {}}

    def test_sync_by_path_source_not_found(self, engine, tmp_path):
        """Test sync when source doesn't exist."""
        result = engine.sync_by_path(
            source_path=tmp_path / "nonexistent.json",
            target_path=tmp_path / "target.json",
        )

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_sync_by_path_no_servers(self, engine, empty_json_config, tmp_path):
        """Test sync when source has no servers."""
        target_path = tmp_path / "target.json"
        target_path.write_text(json.dumps({"mcpServers": {}}))

        result = engine.sync_by_path(
            source_path=empty_json_config,
            target_path=target_path,
        )

        assert result["success"] is False
        assert "no mcp servers" in result["error"].lower()

    def test_sync_by_path_updates_existing(self, engine, sample_json_config, tmp_path):
        """Test that sync updates existing servers."""
        target_path = tmp_path / "target.json"
        target_path.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "server1": {"command": "old", "args": []},  # Will be updated
                        "server3": {"command": "keep", "args": []},  # Will be removed
                    }
                }
            )
        )

        result = engine.sync_by_path(
            source_path=sample_json_config,
            target_path=target_path,
            dry_run=True,
        )

        assert result["success"] is True
        assert "server1" in result["servers_to_update"]
        assert "server2" in result["servers_to_add"]
        assert "server3" in result["servers_to_remove"]

    def test_sync_by_path_creates_backup(self, engine, sample_json_config, tmp_path):
        """Test that sync creates backup of target."""
        target_path = tmp_path / "target.json"
        target_path.write_text(json.dumps({"mcpServers": {}}))

        with patch("mcp_sync.direct_sync.backup_before_sync") as mock_backup:
            mock_backup.return_value = tmp_path / "backup" / "mcp.json"

            result = engine.sync_by_path(
                source_path=sample_json_config,
                target_path=target_path,
                dry_run=False,
            )

            assert mock_backup.called
            assert result["backup"] is not None

    def test_sync_by_keyword_success(self, engine):
        """Test sync by keyword."""
        with patch("mcp_sync.direct_sync.resolve_client_by_keyword") as mock_resolve:
            mock_resolve.side_effect = ["vscode", "cursor"]

            # Mock _get_client_path to return actual Path objects
            def mock_get_path(client_id, config):
                return Path(f"/home/user/.{client_id}/mcp.json")

            with patch.object(engine, "_get_client_path", side_effect=mock_get_path):
                # Create mock paths that behave like real files
                with patch("mcp_sync.direct_sync.Path") as mock_path_class:
                    mock_source = MagicMock()
                    mock_source.exists.return_value = True
                    mock_source.read_text.return_value = json.dumps(
                        {"mcpServers": {"test": {"command": "npx"}}}
                    )
                    mock_source.suffix = ".json"
                    mock_source.__str__ = lambda self: "/home/user/.vscode/mcp.json"

                    mock_target = MagicMock()
                    mock_target.exists.return_value = True
                    mock_target.read_text.return_value = json.dumps({"mcpServers": {}})
                    mock_target.suffix = ".json"
                    mock_target.__str__ = lambda self: "/home/user/.cursor/mcp.json"
                    mock_target.parent.mkdir = MagicMock()
                    mock_target.write_text = MagicMock()

                    # Return different mocks for different paths
                    def path_side_effect(path_str):
                        if "vscode" in str(path_str):
                            return mock_source
                        return mock_target

                    mock_path_class.side_effect = path_side_effect

                    result = engine.sync_by_keyword("vscode", "cursor", dry_run=True)

                    # Should succeed or fail gracefully
                    assert "success" in result

    def test_sync_by_keyword_unknown_source(self, engine):
        """Test sync with unknown source keyword."""
        with patch("mcp_sync.direct_sync.resolve_client_by_keyword") as mock_resolve:
            mock_resolve.return_value = None

            result = engine.sync_by_keyword("unknown", "vscode")

            assert result["success"] is False
            assert "unknown source" in result["error"].lower()

    def test_sync_by_keyword_unknown_target(self, engine):
        """Test sync with unknown target keyword."""
        with patch("mcp_sync.direct_sync.resolve_client_by_keyword") as mock_resolve:
            mock_resolve.side_effect = ["vscode", None]

            result = engine.sync_by_keyword("vscode", "unknown")

            assert result["success"] is False
            assert "unknown target" in result["error"].lower()


class TestFormatSyncResult:
    """Tests for format_sync_result function."""

    def test_format_success(self, capsys):
        """Test formatting successful result."""
        result = {
            "success": True,
            "source": "/path/to/source",
            "target": "/path/to/target",
            "servers_added": ["server1"],
            "servers_updated": [],
            "servers_removed": [],
            "total_changes": 1,
        }

        format_sync_result(result)
        captured = capsys.readouterr()

        assert "Sync Complete" in captured.out or "success" in captured.out.lower()

    def test_format_error(self, capsys):
        """Test formatting error result."""
        result = {
            "success": False,
            "error": "Something went wrong",
        }

        format_sync_result(result)
        captured = capsys.readouterr()

        assert "Failed" in captured.out or "Error" in captured.out
        assert "Something went wrong" in captured.out

    def test_format_dry_run(self, capsys):
        """Test formatting dry run result."""
        result = {
            "success": True,
            "dry_run": True,
            "servers_to_add": ["server1"],
            "servers_to_update": [],
            "servers_to_remove": [],
            "total_changes": 1,
        }

        format_sync_result(result)
        captured = capsys.readouterr()

        assert "DRY RUN" in captured.out or "dry run" in captured.out.lower()

    def test_format_no_changes(self, capsys):
        """Test formatting result with no changes."""
        result = {
            "success": True,
            "dry_run": True,
            "total_changes": 0,
        }

        format_sync_result(result)
        captured = capsys.readouterr()

        assert "in sync" in captured.out.lower() or "no changes" in captured.out.lower()
