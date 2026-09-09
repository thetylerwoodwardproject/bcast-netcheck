"""Resolver response and name resolution are separate pieces of evidence."""

import ipaddress

import dns.asyncresolver
import dns.exception
import dns.resolver

from bcast_netcheck.checks.route import address
from bcast_netcheck.models import CheckResult
from bcast_netcheck.models import CheckStatus as S


async def check(host, settings, server=None, test_name=None):
    name = test_name
    if name is None:
        try:
            ipaddress.ip_address(host)
        except ValueError:
            name = host
    if name is None and server is None:
        return CheckResult("DNS", S.SKIP, host, message="Numeric target; no DNS test configured")
    resolver = dns.asyncresolver.Resolver(configure=server is None)
    if server:
        resolver.nameservers = [await address(server)]
    query = name or "."
    try:
        if name:
            answer = await resolver.resolve_name(
                query, lifetime=settings.timeout * 0.9, search=False
            )
            records = list(answer.addresses())
        else:
            answer = await resolver.resolve(
                query, "NS", lifetime=settings.timeout * 0.9, search=False
            )
            records = [r.to_text() for r in answer]
        return CheckResult(
            "DNS",
            S.PASS,
            server or host,
            message="Resolver answered successfully",
            details={"query": query, "records": records, "resolver_responded": True},
        )
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return CheckResult(
            "DNS",
            S.FAIL,
            server or host,
            message="DNS server reachable but hostname resolution failed",
            details={"query": query, "resolver_responded": True},
        )
    except dns.resolver.NoNameservers:
        return CheckResult(
            "DNS",
            S.FAIL,
            server or host,
            message="No usable DNS answer (server error or transport failure)",
            details={"query": query, "resolver_responded": None},
        )
    except dns.exception.Timeout:
        return CheckResult(
            "DNS",
            S.FAIL,
            server or host,
            message="DNS server unreachable or not responding before deadline",
            details={"query": query, "resolver_responded": False},
        )
