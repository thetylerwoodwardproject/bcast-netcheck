import re

from bcast_netcheck.checks.common import command
from bcast_netcheck.models import CheckResult, CheckStatus


def parse_ping(output: str) -> dict:
    summary = re.search(r"(\d+) packets transmitted,\s*(\d+)(?: packets)? received", output)
    if not summary:
        raise ValueError("Missing ping summary")
    sent, received = map(int, summary.groups())
    if sent < 1 or received > sent:
        raise ValueError("Invalid ping counters")
    samples = [float(x) for x in re.findall(r"time[=<]([\d.]+)\s*ms", output)]
    stats = re.search(r"(?:rtt|round-trip).*?=\s*([\d.]+)/([\d.]+)/([\d.]+)/", output)
    minimum, average, maximum = map(float, stats.groups()) if stats else (None, None, None)
    jitter = (
        sum(abs(b - a) for a, b in zip(samples, samples[1:])) / (len(samples) - 1)
        if len(samples) > 1
        else None
    )
    return dict(
        sent=sent,
        received=received,
        loss_pct=100 * (sent - received) / sent,
        min_ms=minimum,
        avg_ms=average,
        max_ms=maximum,
        jitter_ms=jitter,
        samples_ms=samples,
    )


async def check(host, settings):
    code, out, err = await command(
        [
            "ping",
            "-n",
            "-c",
            str(settings.ping_count),
            "-i",
            "0.2",
            "-W",
            str(max(1, int(settings.timeout))),
            host,
        ],
        settings.timeout,
    )
    try:
        data = parse_ping(out)
    except ValueError:
        message = "ICMP could not execute; check permissions or name resolution"
        return CheckResult("ICMP", CheckStatus.ERROR, host, message=message)
    status = CheckStatus.PASS if data["received"] else CheckStatus.FAIL
    if status == CheckStatus.PASS and (
        data["loss_pct"] >= settings.loss_warn_pct
        or (data["avg_ms"] or 0) > settings.latency_warn_ms
        or (data["jitter_ms"] or 0) > settings.jitter_warn_ms
    ):
        status = CheckStatus.WARN
    data["requested_count"] = settings.ping_count
    data["deadline_limited"] = code == -1
    message = "Reachable" if data["received"] else "No ICMP replies"
    if data["sent"] < settings.ping_count:
        message += " (probe count limited by deadline)"
    return CheckResult(
        "ICMP",
        status,
        host,
        data["avg_ms"],
        "ms",
        message,
        data,
    )
