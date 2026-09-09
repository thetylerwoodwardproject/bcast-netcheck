"""Single-command CLI, retaining direct target and optional device positional arguments."""

import asyncio
import json
from pathlib import Path

import typer

from bcast_netcheck.config import (
    ConfigError,
    Settings,
    config_path,
    load_sites,
    number,
    select_target,
)
from bcast_netcheck.reports import json_report, markdown
from bcast_netcheck.reports.terminal import display
from bcast_netcheck.runner import run
from bcast_netcheck.watch import watch as live_watch

app = typer.Typer(pretty_exceptions_enable=False, add_completion=False)


@app.command()
def main(
    target: str = typer.Argument(..., help="IP address, hostname, or configured station name."),
    device: str | None = typer.Argument(None, help="Only check this configured device."),
    config: Path | None = typer.Option(None, help="Explicit YAML site configuration."),
    ping_count: int = typer.Option(
        5, min=1, max=100, help="ICMP probes per endpoint; watch uses one."
    ),
    timeout: float = typer.Option(
        Settings.timeout, min=0.1, max=120, help="Deadline per check in seconds."
    ),
    concurrency: int = typer.Option(
        Settings.concurrency, min=1, max=100, help="Maximum concurrent checks."
    ),
    watch: bool = typer.Option(False, "--watch", help="Continuously sample ICMP reachability."),
    interval: float = typer.Option(
        5, min=0.1, max=3600, help="Watch start-to-start interval, seconds."
    ),
    report: bool = typer.Option(False, "--report", help="Write a timestamped Markdown report."),
    report_dir: Path = typer.Option(Path("."), help="Existing directory for Markdown reports."),
    json_output: bool = typer.Option(
        False, "--json", help="Output one JSON document only to stdout."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", help="Show structured evidence and path hops."
    ),
    debug: bool = typer.Option(
        False, "--debug", help="Show evidence, timing, and execution metadata."
    ),
):
    """Fast, read-only broadcast network diagnostics (Linux)."""
    try:
        number(timeout, 0.1, 120, "timeout")
        number(interval, 0.1, 3600, "interval")
        if watch and (report or json_output):
            raise ConfigError("--watch cannot be combined with --report or --json")
        sites = load_sites(config_path(config))
        site, endpoints = select_target(target, device, sites)
        settings = Settings(
            timeout=timeout, ping_count=ping_count, concurrency=concurrency, interval=interval
        )
        if watch:
            if not endpoints:
                raise ConfigError("Watch requires at least one configured endpoint")
            asyncio.run(live_watch(target, site, endpoints, settings, bool(device)))
            return
        result = asyncio.run(run(target, site, endpoints, settings, bool(device)))
        if report:
            path = markdown.write(result, report_dir)
            typer.echo(f"Report written: {path}", err=True)
        if json_output:
            typer.echo(json_report.render(result))
        else:
            display(result, verbose or debug, debug)
    except ConfigError as exc:
        if json_output:
            typer.echo(json.dumps({"schema_version": 1, "status": "error", "error": str(exc)}))
        else:
            typer.echo(f"Configuration error: {exc}", err=True)
        raise typer.Exit(3) from None
    except OSError:
        if json_output:
            typer.echo(
                json.dumps(
                    {
                        "schema_version": 1,
                        "status": "error",
                        "error": "Local execution or report file operation failed",
                    }
                )
            )
        else:
            typer.echo("Local execution or report file operation failed", err=True)
        raise typer.Exit(3) from None
    except KeyboardInterrupt:
        typer.echo("Stopped.", err=True)
        raise typer.Exit(130) from None
    raise typer.Exit(result.diagnosis.exit_code)
