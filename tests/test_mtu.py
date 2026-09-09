from bcast_netcheck.checks import mtu
from bcast_netcheck.config import Settings
from bcast_netcheck.models import CheckStatus as S


async def test_mtu_binary_search(monkeypatch):
    sizes = []

    async def probe(host, size, timeout):
        sizes.append(size)
        return "pass" if size <= 1420 else "fragment"

    monkeypatch.setattr(mtu, "probe", probe)
    result = await mtu.check("192.0.2.20", Settings())
    assert result.value == 1420
    assert result.status == S.WARN
    assert len(sizes) <= 15


async def test_silence_not_mtu(monkeypatch):
    async def probe(*args):
        return "unknown"

    monkeypatch.setattr(mtu, "probe", probe)
    result = await mtu.check("192.0.2.20", Settings())
    assert result.value is None
    assert result.status == S.WARN
