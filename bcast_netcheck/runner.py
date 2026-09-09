"""Bounded orchestration; check modules remain independent of site diagnosis."""

import asyncio
from dataclasses import asdict
from datetime import datetime, timezone

from bcast_netcheck import __version__
from bcast_netcheck.checks import dns, mtu, ntp, ping, route, snmp, tcp, traceroute
from bcast_netcheck.checks.common import guarded
from bcast_netcheck.config import Endpoint
from bcast_netcheck.diagnosis import diagnose
from bcast_netcheck.models import CheckResult, DiagnosticRun
from bcast_netcheck.security import configured_secrets, redact


async def run(target, site, endpoints, settings, selected=False, reachability_only=False):
    semaphore = asyncio.Semaphore(settings.concurrency)
    secrets = configured_secrets(endpoints)

    async def execute(key, ep, name, kind, fn, required):
        async with semaphore:
            result = await guarded(name, ep.host, fn, settings.timeout)
            result.endpoint, result.required = key, required
            result.kind, result.label = kind, ep.description or key.removeprefix("device:")
            return result

    jobs = []
    for key, ep in endpoints.items():
        jobs.append(
            execute(
                key, ep, "ICMP", "ping", lambda ep=ep: ping.check(ep.host, settings), ep.required
            )
        )
        if reachability_only:
            route_key = "router" if "router" in endpoints else next(iter(endpoints))
            if key == route_key:
                jobs.append(
                    execute(
                        key,
                        ep,
                        "Route",
                        "route",
                        lambda ep=ep: route.check(ep.host, settings),
                        False,
                    )
                )
            continue
        for port in ep.ports:
            jobs.append(
                execute(
                    key,
                    ep,
                    port.name or f"TCP/{port.port}",
                    "tcp",
                    lambda ep=ep, port=port: tcp.check(ep.host, port, settings.timeout * 0.9),
                    port.required,
                )
            )
        for name, kind, module in [
            ("Route", "route", route),
            ("Traceroute", "traceroute", traceroute),
        ]:
            jobs.append(
                execute(
                    key,
                    ep,
                    name,
                    kind,
                    lambda ep=ep, module=module: module.check(ep.host, settings),
                    False,
                )
            )
        jobs.append(
            execute(
                key,
                ep,
                "Path MTU",
                "mtu",
                lambda ep=ep: mtu.check(ep.host, settings, ep.expected_mtu),
                False,
            )
        )
        jobs.append(
            execute(
                key,
                ep,
                "SNMP",
                "snmp",
                lambda ep=ep: snmp.check(ep.host, settings, ep.snmp),
                bool(ep.snmp.get("enabled", bool(ep.snmp))),
            )
        )
        server = site.dns.get("server") if site and not selected else None
        jobs.append(
            execute(
                key,
                ep,
                "DNS",
                "dns",
                lambda ep=ep, server=server: dns.check(
                    ep.host, settings, server if not _numeric(ep.host) else None
                ),
                # Numeric addresses have an intentional DNS SKIP in direct mode.
                not _numeric(ep.host),
            )
        )
    if site and not selected and not reachability_only:
        if site.dns:
            ep = Endpoint(site.dns["server"])
            jobs.append(
                execute(
                    "dns",
                    ep,
                    "DNS",
                    "dns",
                    lambda: dns.check(
                        site.dns["server"], settings, site.dns["server"], site.dns.get("test_name")
                    ),
                    True,
                )
            )
        if site.ntp:
            ep = Endpoint(site.ntp["server"])
            jobs.append(
                execute(
                    "ntp", ep, "NTP", "ntp", lambda: ntp.check(site.ntp["server"], settings), True
                )
            )
    checks = await asyncio.gather(*jobs)
    diagnosis = diagnose(checks)
    diagnosis.summary = redact(diagnosis.summary, secrets)
    diagnosis.recommendations = redact(diagnosis.recommendations, secrets)
    checks = [CheckResult(**{**redact(asdict(c), secrets), "kind": c.kind}) for c in checks]
    return DiagnosticRun(
        redact(target, secrets),
        redact(site.name, secrets) if site else None,
        redact(site.description, secrets) if site else "",
        datetime.now(timezone.utc).isoformat(),
        __version__,
        checks,
        diagnosis,
    )


def _numeric(host):
    import ipaddress

    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False
