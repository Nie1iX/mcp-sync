"""Interactive wizard for MCP sync operations."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from .clients.repository import ClientRepository
from .config.settings import get_settings
from .direct_sync import DirectSyncEngine
from .fuzzy_match import FuzzyClientMatcher
from .sync import SyncEngine
from .toml_support import TomlConfigManager

console = Console()
logger = logging.getLogger(__name__)


class InteractiveWizard:
    """Interactive wizard for MCP synchronization."""

    def __init__(self):
        self.settings = get_settings()
        self.repository = ClientRepository()
        self.toml_manager = TomlConfigManager()
        self.matcher = FuzzyClientMatcher(self.settings.get_client_definitions())
        self.direct_engine = DirectSyncEngine()

    def run(self):
        """Run the interactive wizard."""
        console.print(
            Panel(
                "[bold blue]Welcome to MCP Sync Interactive Wizard[/bold blue]",
                title="🧙 MCP Sync",
                border_style="blue",
            )
        )

        # Main menu
        while True:
            console.print("\n[bold]What would you like to do?[/bold]")
            console.print("  1. Direct sync (source → target)")
            console.print("  2. Full sync (using master config)")
            console.print("  3. Manage servers")
            console.print("  4. View status")
            console.print("  5. Exit")

            choice = Prompt.ask("Choose", choices=["1", "2", "3", "4", "5"], default="1")

            if choice == "1":
                self._direct_sync_flow()
            elif choice == "2":
                self._full_sync_flow()
            elif choice == "3":
                self._manage_servers_flow()
            elif choice == "4":
                self._view_status_flow()
            elif choice == "5":
                console.print("[bold green]Goodbye![/bold green]")
                break

    def _direct_sync_flow(self):
        """Flow for direct source-to-target sync."""
        console.print("\n[bold]Direct Sync[/bold]")
        console.print("Sync MCP servers directly from one client to another.\n")

        # Discover available clients
        discovered = self.repository.discover_clients()

        if not discovered:
            console.print("[yellow]No MCP clients found on this system.[/yellow]")
            return

        # Show available sources
        console.print("[bold]Available sources:[/bold]")
        for i, client in enumerate(discovered, 1):
            console.print(f"  {i}. {client['client_name']} ({client['path']})")
        console.print(f"  {len(discovered) + 1}. Custom path")

        # Get source selection
        source_choice = Prompt.ask(
            "Select source",
            choices=[str(i) for i in range(1, len(discovered) + 2)],
            default="1",
        )

        if int(source_choice) == len(discovered) + 1:
            # Custom path
            source_path = Path(Prompt.ask("Enter source file path"))
        else:
            source = discovered[int(source_choice) - 1]
            source_path = Path(source["path"])

        # Show available targets (excluding source)
        console.print("\n[bold]Available targets:[/bold]")
        targets = [c for c in discovered if c["path"] != str(source_path)]
        for i, client in enumerate(targets, 1):
            console.print(f"  {i}. {client['client_name']} ({client['path']})")
        console.print(f"  {len(targets) + 1}. Custom path")

        # Get target selection
        target_choice = Prompt.ask(
            "Select target",
            choices=[str(i) for i in range(1, len(targets) + 2)],
            default="1",
        )

        if int(target_choice) == len(targets) + 1:
            # Custom path
            target_path = Path(Prompt.ask("Enter target file path"))
        else:
            target = targets[int(target_choice) - 1]
            target_path = Path(target["path"])

        # Preview changes
        console.print("\n[bold]Previewing changes...[/bold]")
        result = self.direct_engine.sync_by_path(source_path, target_path, dry_run=True)

        if not result.get("success"):
            console.print(f"[bold red]Error:[/bold red] {result.get('error')}")
            return

        total_changes = result.get("total_changes", 0)

        if total_changes == 0:
            console.print("[green]No changes needed - configurations are already in sync.[/green]")
            return

        # Show preview
        table = Table(title="Changes Preview")
        table.add_column("Action", style="cyan")
        table.add_column("Server", style="green")

        for name in result.get("servers_to_add", []):
            table.add_row("[green]Add[/green]", name)
        for name in result.get("servers_to_update", []):
            table.add_row("[yellow]Update[/yellow]", name)
        for name in result.get("servers_to_remove", []):
            table.add_row("[red]Remove[/red]", name)

        console.print(table)

        # Confirm sync
        if not Confirm.ask(f"\nApply {total_changes} change(s)?", default=True):
            console.print("[dim]Sync cancelled.[/dim]")
            return

        # Perform sync
        result = self.direct_engine.sync_by_path(source_path, target_path, dry_run=False)

        if result.get("success"):
            console.print("[bold green]✓ Sync complete![/bold green]")
            if result.get("backup"):
                console.print(f"[dim]Backup: {result['backup']}[/dim]")
        else:
            console.print(f"[bold red]✗ Sync failed:[/bold red] {result.get('error')}")

    def _full_sync_flow(self):
        """Flow for full sync using master config."""
        console.print("\n[bold]Full Sync[/bold]")
        console.print("Sync all registered locations using master configuration.\n")

        sync_engine = SyncEngine(self.settings)

        # Preview
        console.print("[bold]Previewing changes...[/bold]")
        result = sync_engine.sync_all(dry_run=True)

        if not result.updated_locations and not result.conflicts:
            console.print("[green]All configurations are already in sync.[/green]")
            return

        if result.updated_locations:
            console.print(f"\nLocations to update: {len(result.updated_locations)}")
            for loc in result.updated_locations:
                console.print(f"  • {loc}")

        if result.conflicts:
            console.print(f"\n[yellow]Conflicts: {len(result.conflicts)}[/yellow]")

        # Confirm
        if not Confirm.ask("\nApply changes?", default=True):
            console.print("[dim]Sync cancelled.[/dim]")
            return

        # Perform sync
        result = sync_engine.sync_all(dry_run=False)

        if result.updated_locations:
            console.print(
                f"[bold green]✓ Updated {len(result.updated_locations)} location(s)[/bold green]"
            )

        if result.errors:
            console.print(f"[bold red]✗ {len(result.errors)} error(s)[/bold red]")

    def _manage_servers_flow(self):
        """Flow for managing servers."""
        console.print("\n[bold]Manage Servers[/bold]")

        sync_engine = SyncEngine(self.settings)

        status = sync_engine.get_server_status()

        # Show current servers
        all_servers = set()
        all_servers.update(status["global_servers"].keys())
        all_servers.update(status["project_servers"].keys())

        if not all_servers:
            console.print("[dim]No servers configured.[/dim]")
        else:
            console.print("\n[bold]Configured servers:[/bold]")
            for name in sorted(all_servers):
                sources = []
                if name in status["global_servers"]:
                    sources.append("global")
                if name in status["project_servers"]:
                    sources.append("project")

                source_str = ", ".join(sources)
                console.print(f"  • {name} ([dim]{source_str}[/dim])")

        # Actions
        console.print("\n[bold]Actions:[/bold]")
        console.print("  1. Add server")
        console.print("  2. Remove server")
        console.print("  3. Back")

        choice = Prompt.ask("Choose", choices=["1", "2", "3"], default="3")

        if choice == "1":
            self._add_server_flow(sync_engine)
        elif choice == "2":
            self._remove_server_flow(sync_engine)

    def _add_server_flow(self, sync_engine):
        """Flow for adding a server."""
        name = Prompt.ask("Server name")

        # Check if exists
        status = sync_engine.get_server_status()
        if name in status["global_servers"] or name in status["project_servers"]:
            console.print(f"[yellow]Server '{name}' already exists.[/yellow]")
            if not Confirm.ask("Overwrite?"):
                return

        # Get scope
        scope = Prompt.ask(
            "Scope",
            choices=["global", "project"],
            default="global",
        )

        # Get command
        command = Prompt.ask("Command (e.g., npx, python)")
        args_str = Prompt.ask("Arguments (space-separated, optional)", default="")
        env_str = Prompt.ask(
            "Environment variables (KEY=value, comma-separated, optional)", default=""
        )

        # Build config
        config: dict[str, Any] = {"command": command}

        if args_str:
            config["args"] = args_str.split()

        if env_str:
            env_vars = {}
            for pair in env_str.split(","):
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    env_vars[key.strip()] = value.strip()
            if env_vars:
                config["env"] = env_vars

        # Add server
        if scope == "global":
            sync_engine.add_server_to_global(name, config)
        else:
            sync_engine.add_server_to_project(name, config)

        console.print(f"[bold green]✓ Added '{name}' to {scope} config[/bold green]")

    def _remove_server_flow(self, sync_engine):
        """Flow for removing a server."""
        name = Prompt.ask("Server name to remove")

        # Check if exists
        status = sync_engine.get_server_status()
        sources = []
        if name in status["global_servers"]:
            sources.append("global")
        if name in status["project_servers"]:
            sources.append("project")

        if not sources:
            console.print(f"[yellow]Server '{name}' not found.[/yellow]")
            return

        # Get scope
        if len(sources) == 1:
            scope = sources[0]
        else:
            scope = Prompt.ask(
                "Remove from",
                choices=sources,
                default=sources[0],
            )

        # Confirm
        if not Confirm.ask(f"Remove '{name}' from {scope} config?", default=False):
            console.print("[dim]Cancelled.[/dim]")
            return

        # Remove
        if scope == "global":
            if sync_engine.remove_server_from_global(name):
                console.print(f"[bold green]✓ Removed '{name}' from global config[/bold green]")
            else:
                console.print(f"[bold red]✗ Failed to remove '{name}'[/bold red]")
        else:
            # Project removal
            console.print("[yellow]Project server removal not yet implemented.[/yellow]")

    def _view_status_flow(self):
        """Flow for viewing status."""
        console.print("\n[bold]MCP Sync Status[/bold]\n")

        sync_engine = SyncEngine(self.settings)
        status = sync_engine.get_server_status()

        # Global servers
        console.print("[bold]Global Servers:[/bold]")
        if status["global_servers"]:
            for name, config in status["global_servers"].items():
                cmd = config.get("command", "unknown")
                console.print(f"  • [cyan]{name}[/cyan]: {cmd}")
        else:
            console.print("  [dim]None[/dim]")
        if status.get("global_skills") is not None:
            skills = status["global_skills"] or []
            console.print(f"  [magenta]skills[/magenta]: {len(skills)}")
            for skill in skills:
                console.print(f"    [dim]- {skill}[/dim]")
        if status.get("global_allowed_commands") is not None:
            allowed = status["global_allowed_commands"] or []
            console.print(f"  [magenta]allowedCommands[/magenta]: {len(allowed)}")
            for command in allowed:
                console.print(f"    [dim]- {command}[/dim]")

        # Project servers
        console.print("\n[bold]Project Servers:[/bold]")
        if status["project_servers"]:
            for name, config in status["project_servers"].items():
                cmd = config.get("command", "unknown")
                console.print(f"  • [cyan]{name}[/cyan]: {cmd}")
        else:
            console.print("  [dim]None[/dim]")
        if status.get("project_skills") is not None:
            skills = status["project_skills"] or []
            console.print(f"  [magenta]skills[/magenta]: {len(skills)}")
            for skill in skills:
                console.print(f"    [dim]- {skill}[/dim]")
        if status.get("project_allowed_commands") is not None:
            allowed = status["project_allowed_commands"] or []
            console.print(f"  [magenta]allowedCommands[/magenta]: {len(allowed)}")
            for command in allowed:
                console.print(f"    [dim]- {command}[/dim]")

        # Location status
        console.print("\n[bold]Location Status:[/bold]")
        for location_name, servers in status["location_servers"].items():
            if servers == "error":
                console.print(f"  • [red]{location_name}: ERROR[/red]")
            elif servers:
                console.print(f"  • [green]{location_name}[/green]: {len(servers)} server(s)")
            else:
                console.print(f"  • [dim]{location_name}: No servers[/dim]")

        import sys

        if sys.stdin.isatty():
            input("\nPress Enter to continue...")
