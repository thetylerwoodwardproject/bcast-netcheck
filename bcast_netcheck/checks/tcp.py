import asyncio
from time import monotonic

from bcast_netcheck.checks.route import address
from bcast_netcheck.models import CheckResult, CheckStatus


async def check(host, port, timeout):
    start = monotonic()
    writer = None
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(await address(host, timeout), port.port), timeout
        )
        status, message = CheckStatus.PASS, "Open"
    except ConnectionRefusedError:
        status, message = CheckStatus.FAIL, "Connection refused"
    except TimeoutError:
        status, message = CheckStatus.FAIL, "Connection timed out"
    except PermissionError:
        status, message = CheckStatus.ERROR, "Connection blocked by local permissions"
    except OSError:
        status, message = CheckStatus.FAIL, "Address resolution or connection failed"
    finally:
        if writer:
            writer.close()
            await writer.wait_closed()
    return CheckResult(
        port.name or f"TCP/{port.port}",
        status,
        host,
        port.port,
        message=message,
        duration_ms=(monotonic() - start) * 1000,
        required=port.required,
    )
