import click
import tomllib

class Config:
    """Configuration class for the CLI."""

    def __init__(self, ctx):
        self.config_path = ctx.obj["cli_config_path"]

    def load_config(self):
        """Load the configuration file."""
        config = None

        try:
            with open(self.config_path, "rb") as f:
                config = tomllib.load(f)
        except FileNotFoundError:
            click.echo(f"Configuration file not found: {self.config_path}")
            click.echo("Please make sure adapters.toml exists in the cli directory.")
        except Exception as e:
            click.echo(f"Error loading configuration: {e}")

        return config
