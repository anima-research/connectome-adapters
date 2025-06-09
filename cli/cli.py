import click
import os

from pathlib import Path
from cli.config import Config
from cli.commands.restart_cmd import restart
from cli.commands.status_cmd import status
from cli.commands.start_cmd import start
from cli.commands.stop_cmd import stop

@click.group()
@click.pass_context
def cli(ctx):
    """Manage Connectome messaging platform adapters.

    This CLI tool allows you to control adapters that connect Connectome
    to various messaging platforms. You can start, stop, restart, and
    check the status of adapters.

    Configuration is read from cli/adapters.toml in the project directory.
    """
    ctx.ensure_object(dict)

    ctx.obj["cli_dir"] = Path(__file__).resolve().parent  # Get directory containing this file
    ctx.obj["project_root"] = ctx.obj["cli_dir"].parent   # Get parent of cli directory
    ctx.obj["cli_config_path"] = ctx.obj["cli_dir"] / "adapters.toml"

    pid_dir = ctx.obj["project_root"] / ".pids"
    pid_dir.mkdir(exist_ok=True)
    ctx.obj["pid_dir"] = pid_dir

# Register subcommands
cli.add_command(status)
cli.add_command(start)
cli.add_command(stop)
cli.add_command(restart)

def main():
    """Entry point for the connectome-adapters command."""
    cli()

if __name__ == "__main__":
    main()
