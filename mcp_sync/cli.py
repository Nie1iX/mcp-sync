"""Modern CLI implementation using Typer and Rich."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Annotated

import click
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from .backup import BackupManager
from .clients.repository import ClientRepository
from .config.settings import get_settings
from .direct_sync import DirectSyncEngine, format_sync_result
from .interactive import InteractiveWizard
from .sync import SyncEngine

# Initialize Rich console
console = Console()

# Create Typer app
app = typer.Typer(
    name="mcp-sync",
    help="Sync MCP (Model Context Protocol) configurations across AI tools",
    rich_markup_mode="rich",
)

# State for verbose mode
state = {"verbose": False}


def setup_logging(verbose: bool = False):
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
    )


@app.callback()
def main_callback(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output")] = False,
):
    """MCP Sync - Synchronize MCP configurations across AI tools."""
    state["verbose"] = verbose
    setup_logging(verbose)


@app.command()
def scan():
    """🔍 Auto-discover known MCP configs on your system."""
    console.print(Panel("[bold blue]Scanning for MCP configurations...", title="Scan"))

    repository = ClientRepository()
    discovered = repository.discover_clients()

    if not discovered:
        console.print("[yellow]No MCP clients found on this system.[/yellow]")
        raise typer.Exit(1)

    table = Table(title="Discovered MCP Clients")
    table.add_column("Client", style="cyan")
    table.add_column("Path", style="green")
    table.add_column("Type", style="magenta")

    for client in discovered:
        table.add_row(
            client["client_name"],
            client["path"],
            client["config_type"],
        )

    console.print(table)
    console.print(f"\n[bold green]Found {len(discovered)} client(s)[/bold green]")


@app.command()
def status():
    """📊 Show current sync status across all locations."""
    console.print(Panel("[bold blue]MCP Sync Status", title="Status"))

    settings = get_settings()
    sync_engine = SyncEngine(settings)
    server_status = sync_engine.get_server_status()

    # Global servers
    global_tree = Tree("[bold]Global Servers[/bold]")
    global_servers = server_status["global_servers"]
    if global_servers:
        for name, config in global_servers.items():
            cmd = config.get("command", "unknown")
            global_tree.add(f"[cyan]{name}[/cyan]: {cmd}")
    else:
        global_tree.add("[dim]None configured[/dim]")
    if server_status.get("global_skills") is not None:
        skills = server_status["global_skills"] or []
        skills_node = global_tree.add(f"[magenta]skills[/magenta]: {len(skills)}")
        for skill in skills:
            skills_node.add(f"[dim]{skill}[/dim]")
    if server_status.get("global_allowed_commands") is not None:
        allowed = server_status["global_allowed_commands"] or []
        allowed_node = global_tree.add(f"[magenta]allowedCommands[/magenta]: {len(allowed)}")
        for command in allowed:
            allowed_node.add(f"[dim]{command}[/dim]")
    console.print(global_tree)

    # Project servers
    project_tree = Tree("[bold]Project Servers[/bold]")
    project_servers = server_status["project_servers"]
    if project_servers:
        for name, config in project_servers.items():
            cmd = config.get("command", "unknown")
            project_tree.add(f"[cyan]{name}[/cyan]: {cmd}")
    else:
        project_tree.add("[dim]None configured[/dim]")
    if server_status.get("project_skills") is not None:
        skills = server_status["project_skills"] or []
        skills_node = project_tree.add(f"[magenta]skills[/magenta]: {len(skills)}")
        for skill in skills:
            skills_node.add(f"[dim]{skill}[/dim]")
    if server_status.get("project_allowed_commands") is not None:
        allowed = server_status["project_allowed_commands"] or []
        allowed_node = project_tree.add(f"[magenta]allowedCommands[/magenta]: {len(allowed)}")
        for command in allowed:
            allowed_node.add(f"[dim]{command}[/dim]")
    console.print(project_tree)

    # Location status
    location_tree = Tree("[bold]Location Status[/bold]")
    for location_name, servers in server_status["location_servers"].items():
        if servers == "error":
            location_tree.add(f"[red]{location_name}: ERROR[/red]")
        elif servers:
            location_tree.add(f"[green]{location_name}[/green]: {len(servers)} server(s)")
        else:
            location_tree.add(f"[dim]{location_name}: No servers[/dim]")
    console.print(location_tree)


@app.command()
def sync(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", "-n", help="Preview changes without applying")
    ] = False,
    global_only: Annotated[
        bool, typer.Option("--global-only", help="Sync only global configs")
    ] = False,
    project_only: Annotated[
        bool, typer.Option("--project-only", help="Sync only project configs")
    ] = False,
    location: Annotated[
        str | None,
        typer.Option("--location", "-l", help="Sync specific location only"),
    ] = None,
):
    """🔄 Sync configurations across all registered locations."""
    if dry_run:
        console.print(Panel("[bold yellow]DRY RUN - No changes will be made", title="Sync"))
    else:
        console.print(Panel("[bold blue]Syncing configurations...", title="Sync"))

    settings = get_settings()
    sync_engine = SyncEngine(settings)

    result = sync_engine.sync_all(
        dry_run=dry_run,
        global_only=global_only,
        project_only=project_only,
        specific_location=location,
    )

    # Show results
    if result.updated_locations:
        action = "Would update" if dry_run else "Updated"
        console.print(
            f"\n[bold green]{action} {len(result.updated_locations)} location(s):[/bold green]"
        )
        for loc in result.updated_locations:
            console.print(f"  • {loc}")

    if result.conflicts:
        console.print(f"\n[bold yellow]Conflicts detected ({len(result.conflicts)}):[/bold yellow]")
        for conflict in result.conflicts:
            console.print(f"  • [cyan]{conflict['server']}[/cyan] in {conflict['location']}")
            console.print(f"    Resolved using [green]{conflict['source']}[/green] config")

    if result.errors:
        console.print(f"\n[bold red]Errors ({len(result.errors)}):[/bold red]")
        for error in result.errors:
            console.print(f"  • [red]{error['location']}:[/red] {error['error']}")

    if not result.updated_locations and not result.conflicts and not result.errors:
        console.print("[bold green]✓ All configurations are already in sync.[/bold green]")


@app.command()
def diff():
    """📋 Show config differences (what would change)."""
    console.print(Panel("[bold blue]Configuration Differences", title="Diff"))

    settings = get_settings()
    sync_engine = SyncEngine(settings)
    result = sync_engine.sync_all(dry_run=True)

    if not result.updated_locations and not result.conflicts:
        console.print("[bold green]✓ All configurations are in sync.[/bold green]")
        return

    if result.updated_locations:
        count = len(result.updated_locations)
        console.print(f"\n[bold yellow]Locations that would be updated ({count}):[/bold yellow]")
        for loc in result.updated_locations:
            console.print(f"  • {loc}")

    if result.conflicts:
        console.print(f"\n[bold red]Conflicts detected ({len(result.conflicts)}):[/bold red]")
        for conflict in result.conflicts:
            server_name = conflict["server"]
            if server_name in {"skills", "allowedCommands"}:
                console.print(
                    f"  • [cyan]{server_name}[/cyan] in {conflict['location']} "
                    f"(source: {conflict.get('source', 'master')})"
                )
                if "current" in conflict:
                    console.print(f"    Current: {conflict['current']}")
                if "master" in conflict:
                    console.print(f"    Master: {conflict['master']}")
            else:
                console.print(f"  • [cyan]{server_name}[/cyan] in {conflict['location']}")


@app.command(name="list-clients")
def list_clients():
    """📱 Show all supported clients and their detection status."""
    console.print(Panel("[bold blue]Supported MCP Clients", title="Clients"))

    settings = get_settings()
    repository = ClientRepository()
    client_definitions = settings.get_client_definitions()

    table = Table()
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Status", style="bold")
    table.add_column("Description", style="dim")

    for client_id, config in client_definitions.clients.items():
        location = repository._get_client_location(client_id, config)
        status = "[green]✓ Found[/green]" if location else "[red]✗ Not found[/red]"

        table.add_row(
            client_id,
            config.name,
            status,
            config.description or "",
        )

    console.print(table)


@app.command(name="client-info")
def client_info(
    client: Annotated[str, typer.Argument(help="Client ID to show info for")],
):
    """ℹ️ Show detailed information about a specific client."""
    settings = get_settings()
    repository = ClientRepository()
    client_definitions = settings.get_client_definitions()

    if client not in client_definitions.clients:
        console.print(f"[bold red]Client '{client}' not found.[/bold red]")
        console.print("Run [cyan]mcp-sync list-clients[/cyan] to see available clients.")
        raise typer.Exit(1)

    config = client_definitions.clients[client]

    console.print(Panel(f"[bold blue]{config.name}[/bold blue]", title="Client Info"))
    console.print(f"[bold]ID:[/bold] {client}")
    console.print(f"[bold]Description:[/bold] {config.description or 'N/A'}")
    console.print(f"[bold]Config Type:[/bold] {config.config_type}")

    if config.paths:
        console.print("\n[bold]Paths:[/bold]")
        for platform, path in config.paths.items():
            console.print(f"  {platform}: [cyan]{path}[/cyan]")

    # Check if found
    location = repository._get_client_location(client, config)
    if location:
        console.print(f"\n[bold green]✓ Found on this system:[/bold green] {location['path']}")
    else:
        console.print("\n[bold red]✗ Not found on this system[/bold red]")


@app.command()
def add_server(
    name: Annotated[str, typer.Argument(help="Server name")],
    command: Annotated[
        str | None, typer.Option("--command", "-c", help="Command to run the server")
    ] = None,
    args: Annotated[
        str | None,
        typer.Option("--args", "-a", help="Command arguments (comma-separated)"),
    ] = None,
    env: Annotated[
        str | None,
        typer.Option("--env", "-e", help="Environment variables (KEY=value, comma-separated)"),
    ] = None,
    scope: Annotated[
        str | None,
        typer.Option("--scope", "-s", help="Config scope (global or project)"),
    ] = None,
):
    """➕ Add an MCP server to sync."""
    console.print(Panel(f"[bold blue]Adding server: {name}[/bold blue]", title="Add Server"))

    settings = get_settings()
    sync_engine = SyncEngine(settings)

    # Interactive mode if parameters not provided
    if not command or not scope:
        if not scope:
            scope = typer.prompt(
                "Scope",
                type=click.Choice(["global", "project"]),
                default="global",
            )
        if not command:
            command = typer.prompt("Command")

    # Build config
    config: dict = {"command": command}

    if args:
        config["args"] = [arg.strip() for arg in args.split(",")]

    if env:
        env_vars = {}
        for pair in env.split(","):
            if "=" in pair:
                key, value = pair.split("=", 1)
                env_vars[key.strip()] = value.strip()
        if env_vars:
            config["env"] = env_vars

    # Add server
    if scope == "global":
        sync_engine.add_server_to_global(name, config)
        console.print(f"[bold green]✓ Added '{name}' to global config[/bold green]")
    else:
        sync_engine.add_server_to_project(name, config)
        console.print(f"[bold green]✓ Added '{name}' to project config[/bold green]")


@app.command()
def remove_server(
    name: Annotated[str, typer.Argument(help="Server name")],
    scope: Annotated[
        str | None,
        typer.Option("--scope", "-s", help="Config scope (global or project)"),
    ] = None,
):
    """➖ Remove an MCP server from sync."""
    console.print(Panel(f"[bold blue]Removing server: {name}[/bold blue]", title="Remove Server"))

    settings = get_settings()
    sync_engine = SyncEngine(settings)

    # Interactive mode if scope not provided
    if not scope:
        scope = typer.prompt(
            "Remove from",
            type=click.Choice(["global", "project"]),
            default="global",
        )

    if scope == "global":
        if sync_engine.remove_server_from_global(name):
            console.print(f"[bold green]✓ Removed '{name}' from global config[/bold green]")
        else:
            console.print(f"[bold red]✗ Server '{name}' not found in global config[/bold red]")
            raise typer.Exit(1)
    else:
        console.print("[bold yellow]Project server removal not yet implemented[/bold yellow]")
        raise typer.Exit(1)


@app.command(name="list-servers")
def list_servers():
    """📋 Show all managed servers."""
    console.print(Panel("[bold blue]Managed MCP Servers", title="Servers"))

    settings = get_settings()
    sync_engine = SyncEngine(settings)
    status = sync_engine.get_server_status()

    all_servers = set()
    all_servers.update(status["global_servers"].keys())
    all_servers.update(status["project_servers"].keys())

    if not all_servers:
        console.print("[yellow]No servers configured.[/yellow]")
        return

    table = Table()
    table.add_column("Name", style="cyan")
    table.add_column("Source", style="green")
    table.add_column("Command", style="magenta")

    for server_name in sorted(all_servers):
        sources = []
        if server_name in status["global_servers"]:
            sources.append("global")
        if server_name in status["project_servers"]:
            sources.append("project")

        # Get effective config
        if server_name in status["project_servers"]:
            config = status["project_servers"][server_name]
        else:
            config = status["global_servers"][server_name]

        cmd = config.get("command", "unknown")

        table.add_row(
            server_name,
            ", ".join(sources),
            cmd,
        )

    console.print(table)


@app.command()
def vacuum(
    auto_resolve: Annotated[
        str | None,
        typer.Option("--auto-resolve", help="Auto-resolve conflicts (first or last)"),
    ] = None,
    skip_existing: Annotated[
        bool,
        typer.Option("--skip-existing", help="Skip servers already in global config"),
    ] = False,
):
    """🧹 Import MCP servers from discovered configs."""
    console.print(Panel("[bold blue]Vacuum: Importing MCP configurations...", title="Vacuum"))

    settings = get_settings()
    sync_engine = SyncEngine(settings)

    try:
        result = sync_engine.vacuum_configs(auto_resolve=auto_resolve, skip_existing=skip_existing)

        if not result.imported_servers and not result.conflicts:
            console.print("[yellow]No MCP servers found in any discovered locations.[/yellow]")
            return

        if result.imported_servers:
            console.print(
                f"\n[bold green]Imported {len(result.imported_servers)} server(s):[/bold green]"
            )
            for server_name, source in result.imported_servers.items():
                console.print(f"  • [cyan]{server_name}[/cyan] (from {source})")

        if result.conflicts:
            console.print(
                f"\n[bold yellow]Resolved {len(result.conflicts)} conflict(s):[/bold yellow]"
            )
            for conflict in result.conflicts:
                console.print(
                    f"  • [cyan]{conflict['server']}[/cyan] - kept from {conflict['chosen_source']}"
                )

        if result.skipped_servers:
            console.print(
                f"\n[bold dim]Skipped {len(result.skipped_servers)} existing server(s)[/bold dim]"
            )

        msg = "\n[bold green]✓ Vacuum complete![/bold green]"
        msg += " Run [cyan]mcp-sync sync[/cyan] to standardize all configs."
        console.print(msg)

    except KeyboardInterrupt:
        console.print("\n[yellow]Vacuum cancelled.[/yellow]")


@app.command()
def init():
    """🚀 Create a new project .mcp.json file."""
    config_path = Path(".mcp.json")

    if config_path.exists():
        console.print("[bold yellow].mcp.json already exists[/bold yellow]")
        raise typer.Exit(1)

    project_config = {"mcpServers": {}}

    with open(config_path, "w") as f:
        json.dump(project_config, f, indent=2)

    console.print("[bold green]✓ Created .mcp.json in current directory[/bold green]")


@app.command()
def template():
    """📄 Show a template configuration."""
    template_config = {
        "mcpServers": {
            "filesystem": {
                "command": "npx",
                "args": [
                    "-y",
                    "@modelcontextprotocol/server-filesystem",
                    "/path/to/directory",
                ],
            },
            "custom-server": {
                "command": "python",
                "args": ["/path/to/custom/server.py"],
                "env": {"API_KEY": "your-api-key"},
            },
        },
        "skills": [
            {"name": "code-review", "description": "Review pull requests for issues"},
        ],
        "allowedCommands": ["git", "npm", "pytest"],
    }

    console.print(Panel("[bold blue]MCP Configuration Template", title="Template"))
    console.print_json(json.dumps(template_config, indent=2))


@app.command()
def direct(
    source: Annotated[str, typer.Argument(help="Source client keyword or path")],
    target: Annotated[str, typer.Argument(help="Target client keyword or path")],
    dry_run: Annotated[
        bool, typer.Option("--dry-run", "-n", help="Preview changes without applying")
    ] = False,
):
    """🔄 Direct sync from source to target (bypass master config).

    Examples:
        mcp-sync direct vscode cursor
        mcp-sync direct claude codex
        mcp-sync direct ~/.vscode/mcp.json ~/.cursor/mcp.json
    """
    console.print(
        Panel(
            f"[bold blue]Direct Sync[/bold blue]\n{source} → {target}",
            title="Sync",
        )
    )

    engine = DirectSyncEngine()

    # Determine if arguments are keywords or paths
    source_path = Path(source)
    target_path = Path(target)

    if source_path.exists() and target_path.parent.exists():
        # Treat as paths
        result = engine.sync_by_path(source_path, target_path, dry_run=dry_run)
    else:
        # Treat as keywords
        result = engine.sync_by_keyword(source, target, dry_run=dry_run)

    format_sync_result(result)

    if not result.get("success"):
        raise typer.Exit(1)


@app.command()
def interactive():
    """🧙 Interactive sync wizard."""
    wizard = InteractiveWizard()
    wizard.run()


# Backup commands
backup_app = typer.Typer(help="Backup management commands")
app.add_typer(backup_app, name="backup")


@backup_app.command("list")
def backup_list():
    """📦 List available backups."""
    manager = BackupManager()
    backups = manager.list_backups()

    if not backups:
        console.print("[yellow]No backups found.[/yellow]")
        return

    table = Table(title="Available Backups")
    table.add_column("Timestamp", style="cyan")
    table.add_column("Files", style="green")

    for backup in backups:
        table.add_row(
            backup["timestamp"],
            str(len(backup["files"])),
        )

    console.print(table)


@backup_app.command("restore")
def backup_restore(
    timestamp: Annotated[str, typer.Argument(help="Backup timestamp to restore")],
    file_path: Annotated[
        str | None, typer.Option("--file", "-f", help="Specific file to restore")
    ] = None,
):
    """⏪ Restore from a backup."""
    manager = BackupManager()
    result = manager.restore_backup(timestamp, file_path)

    if result:
        if file_path:
            console.print(
                f"[bold green]✓ Restored {file_path} from backup {timestamp}[/bold green]"
            )
        else:
            console.print(f"[bold green]✓ Restored all files from backup {timestamp}[/bold green]")
    else:
        console.print(f"[bold red]✗ Failed to restore backup {timestamp}[/bold red]")
        raise typer.Exit(1)


@backup_app.command("cleanup")
def backup_cleanup(
    keep: Annotated[int, typer.Option("--keep", "-k", help="Number of backups to keep")] = 10,
):
    """🧹 Clean up old backups."""
    manager = BackupManager()
    removed = manager.cleanup_old_backups(keep)

    if removed:
        console.print(f"[bold green]✓ Removed {removed} old backup(s)[/bold green]")
    else:
        console.print("[dim]No old backups to remove[/dim]")


if __name__ == "__main__":
    app()
