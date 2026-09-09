from bcast_netcheck.checks.snmp import check
from bcast_netcheck.config import Settings
from bcast_netcheck.models import CheckStatus as S
from bcast_netcheck.security import redact


async def test_missing_community(monkeypatch):
    monkeypatch.delenv("BCAST_SNMP_COMMUNITY", raising=False)
    result = await check(
        "192.0.2.30", Settings(), {"enabled": True, "community_env": "BCAST_SNMP_COMMUNITY"}
    )
    assert result.status == S.SKIP


def test_redaction():
    assert redact({"message": ["prefix example suffix"]}, ["example"]) == {
        "message": ["prefix [REDACTED] suffix"]
    }


async def test_snmp_success_and_secret_reflection(monkeypatch):
    import pysnmp.hlapi.v3arch.asyncio as api

    monkeypatch.setenv("BCAST_SNMP_COMMUNITY", "example")

    class Engine:
        closed = False

        def close_dispatcher(self):
            self.closed = True

    engine = Engine()
    monkeypatch.setattr(api, "SnmpEngine", lambda: engine)

    async def create(*args, **kwargs):
        return object()

    async def get(*args, **kwargs):
        return None, 0, 0, [(None, "example"), (None, "Generic device"), (None, 123)]

    monkeypatch.setattr(api.UdpTransportTarget, "create", create)
    monkeypatch.setattr(api, "get_cmd", get)
    result = await check(
        "192.0.2.30", Settings(), {"enabled": True, "community_env": "BCAST_SNMP_COMMUNITY"}
    )
    assert result.status == S.PASS
    assert "example" not in str(result)
    assert engine.closed
