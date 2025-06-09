"""
Restart command for connectome-adapters CLI.

Restarts one adapter.
"""

import click
import time

from pathlib import Path
from cli.commands.stop_cmd import stop
from cli.commands.start_cmd import start

@click.command()
@click.argument("adapter_name", required=True)
@click.pass_context
def restart(ctx, adapter_name):
    """Restart one adapter.

    \b
    Examples:
        connectome-adapters restart zulip
    """
    click.echo(f"Restarting adapter: {adapter_name}")
    click.echo("=" * 60)

    ctx.invoke(stop, adapter_name=adapter_name)
    time.sleep(1)
    ctx.invoke(start, adapter_name=adapter_name)

    click.echo("=" * 60)
    click.echo("\nUse 'connectome-adapters status' to check the status.")
