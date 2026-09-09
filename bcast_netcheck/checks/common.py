"""Bounded subprocess execution with cancellation cleanup."""

import asyncio
import os
import platform
import shutil
import signal

from bcast_netcheck.models import CheckResult, CheckStatus


class CheckUnavailable(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


async def command(args: list[str], timeout: float):
    if platform.system() != "Linux":
        raise CheckUnavailable(CheckStatus.SKIP, "This check requires Linux")
    if not shutil.which(args[0]):
        raise CheckUnavailable(CheckStatus.SKIP, f"Missing utility: {args[0]}")
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C"},
        )
    except OSError:
        raise CheckUnavailable(CheckStatus.ERROR, "Cannot execute utility; check permissions")
    communication = asyncio.create_task(proc.communicate())
    expired = False
    try:
        try:
            out, err = await asyncio.wait_for(asyncio.shield(communication), timeout * 0.85)
        except TimeoutError:
            expired = True
            # SIGINT lets ping emit its counters; traceroute retains the observed partial path.
            if proc.returncode is None:
                proc.send_signal(signal.SIGINT)
            try:
                out, err = await asyncio.wait_for(asyncio.shield(communication), timeout * 0.1)
            except TimeoutError:
                if proc.returncode is None:
                    proc.kill()
                out, err = await communication
    finally:
        if proc.returncode is None:
            proc.kill()
        await proc.wait()
        if not communication.done():
            await communication
    return (
        (-1 if expired else proc.returncode),
        out.decode(errors="replace"),
        err.decode(errors="replace"),
    )


async def guarded(name, host, operation, timeout):
    from time import monotonic

    start = monotonic()
    try:
        result = await asyncio.wait_for(operation(), timeout)
    except CheckUnavailable as exc:
        result = CheckResult(name, exc.status, host, message=exc.message)
    except TimeoutError:
        result = CheckResult(name, CheckStatus.ERROR, host, message="Check deadline exceeded")
    except Exception:
        # Never stringify arbitrary exceptions: library errors may carry secrets.
        result = CheckResult(name, CheckStatus.ERROR, host, message="Check execution error")
    result.duration_ms = round((monotonic() - start) * 1000, 2)
    return result
