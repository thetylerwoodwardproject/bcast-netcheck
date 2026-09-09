"""Correlate evidence without asserting an unobserved root cause."""

from bcast_netcheck.models import CheckStatus as S
from bcast_netcheck.models import Diagnosis


def diagnose(checks):
    reach = {c.endpoint: c.status for c in checks if c.name == "ICMP"}
    primary, backup = reach.get("primary"), reach.get("backup")
    up = (S.PASS, S.WARN)
    if primary == backup == S.FAIL:
        return Diagnosis(
            "critical",
            "Both transport endpoints failed ICMP checks; site transport "
            "may be unavailable or ICMP may be filtered.",
            ["Investigate both WAN paths, router interfaces, and ICMP filtering."],
        )
    devices = [c for c in checks if c.name == "ICMP" and c.endpoint.startswith("device:")]
    if reach.get("router") == S.FAIL and devices and all(c.status == S.FAIL for c in devices):
        return Diagnosis(
            "failure",
            "Site router or upstream network path may be unavailable.",
            ["Inspect router reachability and the upstream path; confirm ICMP policy."],
        )
    required_failures = [c for c in checks if c.status == S.FAIL and c.required]
    if required_failures:
        return Diagnosis(
            "failure",
            "A required endpoint or service appears unavailable.",
            ["Inspect failed required checks and the associated network path."],
        )
    if any(c.status == S.ERROR and c.required for c in checks):
        return Diagnosis(
            "error",
            "Required diagnostics could not execute.",
            ["Check local dependencies, permissions, and name resolution."],
        )
    if primary in up and backup == S.FAIL:
        all_up = devices and all(c.status in up for c in devices)
        return Diagnosis(
            "warning",
            (
                "Site devices are reachable with degraded transport redundancy."
                if all_up
                else "Primary gateway is reachable; backup redundancy is degraded."
            ),
            ["Investigate the backup WAN path or associated router interface."],
        )
    if primary == S.FAIL and backup in up:
        return Diagnosis(
            "warning",
            "Primary gateway is unresponsive; backup remains reachable. "
            "Actual traffic failover is not established by these probes.",
            ["Investigate the primary WAN path and inspect the selected route."],
        )
    failed = [c for c in devices if c.status == S.FAIL]
    if (
        reach.get("router") in up
        and len(failed) == 1
        and all(c.status in up for c in devices if c is not failed[0])
    ):
        return Diagnosis(
            "warning",
            f"Failure appears isolated to {failed[0].endpoint.removeprefix('device:')} "
            "or its local network connection.",
            ["Check device power, switch port, VLAN, and local cabling."],
        )
    if any(
        c.status in (S.WARN, S.ERROR)
        or (c.status == S.FAIL and c.kind != "tcp" and not c.name.startswith("TCP/"))
        for c in checks
    ):
        return Diagnosis(
            "warning",
            "Connectivity is degraded or diagnostics are incomplete.",
            ["Review failed and inconclusive checks before assigning a failure domain."],
        )
    if not any(c.status == S.PASS for c in checks):
        return Diagnosis("error", "No successful diagnostic evidence is available.")
    if any(c.status == S.SKIP and (c.required or c.name == "ICMP") for c in checks):
        return Diagnosis(
            "warning",
            "Some required diagnostics were unavailable.",
            ["Install missing utilities or review unconfigured checks."],
        )
    return Diagnosis("healthy", "No required service failures detected in the completed checks.")
