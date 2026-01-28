"""Backup system for MCP configuration files."""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir

logger = logging.getLogger(__name__)


class BackupManager:
    """Manages backups of MCP configuration files."""

    BACKUP_DIR_NAME = "backups"

    def __init__(self, backup_root: Path | None = None):
        """Initialize the backup manager.

        Args:
            backup_root: Root directory for backups. Defaults to ~/.mcp-sync/backups
        """
        if backup_root is None:
            backup_root = Path(user_config_dir("mcp-sync")) / self.BACKUP_DIR_NAME

        self.backup_root = backup_root
        self.logger = logging.getLogger(__name__)

    def backup_file(
        self,
        file_path: Path,
        *,
        _preserve_structure: bool = True,
    ) -> Path | None:
        """Create a backup of a file before modification.

        The backup is stored in a timestamped directory to preserve
        the original directory structure.

        Args:
            file_path: Path to the file to backup
            _preserve_structure: Internal flag for testing (preserves full path structure)

        Returns:
            Path to the backup file, or None if source doesn't exist
        """
        if not file_path.exists():
            return None

        try:
            # Create timestamped backup directory
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            backup_dir = self.backup_root / timestamp

            # Preserve directory structure relative to home
            # For paths like ~/.cursor/mcp.json, create backup/20240128_123456/.cursor/mcp.json
            try:
                # Try to get relative path from home
                relative_path = file_path.relative_to(Path.home())
            except ValueError:
                # If not under home, use just the filename for cleaner structure
                # This handles temp paths in tests gracefully
                relative_path = Path(file_path.name)

            backup_path = backup_dir / relative_path
            backup_path.parent.mkdir(parents=True, exist_ok=True)

            # Copy the file
            shutil.copy2(file_path, backup_path)

            self.logger.info(f"Backed up {file_path} to {backup_path}")
            return backup_path

        except Exception as e:
            self.logger.error(f"Failed to backup {file_path}: {e}")
            return None

    def list_backups(self) -> list[dict[str, Any]]:
        """List all available backups.

        Returns:
            List of backup information dicts with keys:
            - timestamp: Backup timestamp string
            - path: Path to backup directory
            - files: List of backed up files
        """
        if not self.backup_root.exists():
            return []

        backups = []

        for timestamp_dir in sorted(self.backup_root.iterdir(), reverse=True):
            if not timestamp_dir.is_dir():
                continue

            files = []
            for file_path in timestamp_dir.rglob("*"):
                if file_path.is_file():
                    try:
                        rel_path = file_path.relative_to(timestamp_dir)
                        files.append(str(rel_path))
                    except ValueError:
                        files.append(str(file_path))

            if files:
                backups.append(
                    {
                        "timestamp": timestamp_dir.name,
                        "path": timestamp_dir,
                        "files": files,
                    }
                )

        return backups

    def restore_backup(
        self,
        timestamp: str,
        file_path: str | None = None,
        *,
        restore_root: Path | None = None,
    ) -> Path | None:
        """Restore a file from backup.

        Args:
            timestamp: Backup timestamp to restore from
            file_path: Specific file to restore (relative path), or None to restore all
            restore_root: Root directory to restore to (defaults to home directory)

        Returns:
            Path to restored file, or None if failed
        """
        backup_dir = self.backup_root / timestamp

        if not backup_dir.exists():
            self.logger.error(f"Backup {timestamp} not found")
            return None

        # Determine restore root (for testing, can override home)
        target_root = restore_root if restore_root is not None else Path.home()

        try:
            if file_path:
                # Restore specific file
                backup_file = backup_dir / file_path
                if not backup_file.exists():
                    self.logger.error(f"File {file_path} not found in backup {timestamp}")
                    return None

                # Determine original location
                original_path = target_root / file_path
                original_path.parent.mkdir(parents=True, exist_ok=True)

                shutil.copy2(backup_file, original_path)
                self.logger.info(f"Restored {file_path} from backup {timestamp}")
                return original_path
            else:
                # Restore all files
                restored = []
                for backup_file in backup_dir.rglob("*"):
                    if backup_file.is_file():
                        rel_path = backup_file.relative_to(backup_dir)
                        original_path = target_root / rel_path
                        original_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(backup_file, original_path)
                        restored.append(original_path)

                self.logger.info(f"Restored {len(restored)} files from backup {timestamp}")
                return backup_dir

        except Exception as e:
            self.logger.error(f"Failed to restore backup {timestamp}: {e}")
            return None

    def cleanup_old_backups(self, keep_count: int = 10) -> int:
        """Remove old backups, keeping only the most recent ones.

        Args:
            keep_count: Number of backups to keep

        Returns:
            Number of backups removed
        """
        backups = self.list_backups()

        if len(backups) <= keep_count:
            return 0

        removed = 0
        for backup in backups[keep_count:]:
            try:
                shutil.rmtree(backup["path"])
                removed += 1
                self.logger.info(f"Removed old backup: {backup['timestamp']}")
            except Exception as e:
                self.logger.error(f"Failed to remove backup {backup['timestamp']}: {e}")

        return removed

    def get_backup_info(self, timestamp: str) -> dict[str, Any] | None:
        """Get detailed information about a specific backup.

        Args:
            timestamp: Backup timestamp

        Returns:
            Backup info dict or None if not found
        """
        backup_dir = self.backup_root / timestamp

        if not backup_dir.exists():
            return None

        files = []
        total_size = 0

        for file_path in backup_dir.rglob("*"):
            if file_path.is_file():
                stat = file_path.stat()
                total_size += stat.st_size
                try:
                    rel_path = file_path.relative_to(backup_dir)
                    files.append(
                        {
                            "path": str(rel_path),
                            "size": stat.st_size,
                            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        }
                    )
                except ValueError:
                    pass

        return {
            "timestamp": timestamp,
            "path": backup_dir,
            "file_count": len(files),
            "total_size": total_size,
            "files": files,
        }


def backup_before_sync(file_path: Path) -> Path | None:
    """Convenience function to backup a file before sync.

    Args:
        file_path: Path to the file to backup

    Returns:
        Path to backup file, or None if failed
    """
    manager = BackupManager()
    return manager.backup_file(file_path)
