import json

from bcast_netcheck.models import CheckResult, Diagnosis, DiagnosticRun
from bcast_netcheck.models import CheckStatus as S
from bcast_netcheck.reports import json_report, markdown


def sample():
    return DiagnosticRun(
        "WXYZ",
        "WXYZ",
        "Fictional transmitter",
        "2026-01-01T00:00:00+00:00",
        "0.1.0",
        [
            CheckResult(
                "ICMP", S.PASS, "192.0.2.20", 10.0, "ms", "Reachable", endpoint="device:encoder"
            )
        ],
        Diagnosis("healthy", "No failure detected."),
    )


def test_json():
    data = json.loads(json_report.render(sample()))
    assert data["checks"][0]["status"] == "PASS"
    assert data["status"] == "healthy"
    assert data["schema_version"] == 1


def test_markdown(tmp_path):
    run = sample()
    run.checks[0].message = "literal | <script>"
    path = markdown.write(run, tmp_path)
    text = path.read_text()
    assert "# WXYZ Network Diagnostic" in text
    assert "192.0.2.20" in text
    assert "&#124; &lt;script&gt;" in text
    assert markdown.write(run, tmp_path) != path
