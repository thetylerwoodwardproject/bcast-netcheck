import pytest

from bcast_netcheck.diagnosis import diagnose
from bcast_netcheck.models import CheckResult
from bcast_netcheck.models import CheckStatus as S


def icmp(key, status, required=False):
    return CheckResult("ICMP", status, endpoint=key, required=required)


@pytest.mark.parametrize(
    "primary,backup,status",
    [
        (S.PASS, S.PASS, "healthy"),
        (S.PASS, S.FAIL, "warning"),
        (S.FAIL, S.PASS, "warning"),
        (S.FAIL, S.FAIL, "critical"),
        (S.ERROR, S.FAIL, "warning"),
        (S.SKIP, S.PASS, "warning"),
    ],
)
def test_transport(primary, backup, status):
    result = diagnose([icmp("primary", primary), icmp("backup", backup)])
    assert result.status == status


def test_router_failure():
    result = diagnose([icmp("router", S.FAIL, True), icmp("device:encoder", S.FAIL)])
    assert "router or upstream" in result.summary
    assert result.exit_code == 2


def test_isolated_optional_device():
    result = diagnose(
        [
            icmp("router", S.PASS),
            icmp("device:encoder", S.FAIL),
            icmp("device:remote_control", S.PASS),
        ]
    )
    assert result.status == "warning"
    assert "isolated to encoder" in result.summary


@pytest.mark.parametrize(
    "status,code", [(S.PASS, 0), (S.WARN, 1), (S.FAIL, 2), (S.ERROR, 3), (S.SKIP, 3)]
)
def test_exit_codes(status, code):
    assert diagnose([icmp("target", status, True)]).exit_code == code
