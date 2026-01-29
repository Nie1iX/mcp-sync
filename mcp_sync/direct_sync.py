"""Direct sync functionality - sync from source to target without intermediate storage."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.panel import Panel

from .backup import backup_before_sync
from .clients.repository import ClientRepository
from .config.settings import get_settings
from .fuzzy_match import resolve_client_by_keyword
from .toml_support import TomlConfigManager

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)
console = Console()


class DirectSyncEngine:
    """Engine for direct source-to-target synchronization."""

    def __init__(self):
        self.settings = get_settings()
        self.repository = ClientRepository()
        self.toml_manager = TomlConfigManager()
        self.logger = logging.getLogger(__name__)

    def sync_by_keyword(
        self,
        source_keyword: str,
        target_keyword: str,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Sync from source to target using keyword matching.

        Args:
            source_keyword: Keyword for source client (e.g., "vscode", "claude")
            target_keyword: Keyword for target client (e.g., "cursor", "codex")
            dry_run: If True, preview changes without applying

        Returns:
            Result dict with status information
        """
        client_definitions = self.settings.get_client_definitions()

        # Resolve source
        source_id = resolve_client_by_keyword(source_keyword, client_definitions)
        if not source_id:
            return {
                "success": False,
                "error": f"Unknown source keyword: '{source_keyword}'",
            }

        # Resolve target
        target_id = resolve_client_by_keyword(target_keyword, client_definitions)
        if not target_id:
            return {
                "success": False,
                "error": f"Unknown target keyword: '{target_keyword}'",
            }

        # Get client configs
        source_config = client_definitions.clients.get(source_id)
        target_config = client_definitions.clients.get(target_id)

        if not source_config:
            return {
                "success": False,
                "error": f"Source client '{source_id}' not found in definitions",
            }

        if not target_config:
            return {
                "success": False,
                "error": f"Target client '{target_id}' not found in definitions",
            }

        # Get paths
        source_path = self._get_client_path(source_id, source_config)
        target_path = self._get_client_path(target_id, target_config)

        if not source_path:
            return {
                "success": False,
                "error": f"Could not determine path for source '{source_id}'",
            }

        if not target_path:
            return {
                "success": False,
                "error": f"Could not determine path for target '{target_id}'",
            }

        # Check source exists
        if not source_path.exists():
            return {
                "success": False,
                "error": f"Source configuration not found: {source_path}",
            }

        # Perform sync
        return self._sync_paths(
            source_path=source_path,
            target_path=target_path,
            source_id=source_id,
            target_id=target_id,
            dry_run=dry_run,
        )

    def sync_by_path(
        self,
        source_path: Path,
        target_path: Path,
        source_format: str | None = None,
        target_format: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Sync from source path to target path.

        Args:
            source_path: Path to source configuration
            target_path: Path to target configuration
            source_format: Source format ('json', 'toml'), or None to infer
            target_format: Target format ('json', 'toml'), or None to infer
            dry_run: If True, preview changes without applying

        Returns:
            Result dict with status information
        """
        # Infer formats if not provided
        if source_format is None:
            source_format = "toml" if source_path.suffix == ".toml" else "json"
        if target_format is None:
            target_format = "toml" if target_path.suffix == ".toml" else "json"

        # Check source exists
        if not source_path.exists():
            return {
                "success": False,
                "error": f"Source configuration not found: {source_path}",
            }

        return self._sync_paths(
            source_path=source_path,
            target_path=target_path,
            source_id=str(source_path),
            target_id=str(target_path),
            source_format=source_format,
            target_format=target_format,
            dry_run=dry_run,
        )

    def _get_client_path(self, client_id: str, client_config: Any) -> Path | None:
        """Get the configuration file path for a client."""
        import platform

        system = platform.system().lower()
        platform_name = {"darwin": "darwin", "windows": "windows", "linux": "linux"}.get(
            system, "linux"
        )

        # Try primary paths
        if client_config.paths:
            path_template = client_config.paths.get(platform_name)
            if path_template:
                return self._expand_path(path_template)

        # Try fallback paths
        if client_config.fallback_paths:
            path_template = client_config.fallback_paths.get(platform_name)
            if path_template:
                return self._expand_path(path_template)

        return None

    def _expand_path(self, path_template: str) -> Path:
        """Expand a path template with environment variables."""
        import os

        if path_template.startswith("~/"):
            path_template = str(Path.home()) + path_template[1:]

        if "%" in path_template:
            path_template = os.path.expandvars(path_template)

        return Path(path_template)

    def _sync_paths(
        self,
        source_path: Path,
        target_path: Path,
        source_id: str,
        target_id: str,
        source_format: str | None = None,
        target_format: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Perform the actual synchronization between paths."""

        # Infer formats from paths if not provided
        if source_format is None:
            source_format = "toml" if source_path.suffix == ".toml" else "json"
        if target_format is None:
            target_format = "toml" if target_path.suffix == ".toml" else "json"

        # Read source config
        source_data = self.toml_manager.read_config(source_path, source_format)
        source_servers = source_data.get("mcpServers", {})

        if not source_servers:
            return {
                "success": False,
                "error": f"No MCP servers found in source: {source_path}",
            }

        # Read target config (if exists)
        target_data = self.toml_manager.read_config(target_path, target_format)
        target_servers = target_data.get("mcpServers", {})

        # Calculate changes
        servers_to_add = set(source_servers.keys()) - set(target_servers.keys())
        servers_to_update = {
            name
            for name in source_servers.keys()
            if name in target_servers and source_servers[name] != target_servers[name]
        }
        servers_to_remove = set(target_servers.keys()) - set(source_servers.keys())
        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "source": str(source_path),
                "target": str(target_path),
                "servers_to_add": sorted(servers_to_add),
                "servers_to_update": sorted(servers_to_update),
                "servers_to_remove": sorted(servers_to_remove),
                "total_changes": len(servers_to_add)
                + len(servers_to_update)
                + len(servers_to_remove)
            }

        # Create backup of target
        backup_path = None
        if target_path.exists():
            backup_path = backup_before_sync(target_path)
            if backup_path:
                console.print(f"[dim]Backup created: {backup_path}[/dim]")

        # Merge servers
        new_servers = dict(target_servers)
        new_servers.update(source_servers)

        # Write target config
        new_data = {"mcpServers": new_servers}
        success = self.toml_manager.write_config(
            target_path, new_data, target_format, preserve_existing=True
        )

        if not success:
            return {
                "success": False,
                "error": f"Failed to write target configuration: {target_path}",
            }

        return {
            "success": True,
            "source": str(source_path),
            "target": str(target_path),
            "backup": str(backup_path) if backup_path else None,
            "servers_added": sorted(servers_to_add),
            "servers_updated": sorted(servers_to_update),
            "servers_removed": sorted(servers_to_remove),
            "total_changes": len(servers_to_add)
            + len(servers_to_update)
            + len(servers_to_remove)
        }


def format_sync_result(result: dict[str, Any]) -> None:
    """Format and print sync result using Rich."""
    if not result.get("success"):
        console.print(
            Panel(
                f"[bold red]Sync Failed[/bold red]\n{result.get('error', 'Unknown error')}",
                title="Error",
                border_style="red",
            )
        )
        return

    if result.get("dry_run"):
        console.print(
            Panel(
                "[bold yellow]DRY RUN - No changes made[/bold yellow]",
                title="Preview",
                border_style="yellow",
            )
        )

        if result.get("total_changes", 0) == 0:
            console.print("[green]No changes needed - configurations are in sync[/green]")
            return

        if result.get("servers_to_add"):
            console.print(f"\n[green]Servers to add ({len(result['servers_to_add'])}):[/green]")
            for name in result["servers_to_add"]:
                console.print(f"  + {name}")

        if result.get("servers_to_update"):
            console.print(
                f"\n[yellow]Servers to update ({len(result['servers_to_update'])}):[/yellow]"
            )
            for name in result["servers_to_update"]:
                console.print(f"  ~ {name}")

        if result.get("servers_to_remove"):
            console.print(f"\n[red]Servers to remove ({len(result['servers_to_remove'])}):[/red]")
            for name in result["servers_to_remove"]:
                console.print(f"  - {name}")

    else:
        console.print(
            Panel(
                "[bold green]Sync Complete![/bold green]",
                title="Success",
                border_style="green",
            )
        )

        console.print(f"Source: [cyan]{result['source']}[/cyan]")
        console.print(f"Target: [cyan]{result['target']}[/cyan]")

        if result.get("backup"):
            console.print(f"Backup: [dim]{result['backup']}[/dim]")

        if result.get("total_changes", 0) == 0:
            console.print("\n[dim]No changes needed[/dim]")
        else:
            console.print(f"\n[bold]Changes ({result['total_changes']}):[/bold]")

            if result.get("servers_added"):
                console.print(f"  [green]+ Added {len(result['servers_added'])} server(s)[/green]")

            if result.get("servers_updated"):
                console.print(
                    f"  [yellow]~ Updated {len(result['servers_updated'])} server(s)[/yellow]"
                )

            if result.get("servers_removed"):
                console.print(f"  [red]- Removed {len(result['servers_removed'])} server(s)[/red]")
