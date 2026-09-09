import asyncio

import pytest
from typer.testing import CliRunner

from bcast_netcheck.checks.ping import parse_ping
from bcast_netcheck.checks.tcp import check
from bcast_netcheck.cli import app
from bcast_netcheck.config import ConfigError, Port, load_sites, select_target, validate_host
from bcast_netcheck.diagnosis import diagnose
from bcast_netcheck.models import CheckResult
from bcast_netcheck.models import CheckStatus as S


@pytest.mark.parametrize("host", ["192.0.2.1", "2001:db8::1", "encoder.example", "localhost"])
def test_host(host):
    assert validate_host(host) == host


@pytest.mark.parametrize("host", ["999.1.1.1", "-bad", "foo;id", "a b", "", "::invalid"])
def test_invalid_host(host):
    with pytest.raises(ConfigError):
        validate_host(host)


def test_config(tmp_path):
    path = tmp_path / "sites.yaml"
    path.write_text("sites:\n  WXYZ:\n    devices:\n      encoder:\n        host: 192.0.2.20\n")
    sites = load_sites(path)
    assert select_target("WXYZ", "encoder", sites)[1]["device:encoder"].host == "192.0.2.20"
    with pytest.raises(ConfigError):
        select_target("KXYZ", None, sites)
    with pytest.raises(ConfigError):
        select_target("WXYZ", "missing", sites)
    path.write_text("sites: [")
    with pytest.raises(ConfigError):
        load_sites(path)


def test_ping():
    d = parse_ping("""64 bytes time=10.0 ms
64 bytes time=12.0 ms
64 bytes time=11.0 ms
4 packets transmitted, 3 received, 25% packet loss
rtt min/avg/max/mdev = 10.000/11.000/12.000/0.8 ms
""")
    assert d["loss_pct"] == 25
    assert d["jitter_ms"] == 1.5
    assert d["avg_ms"] == 11


async def test_tcp(monkeypatch):
    class Writer:
        closed = False

        def close(self):
            self.closed = True

        async def wait_closed(self):
            pass

    writer = Writer()

    async def opened(*args):
        return None, writer

    monkeypatch.setattr(asyncio, "open_connection", opened)
    assert (await check("192.0.2.20", Port(443), 1)).status == S.PASS
    assert writer.closed

    async def refused(*args):
        raise ConnectionRefusedError

    monkeypatch.setattr(asyncio, "open_connection", refused)
    assert (await check("192.0.2.20", Port(443), 1)).status == S.FAIL


def test_optional_port():
    checks = [CheckResult("ICMP", S.PASS), CheckResult("TCP/80", S.FAIL, required=False)]
    assert diagnose(checks).exit_code == 0
    checks[1].required = True
    assert diagnose(checks).exit_code == 2


def test_cli_help_and_error():
    cli = CliRunner()
    assert cli.invoke(app, ["--help"]).exit_code == 0
    assert cli.invoke(app, ["999.1.1.1"]).exit_code == 3


@pytest.mark.parametrize(
    "fragment",
    [
        "ports: [0]",
        "ports: [65536]",
        "ports: [true]",
        "ports: [1.2]",
        "required: yesplease",
        "snmp: {community: example}",
        "snmp: {community_env: 123}",
        "expected_mtu: .nan",
    ],
)
def test_invalid_endpoint_configuration(tmp_path, fragment):
    path = tmp_path / "sites.yaml"
    path.write_text("sites:\n  WXYZ:\n    router:\n      host: 192.0.2.1\n      " + fragment)
    with pytest.raises(ConfigError):
        load_sites(path)


def test_yaml_error_never_echoes_source(tmp_path):
    path = tmp_path / "sites.yaml"
    path.write_text("sites: [example private content")
    with pytest.raises(ConfigError) as exc:
        load_sites(path)
    assert "private content" not in str(exc.value)
