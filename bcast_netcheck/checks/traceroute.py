"""Bounded UDP traceroute with structured, numeric hops."""

import re
import shutil

from bcast_netcheck.checks.common import command
from bcast_netcheck.checks.route import address
from bcast_netcheck.models import CheckResult
from bcast_netcheck.models import CheckStatus as S


def parse_hops(output):
    hops = []
    for line in output.splitlines():
        match = re.match(r"^\s*(\d+)(?:\??:)?\s+(.+)", line)
        if not match:
            continue
        body = match[2]
        addresses = re.findall(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])", body)
        if not addresses:
            addresses = re.findall(r"\b[0-9a-fA-F]*:[0-9a-fA-F:]+", body)
        times = [float(x) for x in re.findall(r"([\d.]+)\s*ms", body)]
        hops.append(
            {
                "hop": int(match[1]),
                "addresses": addresses,
                "rtt_ms": times,
                "timeout": not addresses,
                "annotation": "unreachable" if "!" in body else None,
            }
        )
    return hops


async def check(host, settings):
    destination = await address(host)
    if shutil.which("traceroute"):
        args = ["traceroute", "-n", "-q", "1", "-m", "12", "-w", "0.2", destination]
    else:
        args = ["tracepath", "-n", "-m", "12", destination]
    code, out, _ = await command(args, settings.timeout)
    hops = parse_hops(out)
    if code not in (0, -1) and not hops:
        return CheckResult(
            "Traceroute",
            S.ERROR,
            host,
            message="Traceroute could not execute; check utility or permissions",
        )
    reached = any(destination in h["addresses"] and not h["annotation"] for h in hops)
    return CheckResult(
        "Traceroute",
        S.PASS if reached else S.WARN,
        host,
        max((h["hop"] for h in hops), default=0),
        "hops",
        "Destination reached" if reached else "Partial path; destination not confirmed",
        {"hops": hops, "reached": reached, "utility": args[0]},
    )
