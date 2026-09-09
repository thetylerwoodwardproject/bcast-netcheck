import asyncio
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from bcast_netcheck import cli, runner
from bcast_netcheck.config import Endpoint, Port, Settings, config_path, load_sites
from bcast_netcheck.models import CheckResult
from bcast_netcheck.models import CheckStatus as S


@pytest.fixture
def mocked_checks(monkeypatch):
    async def ping(host, settings):
        return CheckResult(
            "ICMP",
            S.PASS,
            host,
            10,
            "ms",
            "Reachable",
            {"loss_pct": 0, "jitter_ms": 0, "avg_ms": 10},
        )

    async def tcp(host, port, timeout):
        return CheckResult(f"TCP/{port.port}", S.PASS, host, message="Open")

    async def auxiliary(host, *args, **kwargs):
        return CheckResult("Auxiliary", S.PASS, host)

    monkeypatch.setattr(runner.ping, "check", ping)
    monkeypatch.setattr(runner.tcp, "check", tcp)
    for module in (
        runner.route,
        runner.traceroute,
        runner.mtu,
        runner.snmp,
        runner.dns,
        runner.ntp,
    ):
        monkeypatch.setattr(module, "check", auxiliary)


@pytest.mark.parametrize(
    "args",
    [
        ["127.0.0.1"],
        ["WXYZ", "--config", "examples/sites.yaml"],
        ["WXYZ", "encoder", "--config", "examples/sites.yaml"],
        ["WXYZ", "--config", "examples/sites.yaml", "--json"],
    ],
)
def test_acceptance_cli(mocked_checks, args):
    result = CliRunner().invoke(cli.app, args)
    assert result.exit_code == 0, result.output
    if "--json" in args:
        data = json.loads(result.stdout)
        assert data["site"] == "WXYZ"
        assert data["checks"]


def test_cli_report_and_json(mocked_checks, tmp_path):
    result = CliRunner().invoke(
        cli.app,
        [
            "WXYZ",
            "--config",
            "examples/sites.yaml",
            "--report",
            "--report-dir",
            str(tmp_path),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "healthy"
    assert len(list(tmp_path.glob("wxyz-netcheck-*.md"))) == 1
    assert "Report written" in result.stderr


@pytest.mark.parametrize(
    "args",
    [
        ["KABC", "--json"],
        ["192.0.2.20", "--timeout", "nan", "--json"],
        ["WXYZ", "--watch", "--json"],
        ["WXYZ", "--config", "missing.yaml", "--json"],
    ],
)
def test_cli_errors_json(args):
    result = CliRunner().invoke(cli.app, args)
    assert result.exit_code == 3
    assert json.loads(result.stdout)["status"] == "error"


async def test_bounded_concurrency_and_failure_isolation(mocked_checks, monkeypatch):
    active = 0
    peak = 0

    async def ping(host, settings):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(0.005)
            if host == "192.0.2.1":
                raise RuntimeError("do not echo exceptions")
            return CheckResult("ICMP", S.PASS, host)
        finally:
            active -= 1

    monkeypatch.setattr(runner.ping, "check", ping)
    endpoints = {f"device:d{i}": Endpoint(f"192.0.2.{i}") for i in range(1, 11)}
    result = await runner.run(
        "WXYZ", None, endpoints, Settings(concurrency=3), reachability_only=True
    )
    assert 1 < peak <= 3
    assert sum(c.status == S.ERROR for c in result.checks) == 1
    assert len([c for c in result.checks if c.name == "ICMP"]) == 10


async def test_required_port_and_redaction(mocked_checks, monkeypatch):
    monkeypatch.setenv("BCAST_SNMP_COMMUNITY", "example")

    async def tcp(*args):
        return CheckResult("TCP/443", S.FAIL, "192.0.2.20", message="example")

    monkeypatch.setattr(runner.tcp, "check", tcp)
    ep = Endpoint(
        "192.0.2.20",
        ports=[Port(443, required=True)],
        snmp={"community_env": "BCAST_SNMP_COMMUNITY"},
    )
    result = await runner.run("WXYZ", None, {"device:encoder": ep}, Settings())
    assert result.diagnosis.exit_code == 2
    assert "example" not in str(result)


def test_config_precedence(monkeypatch, tmp_path):
    home = tmp_path / "home"
    user = home / ".config/bcast-netcheck/sites.yaml"
    user.parent.mkdir(parents=True)
    user.write_text("sites: {}")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: home)
    assert config_path() == user
    local = tmp_path / "sites.yaml"
    local.write_text("sites: {}")
    assert config_path() == local
    assert config_path(user) == user


def test_fixture_configuration():
    sites = load_sites(Path("examples/sites.yaml"))
    assert set(sites) == {"WXYZ", "KXYZ"}
    assert sites["WXYZ"].endpoints["device:encoder"].ports[-1].required
