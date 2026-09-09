import dns.exception
import dns.resolver
import pytest

from bcast_netcheck.checks import dns as check_dns
from bcast_netcheck.config import Settings
from bcast_netcheck.models import CheckStatus as S


@pytest.mark.parametrize(
    "error,responded", [(dns.resolver.NXDOMAIN, True), (dns.exception.Timeout, False)]
)
async def test_dns_failure(monkeypatch, error, responded):
    async def resolve(*args, **kwargs):
        raise error

    monkeypatch.setattr(check_dns.dns.asyncresolver.Resolver, "resolve", resolve)
    result = await check_dns.check("encoder.example", Settings())
    assert result.status == S.FAIL
    assert result.details["resolver_responded"] is responded


async def test_numeric_skip():
    assert (await check_dns.check("192.0.2.20", Settings())).status == S.SKIP


async def test_ipv6_only_resolution(monkeypatch):
    class Answers:
        def addresses(self):
            return iter(["2001:db8::20"])

    async def resolve(*args, **kwargs):
        return Answers()

    monkeypatch.setattr(check_dns.dns.asyncresolver.Resolver, "resolve_name", resolve)
    result = await check_dns.check("encoder.example", Settings())
    assert result.status == S.PASS
    assert result.details["records"] == ["2001:db8::20"]
