"""Portable Markdown reports. Configuration and authentication objects are never serialized."""

import html
import json
import os
import re
from datetime import datetime
from pathlib import Path


def escape(value):
    return (
        html.escape(str(value))
        .replace("|", "&#124;")
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("`", "&#96;")
    )


def render(run):
    lines = [
        f"# {escape(run.site or run.target)} Network Diagnostic",
        "",
        f"Date: {escape(run.timestamp)}  ",
        f"Tool version: {run.version}  ",
        f"Site: {escape(run.site or 'Direct target')}  ",
        f"Description: {escape(run.description)}",
        "",
        "## Summary",
        "",
        f"**{run.diagnosis.status.upper()}** — {escape(run.diagnosis.summary)}",
        "",
        "## Recommendations",
        "",
    ]
    lines.extend(f"- {escape(r)}" for r in run.diagnosis.recommendations)
    if not run.diagnosis.recommendations:
        lines.append("No immediate action indicated by completed checks.")
    lines += [
        "",
        "## Test Details",
        "",
        "| Endpoint | Target | Check | Status | Required | Result | Duration (ms) |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for c in run.checks:
        value = f"{c.value} {c.unit or ''}" if c.value is not None else ""
        cells = [
            c.label or c.endpoint,
            c.target or "",
            c.name,
            c.status,
            "yes" if c.required else "no",
            f"{c.message} {value}".strip(),
            c.duration_ms,
        ]
        lines.append("| " + " | ".join(escape(x) for x in cells) + " |")
    lines += ["", "## Structured Evidence", ""]
    for c in run.checks:
        if c.details:
            lines += [f"### {escape(c.endpoint)} — {escape(c.name)}", ""]
            lines.extend("    " + line for line in json.dumps(c.details, indent=2).splitlines())
            lines.append("")
    return "\n".join(lines) + "\n"


def write(run, directory=Path(".")):
    slug = re.sub(r"[^a-z0-9_-]", "-", (run.site or run.target).lower())[:80] or "target"
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S-%f")
    path = directory / f"{slug}-netcheck-{stamp}.md"
    # Exclusive creation prevents clobbering an existing report or following a symlink.
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as report:
        report.write(render(run))
    return path
