from bcast_netcheck.models import CheckResult, Diagnosis, DiagnosticRun
from bcast_netcheck.models import CheckStatus as S
from bcast_netcheck.watch import History


def sample(status):
    return DiagnosticRun(
        "WXYZ",
        "WXYZ",
        "",
        "",
        "0.1.0",
        [CheckResult("ICMP", status, value=10 if status == S.PASS else None, endpoint="primary")],
        Diagnosis("healthy", ""),
    )


def test_flap_duration():
    history = History()
    for now, status in [(0, S.PASS), (0.5, S.FAIL), (1, S.FAIL), (1.5, S.PASS)]:
        history.update(sample(status), now, "17:32:11.240")
    assert "LOST" in history.events[0]
    assert "approximately 1.0s" in history.events[1]
    assert history.metrics("primary")[0] == 50


def test_unknown_breaks_outage_estimate():
    history = History()
    for now, status in enumerate([S.PASS, S.FAIL, S.ERROR, S.PASS]):
        history.update(sample(status), now, "17:32:11")
    assert not any("approximately" in event for event in history.events)
