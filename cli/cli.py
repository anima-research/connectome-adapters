import click
import os
import tomllib

from pathlib import Path
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

    current_dir = Path(__file__).resolve().parent
    cli_config_path = current_dir.parent / "cli" / "adapters.toml"

    try:
        with open(cli_config_path, "rb") as f:
            config = tomllib.load(f)
            if not config:
                click.echo("Configuration file is empty.")
                return
    except FileNotFoundError:
        click.echo(f"Configuration file not found: {cli_config_path}")
        click.echo("Please make sure adapters.toml exists in the cli directory.")
        return
    except Exception as e:
        click.echo(f"Error loading configuration: {e}")
        return

    ctx.obj["adapters"] = config.get("adapters", {})
    ctx.obj["project_root"] = Path(config.get("project_dir", ""))
    ctx.obj["pid_dir"] = ctx.obj["project_root"] / ".pids"
    ctx.obj["pid_dir"].mkdir(exist_ok=True)

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
