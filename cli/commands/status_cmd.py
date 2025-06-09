"""
List command for connectome-adapters CLI.

Lists all available adapters with their status.
"""

import os
import click
import time

from pathlib import Path
from datetime import datetime
from cli.config import Config

@click.command(name="status")
@click.pass_context
def status(ctx):
    """List all available adapters with their current status."""
    config = Config(ctx).load_config()
    if not config:
        return

    adapters_dir = ctx.obj["project_root"] / "src" / "adapters"
    if not adapters_dir.exists():
        click.echo(f"Adapters directory not found: {adapters_dir}")
        return

    available_adapters = []
    for item in adapters_dir.iterdir():
        if item.is_dir() and item.name.endswith("_adapter"):
            adapter_name = item.name.replace("_adapter", "")
            available_adapters.append(adapter_name)

    if not available_adapters:
        click.echo("No adapters found.")
        return

    adapter_config = config.get("adapters", {})
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Configuration Status Table
    click.echo(f"\nAdapter Configuration as of {current_time}:")
    click.echo("=" * 60)
    click.echo(f"{'Adapter':<15} {'Configuration':<20}")
    click.echo("-" * 60)

    enabled_count = 0
    for adapter in sorted(available_adapters):
        enabled = adapter_config.get(adapter, False)
        status = "ENABLED" if enabled else "DISABLED"
        if enabled:
            enabled_count += 1
        click.echo(f"{adapter:<15} {status:<20}")

    click.echo("-" * 60)
    click.echo(f"Total: {len(available_adapters)} adapters, {enabled_count} enabled\n")

    # Runtime Status Table
    click.echo(f"\nAdapter Runtime Status as of {current_time}:")
    click.echo("=" * 60)
    click.echo(f"{'Adapter':<15} {'Status':<20} {'Details':<25}")
    click.echo("-" * 60)

    running_count = 0
    for adapter in sorted(available_adapters):
        pid_file = ctx.obj["pid_dir"] / f"{adapter}.pid"
        status = "NOT STARTED"
        details = ""

        if pid_file.exists():
            try:
                with open(pid_file, "r") as f:
                    pid = f.read().strip()

                try:
                    os.kill(int(pid), 0)  # This just checks if the process exists
                    status = "RUNNING"
                    running_count += 1

                    try:
                        pid_stat = os.stat(pid_file)
                        uptime_seconds = time.time() - pid_stat.st_mtime
                        hours, remainder = divmod(uptime_seconds, 3600)
                        minutes, _ = divmod(remainder, 60)
                        details = f"PID: {pid}, Up: {int(hours)}h {int(minutes)}m"
                    except:
                        details = f"PID: {pid}"

                except (OSError, ProcessLookupError):
                    status = "STOPPED"
                    details = "Stale PID file detected"

                    try:
                        os.unlink(pid_file)
                    except:
                        pass
            except Exception:
                status = "UNKNOWN"
                details = "Error reading PID file"

        click.echo(f"{adapter:<15} {status:<20} {details:<25}")

    click.echo("-" * 60)
    click.echo(f"Total: {len(available_adapters)} adapters, {running_count} running\n")
