"""Linux route inspection without modifying routing state."""

import ipaddress
import json

from bcast_netcheck.checks.common import command
from bcast_netcheck.models import CheckResult
from bcast_netcheck.models import CheckStatus as S


async def address(host, timeout=3.0):
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        pass
    # Avoid non-cancellable libc resolver threads while retaining local hosts-file aliases.
    from pathlib import Path

    import dns.asyncresolver

    try:
        for line in Path("/etc/hosts").read_text().splitlines():
            fields = line.split("#", 1)[0].split()
            if len(fields) > 1 and host.rstrip(".").lower() in [x.lower() for x in fields[1:]]:
                return str(ipaddress.ip_address(fields[0]))
    except (OSError, ValueError):
        pass
    answers = await dns.asyncresolver.Resolver().resolve_name(host, lifetime=timeout, search=True)
    return next(answers.addresses())


def parse_route(output):
    rows = json.loads(output)
    if not rows or not isinstance(rows[0], dict):
        raise ValueError("Missing route")
    row = rows[0]
    return {
        "destination": row.get("dst"),
        "next_hop": row.get("gateway"),
        "interface": row.get("dev"),
        "source": row.get("prefsrc", row.get("src")),
    }


async def check(host, settings):
    destination = await address(host)
    code, out, _ = await command(["ip", "-j", "route", "get", destination], settings.timeout)
    if code:
        return CheckResult("Route", S.ERROR, host, message="Route lookup failed")
    data = parse_route(out)
    return CheckResult(
        "Route",
        S.PASS,
        host,
        message=(f"via {data['next_hop'] or 'direct'} dev {data['interface']}"),
        details=data,
    )
