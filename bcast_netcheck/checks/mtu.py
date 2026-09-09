"""Conservative IPv4 DF probes; silence is never proof of a smaller MTU."""

import ipaddress
import time

from bcast_netcheck.checks.common import command
from bcast_netcheck.checks.route import address
from bcast_netcheck.models import CheckResult
from bcast_netcheck.models import CheckStatus as S


async def probe(host, size, timeout):
    code, out, err = await command(
        ["ping", "-n", "-c", "1", "-W", str(timeout * 0.8), "-M", "do", "-s", str(size - 28), host],
        timeout,
    )
    if code == 0:
        return "pass"
    text = (out + err).lower()
    if any(s in text for s in ("message too long", "frag needed", "mtu=")):
        return "fragment"
    if "not permitted" in text or "permission denied" in text:
        return "permission"
    return "unknown"


async def check(host, settings, expected=None):
    expected = expected or settings.expected_mtu
    destination = await address(host)
    if ipaddress.ip_address(destination).version != 4:
        return CheckResult(
            "Path MTU", S.SKIP, host, message="Version 0.1 DF discovery supports IPv4 only"
        )
    deadline = time.monotonic() + settings.timeout * 0.95
    low, high, proven, attempts = 576, expected, None, 0
    size = expected
    while low <= high and attempts < 15:
        remaining = deadline - time.monotonic()
        if remaining <= 0.02:
            break
        attempts += 1
        try:
            outcome = await probe(destination, size, remaining)
        except TimeoutError:
            outcome = "unknown"
        if outcome in ("unknown", "permission"):
            return CheckResult(
                "Path MTU",
                S.ERROR if outcome == "permission" else S.WARN,
                host,
                proven,
                "bytes",
                "Probe permission denied"
                if outcome == "permission"
                else "Inconclusive: ICMP silence cannot establish path MTU",
                {"expected": expected, "confirmed_lower_bound": proven, "probes": attempts},
            )
        if outcome == "pass":
            proven = size
            low = size + 1
        else:
            high = size - 1
        size = (low + high) // 2
    if proven is None:
        return CheckResult(
            "Path MTU", S.WARN, host, message="No usable MTU established within probe budget"
        )
    complete = low > high
    message = (
        f"At least {expected} bytes supported"
        if proven == expected
        else "Below expected MTU; possible tunnel or encapsulation overhead"
    )
    if not complete:
        message = "Probe budget exhausted; confirmed lower bound only"
    return CheckResult(
        "Path MTU",
        S.PASS if proven == expected else S.WARN,
        host,
        proven,
        "bytes",
        message,
        {
            "expected": expected,
            "confirmed_lower_bound": proven,
            "search_complete": complete,
            "probes": attempts,
        },
    )
