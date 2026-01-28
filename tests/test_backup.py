"""Tests for backup system."""

import json
from unittest.mock import patch

import pytest

from mcp_sync.backup import BackupManager, backup_before_sync


class TestBackupManager:
    """Tests for BackupManager class."""

    @pytest.fixture
    def backup_manager(self, tmp_path):
        """Create a backup manager with temp directory."""
        return BackupManager(backup_root=tmp_path / "backups")

    @pytest.fixture
    def sample_config(self, tmp_path):
        """Create a sample config file."""
        config_path = tmp_path / "test" / "mcp.json"
        config_path.parent.mkdir(parents=True)
        config_path.write_text(json.dumps({"mcpServers": {"test": {"command": "npx"}}}))
        return config_path

    def test_backup_file_creates_backup(self, backup_manager, sample_config):
        """Test that backup_file creates a backup."""
        backup_path = backup_manager.backup_file(sample_config)

        assert backup_path is not None
        assert backup_path.exists()
        assert backup_path.read_text() == sample_config.read_text()

    def test_backup_file_returns_none_for_nonexistent(self, backup_manager, tmp_path):
        """Test that backup_file returns None for non-existent file."""
        nonexistent = tmp_path / "nonexistent.json"
        backup_path = backup_manager.backup_file(nonexistent)

        assert backup_path is None

    def test_backup_preserves_directory_structure(self, backup_manager, sample_config, tmp_path):
        """Test that backup preserves directory structure."""
        backup_path = backup_manager.backup_file(sample_config)

        # Backup should be in timestamped directory
        # For temp paths not under home, structure is: backups/<timestamp>/<filename>
        assert backup_path.name == "mcp.json"
        # Parent should be the timestamp directory
        assert backup_path.parent.parent == backup_manager.backup_root

    def test_list_backups_empty(self, backup_manager):
        """Test listing backups when none exist."""
        backups = backup_manager.list_backups()
        assert backups == []

    def test_list_backups_with_backups(self, backup_manager, sample_config):
        """Test listing backups."""
        backup_manager.backup_file(sample_config)
        backup_manager.backup_file(sample_config)

        backups = backup_manager.list_backups()

        assert len(backups) == 2
        assert all("timestamp" in b for b in backups)
        assert all("files" in b for b in backups)

    def test_restore_backup_specific_file(self, backup_manager, sample_config, tmp_path):
        """Test restoring a specific file from backup."""
        original_content = sample_config.read_text()

        # Create backup
        backup_path = backup_manager.backup_file(sample_config)

        # Get the timestamp from the actual backup path
        # Structure: backups/<timestamp>/mcp.json (for temp paths)
        timestamp = backup_path.parent.name

        # Modify original
        sample_config.write_text(json.dumps({"modified": True}))

        # For temp paths, the file is stored directly in timestamp dir
        rel_path = backup_path.name  # Just the filename

        # Restore with explicit restore_root for testing
        restored_path = backup_manager.restore_backup(timestamp, rel_path, restore_root=tmp_path)

        assert restored_path is not None
        # Check that file was restored to the specified restore_root
        restored_file = tmp_path / rel_path
        assert restored_file.exists()
        assert restored_file.read_text() == original_content

    def test_restore_backup_all_files(self, backup_manager, sample_config, tmp_path):
        """Test restoring all files from backup."""
        # Create backup
        backup1 = backup_manager.backup_file(sample_config)

        # Get timestamp from backup path
        # Structure: backups/<timestamp>/mcp.json
        timestamp = backup1.parent.name

        # Modify original
        sample_config.write_text("{}")

        # Restore all from that timestamp with explicit restore_root
        result = backup_manager.restore_backup(timestamp, restore_root=tmp_path)

        assert result is not None
        # Check that file was restored to the specified restore_root
        restored_file = tmp_path / backup1.name
        assert restored_file.exists()

    def test_restore_nonexistent_backup(self, backup_manager):
        """Test restoring non-existent backup."""
        result = backup_manager.restore_backup("nonexistent")
        assert result is None

    def test_cleanup_old_backups(self, backup_manager, sample_config):
        """Test cleaning up old backups."""
        # Create 5 backups
        for _ in range(5):
            backup_manager.backup_file(sample_config)

        # Cleanup, keeping only 2
        removed = backup_manager.cleanup_old_backups(keep_count=2)

        assert removed == 3

        backups = backup_manager.list_backups()
        assert len(backups) == 2

    def test_cleanup_no_old_backups(self, backup_manager, sample_config):
        """Test cleanup when no old backups to remove."""
        backup_manager.backup_file(sample_config)

        removed = backup_manager.cleanup_old_backups(keep_count=5)

        assert removed == 0

    def test_get_backup_info(self, backup_manager, sample_config):
        """Test getting backup info."""
        backup_path = backup_manager.backup_file(sample_config)
        # Structure: backups/<timestamp>/mcp.json
        timestamp = backup_path.parent.name

        info = backup_manager.get_backup_info(timestamp)

        assert info is not None
        assert info["timestamp"] == timestamp
        assert info["file_count"] >= 1
        assert info["total_size"] >= 0  # File could be empty
        assert "files" in info

    def test_get_backup_info_nonexistent(self, backup_manager):
        """Test getting info for non-existent backup."""
        info = backup_manager.get_backup_info("nonexistent")
        assert info is None


class TestBackupBeforeSync:
    """Tests for backup_before_sync convenience function."""

    def test_backup_before_sync(self, tmp_path):
        """Test the convenience function."""
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"test": True}))

        with patch("mcp_sync.backup.BackupManager") as mock_manager_cls:
            mock_instance = mock_manager_cls.return_value
            mock_instance.backup_file.return_value = tmp_path / "backup" / "config.json"

            result = backup_before_sync(config_path)

            assert mock_instance.backup_file.called
            assert result is not None
