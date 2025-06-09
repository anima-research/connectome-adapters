"""
Start command for connectome-adapters CLI.

Starts one or all adapters.
"""

import click
import os
import time
import signal
import sys
import subprocess

from pathlib import Path
from cli.config import Config

@click.command()
@click.argument("adapter_name", required=False)
@click.pass_context
def start(ctx, adapter_name):
    """Start one or more adapters.

    If ADAPTER_NAME is provided, starts that specific adapter.
    Otherwise, starts all adapters marked as enabled in the configuration.

    \b
    Examples:
        connectome-adapters start
        connectome-adapters start zulip
    """
    config = Config(ctx).load_config()
    if not config:
        return

    adapters_dir = ctx.obj["project_root"] / config.get("base_dir", "src") / "adapters"

    if adapter_name:
        adapter_path = adapters_dir / f"{adapter_name}_adapter"
        if not adapter_path.exists():
            click.echo(f"Error: Adapter '{adapter_name}' not found.")
            return
        adapters_to_start = [adapter_name]
    else:
        adapter_config = config.get("adapters", {})
        adapters_to_start = [
            name for name, enabled in adapter_config.items()
            if enabled and (adapters_dir / f"{name}_adapter").exists()
        ]

        if not adapters_to_start:
            click.echo("No enabled adapters found in configuration.")
            return

    success_count = 0
    failed_adapters = []

    click.echo(f"\nStarting {'adapter' if len(adapters_to_start) == 1 else 'adapters'}:")
    click.echo("=" * 60)

    for adapter in adapters_to_start:
        click.echo(f"Adapter: {adapter}")

        pid_file = ctx.obj["pid_dir"] / f"{adapter}.pid"
        if pid_file.exists():
            try:
                with open(pid_file, "r") as f:
                    pid = int(f.read().strip())

                try:
                    os.kill(pid, 0)
                    click.echo(f"  Already running (PID: {pid})")
                    continue
                except OSError:
                    pid_file.unlink()
            except (ValueError, OSError):
                try:
                    pid_file.unlink()
                except:
                    pass

        adapter_main_file = adapters_dir / f"{adapter}_adapter" / "main.py"
        if not adapter_main_file.exists():
            click.echo(f"  Error: Main file not found at {adapter_main_file}")
            failed_adapters.append(adapter)
            continue

        click.echo(f"  Starting...")
        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(ctx.obj["project_root"])
            process = subprocess.Popen(
                [sys.executable, str(adapter_main_file)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=env["PYTHONPATH"],
                env=env,
                start_new_session=True
            )

            time.sleep(1)
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                if stdout:
                    click.echo(f"  Output: {stdout.decode('utf-8').strip()}")
                click.echo(f"  Failed to start: Process exited immediately")
                if stderr:
                    click.echo(f"  Error: {stderr.decode('utf-8').strip()}")
                failed_adapters.append(adapter)
                continue

            with open(pid_file, "w") as f:
                f.write(str(process.pid))

            click.echo(f"  Started successfully (PID: {process.pid})")
            success_count += 1
        except Exception as e:
            click.echo(f"  Error starting adapter: {e}")
            failed_adapters.append(adapter)

    click.echo("=" * 60)
    if success_count > 0:
        click.echo(f"Successfully started {success_count} adapter(s)")
    if failed_adapters:
        click.echo(f"Failed to start {len(failed_adapters)} adapter(s): {', '.join(failed_adapters)}")

    click.echo("\nUse 'connectome-adapters status' to check the status of all adapters.")
