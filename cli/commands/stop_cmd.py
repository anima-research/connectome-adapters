"""
Stop command for connectome-adapters CLI.

Stops one or all adapters.
"""

import click
import os
import platform
import psutil
import time
import signal
import sys
import subprocess

from pathlib import Path
from cli.config import Config

@click.command()
@click.argument("adapter_name", required=False)
@click.pass_context
def stop(ctx, adapter_name):
    """Stop adapter(-s).
    If ADAPTER_NAME is provided, stops that specific adapter.
    Otherwise, stops all running adapters.
    """
    config = Config(ctx).load_config()
    if not config:
        return

    if adapter_name:
        pid_file = ctx.obj["pid_dir"] / f"{adapter_name}.pid"
        if not pid_file.exists():
            click.echo(f"Error: Adapter '{adapter_name}' is not running or PID file not found.")
            return
        adapters_to_stop = [adapter_name]
    else:
        adapters_to_stop = [
            file.stem for file in ctx.obj["pid_dir"].glob("*.pid")
            if file.is_file()
        ]
        if not adapters_to_stop:
            click.echo("No running adapters found.")
            return

    success_count = 0
    failed_adapters = []

    click.echo(f"\nStopping {'adapter' if len(adapters_to_stop) == 1 else 'adapters'}:")
    click.echo("=" * 60)

    for adapter in adapters_to_stop:
        click.echo(f"Adapter: {adapter}")
        pid_file = ctx.obj["pid_dir"] / f"{adapter}.pid"
        pid = None

        try:
            with open(pid_file, "r") as f:
                pid = int(f.read().strip())
        except (ValueError, FileNotFoundError) as e:
            click.echo(f"  Error reading PID file: {e}")

            try:
                pid_file.unlink()
            except:
                pass

            failed_adapters.append(adapter)
            continue

        if pid is None:
            continue

        try:
            os.kill(pid, 0)  # This will raise OSError if process is not running
            click.echo(f"  Stopping process with PID: {pid}")
            kill_process(pid, graceful=True)

            for _ in range(5):
                try:
                    os.kill(pid, 0)
                    time.sleep(0.5)  # Process still running, wait
                except OSError:
                    break

            try:
                os.kill(pid, 0)
                click.echo("  Process didn't terminate gracefully, using force...")
                kill_process(pid, graceful=False)
            except OSError:
                click.echo("  Process terminated gracefully")

            time.sleep(0.5)

            try:
                os.kill(pid, 0)
                click.echo(f"  Failed to stop process with PID: {pid}")
                failed_adapters.append(adapter)
            except OSError:
                click.echo(f"  Successfully stopped")
                pid_file.unlink()
                success_count += 1

        except OSError:
            click.echo(f"  Process with PID {pid} is not running")
            pid_file.unlink()
            success_count += 1

    click.echo("=" * 60)
    if success_count > 0:
        click.echo(f"Successfully stopped {success_count} adapter(s)")
    if failed_adapters:
        click.echo(f"Failed to stop {len(failed_adapters)} adapter(s): {', '.join(failed_adapters)}")

    click.echo("\nUse 'connectome-adapters status' to check the status of all adapters.")

def kill_process(pid, graceful=True):
    """Kill a process and its subprocesses using psutil.

    Args:
        pid (int): Process ID to kill
        graceful (bool): If True, use SIGTERM for graceful shutdown,
                         otherwise use SIGKILL for force termination
    """
    try:
        system = platform.system()
        process = psutil.Process(pid)

        try:
            children = process.children(recursive=True)
            if system == "Windows":
                children = reversed(children)
        except:
            children = []

        sig = signal.SIGTERM if graceful else signal.SIGKILL
        kill_func = process.terminate if graceful else process.kill

        if system != "Windows":
            try:
                pgid = os.getpgid(pid)

                if pgid == pid:  # Process is a group leader
                    os.killpg(pgid, sig)
                    return
            except:
                pass

        for child in children:
            try:
                child.terminate() if graceful else child.kill()
            except:
                pass

        try:
            kill_func()
        except:
            pass
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        pass
    except Exception:
        try:
            if system == "Windows":
                flag = "" if graceful else "/F"
                subprocess.run(
                    f"taskkill {flag} /PID {pid} /T",
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            else:
                os.kill(pid, sig)
        except:
            pass
