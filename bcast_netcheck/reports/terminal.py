from rich.console import Console
from rich.table import Table
from rich.text import Text

STYLES = {"PASS": "green", "WARN": "yellow", "FAIL": "red", "SKIP": "dim", "ERROR": "magenta"}


def render(run, verbose=False, debug=False):
    table = Table(title=Text(f"Broadcast Network Check — {run.site or run.target}"))
    for title in ("Status", "Endpoint", "Check", "Target", "Result"):
        table.add_column(title)
    for c in run.checks:
        value = ""
        if c.value is not None and c.unit:
            value = (
                f"{c.value:.2f} {c.unit}" if isinstance(c.value, float) else f"{c.value} {c.unit}"
            )
        table.add_row(
            Text(c.status, style=STYLES[c.status]),
            Text(c.label or c.endpoint),
            Text(c.name),
            Text(c.target or ""),
            Text(f"{c.message} {value}".strip()),
        )
        if c.name == "ICMP" and c.details:
            d = c.details
            jitter = (
                f"{d['jitter_ms']:.2f} ms"
                if d.get("jitter_ms") is not None
                else "insufficient samples"
            )
            table.add_row("", "", "Loss / jitter", "", Text(f"{d['loss_pct']:.1f}% / {jitter}"))
        if verbose and c.details:
            table.add_row("", "", "Details", "", Text(str(c.details)))
        if debug:
            table.add_row(
                "",
                "",
                "Execution",
                "",
                Text(f"kind={c.kind}; required={c.required}; duration={c.duration_ms} ms"),
            )
    return table


def display(run, verbose=False, debug=False):
    console = Console()
    console.print(render(run, verbose, debug))
    if run.description:
        console.print(Text(run.description))
    console.print(Text(f"{run.diagnosis.status.upper()}: {run.diagnosis.summary}"))
    for recommendation in run.diagnosis.recommendations:
        console.print(Text(f"Suggested action: {recommendation}"))
